"""Agent configuration — settings, preamble, and prompt templates."""

from dataclasses import dataclass, field

from jinja2 import BaseLoader, Environment

from agent.prompts.loader import load_default_template

DEFAULT_PREAMBLE = r"""\documentclass[12pt]{article}

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

_jinja_env = Environment(loader=BaseLoader())


@dataclass
class AgentConfig:
    """Configuration for the agent pipeline."""

    # LLM settings
    model: str = "openrouter/google/gemini-3-flash-preview"
    temperature: float = 0.1
    max_tokens: int = 16384

    # Pipeline settings
    max_retries: int = 3
    context_lines: int = 40

    # Document settings
    preamble: str = field(default_factory=lambda: DEFAULT_PREAMBLE)

    # Prompt templates (raw Jinja2 strings, overridable)
    transcribe_template: str = field(
        default_factory=lambda: load_default_template("transcribe")
    )
    fix_errors_template: str = field(
        default_factory=lambda: load_default_template("fix_errors")
    )

    # Metadata
    name: str = "notes2latex"
    version: str = "0.1.0"

    def render_transcribe_prompt(self, page_number: int, open_envs: list[str]) -> str:
        """Render the transcription system prompt from stored template."""
        template = _jinja_env.from_string(self.transcribe_template)
        return template.render(page_number=page_number, open_envs=open_envs)

    def render_fix_errors_prompt(self) -> str:
        """Render the fix-errors system prompt from stored template."""
        template = _jinja_env.from_string(self.fix_errors_template)
        return template.render()
