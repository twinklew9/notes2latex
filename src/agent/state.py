"""Pipeline state definitions."""

from typing import Annotated, TypedDict

from core.config import Settings


def _replace(a, b):
    """Reducer that always takes the newer value."""
    return b


class PipelineState(TypedDict, total=False):
    pages: list[str]
    settings_dict: Annotated[dict, _replace]  # serialized Settings for node access
    page_index: Annotated[int, _replace]
    retry_count: Annotated[int, _replace]
    # Body content only — no preamble, no \begin/\end{document}
    base_body: Annotated[str, _replace]
    accumulated_body: Annotated[str, _replace]
    current_page_latex: Annotated[str, _replace]
    compiler_success: Annotated[bool, _replace]
    errors: Annotated[list[dict], _replace]
    output_tex_path: Annotated[str, _replace]
    output_pdf_path: Annotated[str, _replace]


def get_settings(state: PipelineState) -> Settings:
    """Reconstruct Settings from state dict."""
    return Settings(**state.get("settings_dict", {}))
