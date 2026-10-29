# AI Proposal Triage: Design

| | |
|---|---|
| **Name** | Abdul Rehman |
| **Reference** | MATACS-TH-2026-02 |
| **Time actually spent** | About 65–70 minutes |

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
I used Claude Code to draft the design, prompt, write-up and prototype, and to render the diagram; I reviewed and tested each output against the brief. I rejected its first plan and had it re-check every requirement before building, which caught that it had put the diagram's source file in `diagram/` (the brief allows exactly one image there) and had offered a ready-made "disagreement" for this section, which I removed because it must be genuine. Testing on the sample text also showed the prototype wrongly flagging D, because "in the last five years" doesn't literally contain 2021, so I had that check corrected.
