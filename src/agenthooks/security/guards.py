from __future__ import annotations

import re

INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"<script|javascript:", re.IGNORECASE),
    re.compile(r"\[\[(?:system|user|assistant)\]\]", re.IGNORECASE),
    re.compile(r"system\s*:\s*['\"]you", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"disregard\s+(?:all\s+)?(?:previous|prior)\s+", re.IGNORECASE),
]

def injection_scan(query: str | None) -> str | None:
    if not query:
        return None
    for pattern in INJECTION_PATTERNS:
        if pattern.search(query):
            return f"prompt injection pattern detected: '{pattern.pattern[:40]}'"
    return None
