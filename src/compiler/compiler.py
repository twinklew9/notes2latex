"""LaTeX compilation and log parsing."""

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

RE_ERROR = re.compile(r"^! (.+)$", re.MULTILINE)
RE_LINE_NUM = re.compile(r"^l\.(\d+)\s*(.*)", re.MULTILINE)


@dataclass
class LatexError:
    line: int | None
    message: str
    context: str = ""


@dataclass
class CompilerResult:
    success: bool
    pdf_path: Path | None = None
    errors: list[LatexError] = field(default_factory=list)
    log_output: str = ""


def compile_latex(
    latex_source: str,
    latex_engine: str = "pdflatex",
    compile_timeout: int = 60,
    work_dir: Path | None = None,
) -> CompilerResult:
    """Write latex source to a .tex file, compile with latexmk, and parse the log."""
    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="notes2latex_"))

    tex_path = work_dir / "output.tex"
    tex_path.write_text(latex_source, encoding="utf-8")

    cmd = [
        "latexmk",
        f"-{latex_engine}",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={work_dir}",
        str(tex_path),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=compile_timeout,
            cwd=str(work_dir),
        )
    except subprocess.TimeoutExpired:
        return CompilerResult(
            success=False,
            errors=[LatexError(line=None, message="Compilation timed out")],
        )

    log_path = work_dir / "output.log"
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""

    errors = _parse_errors(log_text)
    pdf_path = work_dir / "output.pdf"
    success = proc.returncode == 0 and pdf_path.exists()

    return CompilerResult(
        success=success,
        pdf_path=pdf_path if pdf_path.exists() else None,
        errors=errors,
        log_output=log_text,
    )


def _parse_errors(log_text: str) -> list[LatexError]:
    """Parse LaTeX log for errors by splitting at '!' markers."""
    errors: list[LatexError] = []
    chunks = re.split(r"(?=^! )", log_text, flags=re.MULTILINE)

    for chunk in chunks:
        error_match = RE_ERROR.search(chunk)
        if not error_match:
            continue

        message = error_match.group(1).strip()
        line_match = RE_LINE_NUM.search(chunk)
        line_num = int(line_match.group(1)) if line_match else None
        context = line_match.group(2).strip() if line_match else ""

        errors.append(LatexError(line=line_num, message=message, context=context))

    return errors
