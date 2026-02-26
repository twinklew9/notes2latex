"""Default template loader — reads .md files from the prompts directory."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def load_default_template(name: str) -> str:
    """Read a default prompt template by name (without extension)."""
    path = _PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")
