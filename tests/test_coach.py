"""Parsing must survive a small model that ignores instructions.

Every test here represents a real failure mode seen while building this.
"""

from app import coach, prompts
from app.scenarios import SCENARIOS, get_scenario


# ---------------------------------------------------------------------------
# correction parsing
# ---------------------------------------------------------------------------

def test_parses_well_formed_correction():
    raw = (
        "CORRECTED: I have been working here for three years.\n"
        "WHY: Use the present perfect with 'for' when the action is still ongoing.\n"
        "BETTER: I've been with the company for three years now.\n"
    )
    out = coach.parse_correction(raw)
    assert out["parsed"] is True
    assert out["corrected"] == "I have been working here for three years."
    assert out["why"].startswith("Use the present perfect")
    assert out["better"] == "I've been with the company for three years now."


def test_parses_markdown_bolded_labels():
    raw = (
        "**CORRECTED:** I want to apply for this job.\n"
        "**WHY:** Missing article before 'this job' is fine, but tense was off.\n"
        "**BETTER:** I'd like to apply for the position.\n"
    )
    out = coach.parse_correction(raw)
    assert out["parsed"] is True
    assert out["corrected"] == "I want to apply for this job."
    assert out["better"] == "I'd like to apply for the position."


def test_parses_bold_wrapped_label_before_colon():
    """`**CORRECTED**: value` — emphasis closing before the colon, not after."""
    raw = (
        "**CORRECTED**: I am working here since three years.\n"
        "**WHY**: 'Since' needs a point in time; use 'for' with a duration.\n"
        "**BETTER**: I've been working here for three years.\n"
    )
    out = coach.parse_correction(raw)
    assert out["parsed"] is True
    assert out["corrected"] == "I am working here since three years."
    assert out["better"] == "I've been working here for three years."


def test_parses_colonless_labels_and_lowercase():
    raw = (
        "corrected - i go to market yesterday\n"
        "why - past tense required\n"
        "better - i went to the market yesterday\n"
    )
    out = coach.parse_correction(raw)
    assert out["parsed"] is True
    assert out["corrected"] == "i go to market yesterday"
    assert out["why"] == "past tense required"


def test_parses_labels_written_in_different_case():
    raw = (
        "Corrected: She don't like it.\n"
        "Why: Third person singular takes 'doesn't'.\n"
        "Better: She doesn't like it.\n"
    )
    out = coach.parse_correction(raw)
    assert out["parsed"] is True
    assert out["corrected"] == "She don't like it."


def test_falls_back_to_raw_when_model_rambles():
    raw = "Sure! Your sentence is mostly fine. I would just add an article somewhere."
    out = coach.parse_correction(raw)
    assert out["parsed"] is False
    assert out["raw"].startswith("Sure!")
    assert out["corrected"] == ""


def test_falls_back_to_raw_on_empty_output():
    out = coach.parse_correction("")
    assert out["parsed"] is False
    assert out["raw"] == ""


def test_strips_markdown_headings_in_fallback():
    raw = "### Feedback\nYour grammar is improving, keep going!"
    out = coach.parse_correction(raw)
    assert out["parsed"] is False
    assert not out["raw"].startswith("#")


def test_never_raises_on_garbage():
    for junk in ["{", "```json\n[]\n```", "\x00\x01\x02", "CORRECTED:", None or ""]:
        out = coach.parse_correction(junk)
        assert isinstance(out, dict)
        assert set(out) == {"corrected", "why", "better", "raw", "parsed"}


# ---------------------------------------------------------------------------
# summary parsing
# ---------------------------------------------------------------------------

def test_parses_well_formed_summary():
    raw = (
        "SCORE_FLUENCY: 7\n"
        "SCORE_ACCURACY: 6\n"
        "SCORE_VOCABULARY: 8\n"
        "SUMMARY: Confident turns with a few tense slips.\n"
        "NEXT: Practise past-tense narration of your projects.\n"
    )
    out = coach.parse_summary(raw)
    assert out["fluency"] == 7
    assert out["accuracy"] == 6
    assert out["vocabulary"] == 8
    assert out["summary"].startswith("Confident turns")
    assert out["next_step"].startswith("Practise past-tense")


def test_summary_defaults_to_five_when_field_missing():
    out = coach.parse_summary("SCORE_FLUENCY: 8")
    assert out["fluency"] == 8
    assert out["accuracy"] == 5
    assert out["vocabulary"] == 5
    assert out["summary"]
    assert out["next_step"]


def test_summary_scores_are_clamped_to_one_to_ten():
    out = coach.parse_summary(
        "SCORE_FLUENCY: 42\nSCORE_ACCURACY: -3\nSCORE_VOCABULARY: abc"
    )
    assert out["fluency"] == 10
    assert out["accuracy"] == 1
    assert out["vocabulary"] == 5


def test_summary_never_raises():
    for junk in ["", "[]", "no scores here at all"]:
        out = coach.parse_summary(junk)
        assert 1 <= out["fluency"] <= 10


# ---------------------------------------------------------------------------
# prompt assembly
# ---------------------------------------------------------------------------

def test_partner_prompt_includes_the_role():
    scenario = get_scenario("interview")
    text = coach.partner_system(scenario)
    assert "hiring manager" in text
    assert "Never break character" in text


def test_correction_prompt_embeds_the_learner_message():
    text = coach.correction_system("I go to market yesterday.")
    assert "I go to market yesterday." in text
    assert "CORRECTED:" in text


def test_summary_prompt_embeds_every_turn():
    text = coach.summary_system("Job Interview", ["Hi", "", "I am fine"])
    assert "Job Interview" in text
    assert "Number of learner messages: 3" in text
    assert "- Hi" in text
    assert "- I am fine" in text
    # blank turns are dropped rather than emitting an empty bullet
    assert "\n- \n" not in text


def test_every_scenario_has_id_title_and_role():
    assert len(SCENARIOS) >= 5
    ids = set()
    for s in SCENARIOS:
        assert s.id and s.id not in ids
        assert s.title and s.blurb and s.role_line and s.opening
        ids.add(s.id)


def test_unknown_scenario_is_none():
    assert get_scenario("does-not-exist") is None
