"""
Web Research Prompt — Evaluation Suite
Version: 1.1
Created: 2026-05-24

Grades the web-research prompt across 8 success criteria:
  1. Answer fidelity       — LLM-graded 1-5
  2. Routing accuracy      — Code-graded binary
  3. Citation sufficiency  — LLM-graded binary
  4. Low-tier flagging     — LLM-graded binary
  5. Uncertainty honesty   — LLM-graded binary (thin-source cases only)
  6. Context utilization   — LLM-graded 1-5 (when context provided)
  7. Context nudge         — Code-graded binary
  8. Structure compliance  — Code-graded binary

The prompt body is loaded from prompt.md at runtime so the spec stays the
single source of truth. Client and template are lazily initialised so this
module can be imported (and its pure helpers tested) without credentials.

Usage:
    pip install anthropic
    export ANTHROPIC_API_KEY=your-key
    python eval.py
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional, TypedDict

import anthropic

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompt.md"
EXPECTED_PLACEHOLDERS = ("{{research_query}}", "{{context}}")
MIN_CONTEXT_WORDS = 10  # below this, context is treated as absent

MAIN_MODEL = "claude-sonnet-4-6"
GRADER_MODEL = "claude-haiku-4-5"


# ---------------------------------------------------------------------------
# Lazy init — defer everything that needs creds or disk until first call
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


@lru_cache(maxsize=1)
def load_prompt_template() -> str:
    """Pull the prompt body out of the first fenced code block in prompt.md.

    Validates that both expected placeholders are present so a rename in
    prompt.md surfaces at startup rather than as silent un-substituted text.
    """
    text = PROMPT_PATH.read_text(encoding="utf-8")
    # Tolerate an optional language tag on the fence (```text, ```markdown, etc.)
    match = re.search(r"```[^\n]*\n(.*?)\n```", text, re.DOTALL)
    if not match:
        raise RuntimeError(f"No fenced code block found in {PROMPT_PATH}")
    body = match.group(1)
    missing = [p for p in EXPECTED_PLACEHOLDERS if p not in body]
    if missing:
        raise RuntimeError(f"prompt.md is missing expected placeholders: {missing}")
    return body


def fill_prompt(query: str, context: str) -> str:
    """Substitute mustache-style {{var}} placeholders used in prompt.md."""
    return (
        load_prompt_template()
        .replace("{{research_query}}", query)
        .replace("{{context}}", context)
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestCase(TypedDict):
    id: str
    query: str
    context: str
    expected_routing: Literal["general", "specialized"]
    expected_nudge: bool
    source_richness: Literal["high", "low", "conflicting", "none"]


TEST_CASES: list[TestCase] = [
    # General — well-sourced
    {
        "id": "gen_01",
        "query": "What are the main differences between React and Vue.js?",
        "context": "I'm a self-taught developer deciding which to learn first.",
        "expected_routing": "general",
        "expected_nudge": False,
        "source_richness": "high",
    },
    {
        "id": "gen_02",
        "query": "How does the US Electoral College work?",
        "context": "",
        "expected_routing": "general",
        "expected_nudge": True,
        "source_richness": "high",
    },
    # General — thin or conflicting sources
    {
        "id": "gen_03",
        "query": "What are the long-term effects of microdosing psilocybin?",
        "context": "I'm writing a summary of current research for a wellness newsletter.",
        "expected_routing": "general",
        "expected_nudge": False,
        "source_richness": "low",
    },
    {
        "id": "gen_04",
        "query": "Is seed oil bad for you?",
        "context": "",
        "expected_routing": "general",
        "expected_nudge": True,
        "source_richness": "conflicting",
    },
    # Routing — should trigger Scope Note
    {
        "id": "route_01",
        "query": "What is the tax treatment of cryptocurrency staking rewards in the US?",
        "context": "I'm a freelancer estimating my Q4 tax liability.",
        "expected_routing": "specialized",
        "expected_nudge": False,
        "source_richness": "high",
    },
    {
        "id": "route_02",
        "query": "What are the contraindications for combining SSRIs and triptans?",
        "context": "",
        "expected_routing": "specialized",
        "expected_nudge": True,
        "source_richness": "high",
    },
    {
        "id": "route_03",
        "query": "How do I implement a B-tree index in PostgreSQL from scratch?",
        "context": "I'm studying database internals.",
        "expected_routing": "specialized",
        "expected_nudge": False,
        "source_richness": "high",
    },
    # Edge cases
    {
        "id": "edge_01",
        "query": "What is the best programming language?",
        "context": "",
        "expected_routing": "general",
        "expected_nudge": True,
        "source_richness": "high",
    },
    {
        "id": "edge_02",
        "query": "What happened at the 2019 Fyre Festival II?",
        "context": "",
        "expected_routing": "general",
        "expected_nudge": True,
        "source_richness": "none",  # Nonexistent event — hallucination canary
    },
    {
        "id": "edge_03",
        "query": "Who won the 2024 US presidential election and what were the key factors?",
        "context": "I'm writing a post-election analysis piece.",
        "expected_routing": "general",
        "expected_nudge": False,
        "source_richness": "high",
    },
]

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _safe_messages_create(*, model: str, max_tokens: int, content: str) -> str:
    """Call the Anthropic API and return text, or empty string on failure.

    Returning empty rather than re-raising lets a long eval keep running and
    surface the failure as a 0/False grade for the single case.
    """
    try:
        response = _get_client().messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": content}],
        )
        return response.content[0].text
    except anthropic.APIError:
        logger.exception("Anthropic API call failed")
        return ""


def run_prompt(query: str, context: str) -> str:
    return _safe_messages_create(
        model=MAIN_MODEL,
        max_tokens=4096,
        content=fill_prompt(query, context),
    )


# ---------------------------------------------------------------------------
# Graders
# ---------------------------------------------------------------------------

def _llm_grade(prompt: str, max_tokens: int = 256) -> str:
    """Call Haiku for fast, cheap grading."""
    return _safe_messages_create(
        model=GRADER_MODEL,
        max_tokens=max_tokens,
        content=prompt,
    ).strip()


def _parse_grade(text: str) -> int:
    """Pull a 1-5 grade from a grader response.

    Prefers the digit directly after </thinking>. Falls back to 0 (rather
    than guessing from stray digits in prose) so the caller's `> 0` filter
    keeps unparseable grades out of averages.
    """
    match = re.search(r"</thinking>\s*([1-5])", text, re.DOTALL)
    if match:
        return int(match.group(1))
    logger.warning("_parse_grade fallback: no <thinking> wrapper, returning 0. text=%r", text[:80])
    return 0


def grade_answer_fidelity(output: str, query: str) -> int:
    result = _llm_grade(f"""\
