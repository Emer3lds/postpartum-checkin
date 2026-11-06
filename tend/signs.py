"""Warning signs, alert levels, fixed follow-up questions, and word matching.

Sources:
- CDC Hear Her urgent maternal warning signs:
  https://www.cdc.gov/hearher/maternal-warning-signs/index.html
- AWHONN POST-BIRTH warning signs (the call-911 group, and seizures).

Levels, from highest to lowest:
- call_911: any mention of a sign in the POST-BIRTH call-911 group.
- care_now: her words fit the CDC's description of a sign.
- check_this: she mentions something related, but not the CDC's description.

No clinician has reviewed these levels. This is a demo.
"""

import re

CALL_911 = "call_911"
CARE_NOW = "care_now"
CHECK_THIS = "check_this"
LEVEL_ORDER = {CHECK_THIS: 0, CARE_NOW: 1, CALL_911: 2}

SIGNS = [
    {"id": "headache", "name": "Headache that won't go away or gets worse over time", "source": "CDC"},
    {"id": "dizziness", "name": "Dizziness or fainting", "source": "CDC"},
    {"id": "vision", "name": "Changes in your vision", "source": "CDC"},
    {"id": "fever", "name": "Fever of 100.4°F or higher", "source": "CDC"},
    {"id": "swelling_hands_face", "name": "Extreme swelling of your hands or face", "source": "CDC"},
    {"id": "harm_thoughts", "name": "Thoughts about harming yourself or your baby", "source": "CDC"},
    {"id": "breathing", "name": "Trouble breathing", "source": "CDC"},
    {"id": "chest_heart", "name": "Chest pain or fast-beating heart", "source": "CDC"},
    {"id": "nausea_vomiting", "name": "Severe nausea and throwing up", "source": "CDC"},
    {"id": "belly_pain", "name": "Severe belly pain that doesn't go away", "source": "CDC"},
    {"id": "baby_movement", "name": "Baby's movement stopping or slowing during pregnancy", "source": "CDC"},
    {"id": "bleeding_during", "name": "Vaginal bleeding or fluid leaking during pregnancy", "source": "CDC"},
    {"id": "bleeding_after", "name": "Vaginal bleeding or discharge after pregnancy", "source": "CDC"},
    {"id": "limb", "name": "Severe swelling, redness, or pain of your leg or arm", "source": "CDC"},
    {"id": "tiredness", "name": "Overwhelming tiredness", "source": "CDC"},
    {"id": "seizure", "name": "Seizures", "source": "AWHONN POST-BIRTH"},
]

SIGN_IDS = [s["id"] for s in SIGNS]
SIGN_NAMES = {s["id"]: s["name"] for s in SIGNS}

# Any mention of these goes straight to call 911, whatever anything else says.
ALWAYS_911 = {"harm_thoughts", "breathing", "chest_heart", "seizure"}
# These are only relevant if she is pregnant, and always need care right away.
ALWAYS_CARE_NOW = {"baby_movement", "bleeding_during"}

# Fixed wording, based on the CDC's description of each sign. Yes moves the flag to care_now.
FOLLOW_UPS = {
    "headache": "Has it stayed or gotten worse, even after medicine or fluids, or did it start suddenly?",
    "dizziness": "Did you faint, or does the lightheadedness keep going or keep coming back?",
    "vision": "Are you seeing flashes, bright spots, or blind spots, or is your vision blurry or double?",
    "fever": "Is your temperature 100.4°F or higher?",
    "swelling_hands_face": "Is it hard to bend your fingers, wear your rings, or fully open your eyes, or are your lips or mouth swollen or numb?",
    "nausea_vomiting": "Are you unable to keep fluids down, or is this much worse than an upset stomach?",
    "belly_pain": "Is the pain sharp or cramping, and has it stayed, started suddenly, or gotten worse?",
    "bleeding_after": "Are you soaking one or more pads in an hour, passing clots bigger than an egg or tissue, or noticing discharge that smells bad?",
    "limb": "Do you have swelling, pain, warmth, or redness in a leg or arm?",
    "tiredness": "Is this sudden or severe tiredness or weakness that rest doesn't help, or are you too tired to care for your baby?",
}

