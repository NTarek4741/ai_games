"""Single consolidated mini-games module for Troll Bridge Game.

Contains:
1. Pure game data, card logic, riddle & trivia banks, RPS & reflex rules.
2. All 6 mini-game UI handler classes (RiddleDuelGame, TriviaGateGame,
   RockPaperTrollGame, ReflexGauntletGame, CardOfCourageGame, JokeTollGame).
"""

import difflib
import random
import re
import time
from dataclasses import dataclass, field

import pygame

# ---------------------------------------------------------------------------
# Catalog & Data Definitions
# ---------------------------------------------------------------------------


@dataclass
class GameInfo:
    key: str
    title: str
    verdict_kind: str  # "auto" or "ai"
    input_mode: str  # "text" | "choice" | "timing"
    briefing: str


GAMES = {
    "riddle_duel": GameInfo(
        key="riddle_duel",
        title="Riddle Duel",
        verdict_kind="auto",
        input_mode="text",
        briefing="The troll clears its throat and poses a riddle. Type your answer!",
    ),
    "card_of_courage": GameInfo(
        key="card_of_courage",
        title="Card of Courage",
        verdict_kind="ai",
        input_mode="text",
        briefing="The troll produces a deck of cards. Draw one - the higher it is, the scarier your story must be.",
    ),
    "rock_paper_troll": GameInfo(
        key="rock_paper_troll",
        title="Rock-Paper-Troll",
        verdict_kind="auto",
        input_mode="choice",
        briefing="The troll raises a fist. Best of three, rock-paper-scissors!",
    ),
    "reflex_gauntlet": GameInfo(
        key="reflex_gauntlet",
        title="Reflex Gauntlet",
        verdict_kind="auto",
        input_mode="timing",
        briefing="The troll says it will shout when it's time. Wait for it... then be lightning fast.",
    ),
    "joke_toll": GameInfo(
        key="joke_toll",
        title="Joke Toll",
        verdict_kind="ai",
        input_mode="text",
        briefing="The troll crosses its arms. 'Make me laugh, or you're not getting past.'",
    ),
    "trivia_gate": GameInfo(
        key="trivia_gate",
        title="Trivia Gate",
        verdict_kind="auto",
        input_mode="text",
        briefing="The troll straightens up like a quiz show host and asks you a question.",
    ),
}

GAME_KEYS = list(GAMES.keys())


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def answer_matches(answer: str, accepted: list[str]) -> bool:
    """Fuzzy answer matching for riddles and trivia."""
    normalized = _normalize(answer)
    if not normalized:
        return False
    for candidate in accepted:
        norm_candidate = _normalize(candidate)
        if not norm_candidate:
            continue
        if norm_candidate in normalized or normalized in norm_candidate:
            return True
        if difflib.SequenceMatcher(None, normalized, norm_candidate).ratio() >= 0.72:
            return True
    return False


@dataclass
class QA:
    question: str
    answers: list[str] = field(default_factory=list)


RIDDLES = [
    QA("I speak without a mouth and hear without ears. I have no body, but I come alive with wind. What am I?", ["echo"]),
    QA("What has to be broken before you can use it?", ["egg"]),
    QA("What has many keys but can't open a single lock?", ["piano", "keyboard"]),
    QA("I am always hungry and must always be fed. The finger I touch will soon turn red. What am I?", ["fire"]),
    QA("What can travel around the world while staying in a corner?", ["stamp", "postage stamp"]),
    QA("The more you take, the more you leave behind. What am I?", ["footsteps"]),
    QA("What has a heart that doesn't beat?", ["artichoke"]),
    QA("What gets wetter the more it dries?", ["towel"]),
    QA("I have cities but no houses, forests but no trees, rivers but no water. What am I?", ["map"]),
    QA("What is so fragile that saying its name breaks it?", ["silence"]),
    QA("What has a neck but no head?", ["bottle"]),
    QA("What goes up but never comes down?", ["age", "your age"]),
]

TRIVIA = [
    QA("In Norwegian folklore, what kind of structure do trolls famously guard?", ["bridge", "bridges"]),
    QA("What do you traditionally need three of to satisfy a fairy-tale troll: goats, coins, or riddles?", ["goats", "billy goats"]),
    QA("What is the tough, springy material used to build old rope suspension bridges called?", ["rope", "hemp rope", "cable"]),
    QA("Which sense would you lose first standing in total darkness under a bridge: sight or smell?", ["sight"]),
    QA("In chess, what is the only piece that can jump over other pieces?", ["knight"]),
    QA("What do you call a story passed down by word of mouth, exactly like a troll's legend?", ["folklore", "legend", "myth"]),
    QA("How many sides does a standard die have?", ["6", "six"]),
    QA("What metal, said to repel trolls and fae, is a horseshoe traditionally made of?", ["iron"]),
    QA("What is the term for a bridge that can be raised to let ships pass?", ["drawbridge"]),
]

