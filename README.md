# Rehearsal

**Practise the conversation before it happens.**

An offline English conversation partner. It plays the other person — an
interviewer, a client, a colleague you barely know — comes back in character,
and corrects every message you send. It runs entirely on your own laptop
against an open-weight model. No account, no API key, no internet, no telemetry.

> Built for Hacktoberfest 2026 · DEV Weekend Challenge: **Build for a Friend**

<!-- PERSONALISE: name the friend and their concrete problem here, in one or
     two sentences. This is the single most heavily weighted judging criterion
     ("Relevance to the Prompt and Theme"), so be specific rather than warm.
     Example shape: "This is for Rohit, who freezes in English interviews
     despite being able to reason about distributed systems in Hindi. He had
     three interviews in two weeks and no safe place to practise out loud." -->

## Why this exists

English fluency is not the same as being able to think. Plenty of people can
design a system, lead a team or argue a point perfectly well in their first
language and then go blank when the same conversation has to happen in English.
The gap is almost never grammar knowledge — it is **reps**. Timed, repeated,
low-stakes reps of the actual conversation you are about to have.

The obvious fix is a tutor. Tutors cost money, need scheduling, and — this is
the part that matters — they put your voice, your half-formed sentences and
your job-search anxiety on somebody else's servers.

Rehearsal removes the money, the scheduling and the server. What's left is the
part that was always the point: reps.

## What it does

- **Plays a role, not a chatbot.** Five scenarios ship with the app — job
  interview, client call, small talk, presentation Q&A, travel & service. The
  model stays in character, probes with follow-up questions, and never breaks
  the fourth wall to lecture you.
- **Corrects every message you send.** Each of your turns produces a card with
  your original, a native-speaker rewrite, one sentence naming the actual
  error, and a more idiomatic alternative.
- **Scores the session.** End a session and the model returns a fluency /
  accuracy / vocabulary scorecard plus one specific thing to practise next
  time. Averages accumulate across sessions so progress is visible.
- **Swaps models from the UI.** The dropdown lists whatever is installed in
  Ollama. Change the model, keep everything else — the prompts, the history,
  the scorecard. No code edits, no redeploy.
- **Streams.** The partner's reply arrives token by token over SSE while the
  correction runs concurrently, so a turn costs one round trip rather than two.

## Why open innovation is the whole point

Every one of these is a thing a closed API makes impossible or awkward:

| | With a closed API | With Rehearsal |
|---|---|---|
| **Works offline** | No. The app is a network client with extra steps. | Yes. Pull the model once; afterwards the laptop goes on a plane and it still works. |
| **Your sentences stay yours** | Every practice turn is a request to a third party, logged on their terms. | The transcript lives in one local SQLite file. `data/` is gitignored. There is no outbound call to make. |
| **Swap the model** | You're on their model roadmap, not yours. | One dropdown. Try a bigger model on a desktop, a smaller one on a laptop, same app. |
| **Cost** | Per-token, forever, and the bill scales with how much you practise — which is exactly the behaviour you want to encourage. | One 1.6 GB download. Then practising is free, so practising more is free. |
| **Change how the agent behaves** | Prompt-only, and only within what their system prompt permits. | The three prompts are plain Python strings in `app/prompts.py`. Edit, restart, done. |

The last row is the one that mattered most while building this. The whole
product is a set of instructions to a small model, and the difference between a
useful coach and an annoying one was prompt engineering and output parsing —
not model capability. That is only practical to iterate on when the model, its
weights and the harness are all something you can read, edit and re-run.

### Where open beat closed in practice

**A 2B model was enough.** Rehearsal's core loop is deliberately narrow: stay
in character for 1–3 sentences, and rewrite one message in three labelled
lines. A frontier model would do it better, but "better" here means slightly
smoother phrasing — while costing money per attempt, requiring the network, and
sending practice sentences off-device. On a 4 GB laptop GPU the local model is
fast enough to feel live and good enough to be useful. The closed option would
have been solving a problem this app doesn't have.

**Failure modes were fixable.** A 2B model ignores formatting instructions
constantly — it bolds labels, drops colons, or rambles instead of answering.
Every one of those is a parsing bug, and the fix is a regex and a fallback. If
the model had been behind an API, the only recourse would have been to keep
asking harder. `tests/test_coach.py` is a catalogue of those failures; they're
tested because they happened.

## Demo

<!-- Add a screen recording (5-10s loops work well) and a screenshot here.
     ffmpeg is available for recording: `ffmpeg -f x11grab ...`
     Judges can't reward what they can't see. -->

_GIF / video going here._

## How it's built

```
rehearsal/
├── app/
│   ├── main.py       FastAPI routes + the SSE turn loop
│   ├── llm.py        async Ollama client — the only place the model is touched
│   ├── coach.py      prompt assembly + defensive output parsing
│   ├── prompts.py    the three system prompts (edit these to change behaviour)
│   ├── scenarios.py  role definitions and scripted openings
│   └── store.py      SQLite persistence (sessions, messages, corrections)
├── static/           vanilla HTML/CSS/JS — no build step, no framework, no CDN
└── tests/            37 tests: parser edge cases, persistence, HTTP contract
```

**Open-source AI at the core:**

- **Model:** [`gemma2:2b`](https://huggingface.co/google/gemma-2) (open weights,
  Gemma 2 Terms of Use) running locally.
- **Runtime:** [Ollama](https://ollama.com) (MIT) serving over
  `http://127.0.0.1:11434`.
- **Harness:** written from scratch for this project — FastAPI, httpx,
  SQLite, vanilla JS. No agent framework, so there is nothing between you and
  the three prompts.

**One turn looks like this:**

```
learner message ──┬──► /api/chat   (streamed, in character)  ──► SSE "reply"
                  │      asyncio.gather — concurrent, one round trip
                  └──► /api/generate (three labelled lines)   ──► SSE "correction"
```

Both calls only depend on the learner's message and the transcript, so they run
concurrently. Latency is `max(reply, correction)` rather than the sum.

## Quick start

Requires [Ollama](https://ollama.com/download) and Python 3.10+.

```bash
# 1. one-time: pull the model (~1.6 GB)
ollama pull gemma2:2b

# 2. start the local server
ollama serve &

# 3. start Rehearsal
./run.sh
# → http://127.0.0.1:8000
```

`run.sh` creates the virtualenv on first run and warns you if Ollama isn't up.

### Swapping the model

Pick a different one from the dropdown in the header, or set it before starting:

```bash
OLLAMA_MODEL=qwen2.5:3b ./run.sh
```

Anything with a chat endpoint works — `llama3.2:3b`, `phi3.5`, `mistral`,
`qwen2.5:7b`. Bigger models write better corrections and need more VRAM; the
scorecard prompt is the only place model quality really shows.

## Tests

```bash
.venv/bin/python -m pytest
# 37 passed
```

`tests/test_coach.py` is the interesting one: it documents the ways a small
model refuses to follow instructions, and asserts the app degrades gracefully
instead of throwing.

## Privacy

- The transcript lives in `data/rehearsal.db` — a single local file.
- `data/` is in `.gitignore`, so it cannot be pushed by accident.
- No analytics, no phone-home, no authentication, no cloud dependency.
- Rehearsal makes exactly one kind of network call: to Ollama, by default on
  `127.0.0.1`. Point `OLLAMA_HOST` somewhere else and you've changed that.

## Notes and limits

- Text-only by design — voice mode was cut to protect the deadline.
- Scores come from a 2B model. Treat them as a directional nudge, not a
  placement test.
- Single user, single machine. There is no auth layer because there is no
  multi-user layer.

## License

[MIT](LICENSE)
