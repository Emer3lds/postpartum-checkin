"""Support notices for needs outside the mother's warning signs. All wording is fixed.

Sources:
- American Academy of Pediatrics, HealthyChildren.org (fever in babies 3 months or younger):
  https://www.healthychildren.org/English/health-issues/conditions/fever/Pages/Fever-and-Your-Baby.aspx
- National Domestic Violence Hotline: https://www.thehotline.org/get-help/
"""

import re

BABY_HEALTH = "baby_health"
HOME_SAFETY = "home_safety"
NOTICE_TYPES = [BABY_HEALTH, HOME_SAFETY]

NOTICES = {
    BABY_HEALTH: {
        "type": BABY_HEALTH,
        "title": "This sounds like it's about your baby",
        "body": (
            "This app can't check your baby's health. Call your baby's doctor now about what you wrote. "
            "If your baby is 3 months or younger with a temperature of 100.4°F or higher, call right away. "
            "If you think it's an emergency, call 911."
        ),
        "actions": [{"label": "Call 911", "tel": "911", "note": "If you think it's an emergency"}],
        "source": "American Academy of Pediatrics, HealthyChildren.org",
    },
    HOME_SAFETY: {
        "type": HOME_SAFETY,
        "title": "You deserve to feel safe at home",
        "body": (
            "What you wrote may be about your safety at home. Trained advocates can talk this through with you, "
            "confidentially. If you're in immediate danger, call 911. "
            "If someone may check your phone, call the hotline when you can, and close this app if you need to."
        ),
        "actions": [
            {"label": "Call 1-800-799-7233", "tel": "18007997233", "note": "National Domestic Violence Hotline. You can also text START to 88788."},
            {"label": "Call 911", "tel": "911", "note": "If you're in immediate danger"},
        ],
        "source": "National Domestic Violence Hotline",
    },
}

_FLAGS = re.IGNORECASE | re.DOTALL
_BABY = r"(baby|newborn|infant|my (son|daughter))('s)?"
_BABY_SYMPTOM = (
    r"(fever\w*|temperature|\btemp\b|won't (wake|eat|feed|stop crying)|isn't (eating|feeding|breathing)|"
    r"not (eating|feeding|breathing|waking)|trouble breathing|turning blue|limp|rash|vomit\w*|throwing up|"
    r"no wet diapers|lethargic|seizure)"
)
_PARTNER = r"(partner|husband|boyfriend|wife|girlfriend|\bbf\b|\bhe\b|\bshe\b)"
_HARMFUL_ACT = (
    r"(hit|hits|hitting|slap\w*|chok\w*|shov\w*|threat\w*|won't let me|doesn't let me|isn't letting me|"
    r"takes? my phone|took my phone|hurts? me|hurt me)"
)
_NEAR = r"\W+(?:\w+\W+){0,4}"

_WORDS = {
    BABY_HEALTH: re.compile(rf"{_BABY}{_NEAR}{_BABY_SYMPTOM}|{_BABY_SYMPTOM}{_NEAR}in (my|the) (baby|newborn|infant)", _FLAGS),
    HOME_SAFETY: re.compile(
        rf"{_PARTNER}{_NEAR}{_HARMFUL_ACT}|(afraid|scared) of (my )?(him|her|partner|husband|boyfriend|wife|girlfriend)|"
        r"(don't|do not) feel safe (at home|with)|not safe (at home|with)",
        _FLAGS,
    ),
}


def word_notices(text: str) -> set[str]:
    searchable = text.replace("’", "'").replace("‘", "'")
    return {kind for kind, pattern in _WORDS.items() if pattern.search(searchable)}


def merge_notices(words: set[str], claude: list[str]) -> list[str]:
    """Either check can raise a notice. Unknown values from Claude are ignored."""
    found = words | {n for n in claude if n in NOTICES}
    return [kind for kind in NOTICE_TYPES if kind in found]


def fixed_notice(kind: str) -> dict:
    return NOTICES[kind]
