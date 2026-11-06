# Tend

Tend is a demo check-in app for mothers in the year after giving birth. She speaks or types about her day. Tend keeps a dated history, points out possible urgent warning signs, notices what keeps coming back, and gives her words to say when she seeks care.

Built for a women's health hackathon challenge: helping women get the care and information they need.

> **Demo only. Not a medical device and no clinician has reviewed it.** Don't enter real health information. In an emergency, call 911.

## What it does

- **Check-ins:** Speak (in Chrome) or type an entry.
- **Call 911 and Get care now:** Fixed alerts when her words clearly describe an urgent warning sign.
- **Check this:** A calm card with a fixed follow-up question when an entry might relate to a sign. A "yes" starts the full alert.
- **Everyday entries:** Common new-parent experiences with no warning details are saved without a card, and repeats can still become a pattern.
- **Support notices:** Fixed cards point her to her baby's doctor for a worry about the baby, and to the National Domestic Violence Hotline for a safety concern at home.
- **Words to say:** A script built from fixed wording and her exact words.
- **Pattern catch:** Points out topics that repeat across different days.
- **Clinician summary:** A printable page with her entries, flagged signs, and patterns.
- **Accounts:** Simple login, with each person seeing only their own entries.

## How safety works

Claude Sonnet 5.5 reads each entry, but plain code makes the final safety decisions:

- Word matching always runs. Clear word matches can't be lowered by Claude. Claude can quiet only a weak match, which stays on record for pattern checks.
- A tentative link from Claude becomes a question, not a full alert.
- If Claude's check fails, word matches are raised to a full alert and she's told the full check didn't finish. A baby's symptom shows the baby notice instead, unless it matches a call-911 sign.
- Claude doesn't write the alert, follow-up, or script wording.
- Quotes are checked against what she wrote. If one doesn't match, the app shows her own text.
- Pattern titles are the only Claude-written text she sees. Titles that diagnose or reassure are replaced.
- The app never tells her she's okay. A missed day or a "no" answer doesn't clear a flag.

Sources: [CDC urgent maternal warning signs](https://www.cdc.gov/hearher/maternal-warning-signs/index.html) (the 15 signs and their descriptions) and AWHONN POST-BIRTH warning signs (the call-911 group, seizures, and incisions, read from [a copy of the handout hosted by a health care organization](https://www.kvhealthcare.org/wp-content/uploads/2023/12/PBWSSaveYourLifeHandout_English.pdf)). Sorting signs into these levels was our own decision. Baby fever wording follows the [American Academy of Pediatrics](https://www.healthychildren.org/English/health-issues/conditions/fever/Pages/Fever-and-Your-Baby.aspx), and hotline details come from the [National Domestic Violence Hotline](https://www.thehotline.org/get-help/).

## Testing

- `tests/test_safety.py` checks the safety rules and account privacy without using the API.
- `scripts/eval_safety.py` runs made-up entries through the real Claude check and uses API credits. Results are in `evals/`.

These entries were written by the developer. They are a small check, not evidence of clinical safety, and the word rules can still miss signs or raise false alarms.

## Run it

Requires Python 3.10 or newer. On Windows:

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

Add your Anthropic API key to `.env`, then start the app and open http://localhost:8000:

```bash
.venv\Scripts\python -m uvicorn main:app --port 8000
```

Select **Try the demo account** to see made-up check-ins. Opening it again resets that account.

On Mac or Linux, use `python3 -m venv .venv`, `.venv/bin/python` in place of `.venv\Scripts\python`, and `cp` in place of `copy`.

To run the tests:

```bash
.venv\Scripts\python -m pytest tests
```

## Privacy and limits

- Entries and accounts are stored in a local SQLite file. Passwords are stored as salted hashes, but the data file isn't encrypted.
- Entry text is sent to Anthropic for the Claude check. Chrome's voice input may send audio to Google.
- A real version would need hosted encrypted connections, password reset, stronger data protection, a health privacy review, and clinical review.
- Emergency numbers and guidance are for the US.
- Daily reminders and quick exit aren't built yet.