CARD_RANKS = [
    ("2", 2), ("3", 3), ("4", 4), ("5", 5), ("6", 6), ("7", 7), ("8", 8),
    ("9", 9), ("10", 10), ("Jack", 11), ("Queen", 12), ("King", 13), ("Ace", 14)
]
CARD_SUITS = ["Spades", "Hearts", "Diamonds", "Clubs"]
FEAR_TIERS = [
    (6, "Mild", "a lightly spooky tale, a creaky floorboard or a jump-scare cat will do"),
    (9, "Spooky", "a proper spooky story with real tension and atmosphere"),
    (12, "Terrifying", "a genuinely frightening tale that would keep the troll up at night"),
    (14, "Nightmare", "an absolutely bone-chilling nightmare of a story, the worst thing imaginable"),
]


@dataclass
class CardDraw:
    rank: str
    suit: str
    value: int
    tier: str
    tier_description: str

    @property
    def label(self) -> str:
        return f"{self.rank} of {self.suit}"


def draw_card() -> CardDraw:
    rank, value = random.choice(CARD_RANKS)
    suit = random.choice(CARD_SUITS)
    tier, tier_description = next(
        (label, desc) for threshold, label, desc in FEAR_TIERS if value <= threshold
    )
    return CardDraw(
        rank=rank, suit=suit, value=value, tier=tier, tier_description=tier_description
    )


RPS_CHOICES = ["rock", "paper", "scissors"]
RPS_BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
RPS_LABELS = {"rock": "ROCK", "paper": "PAPER", "scissors": "SCISSORS"}
RPS_ROUNDS_TO_WIN = 2


def rps_round(player_choice: str) -> tuple[str, str]:
    troll_choice = random.choice(RPS_CHOICES)
    if player_choice == troll_choice:
        outcome = "draw"
    elif RPS_BEATS[player_choice] == troll_choice:
        outcome = "win"
    else:
        outcome = "lose"
    return troll_choice, outcome


REFLEX_MIN_DELAY = 1.2
REFLEX_MAX_DELAY = 3.5
REFLEX_WINDOW = 0.5
SPEAKING_TIME_LIMIT = 30  # seconds


# ---------------------------------------------------------------------------
# Mini-game Handlers
# ---------------------------------------------------------------------------


class RiddleDuelGame:
    def __init__(self, main_engine):
        self.engine = main_engine
        self.qa = None

    def start(self):
        self.qa = random.choice(RIDDLES)
        self.engine.game_ctx["qa"] = self.qa

    def handle_key(self, event):
        self.engine._handle_typing(event, self.resolve)

    def update(self):
        pass

    def resolve(self):
        if not self.qa:
            return
        correct = answer_matches(self.engine.text_input, self.qa.answers)
        self.engine.correct_answer = self.qa.answers[0]
        if correct:
            self.engine.win("Correct! The troll grumbles and steps aside.")
        else:
            self.engine.lose(f"Wrong! The answer was '{self.qa.answers[0]}'.")

    def render(self, x: int, y: int, w: int):
        self.engine.small_font.render_to(self.engine.screen, (x, y), "RIDDLE DUEL", self.engine.ACCENT_COLOR)
        if self.qa:
            lines = self.engine.wrap_text(self.engine.font, self.qa.question, w)
            for i, line in enumerate(lines):
                self.engine.font.render_to(
                    self.engine.screen, (x, self.engine.BODY_Y + i * self.engine.LINE_HEIGHT), line, self.engine.TEXT_COLOR
                )
        self.engine.draw_text_input(x, self.engine.INPUT_Y, w)


class TriviaGateGame:
    def __init__(self, main_engine):
        self.engine = main_engine
        self.qa = None

    def start(self):
        self.qa = random.choice(TRIVIA)
        self.engine.game_ctx["qa"] = self.qa

    def handle_key(self, event):
        self.engine._handle_typing(event, self.resolve)

    def update(self):
        pass

    def resolve(self):
        if not self.qa:
            return
        correct = answer_matches(self.engine.text_input, self.qa.answers)
        self.engine.correct_answer = self.qa.answers[0]
        if correct:
            self.engine.win("Correct! The troll grumbles and steps aside.")
        else:
            self.engine.lose(f"Wrong! The answer was '{self.qa.answers[0]}'.")

    def render(self, x: int, y: int, w: int):
        self.engine.small_font.render_to(self.engine.screen, (x, y), "TRIVIA GATE", self.engine.ACCENT_COLOR)
        if self.qa:
            lines = self.engine.wrap_text(self.engine.font, self.qa.question, w)
            for i, line in enumerate(lines):
                self.engine.font.render_to(
                    self.engine.screen, (x, self.engine.BODY_Y + i * self.engine.LINE_HEIGHT), line, self.engine.TEXT_COLOR
                )
        self.engine.draw_text_input(x, self.engine.INPUT_Y, w)


