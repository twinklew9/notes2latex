"""Tests for pipeline routing, helpers, and end-to-end flow."""

from unittest.mock import AsyncMock, patch

import pytest

from notes2latex.config import Settings
from notes2latex.pipeline import (
    PREAMBLE,
    _assemble_document,
    open_environments,
    route_after_advance,
    route_after_compile,
    run_pipeline,
)


class TestRouting:
    def test_route_after_compile_success(self):
        state = {"compiler_success": True, "retry_count": 0, "settings_dict": {}}
        assert route_after_compile(state) == "advance"

    def test_route_after_compile_retry(self):
        state = {"compiler_success": False, "retry_count": 1, "settings_dict": {}}
        assert route_after_compile(state) == "fix"

    def test_route_after_compile_max_retries(self):
        state = {"compiler_success": False, "retry_count": 3, "settings_dict": {}, "page_index": 0}
        assert route_after_compile(state) == "advance"

    def test_route_after_advance_next_page(self):
        # page_index=1 means we just advanced from page 0; page 1 still needs processing
        state = {"page_index": 1, "pages": ["a", "b", "c"]}
        assert route_after_advance(state) == "next_page"

    def test_route_after_advance_done(self):
        # page_index=3 means all 3 pages (0,1,2) are done
        state = {"page_index": 3, "pages": ["a", "b", "c"]}
        assert route_after_advance(state) == "done"

    def test_route_after_advance_single_page(self):
        # page_index=1 after advancing from the only page
        state = {"page_index": 1, "pages": ["a"]}
        assert route_after_advance(state) == "done"

    def test_route_after_advance_two_pages_midway(self):
        # page_index=1 means page 0 done, page 1 still needs processing
        state = {"page_index": 1, "pages": ["a", "b"]}
        assert route_after_advance(state) == "next_page"


class TestOpenEnvironments:
    def test_empty_string(self):
        assert open_environments("") == []

    def test_no_environments(self):
        assert open_environments(r"Hello $x^2$ world") == []

    def test_closed_environment(self):
        latex = r"\begin{theorem}Some theorem.\end{theorem}"
        assert open_environments(latex) == []

    def test_open_environment(self):
        latex = r"\begin{enumerate}\item First"
        assert open_environments(latex) == ["enumerate"]

    def test_nested_open(self):
        latex = (
            r"\begin{theorem}" "\n"
            r"\begin{align}" "\n"
            r"x &= 1"
        )
        assert open_environments(latex) == ["theorem", "align"]

    def test_partially_closed(self):
        latex = (
            r"\begin{theorem}" "\n"
            r"\begin{align}" "\n"
            r"x &= 1" "\n"
            r"\end{align}"
        )
        assert open_environments(latex) == ["theorem"]

    def test_multiple_open_close(self):
        latex = (
            r"\begin{theorem}Thm.\end{theorem}" "\n"
            r"\begin{proof}" "\n"
            r"\begin{align}" "\n"
            r"a &= b"
        )
        assert open_environments(latex) == ["proof", "align"]


class TestAssembleDocument:
    def test_assembles_correctly(self):
        body = "Hello $x^2$."
        doc = _assemble_document(body)
        assert doc.startswith(PREAMBLE)
        assert "Hello $x^2$." in doc
        assert doc.strip().endswith(r"\end{document}")

    def test_empty_body(self):
        doc = _assemble_document("")
        assert r"\begin{document}" in doc
        assert r"\end{document}" in doc


# Body-only mock (no preamble, no \begin/\end{document})
MOCK_BODY = "Hello $x^2$."


class TestPipelineEndToEnd:
    """Mock-based test for the full pipeline flow."""

    @pytest.mark.asyncio
    async def test_single_page_pipeline(self, tmp_path):
        # Create a dummy image file
        from PIL import Image

        img = Image.new("RGB", (100, 100), color="white")
        img_path = tmp_path / "test.png"
        img.save(img_path)

        settings = Settings(output_dir=tmp_path / "output", max_retries=1)

        with (
            patch("notes2latex.pipeline.transcribe_page", new_callable=AsyncMock) as mock_transcribe,
            patch("notes2latex.pipeline.compile_latex") as mock_compile,
        ):
            mock_transcribe.return_value = MOCK_BODY

            from notes2latex.compiler import CompilerResult

            mock_compile.return_value = CompilerResult(
                success=True,
                pdf_path=None,
                errors=[],
                log_output="",
            )

            result = await run_pipeline([img_path], settings)

        # accumulated_body should be body-only
        assert result["accumulated_body"] == MOCK_BODY
        # The assembled document passed to compile should include preamble
        compile_call_args = mock_compile.call_args_list[0][0][0]
        assert PREAMBLE in compile_call_args
        assert r"\end{document}" in compile_call_args
        mock_transcribe.assert_called_once()
        # compile is called in compile_latex_node + finalize_node = 2 times
        assert mock_compile.call_count == 2
