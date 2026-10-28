# Design Write-up

Reference: MATACS-TH-2026-02 · Diagram: [diagram/triage-flow.png](diagram/triage-flow.png) · Prompts: [PROMPTS.md](PROMPTS.md) · Result: [ranking.json](ranking.json)

**Flow in short:**
1. The admin saves the criteria as a versioned set.
2. The reviewer uploads PDFs and picks a category.
3. **AI reads** each proposal into facts, each backed by a verbatim quote.
4. **Code** checks the quotes, applies the gates, calculates scores and sorts.
5. Anything doubtful is flagged, not guessed.
6. **A person** reviews, can override with a reason, and makes the award.
7. Everything is logged.

## 1. AI vs. rules

| Step | Done by |
|---|---|
| Criteria setup, weights must total 100% | Admin screen + code |
| PDF → text | Code |
| Proposal text → facts (price, weeks, licence holder…) | **AI** |
| Check every AI quote exists in the PDF | Code |
| Injection scan | Code keyword scan **and** AI reports suspicious text |
| Mandatory gates, budget and 16-week limits | Code |
| Scores, ranking, status | Code |
| One-line reason | Code template (AI may smooth wording only) |
| Review, overrides, award | Human |

**Why:** proposals are free-form writing, and turning them into facts is what AI does well. The rest is checking and arithmetic, which code does identically every time, can be tested, and can't be persuaded. An AI that scores could be swayed by confident writing or a planted instruction (Proposal C). An AI that only extracts quoted facts gives it little to work with.

## 2. Consistency and explainability
- **Repeatable:**
  - Temperature 0, pinned model and versioned prompt.
  - JSON schema output.
  - Extraction cached by file hash + prompt + model.
  - Scoring is pure arithmetic.
  - Ranked twice, the result is identical. Before a model or prompt upgrade, past proposals are re-run and any differences reviewed.
- **Explainable:** each proposal shows:
  - gate results;
  - each criterion's score, formula and input fact;
  - **the PDF quote behind each fact**;
  - any flags.

  Example: A's price score of 97.1 = lowest eligible price 231,000 ÷ A's 238,000.

**Scoring rules** (admin-editable), normalised against proposals passing the gates:
- Experience: installs ÷ best count
- Price: lowest ÷ this (0 if over the ceiling)
- Timeline: shortest ÷ this (0 if over 16 weeks or missing)
- Warranty: half panel years ÷ 25, half workmanship ÷ best
- Team: 25 points each for named lead, crew, safety plan and monitoring

| | Status | Score | Why |
|---|---|---|---|
| A | Rank 1 | 98.0 | Best experience, fastest, complete team |
| E | Rank 2 | 84.8 | Best warranty and monitoring, fewest installs |
| C | Flagged | (77.1) | Instruction aimed at automated reviewers. "Since 2020" may exceed the 5-year window |
| D | Flagged | (69.8) | No timeline, so the 16-week limit is unverifiable |
| B | Ineligible | – | The bidder holds no licence. A subcontractor is "to be confirmed" |

B's lowest price is irrelevant once it fails a gate. C and D aren't zeroed but held for a person: one is possible misconduct, the other missing information the bidder can supply. Bracketed scores are indicative only.

## 3. Human in the loop
**Checkpoints:**
1. **Admin** publishes criteria, which creates a new version.
2. **Reviewer, flag queue:** each flagged or ineligible proposal needs a decision: uphold, clear (e.g. D supplies a timeline) or correct a fact. Corrections re-run scoring.
3. **Reviewer sign-off:** confirm the list or move a proposal. A written reason is required.
4. **Award:** always human. The tool only recommends.

**Audit log (append-only):**
- user, time, file hashes, criteria version, model and prompt version
- raw AI output, verified facts with quotes, gate results, scores, flags
- every human action, with before/after and the reason

Any result can be reproduced from the log.

## 4. Changing criteria
- Criteria are never edited in place. Saving creates **version 2**, and earlier runs stay tied to version 1, so old results remain reproducible.
- The run shows "scored under v1, newer version exists" with a **re-score** button.
- Weight changes re-run only the arithmetic, which is instant and free.
- A new criterion needing a new fact re-extracts only that fact.
- One ranking never mixes versions.
- Mid-evaluation edits are logged and visible, because changing weights after seeing bids is a fairness concern.

## 5. Risks and safeguards

| Risk | Safeguard |
|---|---|
| **Wrong extraction** | Every fact needs a quote. Code verifies the quote and re-reads numbers from it, and the reviewer sees it. A "held by bidder" field catches B-style subcontracting. |
| **Made-up facts** | `null` when not stated. A quote not found in the PDF is discarded and flagged. Missing facts (D) are flagged, never guessed. |
| **Manipulation / injection** (C) | Proposal text is wrapped as untrusted data, and the AI reports instructions rather than following them. A separate keyword scan doesn't rely on the AI. The AI never scores, so "full marks" has nothing to act on. |
| **Bias** (polish, brand names) | Scores come only from facts and fixed formulas. Names can be hidden during review. |
| **Vague wording** ("to be confirmed", "since 2020") | Low-confidence facts are flagged. |
| **Bad PDFs** | OCR fallback. Little text → manual-entry flag. |
| **Cost / outage** | One cached small-model call per proposal. Re-scoring needs no AI, and facts can be entered manually. |
| **Over-trust** | Labelled "recommended ranking". Award needs human sign-off. |

## Assumptions
- "Last 5 years" = 2021–2026.
- Prices are all-in CAD.
- A missing timeline is flagged, not ineligible, because it's a weighted criterion the bidder can clarify.
- Embedded instructions are flagged, not disqualified, because disqualification is a human procurement decision.
