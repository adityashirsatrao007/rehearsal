"""Persistence round-trips. Uses the throwaway DB set in conftest.py."""

from app import store


def test_create_and_read_session():
    s = store.create_session("interview", "Job Interview", "gemma4:e2b")
    assert s["scenario"] == "interview"
    assert s["model"] == "gemma4:e2b"
    assert store.get_session(s["id"])["scenario_title"] == "Job Interview"


def test_messages_round_trip_in_order():
    s = store.create_session("smalltalk", "Small Talk", "gemma4:e2b")
    first = store.add_message(s["id"], "learner", "Hello there")
    second = store.add_message(s["id"], "partner", "Hey, how's it going?")
    third = store.add_message(s["id"], "learner", "Good thanks")

    msgs = store.get_messages(s["id"])
    assert [m["content"] for m in msgs] == [
        "Hello there",
        "Hey, how's it going?",
        "Good thanks",
    ]
    assert [m["id"] for m in msgs] == [first, second, third]


def test_correction_links_to_a_message():
    s = store.create_session("interview", "Job Interview", "gemma4:e2b")
    mid = store.add_message(s["id"], "learner", "I work in company")
    cid = store.add_correction(s["id"], mid, "I work at a company", "Preposition.", "")

    corrections = store.get_corrections(s["id"])
    assert len(corrections) == 1
    assert corrections[0]["id"] == cid
    assert corrections[0]["message_id"] == mid
    assert corrections[0]["corrected"] == "I work at a company"


def test_delete_session_removes_its_children():
    s = store.create_session("travel", "Travel & Service", "gemma4:e2b")
    mid = store.add_message(s["id"], "learner", "Can I get late checkout?")
    store.add_correction(s["id"], mid, "Could I get a late checkout?", "Politeness.", "")

    assert store.delete_session(s["id"]) is True
    assert store.get_session(s["id"]) is None
    assert store.get_messages(s["id"]) == []
    assert store.get_corrections(s["id"]) == []


def test_delete_missing_session_is_false():
    assert store.delete_session(999_999) is False


def test_finish_session_writes_scorecard():
    s = store.create_session("client", "Client Call", "gemma4:e2b")
    store.add_message(s["id"], "learner", "We are delayed by one week")
    store.finish_session(s["id"], 7, 6, 8, "Solid.", "Past tense next.")

    done = store.get_session(s["id"])
    assert done["ended_at"] is not None
    assert done["score_fluency"] == 7
    assert done["score_accuracy"] == 6
    assert done["score_vocabulary"] == 8
    assert done["next_step"] == "Past tense next."


def test_learner_turns_excludes_partner():
    s = store.create_session("presentation", "Presentation Q&A", "gemma4:e2b")
    store.add_message(s["id"], "partner", "How did you measure it?")
    store.add_message(s["id"], "learner", "We used real user timings")
    store.add_message(s["id"], "partner", "Over what period?")
    store.add_message(s["id"], "learner", "Six weeks, before and after")

    assert store.learner_turns(s["id"]) == [
        "We used real user timings",
        "Six weeks, before and after",
    ]


def test_progress_stats_starts_empty():
    stats = store.progress_stats()
    assert stats["sessions_completed"] == 0
    assert stats["learner_messages"] == 0
    assert stats["avg_fluency"] == 0.0


def test_progress_stats_averages_only_finished_sessions():
    a = store.create_session("interview", "Job Interview", "gemma4:e2b")
    b = store.create_session("client", "Client Call", "gemma4:e2b")
    store.add_message(a["id"], "learner", "one")
    store.add_message(b["id"], "learner", "two")
    store.add_message(b["id"], "learner", "three")

    store.finish_session(a["id"], 8, 6, 7, "ok", "ok")
    # b is deliberately left unfinished — it must not drag the average down,
    # but its messages still count towards total practice volume.

    stats = store.progress_stats()
    assert stats["sessions_completed"] == 1
    assert stats["learner_messages"] == 3
    assert stats["avg_fluency"] == 8.0