_LIMB = r"(legs?|calf|calves|thighs?|arms?)"
_LIMB_SYMPTOM = r"(swell\w*|swollen|red\b|redness|pain\w*|hurt\w*|warm|hot|sore|ach\w*|tender)"
_BELLY = r"(belly|stomach|abdomen|abdominal|tummy|pelvi\w*|uterus|womb|incision|c-?section)"
_BELLY_SYMPTOM = r"(pain\w*|hurt\w*|ach\w*|cramp\w*|stabbing|sharp)"
_NEAR = r"\W+(?:\w+\W+){0,4}"

# Word matching for each sign. It deliberately catches more than it should.
_MENTION = {
    "headache": r"head\s?aches?|migraine|my head (hurts|is pounding|is killing|aches|won't stop)|pounding head|head (is )?pounding",
    "dizziness": r"dizz\w*|faint\w*|passed out|pass out|light[- ]?head\w*|blacked out|black out|spinning|woozy|vertigo|memory gap",
    "vision": r"blurr\w*|double vision|seeing (\w+ )?(spots|stars|flashes|double)|\bspots\b|flashing lights?|flashes|blind spots?|can't see|vision|floaters",
    "fever": r"fever\w*|100\.[4-9]|10[1-5](\.\d)?\s?(°|degrees?|f\b)|temperature|\btemp\b|chills|burning up",
    "swelling_hands_face": r"(hands?|fingers?|face|lips?|eyes?|mouth)\W+(?:\w+\W+){0,4}(swell\w*|swollen|puff\w*)|(swell\w*|swollen|puff\w*)\W+(?:\w+\W+){0,4}(hands?|fingers?|face|lips?|eyes?|mouth)|\bpuffy\b|rings? (\w+ )?(don't|won't|doesn't|do not|does not)\b|rings? (\w+ ){0,2}(tight|snug)|can't (bend|close) my fingers|can't open my eyes|numb (lips?|mouth)",
    "harm_thoughts": (
        r"(harm|hurt|kill)(ing)? myself|(harm|hurt|kill|shak|shake|smother|drown)(ing)? (my|the) baby"
        r"|suicid\w*|end (it all|my life)|want to die|wish i (was|were) dead"
        r"|don't want to (be here|live|wake up|be alive)|better off without me|can't (go on|do this anymore)"
        r"|hopeless\w*|no way out|scary thoughts|intrusive thoughts|bad thoughts|dark thoughts"
    ),
    "breathing": r"(trouble|hard|difficult\w*|can't|cannot|struggling( to)?) (\w+ )?(breath\w*|catch my breath)|short(ness)? of breath|out of breath|breathless|wheez\w*|gasp\w*|tight (throat|chest)|(throat|chest) (feels? |is |was )?tight\w*|prop(ped)? up on pillows",
    "chest_heart": r"chest (pain\w*|hurt\w*|ach\w*|pressure|tight\w*)|pain in my chest|heart\w* (\w+ )?(rac\w*|pound\w*|fast|flutter\w*|skip\w*)|palpitations?|racing heart|fast heart\w*",
    "nausea_vomiting": r"throw\w* up|threw up|vomit\w*|nause\w*|puk\w*|can't keep (\w+ )?(down|food|water|fluids)|sick to my stomach",
    "belly_pain": rf"{_BELLY}{_NEAR}{_BELLY_SYMPTOM}|{_BELLY_SYMPTOM}{_NEAR}{_BELLY}|cramp\w*",
    "baby_movement": r"baby (\w+ )?(isn't|is not|not|stopped|hasn't|has not) (\w+ )?mov\w*|(less|fewer|no) (movement|kicks?)|stopped kicking",
    "bleeding_during": r"\bpregnant\b.*(bleed\w*|leak\w*|fluid|discharge|spotting)|(bleed\w*|leak\w*|fluid|discharge|spotting).*\bpregnant\b",
    "bleeding_after": r"bleed\w*|\bblood\b|soak\w*|clots?\b|discharge|hemorrhag\w*|gush\w*|foul|(smell\w*|stink\w*|odou?r)\W+(?:\w+\W+){0,6}(down there|pads?|blood|vagina\w*)|(pads?|blood|down there|vagina\w*)\W+(?:\w+\W+){0,6}(smell\w*|stink\w*|odou?r)",
    "limb": rf"{_LIMB}{_NEAR}{_LIMB_SYMPTOM}|{_LIMB_SYMPTOM}{_NEAR}{_LIMB}",
    "tiredness": r"exhaust\w*|so tired|too tired|really tired|extremely tired|very tired|fatigue\w*|no energy|can't get out of bed|wiped|drained|\bweak\b|weakness|so sad|sadness|can't stop crying|crying all|feel numb",
    "seizure": r"seizures?|convuls\w*",
}