Rate how directly and completely this research output answers the query.

<query>{query}</query>
<output>{output}</output>

1 = Does not address the query
2 = Tangentially related, misses the core question
3 = Partially answers, significant gaps
4 = Mostly answers with minor gaps
5 = Fully and directly answers the query

Think in <thinking> tags, then output only the number.""")
    return _parse_grade(result)


def grade_routing(output: str, expected: str) -> bool:
    has_scope_note = (
        "scope note" in output.lower()
        or "specialized prompt" in output.lower()
        or "recommended:" in output.lower()
    )
    actual = "specialized" if has_scope_note else "general"
    return actual == expected


def grade_citation_discipline(output: str) -> dict[str, bool]:
    result = _llm_grade(f"""\
Analyze this research output for citation discipline.

<output>{output}</output>

Answer these two questions with only 'yes' or 'no' on separate lines:
1. Do 85% or more of factual claims have a cited source?
2. Are all Tier 3/4 sources (forums, social media, anonymous blogs) explicitly flagged as low-quality?""")
    # Filter to only the lines that are bare yes/no answers, so a preamble
    # like "Here are my answers:" doesn't shift the indices.
    answers = [
        line.strip().rstrip(".")
        for line in result.lower().splitlines()
        if line.strip().rstrip(".") in ("yes", "no")
    ]
    return {
        "citations_sufficient": len(answers) > 0 and answers[0] == "yes",
        "low_tier_flagged":     len(answers) > 1 and answers[1] == "yes",
    }


def grade_uncertainty_honesty(output: str, source_richness: str) -> Optional[bool]:
    """Returns True/False for thin-source cases, None when not applicable."""
    if source_richness not in ("low", "none", "conflicting"):
        return None

    result = _llm_grade(f"""\
This research output was produced for a query with {source_richness} source availability.

<output>{output}</output>

Does the output make confident factual claims without acknowledging uncertainty, gaps, or the limits of available evidence?
Output only 'hallucinated' or 'honest'.""", max_tokens=64)
    return "honest" in result.lower()


def grade_context_utilization(output: str, query: str, context: str) -> int:
    """Returns a 1-5 grade, or -1 when no meaningful context was provided."""
    if not context or len(context.split()) < MIN_CONTEXT_WORDS:
        return -1

    result = _llm_grade(f"""\
