#!/usr/bin/env python3
"""Test the secret scrubber + reveal round-trip."""

import sys

import scrubber

# Windows consoles default to cp1252, which cannot print the emoji below
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

doc = """\
# Project notes
Router BSSID is aa:bb:cc:dd:ee:ff and the AP sits at 192.168.1.1.
api_key = sk-ant-sid02-FAKEFAKEFAKEFAKEFAKEFAKE1234567890abcdef
psk=supersecretwifipassword
Also a github token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ab here.
This base64 blob looks suspicious: Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MGFiY2RlZg==
Just normal prose that should never be touched at all.
"""

res = scrubber.scrub(doc, file_name="notes.md")

print("--- CLEAN OUTPUT ---")
print(res.clean_text)
print("--- REDACTIONS ---")
for tag, val in res.redactions.items():
    print(f"  {tag}  <-  {val}")
print("--- FLAGGED (needs human) ---")
for f in res.flagged:
    print(f"  {f}")

# Assertions
kinds = {tag.split(":")[0] for tag in res.redactions}
assert "[REDACTED_BSSID" in kinds, "BSSID not redacted"
assert "[REDACTED_PRIVATE_IP" in kinds, "private IP not redacted"
assert "[REDACTED_ANTHROPIC_KEY" in kinds, "anthropic key not redacted"
assert "[REDACTED_GITHUB_TOKEN" in kinds, "github token not redacted"
assert any("[REDACTED_SECRET" in t for t in res.redactions), "psk value not redacted"

# Real values must NOT survive in clean text
for bad in ["aa:bb:cc:dd:ee:ff", "sk-ant-sid02-FAKE", "supersecretwifipassword",
            "ghp_ABCDEFGHIJKLMNOP", "192.168.1.1"]:
    assert bad not in res.clean_text, f"LEAK: {bad} survived scrubbing"

# Normal prose untouched
assert "Just normal prose that should never be touched at all." in res.clean_text

# Deterministic tags: same secret -> same tag across runs
res2 = scrubber.scrub(doc, file_name="notes.md")
assert res.redactions == res2.redactions, "tags not deterministic"

# Reveal round-trips back to original
restored = scrubber.reveal(res.clean_text, res.redactions)
assert "aa:bb:cc:dd:ee:ff" in restored and "supersecretwifipassword" in restored
print("\nALL SCRUBBER TESTS PASSED ✅")