class RockPaperTrollGame:
    def __init__(self, main_engine):
        self.engine = main_engine
        self.wins = {"player": 0, "troll": 0}
        self.last_round = None
        self.message_until = 0.0

    def start(self):
        self.wins = {"player": 0, "troll": 0}
        self.last_round = None
        self.message_until = 0.0

    def handle_key(self, event):
        if time.time() < self.message_until:
            return
        choice = None
        if event.key in (pygame.K_1, pygame.K_KP1):
            choice = "rock"
        elif event.key in (pygame.K_2, pygame.K_KP2):
            choice = "paper"
        elif event.key in (pygame.K_3, pygame.K_KP3):
            choice = "scissors"

        if choice is None:
            return

        troll_choice, outcome = rps_round(choice)
        if outcome == "win":
            self.wins["player"] += 1
        elif outcome == "lose":
            self.wins["troll"] += 1

        self.last_round = (choice, troll_choice, outcome)
        self.message_until = time.time() + 1.3

        if self.wins["player"] >= RPS_ROUNDS_TO_WIN:
            self.engine.win("You out-threw the troll, fair and square.")
        elif self.wins["troll"] >= RPS_ROUNDS_TO_WIN:
            self.engine.lose("The troll out-threw you.")

    def update(self):
        pass

    def render(self, x: int, y: int, w: int):
        self.engine.small_font.render_to(self.engine.screen, (x, y), "ROCK-PAPER-TROLL", self.engine.ACCENT_COLOR)
        self.engine.font.render_to(
            self.engine.screen,
            (x, self.engine.BODY_Y),
            f"YOU: {self.wins['player']}   TROLL: {self.wins['troll']}   (FIRST TO {RPS_ROUNDS_TO_WIN} WINS)",
            self.engine.TEXT_COLOR,
        )

        if self.last_round and time.time() < self.message_until:
            player_choice, troll_choice, outcome = self.last_round
            verb = {"win": "beats", "lose": "loses to", "draw": "ties with"}[outcome]
            msg = f"You picked {RPS_LABELS[player_choice]}, troll picked {RPS_LABELS[troll_choice]} - you {verb} it!"
            color = self.engine.GOOD_COLOR if outcome == "win" else self.engine.BAD_COLOR if outcome == "lose" else self.engine.DIM_COLOR
            for i, line in enumerate(self.engine.wrap_text(self.engine.font, msg, w)):
                self.engine.font.render_to(
                    self.engine.screen, (x, self.engine.BODY_Y + 32 + i * self.engine.LINE_HEIGHT), line, color
                )
        else:
            self.engine.small_font.render_to(
                self.engine.screen,
                (x, self.engine.PROMPT_Y),
                "1 = ROCK   2 = PAPER   3 = SCISSORS",
                self.engine.DIM_COLOR,
            )


class ReflexGauntletGame:
    def __init__(self, main_engine):
        self.engine = main_engine
        self.go_time = None
        self.deadline = None
        self.shown_at = None
        self.phase = "WAIT"

    def start(self):
        delay = random.uniform(REFLEX_MIN_DELAY, REFLEX_MAX_DELAY)
        self.go_time = time.time() + delay
        self.deadline = None
        self.shown_at = None
        self.phase = "WAIT"

    def handle_key(self, event):
        if event.key != pygame.K_SPACE:
            return
        if self.phase == "WAIT":
            self.engine.lose("Too eager! You flinched before the troll even said a word.")
        elif self.phase == "GO":
            reaction = time.time() - self.shown_at
            if reaction <= REFLEX_WINDOW:
                self.engine.win(f"Lightning fast! You reacted in {reaction:.2f}s.")
            else:
                self.engine.lose(f"Too slow ({reaction:.2f}s). The troll cackles.")

    def update(self):
        if self.phase == "WAIT" and self.go_time and time.time() >= self.go_time:
            self.phase = "GO"
            self.shown_at = time.time()
            self.deadline = self.shown_at + REFLEX_WINDOW
        elif self.phase == "GO" and self.deadline and time.time() > self.deadline:
            self.engine.lose("Too slow. You never even moved.")

    def render(self, x: int, y: int, w: int):
        self.engine.small_font.render_to(self.engine.screen, (x, y), "REFLEX GAUNTLET", self.engine.ACCENT_COLOR)
        if self.phase == "WAIT":
            self.engine.draw_centered(self.engine.medium_font, "WAIT FOR IT...", self.engine.BODY_Y + 40, self.engine.DIM_COLOR)
        else:
            self.engine.draw_centered(self.engine.big_font, "NOW! PRESS SPACE!", self.engine.BODY_Y + 24, self.engine.BAD_COLOR)