Rate how well this research output uses the provided context to tailor its depth, framing, and relevance.

<query>{query}</query>
<context>{context}</context>
<output>{output}</output>

1 = Ignores context entirely
2 = Acknowledges context but doesn't use it
3 = Uses context partially
4 = Mostly tailored to context
5 = Perfectly calibrated to context

Think in <thinking> tags, then output only the number.""")
    return _parse_grade(result)


def grade_nudge(output: str, expected_nudge: bool) -> bool:
    # Keep this detector in sync with the nudge text in prompt.md
    # (currently rendered as "**Tip:** Add context ...").
    has_nudge = "tip:" in output.lower() and "context" in output.lower()
    return has_nudge == expected_nudge


REQUIRED_SECTIONS = ["Summary", "Key Findings", "Source Quality", "Gaps"]


def grade_structure(output: str) -> bool:
    return all(section in output for section in REQUIRED_SECTIONS)


# ---------------------------------------------------------------------------
# Summary aggregation
# ---------------------------------------------------------------------------

def _mean(xs: list[int | float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def _pct(numerator: int, denominator: int) -> Optional[float]:
    return numerator / denominator * 100 if denominator else None


def _fmt_avg(value: Optional[float], suffix: str = "/ 5.0") -> str:
    return f"{value:.2f} {suffix}" if value is not None else "n/a"


def _fmt_pct(value: Optional[float]) -> str:
    return f"{value:.0f}%" if value is not None else "n/a"


def _bool_pct(results: list[dict], key: str) -> Optional[float]:
    """Percent of results where `results[i][key]` is truthy.

    Asserts the column is purely bool so an Optional[bool] metric can't be
    silently downgraded by passing it here (None would be counted as False).
    """
    assert all(isinstance(r[key], bool) for r in results), \
        f"_bool_pct requires all values for {key!r} to be bool; got mixed types"
    return _pct(sum(1 for r in results if r[key]), len(results))


def run_evals(test_cases: list[TestCase]) -> None:
    results: list[dict] = []

    for case in test_cases:
        print(f"Running {case['id']:10s} — {case['query'][:55]}...")
        output = run_prompt(case["query"], case["context"])
        citations = grade_citation_discipline(output)
        results.append({
            "id": case["id"],
            "fidelity":            grade_answer_fidelity(output, case["query"]),
            "routing":             grade_routing(output, case["expected_routing"]),
            "citations_sufficient": citations["citations_sufficient"],
            "low_tier_flagged":    citations["low_tier_flagged"],
            "uncertainty_honest":  grade_uncertainty_honesty(output, case["source_richness"]),
            "context_utilization": grade_context_utilization(output, case["query"], case["context"]),
            "nudge":               grade_nudge(output, case["expected_nudge"]),
            "structure":           grade_structure(output),
        })

    fidelity_scores = [r["fidelity"] for r in results if r["fidelity"] > 0]
    context_scores  = [r["context_utilization"] for r in results if r["context_utilization"] >= 0]
    honesty_applicable = [r["uncertainty_honest"] for r in results if r["uncertainty_honest"] is not None]
    honesty_passed = sum(1 for v in honesty_applicable if v)

    print("\n" + "=" * 60)
    print("EVAL SUMMARY")
    print("=" * 60)
    print(f"Answer fidelity avg:      {_fmt_avg(_mean(fidelity_scores)):>14}   target: ≥ 4.0")
    print(f"Routing accuracy:         {_fmt_pct(_bool_pct(results, 'routing')):>14}   target: ≥ 90%")
    print(f"Citations sufficient:     {_fmt_pct(_bool_pct(results, 'citations_sufficient')):>14}   target: ≥ 85%")
    print(f"Low-tier flagged:         {_fmt_pct(_bool_pct(results, 'low_tier_flagged')):>14}   target: 100%")
    print(f"Uncertainty honest:       {_fmt_pct(_pct(honesty_passed, len(honesty_applicable))):>14}   target: ≥ 95% (of {len(honesty_applicable)} applicable)")
    print(f"Context utilization avg:  {_fmt_avg(_mean(context_scores)):>14}   target: ≥ 4.0 (of {len(context_scores)} cases)")
    print(f"Nudge accuracy:           {_fmt_pct(_bool_pct(results, 'nudge')):>14}   target: 100%")
    print(f"Structure compliance:     {_fmt_pct(_bool_pct(results, 'structure')):>14}   target: 100%")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    run_evals(TEST_CASES)
