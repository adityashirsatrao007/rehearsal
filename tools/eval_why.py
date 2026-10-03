"""Grounding eval for the correction prompt.

The failure this exists to catch: a small model confidently diagnoses an error
that is not in the learner's sentence — it told someone *since* was wrong in a
message that never used *since*. That is worse than no feedback, because it is
wrong with authority.

This script runs the live correction call over a fixed set of typical learner
errors and checks two things:

  1. any word the WHY line puts in quotes must literally occur in the message;
  2. WHY must share at least one content word with the message.

Run it after every prompt change:

    .venv/bin/python tools/eval_why.py
    OLLAMA_MODEL=gemma2:2b .venv/bin/python tools/eval_why.py   # compare models

Needs `ollama serve` running with the model pulled. It is a measurement tool,
not a test — it talks to a real model, so it is not in `tests/`.
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import coach, llm  # noqa: E402

MESSAGES = [
    "I work in company since three years and yesterday I go to the meeting.",
    "In last project I reduce the loading time from 6 second to 2 second.",
    "I am agree with you but we need discuss about the deadline.",
    "She didn't came to the meeting yesterday.",
    "I have finished the report last night.",
]

_STOP = {
    "the", "a", "an", "to", "of", "in", "on", "is", "are", "was", "were", "be",
    "it", "that", "this", "for", "and", "or", "you", "their", "they", "use",
    "with", "by", "as", "at", "from", "not", "needs", "need", "should",
    "would", "could", "when", "if", "so", "but", "one", "all",
}


def grounded(why: str, message: str, corrected: str = "") -> tuple[bool, str]:
    """True when WHY is actually about the sentence in front of it.

    A quoted token is allowed if it appears in the message (they said it) or in
    the corrected line (it is the fix being shown to them). Anything else was
    invented.
    """
    msg = message.lower()
    fix = (corrected or "").lower()

    # Only real quote marks — an apostrophe inside "didn't" is not a delimiter.
    quoted = re.findall(r'["“]([^"”]{1,40})["”]', why or "")
    if quoted:
        tokens = [q.lower().strip(" .,") for q in quoted]
        if not any(t in msg or t in fix for t in tokens):
            return False, f"quoted {tokens} appears in neither their message nor the rewrite"
        return True, "grounded"

    # No quoted token to check — fall back to asking whether WHY is about this
    # message at all, or just reciting a general grammar rule.
    def content(text: str) -> set[str]:
        return {
            w for w in re.findall(r"[a-z']+", text.lower())
            if len(w) > 2 and w not in _STOP
        }

    said, wrote = content(why or ""), content(msg)
    if said and not (said & wrote):
        return False, f"WHY shares no content word with the message ({sorted(said)[:3]})"
    return True, "grounded"


async def main() -> int:
    print(f"model: {llm.DEFAULT_MODEL}")
    ok = 0
    for message in MESSAGES:
        raw = await llm.generate(
            llm.DEFAULT_MODEL,
            coach.correction_system(message),
            "Learner message above.",
            options=llm.FEEDBACK_OPTIONS,
        )
        card = coach.parse_correction(raw)
        good, note = grounded(card["why"], message, card["corrected"])
        ok += good
        print(f'  [{"PASS" if good else "FAIL"}] {card["why"]}')
        if not good:
            print(f"         -> {note}")
        if not card["parsed"]:
            print(f"         -> parse failed, raw={raw[:120]!r}")
    print(f"grounded {ok}/{len(MESSAGES)}")
    return 0 if ok == len(MESSAGES) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
