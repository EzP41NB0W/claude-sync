"""
secure_store.py — Keep secrets off plaintext disk.

Holds two things: the reversible secrets map (tag -> real value) the
scrubber produces, and a legacy session_key field. The session_key piece
is no longer used by anything (claude.ai sync was retired) but the methods stay so an
existing .claude_sync_store blob from before that change still decodes
cleanly instead of erroring on an unexpected schema.

Backends, in order of preference:
    - Windows: DPAPI via PowerShell ProtectedData (no pywin32 dependency)
    - Fallback: gitignored local file, clearly marked INSECURE

Stored blob is JSON: {"session_key": "...", "secret_map": {tag: value}}.
DPAPI ties decryption to the current Windows user account — another login
on the same box can't read it.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

STORE_NAME = ".claude_sync_store"  # encrypted blob (or plaintext in fallback)


# --- Windows DPAPI backend (via PowerShell, no extra pip deps) ---------------

def _ps(script: str, input_bytes: bytes | None = None) -> bytes:
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        input=input_bytes, capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"PowerShell failed: {proc.stderr.decode(errors='replace')}")
    return proc.stdout


def _dpapi_protect(plaintext: str) -> str:
    b64_in = base64.b64encode(plaintext.encode("utf-8")).decode("ascii")
    script = (
        "$ErrorActionPreference='Stop';"
        "Add-Type -AssemblyName System.Security;"
        f"$b=[Convert]::FromBase64String('{b64_in}');"
        "$p=[Security.Cryptography.ProtectedData]::Protect($b,$null,"
        "[Security.Cryptography.DataProtectionScope]::CurrentUser);"
        "[Convert]::ToBase64String($p)"
    )
    return _ps(script).decode("ascii").strip()


def _dpapi_unprotect(protected_b64: str) -> str:
    script = (
        "$ErrorActionPreference='Stop';"
        "Add-Type -AssemblyName System.Security;"
        f"$b=[Convert]::FromBase64String('{protected_b64}');"
        "$p=[Security.Cryptography.ProtectedData]::Unprotect($b,$null,"
        "[Security.Cryptography.DataProtectionScope]::CurrentUser);"
        "[Convert]::ToBase64String($p)"
    )
    out = _ps(script).decode("ascii").strip()
    return base64.b64decode(out).decode("utf-8")


def _is_windows() -> bool:
    return sys.platform.startswith("win")


# --- Public API --------------------------------------------------------------

class SecureStore:
    def __init__(self, base_dir: Path):
        self.path = Path(base_dir) / STORE_NAME
        self._data: dict[str, Any] = {"session_key": None, "secret_map": {}}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        if self.path.exists():
            raw = self.path.read_text(encoding="utf-8")
            try:
                envelope = json.loads(raw)
                if envelope.get("backend") == "dpapi":
                    plain = _dpapi_unprotect(envelope["blob"])
                    self._data = json.loads(plain)
                else:  # plaintext fallback
                    self._data = envelope.get("data", self._data)
            except (json.JSONDecodeError, RuntimeError, KeyError) as e:
                print(f"  [store] couldn't read secure store: {e}", file=sys.stderr)
        self._loaded = True

    def _save(self) -> None:
        plain = json.dumps(self._data)
        if _is_windows():
            try:
                blob = _dpapi_protect(plain)
                envelope = {"backend": "dpapi", "blob": blob}
            except RuntimeError as e:
                print(f"  [store] DPAPI unavailable ({e}); falling back to plaintext.",
                      file=sys.stderr)
                envelope = {"backend": "plaintext", "data": self._data}
        else:
            print("  [store] non-Windows: using INSECURE plaintext fallback. "
                  "Add keychain/libsecret backend before relying on this.",
                  file=sys.stderr)
            envelope = {"backend": "plaintext", "data": self._data}

        self.path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        # best-effort tighten perms on POSIX
        try:
            self.path.chmod(0o600)
        except (OSError, NotImplementedError):
            pass

    # legacy session key (unused since claude.ai sync retirement) ----------
    def get_session_key(self) -> str | None:
        self._load()
        return self._data.get("session_key")

    def set_session_key(self, key: str) -> None:
        self._load()
        self._data["session_key"] = key.strip()
        self._save()

    # secret map ----------------------------------------------------------
    def get_secret_map(self) -> dict[str, str]:
        self._load()
        return dict(self._data.get("secret_map", {}))

    def merge_secret_map(self, new_entries: dict[str, str]) -> None:
        self._load()
        self._data.setdefault("secret_map", {}).update(new_entries)
        self._save()

    # human-reviewed-and-cleared tokens ("keep" action) --------------------
    def get_ignored_tokens(self) -> set[str]:
        self._load()
        return set(self._data.get("ignored_tokens", []))

    def add_ignored_token(self, token: str) -> None:
        self._load()
        tokens = set(self._data.get("ignored_tokens", []))
        tokens.add(token)
        self._data["ignored_tokens"] = sorted(tokens)
        self._save()

    def is_encrypted(self) -> bool:
        return _is_windows()
