"""Agent-level text utilities for processing LLM output."""

import re


def strip_code_fences(text: str) -> str:
    """Remove all markdown code fences — wrapping or inline."""
    text = text.strip()
    # Remove all ``` fence lines (with optional language tag)
    text = re.sub(r"^```(?:latex|tex)?\s*$", "", text, flags=re.MULTILINE)
    return text.strip()
