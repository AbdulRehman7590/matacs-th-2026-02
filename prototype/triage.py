"""Proposal triage prototype for MATACS-TH-2026-02.

AI reads, code decides:
  1. Extract facts per proposal with the PROMPTS.md extraction prompt (or load cached JSON with --offline).
  2. Verify evidence quotes against the source text when it is available.
  3. Apply mandatory gates, hard limits and the admin's scoring rules from criteria.json.
  4. Write out/ranking.json and an append-only out/audit.jsonl.

Usage:
  python triage.py --offline            # uses extractions/*.json, no API key needed
  python triage.py                      # calls the model for each samples/<letter>.txt
  python triage.py --offline --check    # also compare with ../ranking.json
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROMPT_VERSION = "extract-v1"
LETTERS = ["A", "B", "C", "D", "E"]

INJECTION_PATTERNS = [
    r"rank (it|this|us) first", r"full marks", r"automated review", r"ignore (all|any|previous)",
    r"pre-?approved", r"note to (the )?(ai|model|reviewer|system)",
]
NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty".split())}


# ---------- prompts (single source of truth: PROMPTS.md) ----------

def load_prompt_blocks():
    """Return the fenced blocks of 'Prompt 1' in PROMPTS.md: system, user, criteria example, schema."""
    text = (ROOT / "PROMPTS.md").read_text(encoding="utf-8")
    section = text.split("## Prompt 1", 1)[1].split("## Prompt 2", 1)[0]
    blocks = re.findall(r"```(?:json)?\r?\n(.*?)```", section, flags=re.S)
    system, user, _criteria_example, schema = blocks[:4]
    return system.strip(), user.strip(), schema.strip()


def render_criteria(criteria):
    lines = [f"- [MANDATORY] {c['name']}: {c['description']}." for c in criteria["mandatory"]]
    lines += [f"- [WEIGHTED {c['weight']}%] {c['name']}: {c['description']}." for c in criteria["weighted"]]
    return "\n".join(lines)


# ---------- extraction ----------

def extract_live(letter, text, criteria, model):
    import anthropic
    system, user_tpl, schema = load_prompt_blocks()
    user = (user_tpl
            .replace("{{category_name}}", criteria["category"])
            .replace("{{project_context}}", criteria["project_context"])
            .replace("{{criteria_list}}", render_criteria(criteria))
            .replace("{{output_schema}}", schema)
            .replace("{{proposal_text}}", text))
    client = anthropic.Anthropic()
    for attempt in range(2):  # one retry on invalid JSON, then flag for manual entry
        msg = client.messages.create(model=model, max_tokens=2000, temperature=0,
                                     system=system, messages=[{"role": "user", "content": user}])
        raw = msg.content[0].text
        try:
            return json.loads(raw), raw
        except json.JSONDecodeError:
            continue
    return None, raw


def get(facts, path):
    node = facts
    for key in path.split("."):
        node = node.get(key) if isinstance(node, dict) else None
        if node is None:
            return None
    return node


def value(facts, path):
    fact = get(facts, path)
    return fact.get("value") if isinstance(fact, dict) else None


def iter_facts(node, prefix=""):
    for key, val in node.items():
        if isinstance(val, dict) and "value" in val:
            yield prefix + key, val
        elif isinstance(val, dict):
            yield from iter_facts(val, prefix + key + ".")


def verify_evidence(facts, text, flags):
    """Null out any fact whose quote is not verbatim in the source, or whose number is not in its quote."""
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()
    source = norm(text)
    for path, fact in iter_facts(facts):
        v, quote = fact.get("value"), fact.get("evidence_quote")
        if v is None:
            continue
        if not quote or norm(quote) not in source:
            flags.append(f"{path}: evidence quote not found in source, value discarded")
            fact["value"] = None
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            q = norm(quote).replace(",", "")
            n = int(v) if float(v).is_integer() else v
            words = [w for w, i in NUMBER_WORDS.items() if i == n]
            if str(n) not in q and not any(re.search(rf"\b{w}\b", q) for w in words) \
                    and not (n % 1_000_000 == 0 and f"{n // 1_000_000}m" in q):
                flags.append(f"{path}: number {n} not found in its quote")


def scan_injection(text):
    return [p for p in INJECTION_PATTERNS if re.search(p, text, flags=re.I)]


# ---------- rules: gates, flags, scoring ----------

def check_gates(facts, criteria):
    results = {}
    for gate in criteria["mandatory"]:
        vals = [value(facts, p) for p in gate.get("all_true", [])]
        mins = [(value(facts, p), m) for p, m in gate.get("min_values", {}).items()]
        if any(v is False for v in vals) or any(v is not None and v < m for v, m in mins):
            results[gate["id"]] = "fail"
        elif any(v is None for v in vals) or any(v is None for v, _ in mins):
            results[gate["id"]] = "unknown"
        else:
            results[gate["id"]] = "pass"
    return results


def collect_flags(facts, criteria, gates, flags):
    for item in facts.get("suspicious_content") or []:
        flags.append(f"suspicious content reported by extractor: {item}")
    for gid, result in gates.items():
        if result == "unknown":
            flags.append(f"mandatory gate '{gid}' could not be confirmed")
    for c in criteria["weighted"]:
        if c["method"] == "lower_better" and "limit" in c:
            v = value(facts, c["fact"])
            if v is None:
                flags.append(f"{c['id']}: required fact '{c['fact']}' not stated; limit {c['limit']} unverifiable")
            elif v > c["limit"]:
                flags.append(f"{c['id']}: {v} exceeds limit {c['limit']}")
        if "window_fact" in c:
            start = value(facts, c["window_fact"])
            earliest = criteria["as_of_year"] - c["window_years"]
            if start is not None and start < earliest:
                flags.append(f"{c['id']}: count runs from {start}, before the {earliest} window start")
    for path, fact in iter_facts(facts):
        if fact.get("confidence") == "low" and fact.get("value") is not None and not path.startswith("subcontracting"):
            flags.append(f"{path}: low-confidence extraction ({fact.get('notes')})")


def ratio_higher(v, cohort):
    best = max((x for x in cohort if x is not None), default=None)
    return 0.0 if v is None or not best else min(v / best, 1.0)


def ratio_lower(v, cohort, limit=None):
    if v is None or (limit is not None and v > limit):
        return 0.0
    best = min((x for x in cohort if x is not None and (limit is None or x <= limit)), default=None)
    return best / v if best else 0.0


def score(facts, criteria, cohort):
    """Return (total 0-100, breakdown). cohort = facts of all proposals that passed the gates."""
    breakdown, total = {}, 0.0
    for c in criteria["weighted"]:
        m = c["method"]
        if m == "higher_better":
            s = ratio_higher(value(facts, c["fact"]), [value(f, c["fact"]) for f in cohort])
        elif m == "lower_better":
            s = ratio_lower(value(facts, c["fact"]), [value(f, c["fact"]) for f in cohort], c.get("limit"))
        elif m == "composite":
            s = 0.0
            for part in c["parts"]:
                v = value(facts, part["fact"])
                if part["method"] == "cap":
                    p = 0.0 if v is None else min(v / part["cap"], 1.0)
                else:
                    p = ratio_higher(v, [value(f, part["fact"]) for f in cohort])
                s += part["share"] * p
        elif m == "checklist":
            s = sum(1 for p in c["facts"] if value(facts, p)) / len(c["facts"])
        else:
            raise ValueError(f"unknown scoring method {m}")
        points = c["weight"] * s
        breakdown[c["id"]] = {"criterion_score": round(100 * s, 2), "weighted_points": round(points, 2)}
        total += points
    return round(total, 1), breakdown


def reason(letter, status, rank, total, facts, gates, flags, breakdown):
    if status == "ineligible":
        failed = ", ".join(g for g, r in gates.items() if r == "fail")
        sub = value(facts, "subcontracting")
        return f"Fails mandatory gate(s): {failed}" + (f" ({sub})" if sub else "") + "."
    if status == "flagged":
        indicative = f" Indicative score if cleared: {total}." if total is not None else ""
        return "Held for human review: " + "; ".join(flags) + "." + indicative
    team = int(round(breakdown["team"]["criterion_score"] / 25))
    return (f"Rank {rank} · {total} · gates passed · experience {value(facts, 'experience.qualifying_installs_count')}"
            f" · price {value(facts, 'price_cad')} · {value(facts, 'completion_weeks')} weeks"
            f" · warranty {value(facts, 'panel_warranty_years')}/{value(facts, 'workmanship_warranty_years')} yrs"
            f" · team {team}/4")


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="use cached extractions/ instead of calling the model")
    ap.add_argument("--check", action="store_true", help="compare result with ../ranking.json")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    criteria_raw = (HERE / "criteria.json").read_text(encoding="utf-8")
    criteria = json.loads(criteria_raw)
    assert sum(c["weight"] for c in criteria["weighted"]) == 100, "weights must total 100"

    model = None
    if not args.offline:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        model = os.environ.get("MODEL")
        if not os.environ.get("ANTHROPIC_API_KEY") or not model:
            sys.exit("Set ANTHROPIC_API_KEY and MODEL in .env (see .env.example), or use --offline.")

    out_dir = HERE / "out"
    out_dir.mkdir(exist_ok=True)
    run = {"run_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "criteria_category": criteria["category"], "criteria_version": criteria["version"],
           "criteria_sha256": hashlib.sha256(criteria_raw.encode()).hexdigest(),
           "model": model or "cached", "prompt_version": PROMPT_VERSION, "proposals": {}}

    results = {}
    for letter in LETTERS:
        sample = HERE / "samples" / f"{letter}.txt"
        text = sample.read_text(encoding="utf-8") if sample.exists() else None
        flags, raw = [], None
        if args.offline:
            facts = json.loads((HERE / "extractions" / f"{letter}.json").read_text(encoding="utf-8"))
        else:
            if text is None:
                sys.exit(f"Missing {sample}. Paste proposal {letter}'s text there (git-ignored).")
            facts, raw = extract_live(letter, text, criteria, model)
            if facts is None:
                facts = {}
                flags.append("extraction returned invalid JSON twice; manual entry needed")
        if text is not None:
            if not args.offline:
                verify_evidence(facts, text, flags)
            flags += [f"injection keyword scan matched '{p}'" for p in scan_injection(text)]
        gates = check_gates(facts, criteria)
        collect_flags(facts, criteria, gates, flags)
        results[letter] = {"facts": facts, "gates": gates, "flags": flags, "raw": raw,
                           "source_sha256": hashlib.sha256(text.encode()).hexdigest() if text else None}

    cohort_letters = [k for k, r in results.items() if "fail" not in r["gates"].values()]
    cohort = [results[k]["facts"] for k in cohort_letters]
    for letter, r in results.items():
        if letter not in cohort_letters:
            r["status"], r["score"], r["breakdown"] = "ineligible", None, None
            continue
        r["score"], r["breakdown"] = score(r["facts"], criteria, cohort)
        r["status"] = "flagged" if r["flags"] else "ranked"

    def tie_key(k):
        tb = [value(results[k]["facts"], p) for p in criteria["tie_break"]]
        return (-results[k]["score"], *[(x if x is not None else float("inf")) for x in tb])

    ranked = sorted([k for k, r in results.items() if r["status"] == "ranked"], key=tie_key)
    order = ranked + [k for k in LETTERS if results[k]["status"] == "flagged"] \
        + [k for k in LETTERS if results[k]["status"] == "ineligible"]

    ranking = []
    for letter in order:
        r = results[letter]
        rank = ranked.index(letter) + 1 if letter in ranked else None
        ranking.append({
            "proposal": letter, "rank": rank, "status": r["status"],
            "score": r["score"] if r["status"] == "ranked" else None,
            "reason": reason(letter, r["status"], rank, r["score"], r["facts"], r["gates"], r["flags"], r["breakdown"]),
        })
        run["proposals"][letter] = {k: r[k] for k in ("source_sha256", "gates", "flags", "status", "score", "breakdown", "facts", "raw")}

    (out_dir / "ranking.json").write_text(json.dumps(ranking, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (out_dir / "audit.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(run, ensure_ascii=False) + "\n")

    print(f"{'Prop':<5}{'Status':<12}{'Rank':<6}{'Score':<7}Reason")
    for row in ranking:
        print(f"{row['proposal']:<5}{row['status']:<12}{str(row['rank'] or '-'):<6}{str(row['score'] or '-'):<7}{row['reason']}")
    print(f"\nWrote {out_dir / 'ranking.json'} and appended to {out_dir / 'audit.jsonl'}")

    if args.check:
        expected = json.loads((ROOT / "ranking.json").read_text(encoding="utf-8"))
        key = lambda rows: {r["proposal"]: (r["rank"], r["status"], r["score"]) for r in rows}
        if key(expected) == key(ranking):
            print("CHECK OK: matches ../ranking.json (rank, status, score)")
        else:
            print("CHECK FAILED:\n expected", key(expected), "\n got     ", key(ranking))
            sys.exit(1)


if __name__ == "__main__":
    main()
