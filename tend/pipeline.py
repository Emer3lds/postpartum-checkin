"""Turn one entry into flags and patterns. The safety rules live here, in plain code.

- Word matching always runs, so a failed Claude call cannot hide a matched sign.
- Claude can add signs and raise levels, but cannot remove a sign or lower a level.
- If Claude fails, every word match is treated as at least care_now.
- Every quote shown to her must really appear in what she wrote.
- The alert, follow-up, and script wording are fixed; Claude does not write them.
"""

import logging
import re
from datetime import date

from .claude_check import check_entry
from .signs import (
    CARE_NOW,
    FOLLOW_UPS,
    LEVEL_ORDER,
    SIGN_IDS,
    SIGN_NAMES,
    SIGNS,
    highest_level,
    minimum_level,
    word_flags,
)

log = logging.getLogger("tend")

GENERIC_PATTERN_TITLE = "This keeps coming up in your check-ins"
_SOURCES = {s["id"]: s["source"] for s in SIGNS}

# Pattern titles are the only free text from Claude that she sees.
_BLOCKED_TITLE = re.compile(
    r"diagnos|eclampsia|depress|psychosis|anxiety disorder|infection|sepsis|embol|thrombo|"
    r"cardiomyopath|an(a)?emia|stroke|hemorrhage|hypertension|blood pressure|"
    r"you('| a)re (ok|okay|fine)|nothing|normal|common|don'?t worry|no need|\bwait\b|probably|"
    r"\bmild\b|harmless|\b1 day\b|\bone day\b",
    re.IGNORECASE,
)


