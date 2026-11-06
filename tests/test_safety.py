"""Safety and privacy checks that need no API key or network."""

import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tend import pipeline, store  # noqa: E402
from tend.signs import (  # noqa: E402
    ALWAYS_911,
    CALL_911,
    CARE_NOW,
    CHECK_THIS,
    NOTED,
    SIGN_IDS,
    highest_level,
    word_flags,
)

EVERYDAY_WORDS = {
    "headache": "This headache has been here since yesterday.",
    "dizziness": "I felt really lightheaded on the stairs.",
    "vision": "I keep seeing little spots.",
    "fever": "I have chills and feel hot.",
    "swelling_hands_face": "My rings don't fit anymore.",
    "harm_thoughts": "They'd be better off without me.",
    "breathing": "I can't catch my breath lying down.",
    "chest_heart": "My heart is racing for no reason.",
    "nausea_vomiting": "I can't keep water down.",
    "belly_pain": "My stomach has a sharp pain that keeps coming.",
    "baby_movement": "The baby stopped moving as much today.",
    "bleeding_during": "I'm pregnant again and leaking fluid.",
    "bleeding_after": "I soaked through a pad in an hour.",
    "limb": "My left calf is sore and warm.",
    "tiredness": "I'm too tired to pick up the baby.",
    "seizure": "My sister said I had a seizure.",
}


@pytest.mark.parametrize("sign_id", SIGN_IDS)
def test_word_check_catches_each_sign(sign_id):
    assert sign_id in word_flags(EVERYDAY_WORDS[sign_id])


@pytest.mark.parametrize("sign_id", sorted(ALWAYS_911))
def test_always_urgent_signs_call_911(sign_id):
    assert word_flags(EVERYDAY_WORDS[sign_id])[sign_id]["level"] == CALL_911


@pytest.mark.parametrize(
    "text,sign_id,level",
    [
        ("Little headache this afternoon.", "headache", CHECK_THIS),
        ("My headache won't go away even after Tylenol.", "headache", CARE_NOW),
        ("I'm so tired today.", "tiredness", CHECK_THIS),
        ("I'm too tired to take care of her.", "tiredness", CARE_NOW),
        ("Some bleeding today.", "bleeding_after", CHECK_THIS),
        ("I soaked a pad in an hour.", "bleeding_after", CARE_NOW),
        ("My vision is blurry.", "vision", CARE_NOW),
        ("I passed out in the kitchen.", "dizziness", CALL_911),
        ("A bit dizzy when I stood up.", "dizziness", CHECK_THIS),
    ],
)
def test_levels_from_words(text, sign_id, level):
    assert word_flags(text)[sign_id]["level"] == level


def test_chestfeeding_is_not_an_emergency():
    assert "chest_heart" not in word_flags("Chest feeding went well this morning.")


def test_curly_apostrophes_are_handled():
    assert "swelling_hands_face" in word_flags("My rings don’t fit anymore.")


def _entry(text="I have a little headache.", entry_id=5, day="2026-11-06"):
    return {"id": entry_id, "created_at": f"{day}T09:00:00", "text": text, "flags": [], "patterns": []}


def _failing_llm(*_):
    raise RuntimeError("API down")


def _no_findings(*_):
    return {"signs": [], "patterns": []}


def test_claude_failure_raises_word_matches_to_care_now():
    result = pipeline.analyze(_entry(), [], None, llm=_failing_llm)
    assert result["ai_status"] == "unavailable"
    assert highest_level(result["flags"]) == CARE_NOW


