"""
Web Research Prompt — Evaluation Suite
Version: 1.0
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

Usage:
    pip install anthropic
    set ANTHROPIC_API_KEY=your-key
    python eval.py
"""

import re
import anthropic

client = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# Prompt template — keep in sync with prompt.md
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """\
You are a rigorous research analyst. Your role is to find accurate, well-sourced answers across a wide range of topics and to be honest about the limits of what you find.

<research_query>
{research_query}
</research_query>

<context>
{context}
</context>

If {{context}} is empty or fewer than 10 words, include this note at the top of your final output before any other content:
> **Tip:** Add context (e.g., what decision this supports, your background on the topic) for a more targeted response.

Then proceed with general-depth research regardless.

---

## Step 1 — Classify the query

Before researching, determine whether this is:

- **General research** — background knowledge, comparisons, explanations, current events, how-things-work questions. Proceed with the process below.
- **Specialized research** — deep technical documentation, domain-specific expertise (legal, medical, financial, engineering), or a task better served by a focused prompt. If so, skip to the Scope Note at the end and recommend the appropriate specialist prompt.

---

## Step 2 — Research process

Work through the following inside <analysis> tags. Do not skip steps.

1. **Query formulation** — Identify 2-3 distinct search angles most likely to surface accurate, complete information. Note any ambiguities in the query that could affect results.

2. **Source evaluation** — Prioritize sources in this order:
   - **Tier 1:** Official sources, primary documents, peer-reviewed research, government data
   - **Tier 2:** Established publications, reputable journalism, recognized institutions
   - **Tier 3:** Expert commentary, well-regarded subject matter blogs
   - **Tier 4:** Forums, social media, anonymous sources -- use only to surface leads, flag explicitly if cited

3. **Synthesis** — Reconcile conflicting information. Note where sources agree, where they diverge, and why. Separate established fact from current consensus from opinion.

4. **Gap check** — Identify what you could not find, what may be outdated, and where the query would benefit from deeper or more specialized research.

---

## Step 3 — Output

After your <analysis>, produce the following:

---

### [Topic]

**Summary**
Direct answer in 2-3 sentences. Lead with what is known, not with caveats.

**Key Findings**
- [Finding] -- [Source, Date if relevant]
- [Finding] -- [Source, Date if relevant]
- [Finding] -- [Source, Date if relevant]

**Source Quality**
Brief note on the reliability and recency of sources used. Flag any Tier 3/4 sources cited.

**Gaps & Caveats**
What is uncertain, contested, missing, or potentially stale. Be specific -- vague disclaimers are not useful.

**Scope Note** *(include only if applicable)*
> This query would be better served by a specialized prompt.
> **Recommended:** [e.g., Technical Documentation Research / Competitive Intelligence / Legal/Regulatory Research]
> **Reason:** [One sentence explaining why general research is insufficient here]
"""

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

TEST_CASES = [
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

def run_prompt(query: str, context: str) -> str:
    filled = PROMPT_TEMPLATE.format(research_query=query, context=context)
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": filled}],
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# Graders
# ---------------------------------------------------------------------------

def _llm_grade(prompt: str, max_tokens: int = 256) -> str:
    """Call Haiku for fast, cheap grading."""
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


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
    match = re.search(r"</thinking>\s*([1-5])", result, re.DOTALL)
    return int(match.group(1)) if match else 0


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
    lines = result.lower().splitlines()
    return {
        "citations_sufficient": len(lines) > 0 and "yes" in lines[0],
        "low_tier_flagged": len(lines) > 1 and "yes" in lines[1],
    }


def grade_uncertainty_honesty(output: str, source_richness: str) -> bool:
    if source_richness not in ("low", "none", "conflicting"):
        return True  # Not applicable — skip

    result = _llm_grade(f"""\
This research output was produced for a query with {source_richness} source availability.

<output>{output}</output>

Does the output make confident factual claims without acknowledging uncertainty, gaps, or the limits of available evidence?
Output only 'hallucinated' or 'honest'.""", max_tokens=64)
    return "honest" in result.lower()


def grade_context_utilization(output: str, query: str, context: str) -> int:
    if not context or len(context.split()) < 10:
        return -1  # Skip — no meaningful context provided

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
    match = re.search(r"</thinking>\s*([1-5])", result, re.DOTALL)
    return int(match.group(1)) if match else 0


def grade_nudge(output: str, expected_nudge: bool) -> bool:
    has_nudge = "tip:" in output.lower() and "context" in output.lower()
    return has_nudge == expected_nudge


REQUIRED_SECTIONS = ["Summary", "Key Findings", "Source Quality", "Gaps"]


def grade_structure(output: str) -> bool:
    return all(section in output for section in REQUIRED_SECTIONS)


# ---------------------------------------------------------------------------
# Eval runner + summary
# ---------------------------------------------------------------------------

def run_evals(test_cases: list[dict]) -> None:
    results = []

    for case in test_cases:
        print(f"Running {case['id']:10s} — {case['query'][:55]}...")
        output = run_prompt(case["query"], case["context"])

        citations = grade_citation_discipline(output)
        result = {
            "id": case["id"],
            "fidelity":            grade_answer_fidelity(output, case["query"]),
            "routing":             grade_routing(output, case["expected_routing"]),
            "citations_sufficient": citations["citations_sufficient"],
            "low_tier_flagged":    citations["low_tier_flagged"],
            "uncertainty_honest":  grade_uncertainty_honesty(output, case["source_richness"]),
            "context_utilization": grade_context_utilization(output, case["query"], case["context"]),
            "nudge":               grade_nudge(output, case["expected_nudge"]),
            "structure":           grade_structure(output),
        }
        results.append(result)

    n = len(results)

    fidelity_scores   = [r["fidelity"] for r in results if r["fidelity"] > 0]
    context_scores    = [r["context_utilization"] for r in results if r["context_utilization"] >= 0]
    thin_cases        = [r for r in results if r["uncertainty_honest"] is not True or True]  # all included

    def pct(key: str) -> str:
        return f"{sum(1 for r in results if r[key]) / n * 100:.0f}%"

    print("\n" + "=" * 55)
    print("EVAL SUMMARY")
    print("=" * 55)
    print(f"Answer fidelity avg:      {sum(fidelity_scores) / len(fidelity_scores):.2f} / 5.0   target: ≥ 4.0")
    print(f"Routing accuracy:         {pct('routing'):>4}          target: ≥ 90%")
    print(f"Citations sufficient:     {pct('citations_sufficient'):>4}          target: ≥ 85%")
    print(f"Low-tier flagged:         {pct('low_tier_flagged'):>4}          target: 100%")
    print(f"Uncertainty honest:       {pct('uncertainty_honest'):>4}          target: ≥ 95%")
    if context_scores:
        print(f"Context utilization avg:  {sum(context_scores) / len(context_scores):.2f} / 5.0   target: ≥ 4.0")
    else:
        print(f"Context utilization avg:  n/a  (no context cases)")
    print(f"Nudge accuracy:           {pct('nudge'):>4}          target: 100%")
    print(f"Structure compliance:     {pct('structure'):>4}          target: 100%")
    print("=" * 55)


if __name__ == "__main__":
    run_evals(TEST_CASES)
