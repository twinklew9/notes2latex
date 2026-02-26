"""Typer CLI entry point."""

import asyncio
import logging
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.logging import RichHandler

from notes2latex.config import Settings
from notes2latex.pipeline import run_pipeline

app = typer.Typer(
    name="notes2latex",
    help="Convert handwritten math notes to compiled LaTeX.",
    add_completion=False,
)
console = Console()


@app.command()
def convert(
    files: Annotated[
        list[Path],
        typer.Argument(help="Input PDF or image files", exists=True),
    ],
    model: Annotated[
        Optional[str],
        typer.Option("--model", "-m", help="LLM model name (e.g. openai/gpt-4o)"),
    ] = None,
    output_dir: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Output directory"),
    ] = None,
    max_retries: Annotated[
        Optional[int],
        typer.Option("--max-retries", help="Max fix attempts per page"),
    ] = None,
    dpi: Annotated[
        Optional[int],
        typer.Option("--dpi", help="DPI for PDF rendering"),
    ] = None,
) -> None:
    """Convert handwritten math notes (images/PDFs) to compiled LaTeX."""
    overrides: dict = {}
    if model is not None:
        overrides["model"] = model
    if output_dir is not None:
        overrides["output_dir"] = output_dir
    if max_retries is not None:
        overrides["max_retries"] = max_retries
    if dpi is not None:
        overrides["dpi"] = dpi

    settings = Settings(**overrides)

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_time=False, show_path=False)],
    )

    console.print(
        f"[bold blue]Processing {len(files)} file(s)[/] with model [cyan]{settings.model}[/]"
    )

    result = asyncio.run(run_pipeline(files, settings))

    if result.get("output_pdf_path"):
        console.print(f"[bold green]PDF:[/] {result['output_pdf_path']}")
    if result.get("output_tex_path"):
        console.print(f"[bold green]TeX:[/] {result['output_tex_path']}")
    if not result.get("output_pdf_path"):
        console.print(
            "[bold yellow]Warning:[/] Compilation failed. "
            "LaTeX source was saved but no PDF was produced."
        )


@app.command()
def version() -> None:
    """Show version."""
    from notes2latex import __version__

    console.print(f"notes2latex {__version__}")
