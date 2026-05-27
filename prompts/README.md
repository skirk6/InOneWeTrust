# Prompts

A library of structured LLM prompts, each paired with an automated evaluation suite.

---

## Convention

Each prompt lives in its own folder:

```
prompts/
  <topic>/
    prompt.md   # human-readable spec — template, variables, success criteria
    eval.py     # automated evaluation against the spec's success criteria
```

`eval.py` loads the prompt body from `prompt.md` at runtime, so the spec is the single source of truth — no drift between what the docs say and what the eval grades.

---

## Available Prompts

| Folder | Purpose |
|---|---|
| [`web-research/`](web-research/) | General-purpose research with source-tier discipline (Tier 1–4) and specialist-prompt routing for domain-specific queries. |

---

## Running an Eval

```bash
pip install anthropic
export ANTHROPIC_API_KEY=your-key
python prompts/web-research/eval.py
```

Output is a per-criterion scorecard against the success targets defined in the prompt's spec.

---

> Part of [In One We Trust](https://www.inonewetrust.com) — Faith · Code · Depth