def _norm(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().casefold()


def quote_is_hers(quote: str, text: str) -> bool:
    return bool(quote.strip()) and _norm(quote) in _norm(text)


def safe_title(title: str) -> str:
    title = (title or "").strip()
    if not title or _BLOCKED_TITLE.search(title):
        return GENERIC_PATTERN_TITLE
    return title


def _raise_to(level: str, floor: str) -> str:
    return level if LEVEL_ORDER[level] >= LEVEL_ORDER[floor] else floor


def merge_flags(text: str, hits: dict[str, dict], claude_signs: list[dict], ai_ok: bool) -> list[dict]:
    """Combine both checks. Anything either one found stays flagged."""
    merged: dict[str, dict] = {}
    for sid, hit in hits.items():
        level = hit["level"] if ai_ok else _raise_to(hit["level"], CARE_NOW)
        merged[sid] = {"sign_id": sid, "quote": hit["quote"] or text, "level": level, "source": "words"}

    for sign in claude_signs:
        sid = sign.get("id")
        if sid not in SIGN_NAMES:
            continue
        quote = sign.get("quote", "")
        verified = quote.strip() if quote_is_hers(quote, text) else None
        floor = minimum_level(sid, verified or "")
        level = _raise_to(CARE_NOW, floor) if sign.get("fits_description", True) else floor
        if sid in merged:
            merged[sid]["source"] = "both"
            merged[sid]["level"] = _raise_to(merged[sid]["level"], level)
            if verified:
                merged[sid]["quote"] = verified
        else:
            merged[sid] = {"sign_id": sid, "quote": verified or text, "level": level, "source": "claude"}

    return sorted(merged.values(), key=lambda f: SIGN_IDS.index(f["sign_id"]))


def clean_claude_patterns(raw: list[dict], entries: list[dict]) -> list[dict]:
    by_id = {e["id"]: e for e in entries}
    cleaned = []
    for pattern in raw:
        evidence, seen = [], set()
        for item in pattern.get("evidence", []):
            entry = by_id.get(item.get("entry_id"))
            if entry is None or entry["id"] in seen:
                continue
            seen.add(entry["id"])
            quote = item.get("quote", "")
            evidence.append(
                {
                    "entry_id": entry["id"],
                    "quote": quote.strip() if quote_is_hers(quote, entry["text"]) else entry["text"],
                }
            )
        days = {by_id[item["entry_id"]]["created_at"][:10] for item in evidence}
        if len(days) < 2:  # a pattern must span different days
            continue
        cleaned.append(
            {
                "title": safe_title(pattern.get("title", "")),
                "sign_ids": [s for s in pattern.get("sign_ids", []) if s in SIGN_NAMES],
                "evidence": evidence,
            }
        )
    return cleaned


def repeated_sign_patterns(entries: list[dict], covered: set[str]) -> list[dict]:
    """Code-only backup: the same sign flagged on two or more different days."""
    patterns = []
    for sid in SIGN_IDS:
        if sid in covered:
            continue
        evidence, days = [], set()
        for entry in entries:
            for flag in entry.get("flags", []):
                if flag["sign_id"] == sid:
                    evidence.append({"entry_id": entry["id"], "quote": flag["quote"]})
                    days.add(entry["created_at"][:10])
        if len(days) >= 2:
            patterns.append(
                {
                    "title": f"Entries on {len(days)} days may relate to: {SIGN_NAMES[sid]}",
                    "sign_ids": [sid],
                    "evidence": evidence,
                }
            )
    return patterns


def analyze(current: dict, history: list[dict], birth_date: str | None, llm=check_entry) -> dict:
    """Return flags, patterns, and whether Claude's check completed."""
    hits = word_flags(current["text"])
    claude_signs, claude_patterns, ai_status = [], [], "ok"
    try:
        result = llm(current, history, birth_date)
        claude_signs = result.get("signs", [])
        claude_patterns = result.get("patterns", [])
    except Exception as exc:  # any failure must still leave her with the safe path
        log.warning("Claude check failed: %s", type(exc).__name__)
        ai_status = "unavailable"

    flags = merge_flags(current["text"], hits, claude_signs, ai_status == "ok")
    all_entries = history + [{**current, "flags": flags}]
    patterns = clean_claude_patterns(claude_patterns, all_entries)
    covered = {sid for p in patterns for sid in p["sign_ids"]}
    patterns += repeated_sign_patterns(all_entries, covered)
    return {"flags": flags, "patterns": patterns, "ai_status": ai_status}


def apply_follow_up(flags: list[dict], sign_id: str, answer: str) -> list[dict]:
    """Record her answer. Yes raises the level. No or unsure never lowers anything."""
    updated = []
    for flag in flags:
        if flag["sign_id"] == sign_id:
            flag = {**flag, "answer": answer}
            if answer == "yes":
                flag["level"] = _raise_to(flag["level"], CARE_NOW)
        updated.append(flag)
    return updated


def weeks_since(birth_date: str, today: date | None = None) -> int:
    today = today or date.today()
    return max(0, (today - date.fromisoformat(birth_date)).days // 7)


def build_script(flags: list[dict], birth_date: str | None, today: date | None = None) -> str:
    """Fixed wording plus her exact words. No model writes any part of this."""
    if not flags:
        return ""
    if birth_date:
        born = date.fromisoformat(birth_date)
        weeks = weeks_since(birth_date, today)
        when = "less than a week ago" if weeks == 0 else f"{weeks} week{'s' if weeks != 1 else ''} ago"
        opening = f"I gave birth on {born:%B} {born.day}, {born.year} ({when})."
    else:
        opening = "I gave birth within the last year."

    quotes = []
    for flag in flags:
        if flag["quote"] not in quotes:
            quotes.append(flag["quote"])
    words = "\n".join(f'"{q}"' for q in quotes)

    answers = "".join(
        f'\nWhen asked "{FOLLOW_UPS[f["sign_id"]]}" I answered yes.'
        for f in flags
        if f.get("answer") == "yes" and f["sign_id"] in FOLLOW_UPS
    )

    def names_from(source: str) -> str:
        return "; ".join(SIGN_NAMES[f["sign_id"]] for f in flags if _SOURCES[f["sign_id"]] == source)

    cdc, added = names_from("CDC"), names_from("AWHONN POST-BIRTH")
    relates = ""
    if cdc:
        relates += f"\n\nThese may relate to CDC urgent maternal warning signs: {cdc}."
    if added:
        relates += f"\n\nThese may relate to AWHONN post-birth warning signs: {added}."

    return (
        f"{opening} I need to be checked now.\n\n"
        f"In my own words:\n{words}{answers}{relates}\n\n"
        "Could this be related to my pregnancy?"
    )


def entry_level(flags: list[dict]) -> str | None:
    return highest_level(flags)
