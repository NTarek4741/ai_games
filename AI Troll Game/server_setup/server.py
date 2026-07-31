"""FastAPI server running the troll AI agent on a Dedalus Machine.

Exposes `/judge` endpoint where the agent evaluates traveler attempts
using structured JSON output for reliable verdicts.
"""

import json
import os
from pathlib import Path

import uvicorn
from dedalus_labs import AsyncDedalus
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()

API_KEY = os.environ.get("DEDALUS_API_KEY", "")
CHAT_MODEL = os.environ.get("DEDALUS_CHAT_MODEL", "openai/gpt-4o-mini")
SYSTEM_PROMPT = (Path(__file__).parent / "system_prompt.md").read_text(encoding="utf-8")
STRUCTURED_OUTPUT_ATTEMPTS = 3

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {
            "type": "boolean",
            "description": "True if the traveler's attempt earns them passage.",
        },
        "reason": {
            "type": "string",
            "description": "One or two grumpy, in-character sentences explaining the verdict.",
        },
    },
    "required": ["passed", "reason"],
    "additionalProperties": False,
}


def verify_auth(authorization: str = Header(...)):
    if not authorization.startswith("Bearer ") or authorization[7:] != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid token")
    return authorization[7:]


class JudgeRequest(BaseModel):
    game_key: str
    context: dict = {}
    submission: str = ""


async def _structured_completion(*, system: str, user: str) -> dict | None:
    """Ask the model for JSON matching the verdict schema, retrying on failure."""
    client = AsyncDedalus(api_key=API_KEY)
    for _ in range(STRUCTURED_OUTPUT_ATTEMPTS):
        completion = await client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "verdict", "schema": VERDICT_SCHEMA, "strict": True},
            },
            max_tokens=400,
        )
        content = completion.choices[0].message.content
        if content:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                pass
    return None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/judge")
async def judge(req: JudgeRequest, _: str = Depends(verify_auth)):
    if req.game_key == "card_of_courage":
        instructions = (
            f"The traveler drew the {req.context.get('label', 'card')}, which demands a "
            f"'{req.context.get('tier', 'spooky')}' story: {req.context.get('tier_description', '')}. "
            "Judge whether their story clears that bar. Be a little tough but fair."
        )
    elif req.game_key == "joke_toll":
        instructions = (
            "Judge whether the traveler's joke is funny enough to earn passage. "
            "Be a little tough but fair - groan-worthy puns can still count if they commit to it."
        )
    else:
        instructions = "Judge whether the traveler's attempt satisfies the challenge. Be a little tough but fair."

    data = await _structured_completion(
        system=f"{SYSTEM_PROMPT}\n\n{instructions}",
        user=req.submission.strip() or "(the traveler stood there and said nothing at all)",
    )
    if data and "passed" in data:
        reason = str(data.get("reason") or "").strip() or "The troll grunts noncommittally."
        return {"passed": bool(data["passed"]), "reason": reason}
    raise HTTPException(status_code=502, detail="The troll could not reach a verdict")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
