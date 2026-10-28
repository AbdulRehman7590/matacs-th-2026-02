# Prototype (optional)

A small script that runs the design end to end on proposals A–E. The AI extracts facts; code checks them, applies the gates and scores. Its output matches [../ranking.json](../ranking.json).

| File | Purpose |
|---|---|
| [triage.py](triage.py) | The pipeline: extract → verify quotes → injection scan → gates → score → rank → audit log |
| [criteria.json](criteria.json) | The admin's criteria for the Solar category (gates, weights, limits, scoring method). Nothing is hard-coded in the script |
| [extractions/](extractions/) | Cached extraction results for A–E, so the scoring can be run without an API key |
| [requirements.txt](requirements.txt) | Python dependencies |
| [triage-flow.mmd](triage-flow.mmd) | Mermaid source of [../diagram/triage-flow.png](../diagram/triage-flow.png) |

The prompt is read straight from [../PROMPTS.md](../PROMPTS.md), so the script sends exactly what is documented there.

## Run

```
python -m venv .venv
.venv\Scripts\python -m pip install -r prototype/requirements.txt     # macOS/Linux: .venv/bin/python

# Offline: cached extractions, no API key needed; --check compares with ../ranking.json
.venv\Scripts\python prototype/triage.py --offline --check

# Live: calls the model for each proposal
copy .env.example .env        # then add ANTHROPIC_API_KEY
.venv\Scripts\python prototype/triage.py
```

Output: `prototype/out/ranking.json` and `prototype/out/audit.jsonl`, an append-only log with criteria hash, model, prompt version, facts, gates, scores and flags for every run.

## About the sample text
The brief asks that the sample proposals are not copied into the repository. So:
- The live mode reads each proposal from `prototype/samples/A.txt` … `E.txt`. This folder is git-ignored: paste the text from the brief there locally.
- The cached files in `extractions/` hold only the extracted **values**. Their `evidence_quote` fields are left empty, because quotes would be sample text.
- Quote verification (every quote must appear verbatim in the source) and the keyword injection scan run whenever the sample text is present. The offline demo relies on the extractor's `suspicious_content` field for C.
