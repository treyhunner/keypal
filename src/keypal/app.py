import atexit
import time
from datetime import datetime, timezone
from enum import Enum

import darkdetect
from fsrs import Card, State
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Header, ListItem, ListView, Static

from keypal.keys import matches, normalize, prettify_combo
from keypal.models import Pack, Shortcut, builtin_packs
from keypal.scheduler import review, select_session
from keypal.storage import Storage
from keypal.tmux import TmuxPrefixSwap, current_tmux_prefix, inside_tmux


CSS = """
Screen {
    align: center middle;
}

#home-content, #quiz-content, #stats-content {
    width: 64;
    max-width: 100%;
    height: auto;
}

/* === Home === */

#home-prompt {
    width: 100%;
    text-align: center;
    text-style: bold;
    color: $accent;
    margin-bottom: 1;
}

ListView {
    width: 100%;
    height: auto;
    background: transparent;
    border: none;
    padding: 0;
}

ListItem {
    padding: 1 2;
    height: auto;
    background: $surface;
    margin-bottom: 1;
    border-left: thick $surface;
}

ListItem.--highlight {
    background: $boost;
    border-left: thick $accent;
}

.pack-name {
    width: 100%;
    text-style: bold;
    color: $accent;
}

.pack-desc {
    width: 100%;
    color: $text-muted;
}

.pack-summary {
    width: 100%;
    color: $primary;
    margin-top: 1;
}

/* === Quiz === */

#progress, #prompt, #verdict, #hint, #expected-label {
    width: 100%;
    text-align: center;
}

#progress {
    color: $text-muted;
    height: 1;
    margin-bottom: 1;
}

#prompt {
    text-style: bold;
    color: $accent;
    height: 1;
    margin-bottom: 2;
}

#verdict {
    text-style: bold;
    height: 1;
    margin-top: 1;
}

#verdict.correct {
    color: $success-darken-2;
}

#verdict.wrong {
    color: $error;
}

#expected-label {
    color: $text-muted;
    height: 1;
    margin-top: 1;
}

#hint {
    color: $text-muted;
    height: 1;
    margin-top: 2;
}

/* === Key chips === */

KeyCombo {
    width: 100%;
    height: 3;
    align-horizontal: center;
}

KeyChip {
    border: round $primary;
    padding: 0 1;
    height: 3;
    width: auto;
    color: $foreground;
    background: $surface;
    text-style: bold;
}

KeyChip.correct {
    border: round $success;
    background: $success 15%;
}

KeyChip.wrong {
    border: round $error;
    background: $error 15%;
}

.key-plus {
    width: auto;
    height: 3;
    content-align: center middle;
    color: $text-muted;
    padding: 0 1;
}

.chord-separator {
    width: auto;
    height: 3;
    content-align: center middle;
    color: $accent;
    padding: 0 1;
    text-style: bold;
}

/* === Stats === */

#stats-title {
    width: 100%;
    text-align: center;
    text-style: bold;
    color: $accent;
    margin-bottom: 1;
}

#stats-body {
    width: 100%;
    height: auto;
    padding: 1 2;
    background: $surface;
}

.hidden {
    display: none;
}
"""


class QuizState(Enum):
    ASKING = "asking"
    CORRECT_DONE = "correct_done"
    WRONG_PRACTICE = "wrong_practice"


class KeyChip(Static):
    pass


class KeyCombo(Horizontal):
    def set_combo(self, combo: str | list[str], *, chip_class: str = "") -> None:
        # Accept a single combo string OR a list of combos (chord sequence).
        combos = [combo] if isinstance(combo, str) else list(combo)
        self.remove_children()
        widgets = []
        for ci, single in enumerate(combos):
            if ci > 0:
                widgets.append(Static("→", classes="chord-separator"))
            try:
                parts = prettify_combo(single)
            except ValueError:
                parts = [single]
            for i, part in enumerate(parts):
                if i > 0:
                    widgets.append(Static("+", classes="key-plus"))
                chip = KeyChip(part)
                if chip_class:
                    chip.add_class(chip_class)
                widgets.append(chip)
        self.mount(*widgets)

    def clear(self) -> None:
        self.remove_children()


