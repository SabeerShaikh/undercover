"""Split, search and read the policy wording and claims manual."""

from __future__ import annotations

import re
from typing import Any

HEADING = re.compile(r"^## (\d+)\.\s+(.+)$", re.MULTILINE)

DOCUMENT_NAMES = ("policy_wording", "claims_manual")
DOCUMENT_LABELS = {
    "policy_wording": "Policy wording",
    "claims_manual": "Claims manual",
}


def split_sections(text: str) -> list[dict[str, Any]]:
    """Split a markdown document on numbered ## headings."""
    matches = list(HEADING.finditer(text))
    sections: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append(
            {
                "number": int(match.group(1)),
                "title": match.group(2).strip(),
                "text": text[start:end].strip(),
            }
        )
    return sections


def paragraphs(text: str) -> list[str]:
    """Return non-empty paragraphs of a section."""
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]


def search_sections(sections: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Return sections whose title or text contains query, with matching paragraphs."""
    needle = query.lower()
    hits: list[dict[str, Any]] = []
    for section in sections:
        title = section["title"]
        body = section["text"]
        if needle not in title.lower() and needle not in body.lower():
            continue
        hits.append(
            {
                "number": section["number"],
                "title": title,
                "paragraphs": [p for p in paragraphs(body) if needle in p.lower()],
            }
        )
    return hits


def contents(wording: str, manual: str) -> str:
    """Return number and title of every section, with no section text."""
    lines = ["Contents of the policy wording"]
    for section in split_sections(wording):
        lines.append(f"{section['number']}. {section['title']}")
    lines.append("")
    lines.append("Contents of the claims manual")
    for section in split_sections(manual):
        lines.append(f"{section['number']}. {section['title']}")
    return "\n".join(lines)
