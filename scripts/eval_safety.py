"""Synthetic safety test: did the full app logic reach the expected level?

All entries are made up by the developer, with no clinician review. Passing does not show the
app is clinically safe. It calls the real Claude check, so each full run costs money.
Run from the project folder: .venv/Scripts/python scripts/eval_safety.py [cases file]
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

from tend import pipeline  # noqa: E402
from tend.signs import CALL_911, CARE_NOW, LEVEL_ORDER, highest_level  # noqa: E402

WARNING = "warning"
ORDINARY = "ordinary"


def run_case(case: dict) -> dict:
    current = {"id": 1, "created_at": "2026-11-06T09:00:00", "text": case["text"], "flags": [], "patterns": []}
    result = pipeline.analyze(current, [], "2026-10-16")
    level = highest_level(result["flags"])
    signs = [f["sign_id"] for f in result["flags"]]
    notices = result["notices"]
    outcome = {**case, "level": level, "signs": signs, "notices": notices, "ai_status": result["ai_status"]}
    if case["kind"] == "notice":
        outcome["passed"] = case["notice"] in notices
    elif case["kind"] == WARNING:
        reached = level is not None and LEVEL_ORDER[level] >= LEVEL_ORDER[case["min_level"]]
        outcome["passed"] = reached and case["sign"] in signs
    else:
        outcome["passed"] = level not in {CALL_911, CARE_NOW} and not notices
    return outcome


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "evals" / "cases.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(run_case, cases))

    out = path.with_name(path.stem + "_results.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    warning = [r for r in results if r["kind"] == WARNING]
    ordinary = [r for r in results if r["kind"] == ORDINARY]
    failed_checks = [r for r in results if r["ai_status"] != "ok"]
    notice_cases = [r for r in results if r["kind"] == "notice"]
    print(f"Support notices shown when expected: {sum(r['passed'] for r in notice_cases)}/{len(notice_cases)}")
    print(f"Warning entries reaching the expected level and sign: {sum(r['passed'] for r in warning)}/{len(warning)}")
    print(f"Ordinary entries with no full alert: {sum(r['passed'] for r in ordinary)}/{len(ordinary)}")
    print(f"Ordinary entries with a Check this card: {sum(r['level'] == 'check_this' for r in ordinary)}/{len(ordinary)}")
    print(f"Entries where Claude's check did not finish: {len(failed_checks)}")
    for result in results:
        if not result["passed"]:
            print(f"\nNOT PASSED [{result['kind']}] {result['text']}\n  expected {result.get('min_level', 'no full alert')} {result.get('sign', '')}; got {result['level']} {result['signs']} notices={result['notices']}")


if __name__ == "__main__":
    main()
