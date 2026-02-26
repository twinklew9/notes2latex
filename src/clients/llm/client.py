"""LiteLLM client — thin async wrapper for model completions."""

import logging

import litellm

litellm.suppress_debug_info = True
logging.getLogger("LiteLLM").setLevel(logging.WARNING)


async def acompletion(
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> str:
    """Run an async litellm completion and return the text content."""
    response = await litellm.acompletion(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content
