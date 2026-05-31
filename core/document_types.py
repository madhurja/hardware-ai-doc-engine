from __future__ import annotations

from difflib import get_close_matches


DOCUMENT_TYPES = ("user_manual", "test_report", "compliance_brief", "bom")
TYPE_CHOICES = (*DOCUMENT_TYPES, "all")

ALIASES = {
    "manual": "user_manual",
    "user manual": "user_manual",
    "usermanual": "user_manual",
    "documentation": "user_manual",
    "docs": "user_manual",
    "doc": "user_manual",
    "report": "test_report",
    "test": "test_report",
    "testing": "test_report",
    "test report": "test_report",
    "compliance": "compliance_brief",
    "compliance brief": "compliance_brief",
    "brief": "compliance_brief",
    "bill of materials": "bom",
    "parts": "bom",
    "all": "all",
    "full": "all",
    "package": "all",
    "full package": "all",
}


def resolve_document_type(value: str) -> str:
    normalized = value.strip().lower().replace("-", " ").replace("_", " ")
    compact = normalized.replace(" ", "")
    direct = normalized.replace(" ", "_")

    if direct in TYPE_CHOICES:
        return direct
    if normalized in ALIASES:
        return ALIASES[normalized]
    if compact in ALIASES:
        return ALIASES[compact]

    candidates = list(ALIASES) + [item.replace("_", " ") for item in TYPE_CHOICES]
    match = get_close_matches(normalized, candidates, n=1, cutoff=0.72)
    if match:
        return ALIASES.get(match[0], match[0].replace(" ", "_"))

    raise ValueError(f"Unsupported document type: {value}")
