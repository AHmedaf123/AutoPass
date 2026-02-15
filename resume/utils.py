"""Utility helpers for resume management."""
from __future__ import annotations

from uuid import uuid4

OBJECT_SECTIONS = {"basic_info", "summary"}
ARRAY_SECTIONS = {"experience", "education", "projects", "skills", "languages"}
ALL_SECTIONS = OBJECT_SECTIONS | ARRAY_SECTIONS


def generate_item_id() -> str:
    """Return a short unique identifier for array items."""
    return uuid4().hex


def sanitize_uid(uid: str) -> str:
    """Remove path separators and keep a safe identifier for filenames."""
    cleaned = "".join(ch for ch in uid.strip() if ch.isalnum() or ch in {"-", "_"})
    if not cleaned:
        raise ValueError("Invalid uid")
    return cleaned
