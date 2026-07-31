# Troll Bridge Game

A troll blocks an old bridge (rendered over a real photo of the Brooklyn
Bridge). To cross, you must beat whatever mini-game the troll's AI brain
decides to spring on you.

The troll's brain is a small **FastAPI server running on a [Dedalus
Machine](https://dedaluslabs.ai)** (a real cloud VM). It picks a mini-game
and, for the mini-games with a subjective outcome, judges your attempt and
decides your fate - both via structured (JSON-schema) responses from the
Dedalus Agents API. There is no local mock brain: the pygame client is
purely a client of that server over HTTP.

## Running it

```bash
uv run main.py
```

`uv` reads `pyproject.toml`, creates/updates a local `.venv`, and installs
dependencies - no separate setup script. Every run also provisions the
troll's brain: all existing machines on the account are destroyed and a
fresh Dedalus Machine is created and set up (see below), which takes a few
minutes each time.

## Architecture

```
              HTTP (httpx)                  Dedalus Agents API
main.py  ───────────────────▶  server.py  ───────────────────▶  LLM
(pygame,                       (FastAPI,                        (tool calls +
 your machine)                  Dedalus Machine)                 transcription)
```

- **`main.py`** - the pygame client. Owns all game state and rendering,
  plays out each mini-game, and does the auto-verdict checks (riddle/trivia
  answers, rock-paper-scissors, reflex timing) locally. For the two
  AI-verdict games it POSTs to the deployed server and waits for an answer.
- **`troll_client.py`** - a thin `httpx` wrapper around the server's HTTP
  API. This is the *only* place the client talks to the troll's brain; it
  never calls the Dedalus SDK directly and has no fallback logic - if a
  request fails, main.py retries it rather than guessing locally.
- **`machine/provision.py`** - destroys every machine on the account
  (best-effort), creates a fresh Dedalus Machine, deploys
  `machine/server_setup/` to it, runs the small setup script there (with
  live streamed output), and returns an HTTPS URL for the running server.
  Machines are never woken or reused, so a sleeping/unreachable machine
  can't stall startup.
- **`machine/server_setup/server.py`** - the actual brain: a FastAPI app
  that runs on the Dedalus Machine and calls the Dedalus Agents API
  (structured-output chat completions, and audio transcription).
- **`minigames.py`** - shared game data & pure logic (riddle/trivia banks,
  card tiers, RPS, answer checking). Used by both `main.py` and the
  deployed server (provisioning bundles this file onto the machine
  automatically, so there's exactly one copy of the rules).

## The API key

Both provisioning the machine and running the deployed server need a
`DEDALUS_API_KEY`. `agent.py` loads it from a `.env` file in this folder
(the file is gitignored, so the key never gets committed).

If no key is found, or the machine can't be provisioned, the game refuses
to start (there is intentionally no offline mode).

You can override the models the server uses via environment variables
(picked up by `setup.sh` when the machine is provisioned):

- `DEDALUS_CHAT_MODEL` (default: `openai/gpt-4o-mini`) - used for choosing a
  mini-game and judging outcomes.
- `DEDALUS_TRANSCRIBE_MODEL` (default: `openai/gpt-4o-transcribe`) - used to
  transcribe spoken stories/jokes.

## The mini-games

Each round, the troll's brain picks one of these by calling a tool:

| Mini-game | How it works | Verdict |
|---|---|---|
| **Riddle Duel** | The troll asks a riddle. Type your answer. | Auto - checked in code |
| **Trivia Gate** | The troll asks a themed trivia question. Type your answer. | Auto - checked in code |
| **Rock-Paper-Troll** | Best-of-three rock-paper-scissors against the troll. | Auto - checked in code |
| **Reflex Gauntlet** | Wait for it... then press SPACE the instant the troll says "NOW!" | Auto - timing checked in code |
| **Card of Courage** | Draw a card; the higher it is, the scarier the story you must tell in 30 seconds (spoken or typed). | The troll's AI brain judges |
| **Joke Toll** | Tell the troll a joke (spoken or typed). | The troll's AI brain judges |

Win and the troll fades away, letting you cross. Lose and it shoves you
back for another attempt with a fresh mini-game.

### Voice input

For "Card of Courage" and "Joke Toll" you can speak instead of typing:
press ENTER with an empty text box to start recording (via your
microphone), and ENTER again to stop (or just let the 30-second timer run
out). Your recording is POSTed to the troll's server, which sends it to
Dedalus's transcription endpoint (`openai/gpt-4o-transcribe`); the
resulting text is what the troll judges. If no microphone is available,
this is skipped automatically - just type your answer instead.

## Controls

- **ENTER** - confirm / submit / start & stop speaking
- **Letter keys** - type an answer, story, or joke
- **BACKSPACE** - delete typed text
- **1 / 2 / 3** - Rock / Paper / Scissors
- **SPACE** - react during the Reflex Gauntlet
- **ESC** - quit

## Project layout

```
game/
├── main.py                       # pygame client: rendering, input, state machine
├── agent.py                      # AI Agent setup, API key management & Dedalus HTTP client
├── games.py                      # consolidated mini-game handlers (rendering & input)
├── minigames.py                  # shared game data & pure logic (bundled onto the machine too)
├── .env                          # DEDALUS_API_KEY (gitignored - never commit it)
├── machine/
│   ├── provision.py                 # creates/reuses the Dedalus Machine, deploys the server
│   ├── machines.json                 # persisted machine registry (created at runtime, gitignored)
│   └── server_setup/
│       ├── server.py                   # FastAPI app - the troll's actual brain
│       ├── setup.sh                    # installs deps & a systemd service on the VM
│       └── system_prompt.md             # the troll's persona
├── assets/
│   ├── troll.png                      # troll sprite
│   ├── brooklyn-bridge-4.jpg           # background
│   └── fonts/PressStart2P.ttf           # retro pixel font
└── pyproject.toml                 # client dependencies, used by `uv run main.py`
```

## Extending it

To add a new mini-game: add a `GameInfo` entry to `GAMES` in `minigames.py`
(with a `tool_description` so the AI knows when to pick it), then teach
`main.py` how to play it - a new `game_ctx`/state branch in `start_game()`,
`handle_events()`, `update()`, and a `render_<state>()` method. If it needs
a subjective verdict, add a case to `judge_prompt_for()` in `minigames.py` -
`server.py` picks that up automatically the next time it's redeployed
(provisioning detects the code change via a content hash and redeploys).

## Managing the machine

Machines are ephemeral: every game run first destroys **all** machines on
the Dedalus account (best-effort - a failed delete is logged and skipped),
then creates a brand-new one and sets it up from scratch, so you always
get a clean deploy of the current server code. `machine/machines.json` is
just a breadcrumb of the last created machine; deleting it is safe. You
can also run `uv run python -m machine.provision` directly to provision
without starting the game.
