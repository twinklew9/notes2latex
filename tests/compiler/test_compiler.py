"""Tests for the LaTeX compiler service."""

from compiler.compiler import _parse_errors, compile_latex
from core.config import Settings


class TestParseErrors:
    def test_no_errors(self):
        log = "This is output\nNo errors here\n"
        assert _parse_errors(log) == []

    def test_single_error_with_line(self):
        log = (
            "Some output\n"
            "! Undefined control sequence.\n"
            "l.42 \\badcommand\n"
            "more output\n"
        )
        errors = _parse_errors(log)
        assert len(errors) == 1
        assert errors[0].line == 42
        assert "Undefined control sequence" in errors[0].message

    def test_multiple_errors(self):
        log = (
            "! Missing $ inserted.\n"
            "l.10 some code\n"
            "...\n"
            "! Extra }, or forgotten $.\n"
            "l.25 other code\n"
        )
        errors = _parse_errors(log)
        assert len(errors) == 2
        assert errors[0].line == 10
        assert errors[1].line == 25

    def test_error_without_line_number(self):
        log = "! Emergency stop.\n\nsome other text\n"
        errors = _parse_errors(log)
        assert len(errors) == 1
        assert errors[0].line is None
        assert "Emergency stop" in errors[0].message

    def test_empty_log(self):
        assert _parse_errors("") == []


class TestCompileLatex:
    def test_valid_document(self, tmp_path):
        latex = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "Hello $x^2$.\n"
            "\\end{document}\n"
        )
        settings = Settings()
        result = compile_latex(latex, settings, work_dir=tmp_path)
        assert result.success
        assert result.pdf_path is not None
        assert result.pdf_path.exists()

    def test_invalid_document(self, tmp_path):
        latex = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\undefinedcommandxyz\n"
            "\\end{document}\n"
        )
        settings = Settings()
        result = compile_latex(latex, settings, work_dir=tmp_path)
        assert not result.success
        assert len(result.errors) > 0

    def test_log_output_captured(self, tmp_path):
        latex = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "Hello.\n"
            "\\end{document}\n"
        )
        settings = Settings()
        result = compile_latex(latex, settings, work_dir=tmp_path)
        assert len(result.log_output) > 0
