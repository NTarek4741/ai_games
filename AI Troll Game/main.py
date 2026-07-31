"""Troll Bridge Game

A troll blocks an old bridge. To cross, you must beat whatever challenge the
troll's AI brain (Dedalus) decides to throw at you: a riddle, a scary story
judged for nerve, a round of rock-paper-scissors, a reflex test, a joke, or
a trivia question. Win the mini-game and you cross the bridge; lose and the
troll shoves you back for another try.

Run it with:
    uv run main.py
"""

import math
import random
import sys
import threading
import time
from pathlib import Path

import pygame
import pygame.freetype

import games
from agent import AIAgent
from games import (
    CardOfCourageGame,
    JokeTollGame,
    ReflexGauntletGame,
    RiddleDuelGame,
    RockPaperTrollGame,
    TriviaGateGame,
)

GAME_DIR = Path(__file__).resolve().parent

RETRY_DELAY_SECONDS = 2.5

WIDTH, HEIGHT = 900, 680
FPS = 60

# Retro pixel-art look -------------------------------------------------------
FONT_PATH = GAME_DIR / "assets" / "fonts" / "PressStart2P.ttf"
FONT_SIZE_SMALL = 8
FONT_SIZE_BODY = 12
FONT_SIZE_MEDIUM = 16
FONT_SIZE_BIG = 24
LINE_HEIGHT = 24  # vertical step between wrapped body-text lines
SMALL_LINE_HEIGHT = 18  # vertical step between wrapped small-text lines
TROLL_PIXEL_FACTOR = 4  # downscale factor used to pixelate the troll sprite
SCANLINE_SPACING = 3  # draw one dark row every N pixels
SCANLINE_ALPHA = 26  # darkness of each scanline row (0-255)

# Dialog-panel layout (old-school RPG text box along the bottom) -------------
PANEL_MARGIN = 20
PANEL_HEIGHT = 200
PANEL_BOTTOM = 14
PANEL_X = PANEL_MARGIN
PANEL_W = WIDTH - 2 * PANEL_MARGIN
PANEL_Y = HEIGHT - PANEL_HEIGHT - PANEL_BOTTOM
PANEL_PAD = 24
CONTENT_X = PANEL_X + PANEL_PAD
CONTENT_Y = PANEL_Y + 20
CONTENT_W = PANEL_W - 2 * PANEL_PAD
BODY_Y = CONTENT_Y + 26  # first body-text row, below the small title row
INPUT_BOX_H = 36
INPUT_Y = PANEL_Y + PANEL_HEIGHT - 20 - INPUT_BOX_H  # text box, bottom-anchored
TIMER_Y = INPUT_Y - 24  # countdown row sitting just above the text box
PROMPT_Y = INPUT_Y + 10  # "PRESS ENTER ..." hints share the bottom row

# Troll sprite: big and centered in the open area above the dialog panel -----
TROLL_MAX_W = 760
TROLL_MAX_H = PANEL_Y - 24
TROLL_BOTTOM_Y = PANEL_Y + 30  # feet overlap the panel top edge a little

