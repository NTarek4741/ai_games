# Troll Bridge Game

> **Created as an ambassador for Dedalus Labs** — check out [https://dedaluslabs.ai](https://dedaluslabs.ai).

A retro pixel-art Pygame challenge where an ancient troll guards a bridge over the Brooklyn Bridge. To cross, you must spin the challenge wheel and beat whatever mini-game the troll springs on you.

The troll's brain is a **FastAPI server running on a [Dedalus Machine](https://dedaluslabs.ai)** (a cloud VM). For subjective mini-games (Card of Courage, Joke Toll), the server uses structured JSON-schema outputs via the Dedalus AI Agents API (`dedalus_labs`) to judge your attempt.

---

## Running the Game

1. Navigate to the game directory:
   ```bash
   cd "AI Troll Game"
   ```

2. Make sure you have your `DEDALUS_API_KEY` in `AI Troll Game/.env`:
   ```env
   DEDALUS_API_KEY=your_dedalus_api_key_here
   ```

3. Run the application:
   ```bash
   uv run main.py
   ```

> **Note**: `uv` automatically manages dependencies from `pyproject.toml` and populates the virtual environment. On startup, the game provisions a fresh Dedalus Machine, deploys the FastAPI server, exposes an HTTPS preview tunnel, and connects over HTTP (`httpx`).

---

## Architecture

```
                       HTTP (httpx)                  Dedalus Agents API
main.py & games.py  ───────────────────▶  server.py  ───────────────────▶  LLM
(Pygame Engine &                          (FastAPI on                       (Structured Output
 UI Handlers)                              Dedalus Machine)                  JSON Verdict)
```

- **`main.py`**: The Pygame client entry point. Manages window rendering, frame loop, state transitions, wheel spinner, and background task execution.
- **`games.py`**: Consolidated mini-game module. Contains all riddle banks, trivia questions, card drawing logic, rock-paper-scissors rules, and the 6 mini-game UI handlers.
- **`agent.py`**: HTTP client wrapper (`TrollBrain` and `AIAgent`) that communicates with the troll brain server's `/judge` endpoint.
- **`provision.py`**: Top-level Dedalus Machine manager. Destroys existing machines on the account, creates a fresh VM, deploys `server_setup/`, executes `setup.sh`, exposes the HTTPS preview port, and verifies server health.
- **`server_setup/server.py`**: The troll's FastAPI server deployed to the VM. Exposes `/health` and `/judge` endpoints, querying Dedalus AI via structured JSON schema (`response_format` with `strict: True`).
- **`server_setup/setup.sh`**: VM startup script that installs Python dependencies (`fastapi`, `uvicorn`, `dedalus-labs`, `pydantic`) and registers a systemd service.
- **`server_setup/system_prompt.md`**: System prompt defining the troll's grumpy, bridge-guarding persona.

---

## The Mini-Games

| Mini-game | Description | Verdict |
|---|---|---|
| **Riddle Duel** | The troll poses a riddle. Type your answer. | Auto - checked locally with fuzzy matching |
| **Trivia Gate** | The troll asks a themed trivia question. Type your answer. | Auto - checked locally with fuzzy matching |
| **Rock-Paper-Troll** | Best-of-three rock-paper-scissors match. | Auto - checked locally |
| **Reflex Gauntlet** | Wait for the troll's signal, then press **SPACE** lightning fast. | Auto - reaction timing checked locally |
| **Card of Courage** | Draw a card; the higher the rank, the scarier the story you must type in 30s. | **AI Judged** - evaluated by troll's AI brain on Dedalus |
| **Joke Toll** | Type a joke to try to make the troll laugh in 30s. | **AI Judged** - evaluated by troll's AI brain on Dedalus |

Win the challenge and the troll grumbles and steps aside, letting you cross. Lose and you get shoved back for another attempt with a fresh mini-game.

---

## Environment Variables

Read from `.env` in `AI Troll Game/`:

- `DEDALUS_API_KEY` (**Required**): API key used for VM provisioning and querying the Dedalus AI agent.
- `DEDALUS_CHAT_MODEL` (*Optional*, default: `openai/gpt-4o-mini`): LLM model used by the server for judging subjective attempts.

---

## Controls

- **ENTER**: Confirm wheel land / submit typed text
- **Letter & Number keys**: Type text input for riddles, trivia, stories, or jokes
- **BACKSPACE**: Delete typed text
- **1 / 2 / 3**: Select Rock (1), Paper (2), or Scissors (3) in Rock-Paper-Troll
- **SPACE**: Reaction trigger in Reflex Gauntlet
- **ESC**: Quit game

---

## Project Layout

```
ai_games/
├── README.md                     # Project documentation
└── AI Troll Game/
    ├── main.py                   # Pygame client engine & UI loop
    ├── games.py                  # Consolidated game data & mini-game handlers
    ├── agent.py                  # Dedalus HTTP client & API key manager
    ├── provision.py              # Top-level Dedalus Machine provisioner
    ├── pyproject.toml            # Client dependencies (pygame, httpx, etc.)
    ├── .env                      # DEDALUS_API_KEY (gitignored)
    ├── server_setup/
    │   ├── server.py             # FastAPI server running Dedalus AI agent
    │   ├── setup.sh              # Remote VM deployment script
    │   └── system_prompt.md      # Troll persona prompt
    └── assets/
        ├── troll.png             # Troll sprite
        ├── brooklyn-bridge-4.jpg # Background art
        └── fonts/
            └── PressStart2P.ttf  # Retro pixel font
```
