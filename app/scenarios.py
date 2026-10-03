"""Conversation scenarios — the roles the open-weight model plays.

Each scenario is a one-sentence role line injected into PARTNER_SYSTEM. The
learner picks one at the start of a session.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    emoji: str
    blurb: str
    role_line: str
    opening: str = ""


SCENARIOS: list[Scenario] = [
    Scenario(
        id="interview",
        title="Job Interview",
        emoji="💼",
        blurb="A panel interview for a role you actually want.",
        role_line=(
            "the hiring manager interviewing the learner for a job. "
            "Ask standard interview questions one at a time: about their background, "
            "a project they are proud of, a disagreement with a teammate, and where "
            "they want to be in five years. Probe with 'Can you tell me more about that?'"
        ),
        opening=(
            "Thanks for making the time. Let's start simply — could you tell me "
            "a little about yourself and what you've been working on recently?"
        ),
    ),
    Scenario(
        id="client",
        title="Client Call",
        emoji="🤝",
        blurb="A status call where you have to explain a delay.",
        role_line=(
            "an impatient but fair client on a video call. The learner is presenting "
            "a project status update that includes a one-week delay. Push back on the "
            "delay, ask what it costs you, and ask what they will do differently. "
            "Be professional, not hostile."
        ),
        opening=(
            "Hi — thanks for joining. Before we get into the update, I want to be "
            "straight with you: I'm not thrilled about the timeline. What's happening?"
        ),
    ),
    Scenario(
        id="smalltalk",
        title="Small Talk",
        emoji="☕",
        blurb="A colleague you don't know well, by the coffee machine.",
        role_line=(
            "a friendly colleague the learner has met only twice, making small talk "
            "in an office kitchen. Chat about the weekend, a recent film, the weather, "
            "plans for the evening. Keep it light and let silences be comfortable."
        ),
        opening=(
            "Oh, hey — didn't expect to see you here. How's your week been so far?"
        ),
    ),
    Scenario(
        id="presentation",
        title="Presentation Q&A",
        emoji="🎤",
        blurb="You've just finished. Now they ask the hard questions.",
        role_line=(
            "an audience member asking questions after the learner's presentation on "
            "'How our team cut app load times in half'. Ask practical, occasionally "
            "sceptical questions: how they measured it, what it cost, whether it "
            "would work for a smaller team, what the biggest risk is."
        ),
        opening=(
            "Thanks, that was clear. Quick question — you said load times halved. "
            "How exactly did you measure that, and over what period?"
        ),
    ),
    Scenario(
        id="travel",
        title="Travel & Service",
        emoji="✈️",
        blurb="Hotel, restaurant, taxi — the everyday English that trips you up.",
        role_line=(
            "hotel front desk staff (and later a waiter) dealing with the learner, "
            "a guest. Handle a room problem, a late checkout request, a food allergy "
            "question and a bill that looks wrong. Be helpful but brisk."
        ),
        opening=(
            "Good evening — welcome. Do you have a reservation with us? "
            "May I see your passport, please?"
        ),
    ),
]

SCENARIOS_BY_ID: dict[str, Scenario] = {s.id: s for s in SCENARIOS}


def get_scenario(scenario_id: str) -> Scenario | None:
    return SCENARIOS_BY_ID.get(scenario_id)


def list_scenarios() -> list[dict]:
    return [
        {
            "id": s.id,
            "title": s.title,
            "emoji": s.emoji,
            "blurb": s.blurb,
            "opening": s.opening,
        }
        for s in SCENARIOS
    ]