def test_missing_key_fails_safe_without_using_inherited_settings(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:9")
    result = pipeline.analyze(_entry(), [], None)
    assert result["ai_status"] == "unavailable"
    assert highest_level(result["flags"]) == CARE_NOW


def test_claude_cannot_remove_a_word_match():
    result = pipeline.analyze(_entry(), [], None, llm=_no_findings)
    assert [f["sign_id"] for f in result["flags"]] == ["headache"]
    assert result["flags"][0]["level"] == NOTED
    assert highest_level(result["flags"]) is None


def test_claude_cannot_lower_an_always_urgent_sign():
    text = "I can't catch my breath."
    llm = lambda *_: {"signs": [{"id": "breathing", "quote": text, "strength": "possible"}], "patterns": []}
    assert pipeline.analyze(_entry(text), [], None, llm=llm)["flags"][0]["level"] == CALL_911


def test_possible_harm_link_asks_a_question_not_911():
    text = "I felt really teary around lunch."
    llm = lambda *_: {"signs": [{"id": "harm_thoughts", "quote": text, "strength": "possible"}], "patterns": []}
    flags = pipeline.analyze(_entry(text), [], None, llm=llm)["flags"]
    assert flags[0]["level"] == CHECK_THIS
    assert pipeline.apply_follow_up(flags, "harm_thoughts", "yes")[0]["level"] == CALL_911
    assert pipeline.apply_follow_up(flags, "harm_thoughts", "no")[0]["level"] == CHECK_THIS


def test_ambiguous_venting_starts_with_a_question():
    assert word_flags("I can't do this anymore.")["harm_thoughts"]["level"] == CHECK_THIS
    llm = lambda *_: {"signs": [], "patterns": []}
    flag = pipeline.analyze(_entry("I can't do this anymore."), [], None, llm=llm)["flags"][0]
    assert flag["level"] == CHECK_THIS  # never hidden, even if Claude does not list it


@pytest.mark.parametrize("text", ["It feels like there's no way out of this.", "I feel hopeless."])
def test_cdc_hopelessness_words_call_911(text):
    assert word_flags(text)["harm_thoughts"]["level"] == CALL_911


def test_waking_on_the_floor_calls_911():
    assert word_flags("I woke up on the bathroom floor.")["dizziness"]["level"] == CALL_911


def test_out_of_breath_and_soaked_shirt_do_not_start_full_alerts():
    assert word_flags("Got out of breath chasing the toddler.")["breathing"]["level"] == CHECK_THIS
    assert "bleeding_after" not in word_flags("Night sweats and my shirt was soaked.")
    assert word_flags("I soaked through a pad.")["bleeding_after"]["level"] == CARE_NOW


def test_clear_harm_words_still_call_911_when_claude_says_nothing():
    flag = pipeline.analyze(_entry("I want to die."), [], None, llm=_no_findings)["flags"][0]
    assert flag["level"] == CALL_911


def test_noted_match_is_hidden_but_three_days_become_a_pattern():
    def noted(entry_id, day):
        return {**_entry("So tired.", entry_id, day), "flags": [{"sign_id": "tiredness", "quote": "So tired.", "level": NOTED, "source": "words"}]}
    two = pipeline.repeated_sign_patterns([noted(1, "2026-11-04"), noted(2, "2026-11-05")], set())
    three = pipeline.repeated_sign_patterns([noted(1, "2026-11-04"), noted(2, "2026-11-05"), noted(3, "2026-11-06")], set())
    assert two == [] and three[0]["sign_ids"] == ["tiredness"]
    assert pipeline.build_script(noted(1, "2026-11-04")["flags"], None) == ""


def test_claude_can_raise_a_level():
    llm = lambda *_: {"signs": [{"id": "headache", "quote": "little headache", "strength": "clear"}], "patterns": []}
    assert pipeline.analyze(_entry(), [], None, llm=llm)["flags"][0]["level"] == CARE_NOW


def test_claude_can_add_a_sign_words_missed():
    text = "I don't see the point of anything anymore."
    llm = lambda *_: {"signs": [{"id": "harm_thoughts", "quote": "I don't see the point", "strength": "clear"}], "patterns": []}
    flag = pipeline.analyze(_entry(text), [], None, llm=llm)["flags"][0]
    assert (flag["sign_id"], flag["level"], flag["quote"]) == ("harm_thoughts", CALL_911, "I don't see the point")


def test_invented_quote_is_replaced_with_her_words():
    text = "I don't see the point of anything anymore."
    llm = lambda *_: {"signs": [{"id": "harm_thoughts", "quote": "She plans to hurt herself", "strength": "clear"}], "patterns": []}
    assert pipeline.analyze(_entry(text), [], None, llm=llm)["flags"][0]["quote"] == text


def test_unknown_sign_id_is_ignored():
    llm = lambda *_: {"signs": [{"id": "made_up", "quote": "Hello", "strength": "clear"}], "patterns": []}
    assert pipeline.analyze(_entry("Hello."), [], None, llm=llm)["flags"] == []


def test_follow_up_yes_raises_and_no_keeps_the_flag():
    flags = [{"sign_id": "headache", "quote": "x", "level": CHECK_THIS, "source": "words"}]
    assert pipeline.apply_follow_up(flags, "headache", "yes")[0]["level"] == CARE_NOW
    kept = pipeline.apply_follow_up(flags, "headache", "no")
    assert kept[0]["level"] == CHECK_THIS and kept[0]["answer"] == "no"


@pytest.mark.parametrize(
    "title",
    ["Possible preeclampsia", "This is probably normal", "You're fine", "Signs of postpartum depression", "Wait and see"],
)
def test_unsafe_pattern_titles_are_replaced(title):
    assert pipeline.safe_title(title) == pipeline.GENERIC_PATTERN_TITLE


def test_pattern_requires_two_real_entries_and_real_quotes():
    entries = [_entry("Headache today.", 1, "2026-11-04"), _entry("Headache again.", 2, "2026-11-05")]
    raw = [
        {"title": "Headaches on 2 days", "sign_ids": ["headache"], "evidence": [
            {"entry_id": 1, "quote": "Headache today."}, {"entry_id": 2, "quote": "Severe migraine"}]},
        {"title": "Only one", "sign_ids": [], "evidence": [{"entry_id": 1, "quote": "Headache today."}]},
        {"title": "Fake entry", "sign_ids": [], "evidence": [
            {"entry_id": 1, "quote": "Headache today."}, {"entry_id": 99, "quote": "x"}]},
    ]
    cleaned = pipeline.clean_claude_patterns(raw, entries)
    assert len(cleaned) == 1
    assert cleaned[0]["evidence"][1]["quote"] == "Headache again."


def test_same_day_entries_are_not_a_pattern():
    entries = [_entry("Headache today.", 1), _entry("Headache again.", 2)]
    raw = [{"title": "Headaches", "sign_ids": [], "evidence": [
        {"entry_id": 1, "quote": "Headache today."}, {"entry_id": 2, "quote": "Headache again."}]}]
    assert pipeline.clean_claude_patterns(raw, entries) == []


def test_repeated_sign_found_without_claude():
    earlier = {**_entry("Headache today.", 1, "2026-11-04"),
               "flags": [{"sign_id": "headache", "quote": "Headache today.", "level": CHECK_THIS, "source": "words"}]}
    result = pipeline.analyze(_entry("Headache again.", 2, "2026-11-05"), [earlier], None, llm=_failing_llm)
    assert result["patterns"][0]["sign_ids"] == ["headache"]
    assert len(result["patterns"][0]["evidence"]) == 2


def test_script_uses_her_exact_words():
    flags = [{"sign_id": "vision", "quote": "I keep seeing little spots.", "level": CARE_NOW, "source": "both"}]
    script = pipeline.build_script(flags, "2026-10-16", today=date(2026, 11, 6))
    assert "October 16, 2026 (3 weeks ago)" in script
    assert '"I keep seeing little spots."' in script
    assert "may relate" in script


def test_no_flags_means_no_script():
    assert pipeline.build_script([], None) == ""


@pytest.fixture
def client(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(pipeline, "check_entry", _no_findings)
    monkeypatch.setattr(pipeline.analyze, "__defaults__", (_no_findings,))
    return TestClient(main.app)


def _signup(client, name):
    response = client.post("/api/signup", json={"username": name, "password": "demo-pass-123"})
    assert response.status_code == 200
    return response


def test_must_log_in_to_read_or_write(client):
    assert client.get("/api/state").status_code == 401
    assert client.post("/api/checkin", json={"text": "hello"}).status_code == 401


def test_each_user_sees_only_their_entries(client):
    _signup(client, "maya")
    entry = client.post("/api/checkin", json={"text": "Maya's private headache"}).json()["entry"]
    client.post("/api/logout")

    _signup(client, "rosa")
    assert client.get("/api/state").json()["entries"] == []
    other = client.post(f"/api/entries/{entry['id']}/follow-up", json={"sign_id": "headache", "answer": "yes"})
    assert other.status_code == 404


def test_demo_login_resets_only_the_demo_account(client):
    _signup(client, "maya")
    client.post("/api/checkin", json={"text": "Maya's private headache"})
    client.post("/api/logout")

    first = client.post("/api/demo/login").json()
    assert first["username"] == store.DEMO_USERNAME and len(first["entries"]) == 3
    client.post("/api/checkin", json={"text": "Extra demo entry"})
    assert len(client.post("/api/demo/login").json()["entries"]) == 3
    for entry in first["entries"]:
        assert "private" not in entry["text"]
    client.post("/api/logout")

    assert client.post("/api/login", json={"username": "maya", "password": "demo-pass-123"}).json()["entries"][0]["text"] == "Maya's private headache"


def test_wrong_password_is_rejected_and_password_is_not_stored_plainly(client):
    _signup(client, "maya")
    client.post("/api/logout")
    bad = client.post("/api/login", json={"username": "maya", "password": "wrong-password"})
    assert bad.status_code == 401
    assert client.post("/api/login", json={"username": "maya", "password": "demo-pass-123"}).status_code == 200
    with store.db() as conn:
        stored = conn.execute("SELECT password_hash FROM users").fetchone()["password_hash"]
    assert "demo-pass-123" not in stored


def test_follow_up_yes_changes_the_level_through_the_app(client, monkeypatch):
    _signup(client, "maya")
    monkeypatch.setattr(pipeline.analyze, "__defaults__", (lambda *_: {"signs": [{"id": "headache", "quote": "Little headache today.", "strength": "possible"}], "patterns": []},))
    entry = client.post("/api/checkin", json={"text": "Little headache today."}).json()["entry"]
    assert entry["level"] == CHECK_THIS
    updated = client.post(f"/api/entries/{entry['id']}/follow-up", json={"sign_id": "headache", "answer": "yes"}).json()["entry"]
    assert updated["level"] == CARE_NOW
    assert "I answered yes" in updated["script"]
