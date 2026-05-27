"""
Unit tests for pure helpers in eval.py.

Skips anything that would call the Anthropic API. Run with:
    pip install pytest
    pytest prompts/web-research/test_eval.py
"""

from __future__ import annotations

import textwrap

import pytest

import eval as ev


# ---------------------------------------------------------------------------
# _parse_grade
# ---------------------------------------------------------------------------

def test_parse_grade_with_thinking_wrapper():
    assert ev._parse_grade("<thinking>reasons here</thinking> 4") == 4


def test_parse_grade_with_thinking_and_newline():
    assert ev._parse_grade("<thinking>\nthought\n</thinking>\n3") == 3


def test_parse_grade_bare_digit_returns_zero():
    # Without the <thinking> wrapper we deliberately return 0 so the caller's
    # `> 0` filter excludes the grade from averages.
    assert ev._parse_grade("5") == 0


def test_parse_grade_prose_returns_zero():
    assert ev._parse_grade("I would rate this a 4 out of 5.") == 0


def test_parse_grade_empty_returns_zero():
    assert ev._parse_grade("") == 0


# ---------------------------------------------------------------------------
# grade_routing / grade_nudge / grade_structure
# ---------------------------------------------------------------------------

def test_routing_detects_scope_note():
    assert ev.grade_routing("**Scope Note**: out of band", expected="specialized") is True
    assert ev.grade_routing("**Scope Note**: out of band", expected="general") is False


def test_routing_default_is_general():
    assert ev.grade_routing("Plain answer with no scope tag.", expected="general") is True
    assert ev.grade_routing("Plain answer with no scope tag.", expected="specialized") is False


def test_routing_recognises_recommended_keyword():
    assert ev.grade_routing("Recommended: Legal Research", expected="specialized") is True


def test_nudge_detected_when_expected():
    out = "**Tip:** Add context for a more targeted response."
    assert ev.grade_nudge(out, expected_nudge=True) is True
    assert ev.grade_nudge(out, expected_nudge=False) is False


def test_nudge_absent_when_expected_absent():
    assert ev.grade_nudge("No nudge here.", expected_nudge=False) is True


def test_structure_requires_all_sections():
    full = "Summary\nKey Findings\nSource Quality\nGaps & Caveats"
    assert ev.grade_structure(full) is True
    assert ev.grade_structure("Summary only") is False


# ---------------------------------------------------------------------------
# grade_citation_discipline — defensive yes/no parser
# ---------------------------------------------------------------------------

def test_citation_discipline_clean_yes_no():
    # _llm_grade is normally an API call; we monkey-patch it for this test.
    pass  # See test_citation_discipline_with_preamble below for the patching pattern


def test_citation_discipline_tolerates_preamble(monkeypatch):
    monkeypatch.setattr(ev, "_llm_grade", lambda *a, **kw: "Sure, here are my answers:\nyes\nno")
    result = ev.grade_citation_discipline("...")
    assert result == {"citations_sufficient": True, "low_tier_flagged": False}


def test_citation_discipline_handles_trailing_punctuation(monkeypatch):
    monkeypatch.setattr(ev, "_llm_grade", lambda *a, **kw: "Yes.\nNo.")
    result = ev.grade_citation_discipline("...")
    assert result == {"citations_sufficient": True, "low_tier_flagged": False}


# ---------------------------------------------------------------------------
# fill_prompt + load_prompt_template
# ---------------------------------------------------------------------------

def test_fill_prompt_substitutes_both_placeholders():
    out = ev.fill_prompt("the query", "the context")
    assert "{{research_query}}" not in out
    assert "{{context}}" not in out
    assert "the query" in out
    assert "the context" in out


def test_load_prompt_template_missing_block(tmp_path, monkeypatch):
    bad = tmp_path / "prompt.md"
    bad.write_text("# Header\nNo fences here.\n")
    monkeypatch.setattr(ev, "PROMPT_PATH", bad)
    ev.load_prompt_template.cache_clear()
    with pytest.raises(RuntimeError, match="No fenced code block"):
        ev.load_prompt_template()


def test_load_prompt_template_missing_placeholder(tmp_path, monkeypatch):
    bad = tmp_path / "prompt.md"
    bad.write_text(textwrap.dedent("""\
        # Spec
        ```
        Body without the expected placeholders.
        ```
    """))
    monkeypatch.setattr(ev, "PROMPT_PATH", bad)
    ev.load_prompt_template.cache_clear()
    with pytest.raises(RuntimeError, match="missing expected placeholders"):
        ev.load_prompt_template()


def test_load_prompt_template_accepts_language_tag(tmp_path, monkeypatch):
    good = tmp_path / "prompt.md"
    good.write_text(textwrap.dedent("""\
        # Spec
        ```markdown
        Query: {{research_query}}
        Context: {{context}}
        ```
    """))
    monkeypatch.setattr(ev, "PROMPT_PATH", good)
    ev.load_prompt_template.cache_clear()
    body = ev.load_prompt_template()
    assert "{{research_query}}" in body
    assert "{{context}}" in body


# ---------------------------------------------------------------------------
# _mean / _pct / _bool_pct
# ---------------------------------------------------------------------------

def test_mean_with_values():
    assert ev._mean([2, 4, 6]) == 4.0


def test_mean_empty_returns_none():
    assert ev._mean([]) is None


def test_pct_with_denominator():
    assert ev._pct(3, 4) == 75.0


def test_pct_zero_denominator_returns_none():
    assert ev._pct(0, 0) is None


def test_bool_pct_rejects_mixed_types():
    bad_results = [{"k": True}, {"k": None}]
    with pytest.raises(AssertionError):
        ev._bool_pct(bad_results, "k")


def test_bool_pct_normal_case():
    results = [{"k": True}, {"k": False}, {"k": True}, {"k": True}]
    assert ev._bool_pct(results, "k") == 75.0


# ---------------------------------------------------------------------------
# _fmt_avg / _fmt_pct
# ---------------------------------------------------------------------------

def test_fmt_avg_with_value():
    assert ev._fmt_avg(4.234) == "4.23 / 5.0"


def test_fmt_avg_none():
    assert ev._fmt_avg(None) == "n/a"


def test_fmt_pct_with_value():
    assert ev._fmt_pct(87.3) == "87%"


def test_fmt_pct_none():
    assert ev._fmt_pct(None) == "n/a"
