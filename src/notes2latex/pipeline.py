"""LangGraph pipeline — the agentic generate→compile→fix loop."""

import asyncio
import logging
import re
import shutil
from pathlib import Path
from typing import Annotated, TypedDict

from jinja2 import Environment, FileSystemLoader
from langgraph.graph import END, StateGraph

from notes2latex.compiler import compile_latex
from notes2latex.config import Settings
from notes2latex.llm import fix_latex, transcribe_page
from notes2latex.preprocessor import load_pages

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Static preamble — single source of truth
# ---------------------------------------------------------------------------

PREAMBLE = r"""\documentclass[12pt]{article}

% --- Packages ---
\usepackage{amsmath, amssymb, amsthm}
\usepackage{mathtools}
\usepackage{thmtools}
\usepackage{cancel}
\usepackage{mathrsfs}

% physics redefines \div to divergence — save and restore
\let\olddiv\div
\usepackage{physics}
\let\div\olddiv

\usepackage{siunitx}
\usepackage{tikz, tikz-cd, pgfplots}
\pgfplotsset{compat=1.18}
\usetikzlibrary{decorations.pathreplacing, arrows.meta, calc}
\usepackage{algorithm2e}
\usepackage{listings}
\usepackage{geometry}
\geometry{margin=1in}
\usepackage{enumitem}
\usepackage{hyperref}
\usepackage{tcolorbox}

% --- Theorem environments ---
\newtheorem{theorem}{Theorem}[section]
\newtheorem{lemma}[theorem]{Lemma}
\newtheorem{corollary}[theorem]{Corollary}
\newtheorem{proposition}[theorem]{Proposition}
\theoremstyle{definition}
\newtheorem{definition}[theorem]{Definition}
\newtheorem{example}[theorem]{Example}
\newtheorem{exercise}[theorem]{Exercise}
\theoremstyle{remark}
\newtheorem{remark}[theorem]{Remark}
\newtheorem{notation}[theorem]{Notation}

\begin{document}"""


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


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


def _get_settings(state: PipelineState) -> Settings:
    """Reconstruct Settings from state dict."""
    return Settings(**state.get("settings_dict", {}))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent / "prompts"

_RE_ENV = re.compile(r"\\(begin|end)\{([^}]+)\}")


def _jinja_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)))


def open_environments(latex: str) -> list[str]:
    """Return stack of environments still open at end of the string."""
    stack: list[str] = []
    for m in _RE_ENV.finditer(latex):
        if m.group(1) == "begin":
            stack.append(m.group(2))
        elif stack and stack[-1] == m.group(2):
            stack.pop()
    return stack


def _assemble_document(body: str) -> str:
    """Wrap body content in the static preamble and document environment."""
    return PREAMBLE + "\n" + body + "\n\\end{document}\n"


def _strip_preamble_from_body(latex: str) -> str:
    """Strip preamble lines that the model mistakenly includes in body-only output."""
    lines = latex.splitlines()
    filtered = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(r"\documentclass"):
            continue
        if stripped.startswith(r"\usepackage"):
            continue
        if stripped == r"\begin{document}":
            continue
        if stripped == r"\end{document}":
            continue
        if stripped.startswith(r"\newtheorem"):
            continue
        if stripped.startswith(r"\theoremstyle"):
            continue
        if stripped.startswith(r"\pgfplotsset"):
            continue
        if stripped.startswith(r"\geometry{"):
            continue
        if stripped.startswith(r"\declaretheoremstyle"):
            continue
        if stripped.startswith(r"\declaretheorem"):
            continue
        filtered.append(line)
    return "\n".join(filtered)


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
    settings = _get_settings(state)
    page_idx = state["page_index"]
    page_b64 = state["pages"][page_idx]

    logger.info("Generating LaTeX for page %d/%d", page_idx + 1, len(state["pages"]))

    accumulated_body = state.get("accumulated_body", "")
    open_envs = open_environments(accumulated_body) if accumulated_body else []

    template = _jinja_env().get_template("transcribe.md")
    system_prompt = template.render(
        page_number=page_idx + 1,
        open_envs=open_envs,
    )

    # Pass body tail as context (llm.py truncates to last N lines)
    # Body-only = no preamble noise in the context window
    context = accumulated_body if accumulated_body else ""

    latex = await transcribe_page(
        image_b64=page_b64,
        system_prompt=system_prompt,
        settings=settings,
        context_latex=context,
    )

    latex = _strip_preamble_from_body(latex)
    base = accumulated_body
    new_body = (base + "\n" + latex) if base else latex

    return {
        "current_page_latex": latex,
        "base_body": base,
        "accumulated_body": new_body,
        "retry_count": 0,
    }


async def compile_latex_node(state: PipelineState) -> dict:
    settings = _get_settings(state)
    body = state["accumulated_body"]

    # Temporarily close any environments still open at the end of the body
    # so compilation succeeds even when an environment spans pages.
    # The real accumulated_body is NOT modified — only the compilation input.
    open_envs = open_environments(body)
    if open_envs:
        closing_tags = "\n".join(rf"\end{{{env}}}" for env in reversed(open_envs))
        body = body + "\n" + closing_tags

    full_doc = _assemble_document(body)
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
    settings = _get_settings(state)
    retry = state["retry_count"] + 1
    page_idx = state["page_index"]

    logger.info("Fix attempt %d for page %d", retry, page_idx + 1)

    # Calculate line offset: preamble lines + base_body lines
    preamble_lines = PREAMBLE.count("\n") + 1
    base_body = state["base_body"]
    base_lines = base_body.count("\n") + 1 if base_body else 0
    offset = preamble_lines + base_lines

    adjusted_errors = []
    for e in state["errors"]:
        adjusted = dict(e)
        if adjusted.get("line") is not None:
            adjusted["line"] = max(1, adjusted["line"] - offset)
        adjusted_errors.append(adjusted)

    template = _jinja_env().get_template("fix_errors.md")
    system_prompt = template.render()

    fixed_page = await fix_latex(
        latex_source=state["current_page_latex"],
        errors=adjusted_errors,
        system_prompt=system_prompt,
        settings=settings,
    )

    fixed_page = _strip_preamble_from_body(fixed_page)
    base = state["base_body"]
    new_body = (base + "\n" + fixed_page) if base else fixed_page

    return {
        "current_page_latex": fixed_page,
        "accumulated_body": new_body,
        "retry_count": retry,
    }


async def advance_page_node(state: PipelineState) -> dict:
    return {
        "page_index": state["page_index"] + 1,
        "retry_count": 0,
    }


async def finalize_node(state: PipelineState) -> dict:
    settings = _get_settings(state)
    output_dir = settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Assemble full document from body
    full_doc = _assemble_document(state["accumulated_body"])

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
    settings = _get_settings(state)
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