WHEEL_CENTER = (WIDTH // 2, HEIGHT // 2 - 30)
WHEEL_RADIUS = 170
WHEEL_SPIN_SECONDS = 3.2
WHEEL_MIN_SPINS = 4
WHEEL_MAX_SPINS = 6
WHEEL_COLORS = [
    (198, 60, 60),
    (60, 130, 198),
    (70, 170, 100),
    (205, 150, 40),
    (150, 80, 190),
    (45, 175, 175),
]

TEXT_COLOR = (245, 245, 245)
DIM_COLOR = (190, 190, 200)
ACCENT_COLOR = (255, 205, 60)
GOOD_COLOR = (120, 230, 140)
BAD_COLOR = (235, 90, 90)
PANEL_RGBA = (14, 14, 30, 232)
BORDER_COLOR = (230, 230, 210)
INPUT_BG_RGBA = (255, 255, 255, 28)

GREETING_LINES = [
    "Halt! None shall cross this bridge without besting me first.",
    "Well, well, another traveler foolish enough to try their luck.",
    "You want to cross? Ha! You'll have to earn it.",
    "Stop right there. This bridge belongs to me.",
    "Another one? Fine. Let's see what you've got.",
]

LOADING_MESSAGES = [
    "SPAWNING TROLL BRAIN",
    "CONNECTING TO DEDALUS MACHINE",
    "WAKING THE TROLL FROM SLUMBER",
    "PREPARING THE BRIDGE CHALLENGE",
    "ALMOST READY TO RUMBLE",
]


def load_image(path: Path):
    """Load an image file with alpha, returning None if it is missing/broken."""
    if path.exists():
        try:
            return pygame.image.load(str(path)).convert_alpha()
        except Exception as exc:
            print(f"Could not load {path.name}: {exc}")
    return None


def scale_to_cover(surface, target_w, target_h):
    """Scale (and center-crop) a surface so it fully covers target_w x target_h."""
    sw, sh = surface.get_size()
    scale = max(target_w / sw, target_h / sh)
    new_w, new_h = round(sw * scale), round(sh * scale)
    scaled = pygame.transform.smoothscale(surface, (new_w, new_h))
    x = (new_w - target_w) // 2
    y = (new_h - target_h) // 2
    return scaled.subsurface((x, y, target_w, target_h)).copy()


def scale_to_fit(surface, max_w, max_h):
    """Scale a surface down (or up) so it fits inside max_w x max_h."""
    sw, sh = surface.get_size()
    scale = min(max_w / sw, max_h / sh)
    return pygame.transform.smoothscale(surface, (round(sw * scale), round(sh * scale)))


def pixelate(surface, factor):
    """Give a surface chunky old-school pixels by shrinking then re-enlarging it."""
    w, h = surface.get_size()
    small = pygame.transform.smoothscale(surface, (max(1, w // factor), max(1, h // factor)))
    return pygame.transform.scale(small, (w, h))


def make_scanlines(width, height):
    """Build the reusable CRT scanline overlay: a faint dark row every few pixels."""
    overlay = pygame.Surface((width, height), pygame.SRCALPHA)
    for y in range(0, height, SCANLINE_SPACING):
        overlay.fill((0, 0, 0, SCANLINE_ALPHA), (0, y, width, 1))
    return overlay


def wrap_text(font, text, max_width):
    """Word-wrap text into lines that each fit within max_width pixels."""
    words = text.split(" ")
    lines = []
    current = []
    for word in words:
        candidate = " ".join(current + [word])
        if current and font.get_rect(candidate).width > max_width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def tail_to_fit(font, text, max_width):
    """Return the longest suffix of text that fits within max_width pixels."""
    if not text:
        return ""
    for i in range(len(text)):
        if font.get_rect(text[i:]).width <= max_width:
            return text[i:]
    return ""


def load_font(size):
    """Load the bundled pixel font at the given size, with a system fallback."""
    if FONT_PATH.exists():
        return pygame.freetype.Font(str(FONT_PATH), size)
    return pygame.freetype.SysFont("Courier", size * 2, bold=True)


def load_scaled_background():
    """Load the bridge backdrop, scaled to cover the whole window (or None)."""
    image = load_image(GAME_DIR / "assets" / "brooklyn-bridge-4.jpg")
    return scale_to_cover(image, WIDTH, HEIGHT) if image else None


class AsyncTask:
    """Runs fn(*args, **kwargs) on a background thread so the game loop never blocks."""

    def __init__(self, fn, *args, **kwargs):
        """Start the background thread running fn immediately."""
        self.result = None
        self.error = None
        self.done = False
        self._thread = threading.Thread(
            target=self._run, args=(fn, args, kwargs), daemon=True
        )
        self._thread.start()

    def _run(self, fn, args, kwargs):
        """Execute fn, capturing its result or any exception it raised."""
        try:
            self.result = fn(*args, **kwargs)
        except Exception as exc:
            self.error = exc
        finally:
            self.done = True


class TrollBridgeGame:
    """Main game engine: manages window, assets, wheel, and mini-game routing."""

    def __init__(self, base_url: str, api_key: str):
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Troll Bridge Game")
        self.clock = pygame.time.Clock()

        # Layout constants exposed for mini-games
        self.TEXT_COLOR = TEXT_COLOR
        self.DIM_COLOR = DIM_COLOR
        self.ACCENT_COLOR = ACCENT_COLOR
        self.GOOD_COLOR = GOOD_COLOR
        self.BAD_COLOR = BAD_COLOR
        self.BODY_Y = BODY_Y
        self.LINE_HEIGHT = LINE_HEIGHT
        self.SMALL_LINE_HEIGHT = SMALL_LINE_HEIGHT
        self.INPUT_Y = INPUT_Y
        self.TIMER_Y = TIMER_Y
        self.PROMPT_Y = PROMPT_Y
        self.wrap_text = wrap_text

        self.font = load_font(FONT_SIZE_BODY)
        self.small_font = load_font(FONT_SIZE_SMALL)
        self.big_font = load_font(FONT_SIZE_BIG)
        self.medium_font = load_font(FONT_SIZE_MEDIUM)

        self._load_art()

        # AI Agent Client initialized via agent.py
        self.agent = AIAgent(base_url, api_key)

        # Initialize mini-game module instances
        self.games = {
            "riddle_duel": RiddleDuelGame(self),
            "trivia_gate": TriviaGateGame(self),
            "rock_paper_troll": RockPaperTrollGame(self),
            "reflex_gauntlet": ReflexGauntletGame(self),
            "card_of_courage": CardOfCourageGame(self),
            "joke_toll": JokeTollGame(self),
        }
        self.current_game_instance = None

        self.pending_task = None
        self.pending_task_factory = None
        self.brain_error = None
        self.retry_at = None
        self.reset_round()

    def _load_art(self):
        """Load backdrop, pixelated troll sprite, and CRT scanlines."""
        self.background = load_scaled_background()
        self.troll_image = None
        troll_raw = load_image(GAME_DIR / "assets" / "troll.png")
        if troll_raw:
            fitted = scale_to_fit(troll_raw, TROLL_MAX_W, TROLL_MAX_H)
            self.troll_image = pixelate(fitted, TROLL_PIXEL_FACTOR)
        self.scanlines = make_scanlines(WIDTH, HEIGHT)

    def reset_round(self):
        """Reset all per-round state back to the intro greeting."""
        self.state = "INTRO"
        self.troll_line = random.choice(GREETING_LINES)
        self.troll_alpha = 255
        self.troll_fading = False
        self.fade_speed = 6
        self.state_timer = 0

        self.current_game = None
        self.current_game_instance = None
        self.game_ctx = {}
        self.text_input = ""
        self.transcript = ""
        self.verdict_reason = ""
        self.correct_answer = None

        self.wheel_target_key = None
        self.wheel_angle = 0.0
        self.wheel_final_angle = 0.0
        self.wheel_spin_start = None

        self.pending_task = None
        self.pending_task_factory = None
        self.brain_error = None
        self.retry_at = None

    def begin_challenge(self):
        """Spin the wheel to randomly pick a mini-game."""
        self.state = "WHEEL_SPIN"
        self.wheel_target_key = random.choice(games.GAME_KEYS)
        n = len(games.GAME_KEYS)
        index = games.GAME_KEYS.index(self.wheel_target_key)
        sector = 360 / n
        landing_angle = (n - index) * sector - sector / 2
        spins = random.randint(WHEEL_MIN_SPINS, WHEEL_MAX_SPINS)
        self.wheel_final_angle = 360 * spins + landing_angle
        self.wheel_angle = 0.0
        self.wheel_spin_start = time.time()

    def launch_task(self, fn, *args, **kwargs):
        """Run fn(*args, **kwargs) on background thread with auto-retry."""
        self.pending_task_factory = lambda: AsyncTask(fn, *args, **kwargs)
        self.pending_task = self.pending_task_factory()
        self.brain_error = None
        self.retry_at = None

    def start_game(self, key):
        """Start the selected mini-game module."""
        self.current_game = key
        self.game_ctx = {}
        self.text_input = ""
        self.transcript = ""
        self.verdict_reason = ""
        self.correct_answer = None

        self.current_game_instance = self.games[key]
        self.state = "PLAYING_MINIGAME"
        self.current_game_instance.start()

    def win(self, reason=""):
        """Enter WIN state: show reason and fade out troll."""
        self.verdict_reason = reason
        self.state = "WIN"
        self.state_timer = 0
        self.troll_fading = True

    def lose(self, reason=""):
        """Enter LOSE state: show reason and wait for retry."""
        self.verdict_reason = reason
        self.state = "LOSE"
        self.state_timer = 0

    def submit_story_or_joke(self, game_key: str, text: str):
        """Send story or joke submission to AI Agent via agent.py data handler."""
        self.transcript = (text or "").strip()
        self.state = "AWAITING_VERDICT"
        self.launch_task(
            self.agent.process_judgment_response,
            game_key,
            dict(self.game_ctx),
            self.transcript,
        )

    def handle_events(self):
        """Pump event queue."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and not self._handle_key(event):
                return False
        return True

    def _handle_key(self, event):
        """Route keys to global state or active mini-game instance."""
        if event.key == pygame.K_ESCAPE:
            return False

        if self.state == "INTRO":
            if event.key == pygame.K_RETURN:
                self.begin_challenge()
        elif self.state == "WHEEL_RESULT":
            if event.key == pygame.K_RETURN:
                self.start_game(self.wheel_target_key)
        elif self.state == "PLAYING_MINIGAME" and self.current_game_instance:
            self.current_game_instance.handle_key(event)
        elif self.state in ("WIN", "LOSE") and self.state_timer > 20:
            self.reset_round()

        return True

    def _handle_typing(self, event, submit_callback):
        """Utility for text input typing inside mini-games."""
        if event.key == pygame.K_RETURN:
            if self.text_input.strip():
                submit_callback()
        elif event.key == pygame.K_BACKSPACE:
            self.text_input = self.text_input[:-1]
        elif event.unicode and event.unicode.isprintable():
            self.text_input += event.unicode

    def update(self):
        """Advance time-based state and active mini-game per frame."""
        self.state_timer += 1
        self._update_wheel()
        self._update_pending_task()
        self._update_troll_fade()

        if self.state == "PLAYING_MINIGAME" and self.current_game_instance:
            self.current_game_instance.update()

    def _update_wheel(self):
        """Ease wheel rotation."""
        if self.state != "WHEEL_SPIN":
            return
        elapsed = time.time() - self.wheel_spin_start
        t = min(1.0, elapsed / WHEEL_SPIN_SECONDS)
        eased = 1 - (1 - t) ** 3
        self.wheel_angle = self.wheel_final_angle * eased
        if t >= 1.0:
            self.state = "WHEEL_RESULT"

    def _update_pending_task(self):
        """Check AI background task status."""
        if self.pending_task and self.pending_task.done:
            self.resolve_pending_task()
        elif (
            self.pending_task is None and self.retry_at and time.time() >= self.retry_at
        ):
            self.retry_at = None
            self.pending_task = self.pending_task_factory()

    def _update_troll_fade(self):
        """Fade troll sprite on win."""
        if self.troll_fading:
            self.troll_alpha = max(0, self.troll_alpha - self.fade_speed)
            if self.troll_alpha == 0:
                self.troll_fading = False

    def resolve_pending_task(self):
        """Apply finished AI Agent response result from agent.py."""
        task = self.pending_task
        self.pending_task = None

        if task.error:
            print(f"[agent_client] request failed, retrying: {task.error}")
            self.brain_error = str(task.error)
            self.retry_at = time.time() + RETRY_DELAY_SECONDS
            return

        self.brain_error = None

        if self.state == "AWAITING_VERDICT":
            passed, reason = task.result
            if passed:
                self.win(reason)
            else:
                self.lose(reason)

    def draw(self):
        """Render frame: background, wheel/troll, dialog panel, scanlines."""
        self._draw_background()
        if self.state in ("WHEEL_SPIN", "WHEEL_RESULT"):
            self.draw_wheel_overlay()
        else:
            self.draw_troll()
            self.draw_panel()
        self._draw_scanlines()
        pygame.display.flip()

    def _draw_background(self):
        if self.background:
            self.screen.blit(self.background, (0, 0))
        else:
            self.screen.fill((110, 150, 200))

    def _draw_scanlines(self):
        self.screen.blit(self.scanlines, (0, 0))

    def draw_centered(self, font, text, y, color):
        rect = font.get_rect(text)
        font.render_to(self.screen, (WIDTH // 2 - rect.width // 2, y), text, color)

    def draw_troll(self):
        if self.troll_alpha <= 0 or not self.troll_image:
            return
        self.troll_image.set_alpha(self.troll_alpha)
        rect = self.troll_image.get_rect(centerx=WIDTH // 2, bottom=TROLL_BOTTOM_Y)
        self.screen.blit(self.troll_image, rect)

    def draw_panel(self):
        panel = pygame.Surface((PANEL_W, PANEL_HEIGHT), pygame.SRCALPHA)
        panel.fill(PANEL_RGBA)
        pygame.draw.rect(panel, BORDER_COLOR, panel.get_rect(), 4)
        pygame.draw.rect(panel, BORDER_COLOR, panel.get_rect().inflate(-12, -12), 1)
        self.screen.blit(panel, (PANEL_X, PANEL_Y))

        if self.state == "INTRO":
            self.render_intro(CONTENT_X, CONTENT_Y, CONTENT_W)
        elif self.state == "PLAYING_MINIGAME" and self.current_game_instance:
            self.current_game_instance.render(CONTENT_X, CONTENT_Y, CONTENT_W)
        elif self.state == "AWAITING_VERDICT":
            self.render_waiting_on_brain(CONTENT_X, CONTENT_Y, CONTENT_W, "THE TROLL MULLS IT OVER")
        elif self.state == "WIN":
            self.render_win(CONTENT_X, CONTENT_Y, CONTENT_W)
        elif self.state == "LOSE":
            self.render_lose(CONTENT_X, CONTENT_Y, CONTENT_W)

    def render_intro(self, x, y, w):
        for i, line in enumerate(wrap_text(self.font, self.troll_line, w)):
            self.font.render_to(self.screen, (x, y + i * LINE_HEIGHT), line, TEXT_COLOR)
        self.small_font.render_to(
            self.screen,
            (x, PROMPT_Y),
            "PRESS ENTER TO SPIN THE WHEEL AND FACE THE TROLL'S CHALLENGE",
            ACCENT_COLOR,
        )

    def draw_wheel_overlay(self):
        dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        self.screen.blit(dim, (0, 0))

        self._draw_wheel_legend()
        self._draw_wheel_body()
        self._draw_wheel_pointer()
        self._draw_wheel_caption()

    def _draw_wheel_caption(self):
        if self.state == "WHEEL_RESULT":
            title = games.GAMES[self.wheel_target_key].title.upper()
            self.draw_centered(
                self.medium_font,
                f"THE WHEEL LANDS ON: {title}!",
                HEIGHT - 130,
                ACCENT_COLOR,
            )
            self.draw_centered(
                self.small_font, "PRESS ENTER TO BEGIN", HEIGHT - 92, DIM_COLOR
            )
        else:
            self.draw_centered(self.medium_font, "SPINNING...", HEIGHT - 110, DIM_COLOR)

    def _draw_wheel_body(self):
        cx, cy = WHEEL_CENTER
        r = WHEEL_RADIUS
        n = len(games.GAME_KEYS)
        sector = 360 / n
        angle = self.wheel_angle

        for i in range(n):
            start_a = math.radians(angle + i * sector)
            end_a = math.radians(angle + (i + 1) * sector)
            color = WHEEL_COLORS[i % len(WHEEL_COLORS)]
            steps = 12
            pts = [(cx, cy)]
            for s in range(steps + 1):
                a = start_a + (end_a - start_a) * (s / steps)
                pts.append((cx + r * math.sin(a), cy - r * math.cos(a)))
            pygame.draw.polygon(self.screen, color, pts)
            pygame.draw.polygon(self.screen, (255, 255, 255, 80), pts, 2)

        pygame.draw.circle(self.screen, (255, 255, 255), (cx, cy), r, 3)
        pygame.draw.circle(self.screen, (50, 50, 50), (cx, cy), 18)

    def _draw_wheel_pointer(self):
        cx, cy = WHEEL_CENTER
        r = WHEEL_RADIUS
        tip = (cx, cy - r - 6)
        left = (cx - 14, cy - r - 26)
        right = (cx + 14, cy - r - 26)
        pygame.draw.polygon(self.screen, (255, 220, 50), [tip, left, right])
        pygame.draw.polygon(self.screen, (0, 0, 0), [tip, left, right], 2)

    def _draw_wheel_legend(self):
        legend_x = WIDTH // 2 - 260
        legend_y = 26
        cols = 2
        item_w = 260
        row_h = 24
        for i, key in enumerate(games.GAME_KEYS):
            col = i % cols
            row = i // cols
            lx = legend_x + col * item_w
            ly = legend_y + row * row_h
            color = WHEEL_COLORS[i % len(WHEEL_COLORS)]
            pygame.draw.rect(self.screen, color, (lx, ly + 2, 14, 14))
            self.small_font.render_to(
                self.screen,
                (lx + 24, ly + 4),
                games.GAMES[key].title.upper(),
                DIM_COLOR,
            )

    def render_waiting_on_brain(self, x, y, w, label):
        dots = "." * (1 + (self.state_timer // 20) % 3)
        self.medium_font.render_to(
            self.screen, (x, y + 16), f"{label}{dots}", ACCENT_COLOR
        )
        if self.brain_error:
            lines = wrap_text(
                self.small_font,
                f"Lost contact with the troll's brain ({self.brain_error}) - retrying...",
                w,
            )
            for i, line in enumerate(lines):
                self.small_font.render_to(
                    self.screen, (x, y + 56 + i * SMALL_LINE_HEIGHT), line, BAD_COLOR
                )

    def draw_speaking_input(self, y, w, deadline):
        remaining = (
            max(0, int(deadline - time.time())) if deadline else 0
        )
        timer_color = BAD_COLOR if remaining <= 5 else ACCENT_COLOR
        self.small_font.render_to(
            self.screen, (CONTENT_X, y), f"TIME LEFT: {remaining}S", timer_color
        )
        hint = "TYPE YOUR ANSWER AND PRESS ENTER"
        hint_rect = self.small_font.get_rect(hint)
        self.small_font.render_to(
            self.screen, (CONTENT_X + w - hint_rect.width, y), hint, DIM_COLOR
        )
        self.draw_text_input(CONTENT_X, y + 22, w)

    def draw_text_input(self, x, y, w):
        box = pygame.Surface((w, INPUT_BOX_H), pygame.SRCALPHA)
        box.fill(INPUT_BG_RGBA)
        self.screen.blit(box, (x, y))
        pygame.draw.rect(self.screen, BORDER_COLOR, (x, y, w, INPUT_BOX_H), 2)
        cursor = "_" if (self.state_timer // 30) % 2 == 0 else " "
        shown = tail_to_fit(self.font, self.text_input + cursor, w - 20)
        self.font.render_to(
            self.screen,
            (x + 10, y + (INPUT_BOX_H - FONT_SIZE_BODY) // 2),
            shown,
            TEXT_COLOR,
        )

    def render_win(self, x, y, w):
        self.draw_centered(self.big_font, "YOU CROSSED THE BRIDGE!", y + 4, GOOD_COLOR)
        for i, line in enumerate(wrap_text(self.font, self.verdict_reason, w)):
            self.draw_centered(self.font, line, y + 52 + i * LINE_HEIGHT, TEXT_COLOR)
        if self.state_timer > 20:
            self.draw_centered(
                self.small_font, "PRESS ANY KEY TO PLAY AGAIN", PROMPT_Y, DIM_COLOR
            )

    def render_lose(self, x, y, w):
        self.draw_centered(self.big_font, "THE TROLL BLOCKS YOUR PATH!", y + 4, BAD_COLOR)
        for i, line in enumerate(wrap_text(self.font, self.verdict_reason, w)):
            self.draw_centered(self.font, line, y + 52 + i * LINE_HEIGHT, TEXT_COLOR)
        if self.state_timer > 20:
            self.draw_centered(
                self.small_font, "PRESS ANY KEY TO TRY AGAIN", PROMPT_Y, DIM_COLOR
            )

    def run(self):
        running = True
        while running:
            running = self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()


def print_console_banner():
    print("=" * 60)
    print("TROLL BRIDGE GAME")
    print("=" * 60)
    print()
    print("Spin the wheel to pick a random mini-game for the troll to challenge you with:")
    for game in games.GAMES.values():
        kind = "auto-verdict" if game.verdict_kind == "auto" else "troll judges"
        print(f"  - {game.title} ({kind})")
    print()
    print("Controls: ENTER to confirm, letters to type, ESC to quit.")
    print()


def run_loading_loop(screen, clock, provision_task):
    medium_font = load_font(FONT_SIZE_MEDIUM)
    small_font = load_font(FONT_SIZE_SMALL)
    background = load_scaled_background()
    scanlines = make_scanlines(WIDTH, HEIGHT)

    loading_angle = 0.0
    loading_timer = 0
    status_index = 0

    while not provision_task.done:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False

        loading_timer += 1
        loading_angle = (loading_angle + 2.0) % 360
        if loading_timer % 120 == 0:
            status_index = (status_index + 1) % len(LOADING_MESSAGES)

        draw_loading_screen(
            screen,
            medium_font,
            small_font,
            background,
            scanlines,
            loading_angle,
            loading_timer,
            LOADING_MESSAGES[status_index],
        )
        pygame.display.flip()
        clock.tick(FPS)

    return True


def draw_loading_screen(
    screen, medium_font, small_font, background, scanlines, angle, timer, status_text
):
    if background:
        screen.blit(background, (0, 0))
    else:
        screen.fill((110, 150, 200))

    dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 180))
    screen.blit(dim, (0, 0))

    center_x, center_y = WIDTH // 2, HEIGHT // 2 - 50
    radius = 60
    pygame.draw.circle(screen, (200, 200, 200), (center_x, center_y), radius, 3)
    arc_points = []
    for a in range(0, 121, 5):
        rad = math.radians(angle + a)
        arc_points.append(
            (center_x + radius * math.sin(rad), center_y - radius * math.cos(rad))
        )
    if len(arc_points) >= 2:
        pygame.draw.lines(screen, ACCENT_COLOR, False, arc_points, 6)
    pygame.draw.circle(screen, ACCENT_COLOR, (center_x, center_y), 8)

    text_rect = medium_font.get_rect(status_text)
    medium_font.render_to(
        screen,
        (WIDTH // 2 - text_rect.width // 2, HEIGHT // 2 + 30),
        status_text,
        TEXT_COLOR,
    )
    dots = "." * (1 + (timer // 20) % 3)
    dots_rect = small_font.get_rect(dots)
    small_font.render_to(
        screen,
        (WIDTH // 2 - dots_rect.width // 2, HEIGHT // 2 + 70),
        dots,
        DIM_COLOR,
    )

    screen.blit(scanlines, (0, 0))


def main():
    """Boot pygame, provision AI agent server via agent.py, start game."""
    pygame.init()
    pygame.freetype.init()

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Troll Bridge Game")
    clock = pygame.time.Clock()

    print_console_banner()

    print("Provisioning the troll's AI agent brain on a Dedalus Machine...")

    provision_task = AsyncTask(AIAgent.provision_server)
    if not run_loading_loop(screen, clock, provision_task):
        pygame.quit()
        sys.exit(0)

    if provision_task.error:
        print(f"\nCould not provision the troll's brain: {provision_task.error}")
        pygame.quit()
        sys.exit(1)

    handle = provision_task.result
    print(f"\nTroll's brain ready at {handle.base_url}\n")

    game = TrollBridgeGame(handle.base_url, handle.api_key)
    game.run()


if __name__ == "__main__":
    main()
