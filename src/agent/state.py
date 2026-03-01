"""Pipeline state definitions."""

from pathlib import Path
from typing import Annotated, TypedDict

from agent.config import AgentConfig


def _replace(a, b):
    """Reducer that always takes the newer value."""
    return b


class PipelineState(TypedDict, total=False):
    pages: list[str]
    config_dict: Annotated[dict, _replace]  # serialized AgentConfig scalars
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


def get_config(state: PipelineState) -> AgentConfig:
    """Reconstruct AgentConfig from state dict (templates loaded from files)."""
    raw = dict(state.get("config_dict", {}))
    if "output_dir" in raw:
        raw["output_dir"] = Path(raw["output_dir"])
    return AgentConfig(**raw)
