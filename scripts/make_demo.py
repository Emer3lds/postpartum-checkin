"""Run the sample mother's earlier check-ins through the real checks and save the results.

The demo account then shows real output without waiting on Claude for each old entry.
Run from the project folder: .venv/Scripts/python scripts/make_demo.py
"""

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

from tend import pipeline  # noqa: E402

BIRTH_DAYS_AGO = 21
ENTRIES = [
    (6, 15, "Slept maybe three hours. Little headache this afternoon, probably just no sleep. Baby fed well though."),
    (4, 14, "Little headache again after lunch. My rings feel snug today, I figured it's the heat."),
    (2, 16, "Feeling kind of off. Another headache, so I drank some water. Mom came over to help with the baby."),
]
# Typed live in the video. Checked here, but not saved in the demo account.
LIVE_ENTRY = "Headache is back and Tylenol didn't touch it. My rings don't fit anymore and I keep seeing little spots."


def main() -> None:
    now = datetime.now()
    birth_date = (now - timedelta(days=BIRTH_DAYS_AGO)).date().isoformat()
    history, seed = [], []
    for entry_id, (days_ago, hour, text) in enumerate(ENTRIES, start=1):
        created = (now - timedelta(days=days_ago)).replace(hour=hour, minute=12, second=0, microsecond=0)
        current = {"id": entry_id, "created_at": created.isoformat(), "text": text, "flags": [], "patterns": []}
        result = pipeline.analyze(current, history, birth_date)
        if result["ai_status"] != "ok":
            raise SystemExit("Claude check did not finish. Check the API key in .env.")
        history.append({**current, **result})
        seed.append({"id": entry_id, "days_ago": days_ago, "hour": hour, "text": text, **result})
        print(entry_id, [f"{f['sign_id']}:{f['level']}" for f in result["flags"]], [p["title"] for p in result["patterns"]])

    (ROOT / "demo_seed.json").write_text(
        json.dumps({"birth_days_ago": BIRTH_DAYS_AGO, "entries": seed}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    current = {"id": 4, "created_at": now.isoformat(timespec="seconds"), "text": LIVE_ENTRY, "flags": [], "patterns": []}
    started = time.time()
    live = pipeline.analyze(current, history, birth_date)
    print(f"\nLIVE ({time.time() - started:.1f}s, Claude: {live['ai_status']})")
    print([f"{f['sign_id']}:{f['level']}" for f in live["flags"]])
    for pattern in live["patterns"]:
        print(pattern["title"], [e["entry_id"] for e in pattern["evidence"]])
    print("\n" + pipeline.build_script(live["flags"], birth_date))


if __name__ == "__main__":
    main()
