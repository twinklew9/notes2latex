"""LangGraph pipeline — the agentic generate→compile→fix loop."""

import asyncio
import shutil
from pathlib import Path

from langgraph.graph import END, StateGraph
from tenacity import retry, stop_after_attempt, wait_exponential

from agent.config import AgentConfig
from agent.state import PipelineState, get_settings
from agent.utils.text import strip_code_fences
from clients.llm.client import acompletion
from compiler.compiler import compile_latex
from core.config import Settings
from core.logger import get_logger
from document.preprocessing import load_pages
from document.processing import assemble_document, open_environments, strip_preamble_from_body

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Domain LLM functions
# ---------------------------------------------------------------------------


def _make_agent_config(settings: Settings) -> AgentConfig:
    """Construct an AgentConfig from application Settings."""
    return AgentConfig(
        model=settings.model,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        max_retries=settings.max_retries,
        context_lines=settings.context_lines,
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
async def transcribe_page(
    image_b64: str,
    system_prompt: str,
    config: AgentConfig,
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
        tail = "\n".join(lines[-config.context_lines :])
        user_content.append({
            "type": "text",
            "text": (
                "Here is the LaTeX body from previous pages (last "
                f"{config.context_lines} lines):\n```latex\n{tail}\n```\n"
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

    text = await acompletion(
        model=config.model,
        messages=messages,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
    return strip_code_fences(text)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def fix_latex(
    latex_source: str,
    errors: list[dict],
    system_prompt: str,
    config: AgentConfig,
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

    text = await acompletion(
        model=config.model,
        messages=messages,
        temperature=0.0,
        max_tokens=config.max_tokens,
    )
    return strip_code_fences(text)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def preprocess_node(state: PipelineState) -> dict:
    return {
        "page_index": 0,
        "retry_count": 0,
        "base_body": "",
        "accumulated_body": "",
        "current_page_latex": "",
        "compiler_success": False,
        "errors": [],
        "output_tex_path": "",
        "output_pdf_path": "",
    }


async def generate_latex_node(state: PipelineState) -> dict:
    settings = get_settings(state)
    config = _make_agent_config(settings)
    page_idx = state["page_index"]
    page_b64 = state["pages"][page_idx]

    logger.info("Generating LaTeX for page %d/%d", page_idx + 1, len(state["pages"]))

    accumulated_body = state.get("accumulated_body", "")
    open_envs = open_environments(accumulated_body) if accumulated_body else []

    system_prompt = config.render_transcribe_prompt(
        page_number=page_idx + 1,
        open_envs=open_envs,
    )

    # Pass body tail as context
    context = accumulated_body if accumulated_body else ""

    latex = await transcribe_page(
        image_b64=page_b64,
        system_prompt=system_prompt,
        config=config,
        context_latex=context,
    )

    latex = strip_preamble_from_body(latex)
    base = accumulated_body
    new_body = (base + "\n" + latex) if base else latex

    return {
        "current_page_latex": latex,
        "base_body": base,
        "accumulated_body": new_body,
        "retry_count": 0,
    }


async def compile_latex_node(state: PipelineState) -> dict:
    settings = get_settings(state)
    config = _make_agent_config(settings)
    body = state["accumulated_body"]

    # Temporarily close any environments still open at the end of the body
    open_envs = open_environments(body)
    if open_envs:
        closing_tags = "\n".join(rf"\end{{{env}}}" for env in reversed(open_envs))
        body = body + "\n" + closing_tags

    full_doc = assemble_document(body, config.preamble)
    result = await asyncio.to_thread(compile_latex, full_doc, settings)

    if result.errors:
        logger.warning(
            "Page %d compile errors: %s",
            state["page_index"] + 1,
            "; ".join(e.message for e in result.errors),
        )
    else:
        logger.info("Page %d compiled successfully", state["page_index"] + 1)

    return {
        "compiler_success": result.success,
        "errors": [
            {"line": e.line, "message": e.message, "context": e.context}
            for e in result.errors
        ],
    }


async def fix_latex_node(state: PipelineState) -> dict:
    settings = get_settings(state)
    config = _make_agent_config(settings)
    retry_count = state["retry_count"] + 1
    page_idx = state["page_index"]

    logger.info("Fix attempt %d for page %d", retry_count, page_idx + 1)

    # Calculate line offset: preamble lines + base_body lines
    preamble_lines = config.preamble.count("\n") + 1
    base_body = state["base_body"]
    base_lines = base_body.count("\n") + 1 if base_body else 0
    offset = preamble_lines + base_lines

    adjusted_errors = []
    for e in state["errors"]:
        adjusted = dict(e)
        if adjusted.get("line") is not None:
            adjusted["line"] = max(1, adjusted["line"] - offset)
        adjusted_errors.append(adjusted)

    system_prompt = config.render_fix_errors_prompt()

    fixed_page = await fix_latex(
        latex_source=state["current_page_latex"],
        errors=adjusted_errors,
        system_prompt=system_prompt,
        config=config,
    )

    fixed_page = strip_preamble_from_body(fixed_page)
    base = state["base_body"]
    new_body = (base + "\n" + fixed_page) if base else fixed_page

    return {
        "current_page_latex": fixed_page,
        "accumulated_body": new_body,
        "retry_count": retry_count,
    }


async def advance_page_node(state: PipelineState) -> dict:
    return {
        "page_index": state["page_index"] + 1,
        "retry_count": 0,
    }


async def finalize_node(state: PipelineState) -> dict:
    settings = get_settings(state)
    config = _make_agent_config(settings)
    output_dir = settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Assemble full document from body
    full_doc = assemble_document(state["accumulated_body"], config.preamble)

    # Write final .tex
    tex_path = output_dir / "output.tex"
    tex_path.write_text(full_doc, encoding="utf-8")

    # One final compilation to get the PDF in the output dir
    result = await asyncio.to_thread(compile_latex, full_doc, settings)

    output_pdf = ""
    if result.pdf_path and result.pdf_path.exists():
        dest = output_dir / "output.pdf"
        shutil.copy2(result.pdf_path, dest)
        output_pdf = str(dest)

    # Save compiler log
    if result.log_output:
        log_path = output_dir / "output.log"
        log_path.write_text(result.log_output, encoding="utf-8")

    if output_pdf:
        logger.info("PDF saved to %s", output_pdf)
    else:
        logger.warning("Final compilation failed — only .tex saved")

    return {
        "output_tex_path": str(tex_path),
        "output_pdf_path": output_pdf,
    }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def route_after_compile(state: PipelineState) -> str:
    if state.get("compiler_success"):
        return "advance"
    settings = get_settings(state)
    if state.get("retry_count", 0) >= settings.max_retries:
        logger.warning(
            "Max retries reached for page %d, advancing anyway",
            state["page_index"] + 1,
        )
        return "advance"  # give up on this page, move on
    return "fix"


def route_after_advance(state: PipelineState) -> str:
    if state["page_index"] >= len(state["pages"]):
        return "done"
    return "next_page"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_graph() -> StateGraph:
    graph = StateGraph(PipelineState)

    graph.add_node("preprocess", preprocess_node)
    graph.add_node("generate_latex", generate_latex_node)
    graph.add_node("compile_latex", compile_latex_node)
    graph.add_node("fix_latex", fix_latex_node)
    graph.add_node("advance_page", advance_page_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("preprocess")
    graph.add_edge("preprocess", "generate_latex")
    graph.add_edge("generate_latex", "compile_latex")

    graph.add_conditional_edges(
        "compile_latex",
        route_after_compile,
        {
            "fix": "fix_latex",
            "advance": "advance_page",
        },
    )

    graph.add_edge("fix_latex", "compile_latex")

    graph.add_conditional_edges(
        "advance_page",
        route_after_advance,
        {
            "next_page": "generate_latex",
            "done": "finalize",
        },
    )

    graph.add_edge("finalize", END)

    return graph


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_pipeline(file_paths: list[Path], settings: Settings) -> PipelineState:
    """Run the full conversion pipeline on the given input files."""
    pages = load_pages(file_paths, settings)

    logger.info("Loaded %d page(s) from %d file(s)", len(pages), len(file_paths))

    graph = build_graph()
    compiled = graph.compile()

    initial_state: PipelineState = {
        "pages": pages,
        "settings_dict": settings.model_dump(mode="json"),
        "page_index": 0,
        "retry_count": 0,
        "base_body": "",
        "accumulated_body": "",
        "current_page_latex": "",
        "compiler_success": False,
        "errors": [],
        "output_tex_path": "",
        "output_pdf_path": "",
    }

    final_state = await compiled.ainvoke(initial_state)
    return final_state
