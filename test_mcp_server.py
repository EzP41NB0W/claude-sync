"""
test_mcp_server.py — smoke test for mcp_server.py, exercising it through the
real MCP client/server protocol (not just calling the Python functions
directly), per the project's standing testing convention.

Only exercises read-only tools + build_rollup (rebuilds are cheap/idempotent
per rollup.py's own design). Deliberately does NOT call add_learning here —
that would write a permanent test line into the real learnings.md.

Run:
    python test_mcp_server.py
"""

import asyncio

from fastmcp import Client
from mcp_server import mcp


async def main():
    async with Client(mcp) as client:
        tools = await client.list_tools()
        print("=== Registered tools ===")
        for t in tools:
            print(f"- {t.name}: {t.description.splitlines()[0]}")
        print()

        print("=== build_rollup ===")
        result = await client.call_tool("build_rollup", {})
        print(f"  {result.data}")
        print()

        print("=== list_projects ===")
        result = await client.call_tool("list_projects", {})
        projects = result.data
        for p in projects:
            print(f"  {p['name']:20s} {p['chunk']}  {p['lines']} lines")
        print()

        assert projects, "expected at least one project after build_rollup"
        name = "claude-sync" if any(p["name"] == "claude-sync" for p in projects) else projects[0]["name"]
        print(f"=== get_project: {name} ===")
        result = await client.call_tool("get_project", {"name": name})
        section = result.data
        assert "text" in section, f"unexpected response: {section}"
        print(f"  got {len(section['text'])} chars, starts with: {section['text'][:60]!r}")
        print()

        print("=== get_project: nonexistent-project-xyz (error path) ===")
        result = await client.call_tool("get_project", {"name": "nonexistent-project-xyz"})
        print(f"  {result.data}")
        print()

        print("=== search: 'example' (notes) ===")
        result = await client.call_tool("search", {"query": "example", "max_results": 5})
        hits = result.data
        assert isinstance(hits, list), f"expected a list, got {hits!r}"
        for h in hits:
            assert {"project", "line", "text", "snippet", "score"} <= set(h), f"bad hit shape: {h}"
        print(f"  {len(hits)} hit(s); top: {hits[0] if hits else '(none)'}")
        print()

        print("=== search: separator-insensitive 'one wire' vs 'one-wire' ===")
        a = (await client.call_tool("search", {"query": "one-wire", "max_results": 40})).data
        b = (await client.call_tool("search", {"query": "one wire", "max_results": 40})).data
        print(f"  'one-wire' -> {len(a)} hit(s), 'one wire' -> {len(b)} hit(s) (should match)")
        print()

        print("=== search_code: 'setup' (source) ===")
        result = await client.call_tool("search_code", {"query": "setup", "max_results": 5})
        hits = result.data
        assert isinstance(hits, list), f"expected a list, got {hits!r}"
        for h in hits:
            assert {"project", "file", "line", "text", "snippet", "score"} <= set(h), f"bad hit shape: {h}"
        print(f"  {len(hits)} hit(s); top file: {hits[0]['file'] if hits else '(none)'}")


if __name__ == "__main__":
    asyncio.run(main())
