"""
scrubber.py — Catch secrets before they propagate.

Design philosophy: the scariest threat is the human pasting a passphrase
into a doc at 2am and forgetting. So the scrubber is a patient bouncer at
the door. Known-pattern secrets get auto-redacted and recorded in a local
reversible map. Ambiguous high-entropy strings that we CAN'T classify get
flagged for human eyes rather than silently passed or silently mangled.

Replacement style: labeled + short deterministic hash, e.g.
    aa:bb:cc:dd:ee:ff  ->  [REDACTED_BSSID:a3f9]
Same secret always maps to the same tag, so context survives across
sessions ("the device tagged a3f9") without ever exposing the value.

HONEST LIMIT: regex secret detection is good, never perfect. High-entropy
keys with known prefixes and structured tokens (MAC/IP) catch reliably.
Freeform passphrases that read like prose cannot be caught without flagging
half your sentences. That's why unclassifiable-but-suspicious -> BLOCK+ASK.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Callable


def _tag(kind: str, value: str) -> str:
    h = hashlib.sha256(value.encode("utf-8")).hexdigest()[:4]
    return f"[REDACTED_{kind}:{h}]"


# --- Detection patterns ------------------------------------------------------
# Each entry: (KIND, compiled regex). Order matters — most specific first so a
# session key isn't swallowed by the generic "long token" rule.
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("ANTHROPIC_KEY", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("AWS_KEY",       re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("GITHUB_TOKEN",  re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("GOOGLE_KEY",    re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b")),
    ("SLACK_TOKEN",   re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("PRIVATE_KEY",   re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("BSSID",         re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")),
    # private / link-local IPv4 ranges (don't redact public IPs by default)
    ("PRIVATE_IP",    re.compile(
        r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|192\.168\.\d{1,3}\.\d{1,3}"
        r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b")),
]

# key=value lines whose KEY name screams secret -> redact the VALUE
SECRET_ASSIGN = re.compile(
    r"(?i)\b(pass(?:word|phrase)?|psk|secret|api[_-]?key|token|bearer|cookie|"
    r"sessionkey)\b\s*[:=]\s*(\S+)")

# Candidate "looks like a secret blob" for entropy screening: long unbroken
# token of base64/hex-ish chars. We don't auto-redact these — we entropy-test.
# NOTE: uses lookaround instead of \b because \b is defined relative to \w,
# and '=' (common base64 padding) is not a word character. A trailing \b
# right before/after '=' doesn't reliably match, which silently truncated
# padded base64 tokens by one character. (-?<![...]) ensures we don't start
# mid-token when scanning forward.
BLOB = re.compile(r"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/=_-]{24,}(?![A-Za-z0-9+/=_-])")

# Lowered floor so things we DON'T want to touch (prose, file paths) pass.
ENTROPY_THRESHOLD = 4.0  # bits/char; random base64 ~5.0-6.0, english ~2.5-3.5


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    counts: dict[str, int] = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


@dataclass
class ScrubResult:
    clean_text: str
    redactions: dict[str, str] = field(default_factory=dict)  # tag -> real value
    flagged: list[dict] = field(default_factory=list)         # needs human eyes

    @property
    def had_redactions(self) -> bool:
        return bool(self.redactions)

    @property
    def needs_review(self) -> bool:
        return bool(self.flagged)


def scrub(text: str, file_name: str = "", ignore_tokens: set[str] | None = None) -> ScrubResult:
    """
    Returns a ScrubResult with clean_text (placeholders substituted),
    a tag->value map for everything redacted, and a list of flagged
    suspicious-but-unclassified strings that should block until reviewed.

    ignore_tokens: strings a human has already reviewed and marked safe
    ("keep" action). Without this, the entropy screen would re-flag the
    same reviewed string on every single plan call forever, since the
    scrubber re-scans fresh each time with no memory of past decisions.
    """
    ignore_tokens = ignore_tokens or set()
    redactions: dict[str, str] = {}
    flagged: list[dict] = []

    def replace_kind(kind: str) -> Callable[[re.Match], str]:
        def _r(m: re.Match) -> str:
            val = m.group(0)
            tag = _tag(kind, val)
            redactions[tag] = val
            return tag
        return _r

    out = text
    for kind, pat in PATTERNS:
        out = pat.sub(replace_kind(kind), out)

    # key=value secret assignments: redact only the value portion
    def _assign(m: re.Match) -> str:
        key, val = m.group(1), m.group(2)
        # if the value was already redacted by a prior pattern, leave it
        if val.startswith("[REDACTED_"):
            return m.group(0)
        tag = _tag("SECRET", val)
        redactions[tag] = val
        return m.group(0).replace(val, tag)
    out = SECRET_ASSIGN.sub(_assign, out)

    # Entropy screen for unclassified blobs -> FLAG, do not auto-redact.
    for m in BLOB.finditer(out):
        token = m.group(0)
        if token.startswith("[REDACTED_"):
            continue
        if token in ignore_tokens:
            continue
        if shannon_entropy(token) >= ENTROPY_THRESHOLD:
            # context line for the human
            start = out.rfind("\n", 0, m.start()) + 1
            end = out.find("\n", m.end())
            line = out[start: end if end != -1 else len(out)].strip()
            flagged.append({
                "file_name": file_name,
                "token_preview": token[:6] + "…",
                "entropy": round(shannon_entropy(token), 2),
                "line": line[:120],
            })

    return ScrubResult(clean_text=out, redactions=redactions, flagged=flagged)


def reveal(text: str, secret_map: dict[str, str]) -> str:
    """Reverse scrubbing locally: swap [REDACTED_*:hash] tags back to values."""
    out = text
    for tag, val in secret_map.items():
        out = out.replace(tag, val)
    return out
