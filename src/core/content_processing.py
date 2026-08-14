"""Deterministic Bronze-to-Silver Markdown processing with evidence preservation."""

from __future__ import annotations

import re
import unicodedata


_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+\S")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
_FENCE = re.compile(r"^\s*(```|~~~)")
_COPYRIGHT = re.compile(
    r"^(?:©|copyright\b).{0,100}\ball rights reserved\.?$",
    re.IGNORECASE,
)
_EXACT_BOILERPLATE = {
    "accept all cookies",
    "back to top",
    "cookie preferences",
    "cookie settings",
    "log in",
    "menu",
    "privacy policy",
    "sign in",
    "skip to content",
    "subscribe",
    "terms of service",
}
_NAVIGATION_WORDS = {
    "about",
    "blog",
    "contact",
    "home",
    "in",
    "log",
    "login",
    "menu",
    "news",
    "pricing",
    "privacy",
    "products",
    "search",
    "services",
    "sign",
    "subscribe",
}
_WORD = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)


def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 3


def _is_obvious_boilerplate(line: str) -> bool:
    normalized = line.strip().casefold().strip(" .:;|-")
    if not normalized:
        return False
    if normalized in _EXACT_BOILERPLATE or _COPYRIGHT.fullmatch(line.strip()):
        return True
    tokens = re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
    return bool(tokens) and len(tokens) <= 8 and set(tokens) <= _NAVIGATION_WORDS


def normalize_evidence_content(content: str) -> tuple[str, int]:
    """Normalize noise conservatively while preserving Markdown structure."""
    normalized = unicodedata.normalize("NFC", str(content)).replace("\r\n", "\n").replace("\r", "\n")
    output: list[str] = []
    removed_boilerplate = 0
    inside_fence = False

    for raw_line in normalized.split("\n"):
        line = raw_line.replace("\u00a0", " ").rstrip()
        if _FENCE.match(line):
            inside_fence = not inside_fence
            output.append(line.strip())
            continue
        if inside_fence:
            output.append(line)
            continue

        structural = bool(
            _HEADING.match(line) or _LIST_ITEM.match(line) or _is_table_line(line)
        )
        if structural:
            cleaned_line = line.strip() if _HEADING.match(line) or _is_table_line(line) else line
        else:
            cleaned_line = re.sub(r"[\t ]+", " ", line).strip()
            if _is_obvious_boilerplate(cleaned_line):
                removed_boilerplate += 1
                continue

        if not cleaned_line:
            if output and output[-1] != "":
                output.append("")
            continue
        output.append(cleaned_line)

    while output and output[-1] == "":
        output.pop()
    return "\n".join(output), removed_boilerplate


def evidence_word_count(content: str) -> int:
    return len(_WORD.findall(content))
