"""
Shared utilities used across packages.

These are small, pure functions with no external dependencies.
Import from here instead of duplicating across packages.
"""

from __future__ import annotations

import hashlib
import re
import uuid


def generate_id(prefix: str = "") -> str:
    """Generate a UUID4 string, optionally prefixed."""
    uid = str(uuid.uuid4())
    return f"{prefix}-{uid}" if prefix else uid


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to max_length, appending suffix if truncated."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def content_hash(text: str) -> str:
    """Return a short SHA256 hash of text content (for deduplication)."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def clean_whitespace(text: str) -> str:
    """Normalize whitespace: collapse multiple spaces/newlines."""
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_code_blocks(text: str) -> list[dict[str, str]]:
    """
    Extract fenced code blocks from markdown text.

    Returns list of dicts with 'language' and 'code' keys.
    """
    pattern = r"```(\w*)\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    return [{"language": lang or "text", "code": code.strip()} for lang, code in matches]


def count_tokens_approx(text: str) -> int:
    """
    Approximate token count (4 chars ≈ 1 token for English text).

    Not accurate — use only for rough budget estimates.
    """
    return len(text) // 4