class ConfirmSwapModal(ModalScreen[bool]):
    BINDINGS = [
        ("y,enter", "confirm", "Yes"),
        ("n,escape", "cancel", "No"),
    ]

    DEFAULT_CSS = """
    ConfirmSwapModal {
        align: center middle;
        background: black 40%;
    }

    #modal-content {
        width: 64;
        max-width: 90%;
        height: auto;
        padding: 1 2;
        border: thick $accent;
        background: $surface;
    }

    #modal-title {
        text-style: bold;
        color: $warning;
        text-align: center;
        margin-bottom: 1;
    }

    #modal-message {
        text-align: center;
        margin-bottom: 1;
    }

    #modal-buttons {
        width: 100%;
        height: 3;
        align-horizontal: center;
        margin-top: 1;
    }

    #modal-buttons Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-content"):
            yield Static("This pack uses your tmux prefix", id="modal-title")
            yield Static(
                "Continuing will disable your tmux prefix until you leave this pack. "
                "tmux navigation (switching windows, sessions, panes) will not work.",
                id="modal-message",
            )
            with Horizontal(id="modal-buttons"):
                yield Button("Continue", id="confirm-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self.dismiss(True)
        elif event.button.id == "cancel-btn":
            self.dismiss(False)


class HomeScreen(Screen):
    BINDINGS = [
        ("q", "app.quit", "Quit"),
        ("s", "stats", "Stats"),
        ("d", "diagnostics", "Test keys"),
    ]

    def action_diagnostics(self) -> None:
        self.app.push_screen(DiagnosticScreen())

    def action_stats(self) -> None:
        self.app.push_screen(StatsScreen(self._packs, self.app.storage))

    def __init__(self, packs: tuple[Pack, ...]) -> None:
        super().__init__()
        self._packs = packs

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="home-content"):
            yield Static("Choose a pack to practice", id="home-prompt")
            yield ListView(
                *(
                    ListItem(
                        Static(pack.name, classes="pack-name"),
                        Static(pack.description, classes="pack-desc"),
                        Static(self._pack_counts(pack), classes="pack-summary"),
                        id=f"pack-{pack.id}",
                    )
                    for pack in self._packs
                )
            )
        yield Footer()

    def on_screen_resume(self) -> None:
        for pack in self._packs:
            label = self.query_one(f"#pack-{pack.id} .pack-summary", Static)
            label.update(self._pack_counts(pack))

    def _pack_counts(self, pack: Pack) -> str:
        cards = self.app.storage.load_cards()
        now = datetime.now(timezone.utc)
        due = 0
        new = 0
        for shortcut in pack.shortcuts:
            card = cards.get(pack.shortcut_id(shortcut))
            if card is None:
                new += 1
            elif card.due is None or card.due <= now:
                due += 1
        if due == 0 and new == 0:
            return "all caught up"
        parts = []
        if due:
            parts.append(f"{due} due")
        if new:
            parts.append(f"{new} new")
        return " · ".join(parts)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        prefix = "pack-"
        if event.item.id is None or not event.item.id.startswith(prefix):
            return
        pack_id = event.item.id[len(prefix):]
        pack = next((p for p in self._packs if p.id == pack_id), None)
        if pack is None:
            return
        if self._needs_prefix_swap(pack):
            def handle_response(confirmed: bool | None) -> None:
                if confirmed:
                    self.app.tmux_swap.activate()
                    self.app.push_screen(QuizScreen(pack, self.app.storage))
            self.app.push_screen(ConfirmSwapModal(), handle_response)
        else:
            self.app.push_screen(QuizScreen(pack, self.app.storage))

    def _needs_prefix_swap(self, pack: Pack) -> bool:
        if not pack.prefix or not inside_tmux():
            return False
        user_prefix = current_tmux_prefix()
        if user_prefix is None:
            return False
        try:
            return normalize(user_prefix) == normalize(pack.prefix)
        except ValueError:
            return False


class DiagnosticScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="quiz-content"):
            yield Static("", id="progress")
            yield Static("Press any key combo", id="prompt")
            yield KeyCombo(id="your-combo")
            yield Static("", id="verdict")
            yield Static("", id="expected-label")
            yield KeyCombo(id="expected-combo")
            yield Static("Esc to return", id="hint")
        yield Footer()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            return  # let binding handle
        event.stop()
        verdict = self.query_one("#verdict", Static)
        verdict.update(f"Textual saw: {event.key!r}")
        your_combo = self.query_one("#your-combo", KeyCombo)
        try:
            your_combo.set_combo(event.key)
        except ValueError:
            your_combo.clear()


class StatsScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self, packs: tuple[Pack, ...], storage: Storage) -> None:
        super().__init__()
        self._packs = packs
        self._storage = storage

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="stats-content"):
            yield Static("Stats", id="stats-title")
            yield Static(self._render_stats(), id="stats-body")
        yield Footer()

    def _render_stats(self) -> str:
        cards = self._storage.load_cards()
        review_count = sum(1 for _ in self._storage.read_reviews())
        now = datetime.now(timezone.utc)

        state_counts = {state: 0 for state in State}
        for card in cards.values():
            state_counts[card.state] = state_counts.get(card.state, 0) + 1

        pack_lines = []
        for pack in self._packs:
            tracked = sum(1 for s in pack.shortcuts if pack.shortcut_id(s) in cards)
            due = sum(
                1
                for s in pack.shortcuts
                if (card := cards.get(pack.shortcut_id(s))) is not None
                and (card.due is None or card.due <= now)
            )
            total = len(pack.shortcuts)
            pack_lines.append(f"  {pack.name}: {tracked}/{total} tracked, {due} due")

        lines = [
            f"Reviews completed: {review_count}",
            "",
            "Cards by state:",
            *[f"  {state.name}: {state_counts.get(state, 0)}" for state in State],
            "",
            "Per pack:",
            *pack_lines,
        ]
        return "\n".join(lines)


class QuizScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back to home")]

    def __init__(self, pack: Pack, storage: Storage) -> None:
        super().__init__()
        self._pack = pack
        self._storage = storage
        self._cards: dict[str, Card] = storage.load_cards()
        self._aliases: dict[str, set[str]] = storage.load_aliases()
        self._shortcuts: list[Shortcut] = select_session(pack, self._cards)
        self._index = 0
        self._state: QuizState = QuizState.ASKING
        self._start_ns: int | None = None
        self._last_pressed_seq: list[str] = []
        self._chord_buffer: list[str] = []
        self._pending_elapsed_ms: int = 0

    def _expected_seq(self, shortcut: Shortcut) -> list[str]:
        if self._pack.prefix:
            return [self._pack.prefix, shortcut.keys[0]]
        return [shortcut.keys[0]]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="quiz-content"):
            yield Static("", id="progress")
            yield Static("", id="prompt")
            yield KeyCombo(id="your-combo")
            yield Static("", id="verdict")
            yield Static("", id="expected-label")
            yield KeyCombo(id="expected-combo")
            yield Static("", id="hint")
        yield Footer()

    def on_mount(self) -> None:
        self._begin_card()

    def on_unmount(self) -> None:
        # Restore tmux prefix if it was swapped to enter this pack.
        self.app.tmux_swap.deactivate()

    def _current(self) -> Shortcut | None:
        if self._index >= len(self._shortcuts):
            return None
        return self._shortcuts[self._index]

    def _begin_card(self) -> None:
        self._state = QuizState.ASKING
        self._last_pressed_seq = []
        self._chord_buffer = []
        self._start_ns = time.monotonic_ns() if self._current() else None
        self._render_state()

    def _render_state(self) -> None:
        shortcut = self._current()
        progress = self.query_one("#progress", Static)
        prompt = self.query_one("#prompt", Static)
        your_combo = self.query_one("#your-combo", KeyCombo)
        verdict = self.query_one("#verdict", Static)
        expected_label = self.query_one("#expected-label", Static)
        expected_combo = self.query_one("#expected-combo", KeyCombo)
        hint = self.query_one("#hint", Static)

        your_combo.clear()
        expected_combo.clear()
        expected_label.update("")
        verdict.update("")
        verdict.remove_class("correct")
        verdict.remove_class("wrong")

        if shortcut is None:
            progress.update("")
            prompt.update("Session complete")
            hint.update("Press Enter to return home")
            return

        progress.update(f"{self._index + 1} / {len(self._shortcuts)}")
        prompt.update(shortcut.action)

        if self._state is QuizState.ASKING:
            if self._chord_buffer:
                your_combo.set_combo(list(self._chord_buffer))
                hint.update("Now press the next key…")
            else:
                hint.update("Press the shortcut · Space if you don't know")
            return

        expected_seq = self._expected_seq(shortcut)

        if self._state is QuizState.CORRECT_DONE:
            # Show the canonical pack combo (full chord for chord packs).
            your_combo.set_combo(expected_seq, chip_class="correct")
            verdict.update("Correct")
            verdict.add_class("correct")
            hint.update("Press Enter to continue")
            return

        # WRONG_PRACTICE
        verdict.update("Wrong" if self._last_pressed_seq else "Don't know")
        verdict.add_class("wrong")
        expected_label.update("Try this:")
        expected_combo.set_combo(expected_seq, chip_class="correct")
        if self._chord_buffer:
            your_combo.set_combo(list(self._chord_buffer))
            hint.update("Now press the next key…")
        else:
            if self._last_pressed_seq:
                your_combo.set_combo(self._last_pressed_seq, chip_class="wrong")
            hint.update("Press the shortcut · Y if you actually had it · Enter to skip")

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            return  # let binding handle
        if self._current() is None:
            # Session complete: Enter returns home.
            if event.key == "enter":
                event.stop()
                self.app.pop_screen()
            return

        if self._state is QuizState.ASKING:
            self._handle_asking(event)
        elif self._state is QuizState.CORRECT_DONE:
            self._handle_correct_done(event)
        else:
            self._handle_wrong_practice(event)

    def _handle_asking(self, event: events.Key) -> None:
        event.stop()
        shortcut = self._current()
        assert shortcut is not None

        expected_seq = self._expected_seq(shortcut)

        # "Don't know" = Space at the very start (no chord-progress)
        if event.key == "space" and not self._chord_buffer:
            self._pending_elapsed_ms = self._elapsed_ms()
            self._last_pressed_seq = []
            self._state = QuizState.WRONG_PRACTICE
            self._render_state()
            return

        self._chord_buffer.append(event.key)

        # Wrong on first key: complete the attempt as just this key
        if len(self._chord_buffer) == 1 and not matches(event.key, [expected_seq[0]], self._aliases):
            self._pending_elapsed_ms = self._elapsed_ms()
            self._last_pressed_seq = list(self._chord_buffer)
            self._chord_buffer = []
            self._state = QuizState.WRONG_PRACTICE
            self._render_state()
            return

        # Wait for more keys if chord is incomplete; render progress so user sees their press.
        if len(self._chord_buffer) < len(expected_seq):
            self._render_state()
            return

        # Full sequence collected; compare
        self._pending_elapsed_ms = self._elapsed_ms()
        correct = all(
            matches(actual, [expected], self._aliases)
            for actual, expected in zip(self._chord_buffer, expected_seq)
        )
        self._last_pressed_seq = list(self._chord_buffer)
        self._chord_buffer = []
        self._state = QuizState.CORRECT_DONE if correct else QuizState.WRONG_PRACTICE
        self._render_state()

    def _handle_correct_done(self, event: events.Key) -> None:
        if event.key == "enter":
            event.stop()
            self._finalize(correct=True)

    def _handle_wrong_practice(self, event: events.Key) -> None:
        shortcut = self._current()
        assert shortcut is not None
        expected_seq = self._expected_seq(shortcut)

        # Empty buffer + Y = "got it right" override
        if not self._chord_buffer and event.key == "y":
            event.stop()
            self._remember_alias_seq(self._last_pressed_seq, expected_seq)
            self._finalize(correct=True)
            return

        # Empty buffer + Enter = skip practice
        if not self._chord_buffer and event.key == "enter":
            event.stop()
            self._finalize(correct=False)
            return

        # Otherwise: collect chord keys for retry
        self._chord_buffer.append(event.key)

        # First key wrong on retry: surface what they pressed and reset.
        if len(self._chord_buffer) == 1 and not matches(event.key, [expected_seq[0]], self._aliases):
            self._last_pressed_seq = list(self._chord_buffer)
            self._chord_buffer = []
            self._render_state()
            return

        # Need more keys: render progress so user sees their press.
        if len(self._chord_buffer) < len(expected_seq):
            self._render_state()
            return

        # Full sequence collected on retry
        all_match = all(
            matches(actual, [expected], self._aliases)
            for actual, expected in zip(self._chord_buffer, expected_seq)
        )
        if all_match:
            event.stop()
            self._chord_buffer = []
            self._finalize(correct=False)  # was wrong on first attempt; just practiced
        else:
            # Wrong full chord on retry: replace the displayed attempt with the new one.
            self._last_pressed_seq = list(self._chord_buffer)
            self._chord_buffer = []
            self._render_state()

    def _remember_alias_seq(self, pressed_seq: list[str], expected_seq: list[str]) -> None:
        if not pressed_seq or len(pressed_seq) != len(expected_seq):
            return  # nothing to alias, or length mismatch
        changed = False
        for actual, expected in zip(pressed_seq, expected_seq):
            try:
                normalized_pressed = normalize(actual)
                normalized_expected = normalize(expected)
            except ValueError:
                continue
            if normalized_pressed == normalized_expected:
                continue
            self._aliases.setdefault(normalized_expected, set()).add(normalized_pressed)
            changed = True
        if changed:
            self._storage.save_aliases(self._aliases)

    def _finalize(self, *, correct: bool) -> None:
        shortcut = self._current()
        if shortcut is not None:
            self._record_answer(shortcut, correct=correct, response_time_ms=self._pending_elapsed_ms)
        self._advance()

    def _advance(self) -> None:
        self._index += 1
        self._begin_card()

    def _elapsed_ms(self) -> int:
        if self._start_ns is None:
            return 0
        return (time.monotonic_ns() - self._start_ns) // 1_000_000

    def _record_answer(self, shortcut: Shortcut, *, correct: bool, response_time_ms: int) -> None:
        shortcut_id = self._pack.shortcut_id(shortcut)
        card = self._cards.get(shortcut_id, Card())
        updated, log = review(card, correct=correct, response_time_ms=int(response_time_ms))
        self._cards[shortcut_id] = updated
        self._storage.save_cards(self._cards)
        self._storage.append_review(shortcut_id, log)


class KeypalApp(App):
    TITLE = "keypal"
    CSS = CSS

    def __init__(self) -> None:
        super().__init__()
        self.packs = builtin_packs()
        self.storage = Storage()
        self.tmux_swap = TmuxPrefixSwap()
        atexit.register(self.tmux_swap.deactivate)

    def on_mount(self) -> None:
        if darkdetect.theme() == "Light":
            self.theme = "textual-light"
        self.push_screen(HomeScreen(self.packs))


def main() -> None:
    KeypalApp().run()


if __name__ == "__main__":
    main()