# Words that fit the CDC's description closely enough that the level starts at care_now.
_DESCRIPTION = {
    "headache": r"(won't|doesn't|not|isn't|hasn't|didn't) (\w+ ){0,3}(go away|going away|gone away|stop|better|help|touch)|even after|worse|worst|sudden\w*|severe|days? (now|straight|in a row)",
    "dizziness": r"faint\w*|passed out|pass out|blacked out|black out|memory gap",
    "vision": r"blurr\w*|double|spots|flash\w*|can't see|lost my vision",
    "fever": r"100\.[4-9]|10[1-5](\.\d)?\s?(°|degrees?|f\b)",
    "swelling_hands_face": r"rings? (\w+ )?(don't|won't|doesn't|do not|does not)\b|can't (bend|close) my fingers|can't open my eyes|numb (lips?|mouth)|lips? (\w+ )?(swollen|swell\w*)",
    "nausea_vomiting": r"can't keep (\w+ )?(down|food|water|fluids)|severe|nonstop|non-stop|keeps? (throwing|vomiting)",
    "belly_pain": r"sharp|stabbing|severe|won't go away|doesn't go away|worse|sudden\w*|keeps coming",
    "bleeding_after": r"soak\w*|clots?\b|tissue|foul|smell\w*|stink\w*|odou?r|heavy|hemorrhag\w*|gush\w*",
    "limb": r"swell\w*|swollen|warm|hot|\bred\b|redness",
    "tiredness": r"too tired|can't get out of bed|can't care|rest (doesn't|isn't|won't)|sudden\w*|severe|extreme\w*",
}

_FLAGS = re.IGNORECASE | re.DOTALL
MENTION = {sid: re.compile(p, _FLAGS) for sid, p in _MENTION.items()}
DESCRIPTION = {sid: re.compile(p, _FLAGS) for sid, p in _DESCRIPTION.items()}
PASSED_OUT = re.compile(r"faint(ed)?\b|passed out|pass out|blacked out|black out", _FLAGS)


def _normalize_apostrophes(text: str) -> str:
    return text.replace("’", "'").replace("‘", "'")


def sentence_containing(text: str, start: int, end: int) -> str:
    """Return the sentence around a match, in her exact words."""
    left = max(text.rfind(c, 0, start) for c in ".!?\n") + 1
    rights = [i for i in (text.find(c, end) for c in ".!?\n") if i != -1]
    right = (min(rights) + 1) if rights else len(text)
    return text[left:right].strip()


def minimum_level(sign_id: str, sentence: str = "") -> str:
    """The lowest level this mention may have. Claude may raise it, never lower it."""
    if sign_id in ALWAYS_911:
        return CALL_911
    if sign_id == "dizziness" and PASSED_OUT.search(sentence):
        return CALL_911
    if sign_id in ALWAYS_CARE_NOW:
        return CARE_NOW
    pattern = DESCRIPTION.get(sign_id)
    if pattern and pattern.search(_normalize_apostrophes(sentence)):
        return CARE_NOW
    return CHECK_THIS


def word_flags(text: str) -> dict[str, dict]:
    """Map each matched sign to the sentence that matched it and its minimum level."""
    searchable = _normalize_apostrophes(text)  # same length, so positions line up
    found = {}
    for sid, pattern in MENTION.items():
        match = pattern.search(searchable)
        if match:
            sentence = sentence_containing(text, match.start(), match.end())
            found[sid] = {"quote": sentence, "level": minimum_level(sid, sentence)}
    return found


def highest_level(flags: list[dict]) -> str | None:
    if not flags:
        return None
    return max((f["level"] for f in flags), key=LEVEL_ORDER.__getitem__)
