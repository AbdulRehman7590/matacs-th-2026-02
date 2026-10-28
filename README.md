# AI Proposal Triage: Design

| | |
|---|---|
| **Name** | TODO: your full name |
| **Reference** | MATACS-TH-2026-02 |
| **Time actually spent** | TODO: e.g. 1 h 30 min |

## Files
- [WRITEUP.md](WRITEUP.md): answers to the five questions, with the scoring rules and the result on the sample set
- [diagram/triage-flow.png](diagram/triage-flow.png): process flow from upload to ranked output. AI steps, rule steps and human checkpoints are colour-coded
- [PROMPTS.md](PROMPTS.md): the extraction prompt and output schema exactly as sent, plus an optional reason-wording prompt
- [ranking.json](ranking.json): expected ranking of proposals A–E
- [prototype/](prototype/) (optional): a script that runs the prompt and scoring rules on the samples ([prototype/README.md](prototype/README.md))
- [.env.example](.env.example): environment variables for the prototype (no keys committed)

## The design in one line
AI only **reads** proposals into facts backed by quotes. Plain code **checks and scores** them using the admin's criteria. A **person** reviews flags, can override with a reason, and makes the award. Every step is logged.

**Result:**
1. A (98.0)
2. E (84.8)

C is **flagged** for an embedded instruction aimed at automated reviewers. D is **flagged** because it gives no timeline. B is **ineligible** because the bidder holds no electrical licence.

## How I used AI tools
I used Claude Code to read the brief, draft the design, write the prompt, the write-up and the prototype, and render the diagram. I then reviewed and checked every output against the brief. TODO: describe at least one place where you disagreed with or corrected the AI's output, and why.
