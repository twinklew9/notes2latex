"""LiteLLM wrapper for vision transcription and error fixing."""

import logging
import re

import litellm
from tenacity import retry, stop_after_attempt, wait_exponential

litellm.suppress_debug_info = True
logging.getLogger("LiteLLM").setLevel(logging.WARNING)

from notes2latex.config import Settings


def _strip_code_fences(text: str) -> str:
    """Remove all markdown code fences — wrapping or inline."""
    text = text.strip()
    # Remove all ``` fence lines (with optional language tag)
    text = re.sub(r"^```(?:latex|tex)?\s*$", "", text, flags=re.MULTILINE)
    return text.strip()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
async def transcribe_page(
    image_b64: str,
    system_prompt: str,
    settings: Settings,
    context_latex: str = "",
) -> str:
    """Send a page image to the VLM and return LaTeX source."""
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
    ]

    user_content: list[dict] = []

    if context_latex:
        # Send only the last N lines of body as context to stay within token limits
        lines = context_latex.splitlines()
        tail = "\n".join(lines[-settings.context_lines :])
        user_content.append({
            "type": "text",
            "text": (
                "Here is the LaTeX body from previous pages (last "
                f"{settings.context_lines} lines):\n```latex\n{tail}\n```\n"
                "Continue typesetting the next page shown in the image."
            ),
        })

    user_content.append({
        "type": "text",
        "text": "Typeset the handwritten math notes in this image into LaTeX body content.",
    })

    user_content.append({
        "type": "image_url",
        "image_url": {
            "url": f"data:image/png;base64,{image_b64}",
            "detail": "high",
        },
    })

    messages.append({"role": "user", "content": user_content})

    response = await litellm.acompletion(
        model=settings.model,
        messages=messages,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
    )
    return _strip_code_fences(response.choices[0].message.content)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def fix_latex(
    latex_source: str,
    errors: list[dict],
    system_prompt: str,
    settings: Settings,
) -> str:
    """Send broken LaTeX + errors to LLM, return fixed LaTeX."""
    error_text = "\n".join(
        f"- Line {e.get('line', '?')}: {e['message']}"
        + (f" (context: {e['context']})" if e.get("context") else "")
        for e in errors
    )

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"The following LaTeX source has compilation errors:\n\n"
                f"```latex\n{latex_source}\n```\n\n"
                f"Errors:\n{error_text}\n\n"
                f"Return ONLY the corrected complete LaTeX source."
            ),
        },
    ]

    response = await litellm.acompletion(
        model=settings.model,
        messages=messages,
        temperature=0.0,
        max_tokens=settings.max_tokens,
    )
    return _strip_code_fences(response.choices[0].message.content)