class CardOfCourageGame:
    def __init__(self, main_engine):
        self.engine = main_engine
        self.phase = "PROMPT"
        self.speak_deadline = None
        self.drawn_card = None

    def start(self):
        self.phase = "PROMPT"
        self.speak_deadline = None
        self.drawn_card = None

    def handle_key(self, event):
        if self.phase == "PROMPT":
            if event.key == pygame.K_RETURN:
                card = draw_card()
                self.drawn_card = card
                self.engine.game_ctx = {
                    "label": card.label,
                    "tier": card.tier,
                    "tier_description": card.tier_description,
                }
                self.speak_deadline = time.time() + SPEAKING_TIME_LIMIT
                self.phase = "STORY_INPUT"
        elif self.phase == "STORY_INPUT":
            self.engine._handle_typing(event, self.submit)

    def update(self):
        if self.phase == "STORY_INPUT" and self.speak_deadline and time.time() >= self.speak_deadline:
            self.submit()
            self.speak_deadline = None

    def submit(self):
        submission_text = self.engine.text_input
        self.engine.submit_story_or_joke("card_of_courage", submission_text)

    def render(self, x: int, y: int, w: int):
        self.engine.small_font.render_to(self.engine.screen, (x, y), "CARD OF COURAGE", self.engine.ACCENT_COLOR)
        if self.phase == "PROMPT":
            for i, line in enumerate(
                self.engine.wrap_text(self.engine.font, GAMES["card_of_courage"].briefing, w)
            ):
                self.engine.font.render_to(
                    self.engine.screen, (x, self.engine.BODY_Y + i * self.engine.LINE_HEIGHT), line, self.engine.TEXT_COLOR
                )
            self.engine.small_font.render_to(
                self.engine.screen, (x, self.engine.PROMPT_Y), "PRESS ENTER TO DRAW", self.engine.ACCENT_COLOR
            )
        else:
            ctx = self.engine.game_ctx
            headline = f"YOU DREW THE {ctx['label'].upper()}! FEAR TIER: {ctx['tier'].upper()}"
            self.engine.small_font.render_to(self.engine.screen, (x, self.engine.BODY_Y), headline, self.engine.ACCENT_COLOR)
            desc_lines = self.engine.wrap_text(
                self.engine.small_font, f"Tell a story that is {ctx['tier_description']}.", w
            )
            for i, line in enumerate(desc_lines):
                self.engine.small_font.render_to(
                    self.engine.screen,
                    (x, self.engine.BODY_Y + self.engine.SMALL_LINE_HEIGHT + 4 + i * self.engine.SMALL_LINE_HEIGHT),
                    line,
                    self.engine.DIM_COLOR,
                )
            self.engine.draw_text_input(x, self.engine.INPUT_Y, w)


class JokeTollGame:
    def __init__(self, main_engine):
        self.engine = main_engine
        self.speak_deadline = None

    def start(self):
        self.speak_deadline = time.time() + SPEAKING_TIME_LIMIT

    def handle_key(self, event):
        self.engine._handle_typing(event, self.submit)

    def update(self):
        if self.speak_deadline and time.time() >= self.speak_deadline:
            self.submit()
            self.speak_deadline = None

    def submit(self):
        submission_text = self.engine.text_input
        self.engine.submit_story_or_joke("joke_toll", submission_text)

    def render(self, x: int, y: int, w: int):
        self.engine.small_font.render_to(self.engine.screen, (x, y), "JOKE TOLL", self.engine.ACCENT_COLOR)
        for i, line in enumerate(
            self.engine.wrap_text(self.engine.font, GAMES["joke_toll"].briefing, w)
        ):
            self.engine.font.render_to(
                self.engine.screen, (x, self.engine.BODY_Y + i * self.engine.LINE_HEIGHT), line, self.engine.TEXT_COLOR
            )
        self.engine.draw_text_input(x, self.engine.INPUT_Y, w)
