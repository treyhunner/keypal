import atexit
import time
from datetime import datetime, timezone
from enum import Enum

import darkdetect
from fsrs import Card, State
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
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

#auto-advance-dots {
    width: 100%;
    height: 1;
    margin-top: 1;
}

#auto-advance-dots .dot {
    width: 1fr;
    text-align: center;
    color: $accent;
    text-style: bold;
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

#browse-content {
    width: 80;
    max-width: 100%;
    height: 100%;
    padding: 0 2;
}

#browse-title {
    text-style: bold;
    color: $accent;
    text-align: center;
    margin-bottom: 1;
}

#browse-desc {
    color: $text-muted;
    text-align: center;
    margin-bottom: 1;
}

#browse-prefix {
    color: $text-muted;
    text-align: center;
    margin-bottom: 1;
}

.browse-row {
    width: 100%;
    height: 1;
    padding: 0 1;
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
        ("b", "browse", "Browse pack"),
        ("s", "stats", "Stats"),
        ("d", "diagnostics", "Test keys"),
    ]

    def action_diagnostics(self) -> None:
        self.app.push_screen(DiagnosticScreen())

    def action_stats(self) -> None:
        self.app.push_screen(StatsScreen(self._packs, self.app.storage))

    def action_browse(self) -> None:
        list_view = self.query_one(ListView)
        item = list_view.highlighted_child
        if item is None or item.id is None:
            return
        prefix = "pack-"
        if not item.id.startswith(prefix):
            return
        pack_id = item.id[len(prefix):]
        pack = next((p for p in self._packs if p.id == pack_id), None)
        if pack is not None:
            self.app.push_screen(BrowseScreen(pack))

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
        disabled = self.app.storage.load_disabled()
        now = datetime.now(timezone.utc)
        due = 0
        new = 0
        for shortcut in pack.shortcuts:
            sid = pack.shortcut_id(shortcut)
            if sid in disabled:
                continue
            card = cards.get(sid)
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


class BrowseScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self, pack: Pack) -> None:
        super().__init__()
        self._pack = pack

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="browse-content"):
            yield Static(self._pack.name, id="browse-title")
            yield Static(self._pack.description, id="browse-desc")
            if self._pack.prefix:
                pretty = "+".join(prettify_combo(self._pack.prefix))
                yield Static(
                    f"All shortcuts shown after prefix [b]{pretty}[/]",
                    id="browse-prefix",
                )
            for shortcut in self._pack.shortcuts:
                action = shortcut.action
                keys = "  /  ".join("+".join(prettify_combo(k)) for k in shortcut.keys)
                yield Static(
                    f"{action:<42}  [b $primary]{keys}[/]",
                    classes="browse-row",
                )
        yield Footer()


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
        disabled = self._storage.load_disabled()
        review_count = sum(1 for _ in self._storage.read_reviews())
        now = datetime.now(timezone.utc)

        state_counts = {state: 0 for state in State}
        for card in cards.values():
            state_counts[card.state] = state_counts.get(card.state, 0) + 1

        pack_lines = []
        for pack in self._packs:
            active_ids = [pack.shortcut_id(s) for s in pack.shortcuts if pack.shortcut_id(s) not in disabled]
            tracked = sum(1 for sid in active_ids if sid in cards)
            due = sum(
                1
                for sid in active_ids
                if (card := cards.get(sid)) is not None
                and (card.due is None or card.due <= now)
            )
            total = len(active_ids)
            skipped = len(pack.shortcuts) - total
            line = f"  {pack.name}: {tracked}/{total} tracked, {due} due"
            if skipped:
                line += f" ({skipped} skipped)"
            pack_lines.append(line)

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
    BINDINGS = [
        ("escape", "app.pop_screen", "Back to home"),
        ("f4", "dismiss_card", "Skip forever"),
    ]

    AUTO_ADVANCE_TICKS = 4  # 4 ticks at 1s each = 3 dots shown then advance
    AUTO_ADVANCE_INTERVAL_S = 1.0
    DOT_CHAR = "●"

    def __init__(self, pack: Pack, storage: Storage) -> None:
        super().__init__()
        self._pack = pack
        self._storage = storage
        self._cards: dict[str, Card] = storage.load_cards()
        self._aliases: dict[str, set[str]] = storage.load_aliases()
        self._disabled: set[str] = storage.load_disabled()
        self._shortcuts: list[Shortcut] = select_session(
            pack, self._cards, disabled=self._disabled
        )
        self._index = 0
        self._state: QuizState = QuizState.ASKING
        self._start_ns: int | None = None
        self._last_pressed_seq: list[str] = []
        self._chord_buffer: list[str] = []
        self._pending_elapsed_ms: int = 0
        self._auto_advance_step = 0
        self._auto_advance_timer = None

    def _expected_seq(self, shortcut: Shortcut) -> list[str]:
        """Canonical display sequence (first listed key for each position)."""
        if self._pack.prefix:
            return [self._pack.prefix, shortcut.keys[0]]
        return [shortcut.keys[0]]

    def _expected_chord_length(self) -> int:
        return 2 if self._pack.prefix else 1

    def _match_position(self, position: int, key: str, shortcut: Shortcut) -> bool:
        """Match a single keypress against any valid value at that chord position."""
        if self._pack.prefix and position == 0:
            return matches(key, [self._pack.prefix], self._aliases)
        # Final position (chord position 1, or single combo position 0): any of shortcut.keys
        return matches(key, shortcut.keys, self._aliases)

    def _evaluate_chord(self, buffer: list[str], shortcut: Shortcut) -> bool:
        if len(buffer) != self._expected_chord_length():
            return False
        return all(self._match_position(i, key, shortcut) for i, key in enumerate(buffer))

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="quiz-content"):
            yield Static("", id="progress")
            yield Static("", id="prompt")
            yield KeyCombo(id="your-combo")
            yield Static("", id="verdict")
            with Horizontal(id="auto-advance-dots"):
                yield Static("", id="dot-1", classes="dot")
                yield Static("", id="dot-2", classes="dot")
                yield Static("", id="dot-3", classes="dot")
            yield Static("", id="expected-label")
            yield KeyCombo(id="expected-combo")
            yield Static("", id="hint")
        yield Footer()

    def on_mount(self) -> None:
        self._begin_card()

    def on_unmount(self) -> None:
        self._cancel_auto_advance()
        # Restore tmux prefix if it was swapped to enter this pack.
        self.app.tmux_swap.deactivate()

    def _current(self) -> Shortcut | None:
        if self._index >= len(self._shortcuts):
            return None
        return self._shortcuts[self._index]

    def _begin_card(self) -> None:
        self._cancel_auto_advance()
        self._state = QuizState.ASKING
        self._last_pressed_seq = []
        self._chord_buffer = []
        self._start_ns = time.monotonic_ns() if self._current() else None
        self._render_state()

    def _start_auto_advance(self) -> None:
        self._cancel_auto_advance()
        self._auto_advance_step = 0
        self._auto_advance_timer = self.set_interval(
            self.AUTO_ADVANCE_INTERVAL_S, self._tick_auto_advance
        )

    def _cancel_auto_advance(self) -> None:
        if self._auto_advance_timer is not None:
            self._auto_advance_timer.stop()
            self._auto_advance_timer = None
        self._auto_advance_step = 0

    def _tick_auto_advance(self) -> None:
        self._auto_advance_step += 1
        if self._auto_advance_step >= self.AUTO_ADVANCE_TICKS:
            self._cancel_auto_advance()
            self._finalize(correct=True)
        else:
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
        for i in (1, 2, 3):
            self.query_one(f"#dot-{i}", Static).update("")

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
                hint.update("Press the shortcut · Space if you don't know · F4 to skip forever")
            return

        expected_seq = self._expected_seq(shortcut)

        if self._state is QuizState.CORRECT_DONE:
            # Show the canonical pack combo (full chord for chord packs).
            your_combo.set_combo(expected_seq, chip_class="correct")
            verdict.update("Correct")
            verdict.add_class("correct")
            for i in (1, 2, 3):
                cell = self.query_one(f"#dot-{i}", Static)
                cell.update(self.DOT_CHAR if self._auto_advance_step >= i else "")
            hint.update("Press Enter to continue · F4 to skip forever")
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
            hint.update("Y if you had it · Enter to skip once · F4 to skip forever")

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            return  # let binding handle
        if event.key == "f4":
            # Handled here too because our state-machine handlers consume keypresses
            # before the screen-level binding system gets a chance to fire.
            event.stop()
            self.action_dismiss_card()
            return
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

        # "Don't know" = Space at the very start (no chord-progress)
        if event.key == "space" and not self._chord_buffer:
            self._pending_elapsed_ms = self._elapsed_ms()
            self._last_pressed_seq = []
            self._state = QuizState.WRONG_PRACTICE
            self._render_state()
            return

        self._chord_buffer.append(event.key)

        # Wrong at the current position: complete the attempt as just what they pressed.
        position = len(self._chord_buffer) - 1
        if not self._match_position(position, event.key, shortcut):
            self._pending_elapsed_ms = self._elapsed_ms()
            self._last_pressed_seq = list(self._chord_buffer)
            self._chord_buffer = []
            self._state = QuizState.WRONG_PRACTICE
            self._render_state()
            return

        # Wait for more keys if chord is incomplete.
        if len(self._chord_buffer) < self._expected_chord_length():
            self._render_state()
            return

        # Full sequence collected and all positions matched — correct.
        self._pending_elapsed_ms = self._elapsed_ms()
        self._last_pressed_seq = list(self._chord_buffer)
        self._chord_buffer = []
        self._state = QuizState.CORRECT_DONE
        self._start_auto_advance()
        self._render_state()

    def _handle_correct_done(self, event: events.Key) -> None:
        if event.key == "enter":
            event.stop()
            self._cancel_auto_advance()
            self._finalize(correct=True)

    def _handle_wrong_practice(self, event: events.Key) -> None:
        shortcut = self._current()
        assert shortcut is not None

        # Empty buffer + Y = "got it right" override
        if not self._chord_buffer and event.key == "y":
            event.stop()
            self._remember_alias_seq(self._last_pressed_seq, self._expected_seq(shortcut))
            self._finalize(correct=True)
            return

        # Empty buffer + Enter = skip practice
        if not self._chord_buffer and event.key == "enter":
            event.stop()
            self._finalize(correct=False)
            return

        # Otherwise: collect chord keys for retry
        self._chord_buffer.append(event.key)

        position = len(self._chord_buffer) - 1
        if not self._match_position(position, event.key, shortcut):
            # Wrong key at this position: surface what they pressed and reset buffer.
            self._last_pressed_seq = list(self._chord_buffer)
            self._chord_buffer = []
            self._render_state()
            return

        # Need more keys: render progress so user sees their press.
        if len(self._chord_buffer) < self._expected_chord_length():
            self._render_state()
            return

        # Full sequence collected on retry — all positions matched.
        event.stop()
        self._chord_buffer = []
        self._finalize(correct=False)  # was wrong on first attempt; just practiced

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

    def action_dismiss_card(self) -> None:
        shortcut = self._current()
        if shortcut is None:
            return
        self._cancel_auto_advance()
        self._disabled.add(self._pack.shortcut_id(shortcut))
        self._storage.save_disabled(self._disabled)
        # Skip recording an FSRS rating; just move on.
        self._advance()


class KeypalApp(App):
    TITLE = "keypal"
    CSS = CSS
    ENABLE_COMMAND_PALETTE = False  # don't steal Ctrl+P from quiz capture

    def __init__(self) -> None:
        super().__init__()
        self.packs = builtin_packs()
        self.storage = Storage()
        self.tmux_swap = TmuxPrefixSwap()
        atexit.register(self.tmux_swap.deactivate)

    def on_mount(self) -> None:
        match darkdetect.theme():
            case "Light":
                self.theme = "solarized-light"
            case "Dark":
                self.theme = "solarized-dark"
        self.push_screen(HomeScreen(self.packs))


def main() -> None:
    KeypalApp().run()


if __name__ == "__main__":
    main()
