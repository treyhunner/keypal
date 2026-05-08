import atexit
import time
from datetime import datetime, timedelta, timezone
from enum import Enum

import darkdetect
from fsrs import Card, State
from textual import events
from textual._ansi_sequences import ANSI_SEQUENCES_KEYS, IGNORE_SEQUENCE
from textual._xterm_parser import XTermParser
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.driver import Driver
from textual.drivers.linux_driver import LinuxDriver
from textual.keys import Keys
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    ListItem,
    ListView,
    Static,
)

from keypal.keys import matches, normalize, prettify_combo
from keypal.models import Pack, Shortcut, builtin_packs
from keypal.scheduler import (
    PERSONAL_LOOKBACK_DAYS,
    Thresholds,
    get_thresholds,
    review,
    select_multi_session,
)
from keypal.storage import Storage
from keypal.tmux import TmuxPrefixSwap, current_tmux_prefix, inside_tmux

PACK_COLORS = {
    "readline": "green",
    "python_repl": "blue",
    "tmux": "yellow",
    "obsidian": "magenta",
}


# --- Monkey-patch for https://github.com/Textualize/textual/issues/6378 ---
# Textual's XTermParser silently drops the Alt prefix for keys whose ANSI
# sequence maps to a tuple in ANSI_SEQUENCES_KEYS (Enter, Space, Backspace,
# Tab, all Ctrl+letter). Pressing Alt+Enter produces Key("enter") instead of
# Key("alt+enter"). The "tuple branch" in `_sequence_to_key_events` ignores
# the alt parameter; the single-character branch (a few lines below it) does
# check it. Until upstream fixes it, replicate the alt-prefix handling here.
_textual_original_sequence_to_key_events = XTermParser._sequence_to_key_events


def _patched_sequence_to_key_events(self, sequence: str, alt: bool = False):
    if alt:
        keys = ANSI_SEQUENCES_KEYS.get(sequence)
        if keys is not IGNORE_SEQUENCE and isinstance(keys, tuple):
            for key in keys:
                name = key.value
                if name and name != Keys.Escape.value:
                    name = f"alt+{name}"
                yield events.Key(name, sequence if len(sequence) == 1 else None)
            return
    yield from _textual_original_sequence_to_key_events(self, sequence, alt)


XTermParser._sequence_to_key_events = _patched_sequence_to_key_events


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

#practice-btn {
    width: 100%;
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

.pack-header {
    width: 100%;
    height: 1;
}

.pack-header Checkbox {
    width: auto;
    height: 1;
    padding: 0;
    border: none;
    background: transparent;
    min-width: 0;
}

.pack-name {
    width: 1fr;
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

#progress, #pack-label, #prompt, #verdict, #hint, #expected-label {
    width: 100%;
    text-align: center;
}

#progress {
    color: $text-muted;
    height: 1;
    margin-bottom: 1;
}

#pack-label {
    height: 1;
    text-style: bold;
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

#demo-label {
    width: 100%;
    text-align: center;
    color: $text-muted;
    height: 1;
    margin-top: 1;
}

TextBufferDemo {
    width: auto;
    max-width: 100%;
    height: 3;
    border: round $primary;
    padding: 0 1;
    color: $foreground;
    background: $surface;
    content-align: center middle;
}

#demo-row {
    width: 100%;
    height: auto;
    align-horizontal: center;
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

#browse-list {
    height: auto;
    background: transparent;
    border: none;
    padding: 0;
}

#browse-list ListItem {
    height: 1;
    padding: 0 1;
    background: transparent;
    margin: 0;
}

#browse-list ListItem.--highlight {
    background: $boost;
}

#browse-hint {
    color: $text-muted;
    text-align: center;
    margin-top: 1;
}

.hidden {
    display: none;
}
"""


def _format_relative(delta: timedelta) -> str:
    """Render a future timedelta as 'a moment', '5 min', '2h', '3d'."""
    seconds = delta.total_seconds()
    if seconds < 60:
        return "a moment"
    if seconds < 3600:
        return f"{int(seconds / 60)} min"
    if seconds < 86400:
        return f"{int(seconds / 3600)}h"
    return f"{int(seconds / 86400)}d"


class LegacyKeyboardDriver(LinuxDriver):
    """Linux driver with the kitty keyboard protocol request suppressed.

    The kitty protocol confuses Textual's input parsing in some terminal stacks
    (notably tmux without `extended-keys on`, GNOME Terminal/VTE, etc.), where
    `Alt+Enter` ends up reported as plain `enter`. Suppressing the protocol
    forces the legacy ESC-prefix parser, which reliably maps `\\x1b\\n` to
    `alt+enter` (the same logic Python's pyrepl uses).
    """

    _SUPPRESSED = (b"\x1b[>1u", b"\x1b[<u", "\x1b[>1u", "\x1b[<u")

    def write(self, data) -> None:
        if data in self._SUPPRESSED:
            return
        super().write(data)


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


class TextBufferDemo(Static):
    """Animated demo of a text-edit shortcut. Cycles before <-> after every 1.5s.

    The before/after strings encode the cursor with the '│' character.
    """

    CYCLE_INTERVAL_S = 1.5

    def __init__(self, before: str, after: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._before = before
        self._after = after
        self._showing_before = True
        self._timer = None

    def on_mount(self) -> None:
        self._render_state()
        self._timer = self.set_interval(self.CYCLE_INTERVAL_S, self._toggle)

    def on_unmount(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _toggle(self) -> None:
        self._showing_before = not self._showing_before
        self._render_state()

    def _render_state(self) -> None:
        text = self._before if self._showing_before else self._after
        # Render the cursor cell as inverted; everything else as plain.
        rendered = ""
        for char in text:
            if char == "│":
                rendered += "[reverse] [/reverse]"
            else:
                rendered += char
        self.update(rendered)


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
        ("p", "practice", "Practice"),
        ("x", "toggle_pack", "Toggle pack"),
        ("b", "browse", "Browse pack"),
        ("s", "stats", "Stats"),
        ("d", "diagnostics", "Test keys"),
    ]

    def action_diagnostics(self) -> None:
        self.app.push_screen(DiagnosticScreen())

    def action_stats(self) -> None:
        self.app.push_screen(StatsScreen(self._packs, self._storage))

    def action_browse(self) -> None:
        pack = self._highlighted_pack()
        if pack is not None:
            self.app.push_screen(BrowseScreen(pack, self._storage))

    def __init__(self, packs: tuple[Pack, ...], storage: Storage) -> None:
        super().__init__()
        self._packs = packs
        self._storage = storage
        saved = storage.load_selected_packs()
        if saved is None:
            self._selected: set[str] = {p.id for p in packs}
        else:
            self._selected = saved & {p.id for p in packs}

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="home-content"):
            yield Button("Practice", id="practice-btn", variant="primary")
            yield ListView(
                *(
                    ListItem(
                        Horizontal(
                            self._pack_checkbox(pack),
                            Static(pack.name, classes="pack-name"),
                            classes="pack-header",
                        ),
                        Static(pack.description, classes="pack-desc"),
                        Static(self._pack_counts(pack), classes="pack-summary"),
                        id=f"pack-{pack.id}",
                    )
                    for pack in self._packs
                )
            )
        yield Footer()

    def _pack_checkbox(self, pack: Pack) -> Checkbox:
        cb = Checkbox("", value=pack.id in self._selected, id=f"check-{pack.id}")
        cb.can_focus = False
        return cb

    def on_key(self, event: events.Key) -> None:
        if isinstance(self.focused, Button):
            lv = self.query_one(ListView)
            if event.key == "down":
                lv.index = 0
                lv.focus()
                event.stop()
            elif event.key == "up":
                lv.index = len(lv) - 1
                lv.focus()
                event.stop()
            return
        if isinstance(self.focused, ListView):
            lv = self.query_one(ListView)
            if event.key == "up" and lv.index == 0:
                self.query_one("#practice-btn", Button).focus()
                event.stop()
            elif event.key == "down" and lv.index == len(lv) - 1:
                self.query_one("#practice-btn", Button).focus()
                event.stop()

    def on_screen_resume(self) -> None:
        for pack in self._packs:
            label = self.query_one(f"#pack-{pack.id} .pack-summary", Static)
            label.update(self._pack_counts(pack))

    def _highlighted_pack(self) -> Pack | None:
        list_view = self.query_one(ListView)
        item = list_view.highlighted_child
        if item is None or item.id is None:
            return None
        prefix = "pack-"
        if not item.id.startswith(prefix):
            return None
        pack_id = item.id[len(prefix) :]
        return next((p for p in self._packs if p.id == pack_id), None)

    def action_toggle_pack(self) -> None:
        pack = self._highlighted_pack()
        if pack is None:
            return
        checkbox = self.query_one(f"#check-{pack.id}", Checkbox)
        checkbox.value = not checkbox.value

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        prefix = "check-"
        if event.checkbox.id is None or not event.checkbox.id.startswith(prefix):
            return
        pack_id = event.checkbox.id[len(prefix) :]
        if event.value:
            self._selected.add(pack_id)
        else:
            self._selected.discard(pack_id)
        self._storage.save_selected_packs(self._selected)

    def _pack_counts(self, pack: Pack) -> str:
        cards = self._storage.load_cards()
        disabled = self._storage.load_disabled()
        now = datetime.now(timezone.utc)
        due = 0
        new = 0
        shared_known = (
            0  # shortcut shared with another pack and already practiced (not due)
        )
        upcoming: list[datetime] = []
        for shortcut in pack.shortcuts:
            sid = pack.shortcut_id(shortcut)
            if sid in disabled:
                continue
            card = cards.get(sid)
            is_shared = bool(shortcut.shared_id) and not shortcut.shared_id.startswith(
                f"{pack.id}:"
            )
            if card is None:
                new += 1
            elif card.due is None or card.due <= now:
                due += 1
            else:
                upcoming.append(card.due)
                if is_shared:
                    shared_known += 1
        if due == 0 and new == 0 and shared_known == 0:
            if upcoming:
                return f"all caught up · next due in {_format_relative(min(upcoming) - now)}"
            return "all caught up"
        parts = []
        if due:
            parts.append(f"{due} due")
        if new:
            parts.append(f"{new} new")
        if shared_known:
            parts.append(f"{shared_known} shared")
        return " · ".join(parts)

    def action_practice(self) -> None:
        selected = tuple(p for p in self._packs if p.id in self._selected)
        if selected:
            self._start_quiz(selected)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "practice-btn":
            self.action_practice()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        prefix = "pack-"
        if event.item.id is None or not event.item.id.startswith(prefix):
            return
        pack_id = event.item.id[len(prefix) :]
        pack = next((p for p in self._packs if p.id == pack_id), None)
        if pack is not None:
            self._start_quiz((pack,))

    def _start_quiz(self, packs: tuple[Pack, ...]) -> None:
        if self._any_needs_prefix_swap(packs):

            def handle_response(confirmed: bool | None) -> None:
                if confirmed:
                    self.app.tmux_swap.activate()
                    self.app.push_screen(QuizScreen(packs, self._storage))

            self.app.push_screen(ConfirmSwapModal(), handle_response)
        else:
            self.app.push_screen(QuizScreen(packs, self._storage))

    def _any_needs_prefix_swap(self, packs: tuple[Pack, ...]) -> bool:
        if not inside_tmux():
            return False
        user_prefix = current_tmux_prefix()
        if user_prefix is None:
            return False
        for pack in packs:
            if not pack.prefix:
                continue
            try:
                if normalize(user_prefix) == normalize(pack.prefix):
                    return True
            except ValueError:
                continue
        return False


class BrowseScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self, pack: Pack, storage: Storage) -> None:
        super().__init__()
        self._pack = pack
        self._storage = storage

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
            yield ListView(
                *(
                    ListItem(
                        Static(self._browse_label(shortcut)),
                        id=f"shortcut-{i}",
                    )
                    for i, shortcut in enumerate(self._pack.shortcuts)
                ),
                id="browse-list",
            )
            yield Static("Enter to practice · Esc to go back", id="browse-hint")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#browse-list", ListView).focus()

    def _browse_label(self, shortcut: Shortcut) -> str:
        action = shortcut.action
        keys = "  /  ".join("+".join(prettify_combo(k)) for k in shortcut.keys)
        shared = ""
        if shortcut.shared_id and not shortcut.shared_id.startswith(
            f"{self._pack.id}:"
        ):
            ns = shortcut.shared_id.split(":", 1)[0]
            shared = f"  [$text-muted i](common with {ns})[/]"
        return f"{action:<42}  [b $primary]{keys}[/]{shared}"

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        prefix = "shortcut-"
        if event.item.id is None or not event.item.id.startswith(prefix):
            return
        idx = int(event.item.id[len(prefix) :])
        shortcut = self._pack.shortcuts[idx]
        self.app.push_screen(QuizScreen((self._pack,), self._storage, force=[shortcut]))


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
            active_ids = [
                pack.shortcut_id(s)
                for s in pack.shortcuts
                if pack.shortcut_id(s) not in disabled
            ]
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

    def __init__(
        self,
        packs: tuple[Pack, ...],
        storage: Storage,
        force: list[Shortcut] | None = None,
    ) -> None:
        super().__init__()
        self._packs = packs
        self._storage = storage
        self._cards: dict[str, Card] = storage.load_cards()
        self._aliases: dict[str, set[str]] = storage.load_aliases()
        self._disabled: set[str] = storage.load_disabled()
        self._seen: set[str] = storage.load_seen()
        self._thresholds = self._compute_thresholds()
        if force is not None:
            self._session = [(s, packs[0]) for s in force]
        else:
            self._session = select_multi_session(
                packs, self._cards, disabled=self._disabled, seen=self._seen
            )
        self._index = 0
        self._state: QuizState = QuizState.ASKING
        self._start_ns: int | None = None
        self._first_key_ns: int | None = None
        self._last_pressed_seq: list[str] = []
        self._chord_buffer: list[str] = []
        self._pending_elapsed_ms: int = 0
        self._auto_advance_step = 0
        self._auto_advance_timer = None

    def _compute_thresholds(self) -> Thresholds:
        cutoff = datetime.now(timezone.utc) - timedelta(days=PERSONAL_LOOKBACK_DAYS)
        recent_signals = [
            signals
            for _sid, log, signals in self._storage.read_reviews()
            if datetime.fromisoformat(log.to_dict()["review_datetime"]) >= cutoff
        ]
        return get_thresholds(recent_signals)

    def _expected_seq(self, shortcut: Shortcut, pack: Pack) -> list[str]:
        if pack.prefix:
            return [pack.prefix, shortcut.keys[0]]
        return [shortcut.keys[0]]

    def _expected_chord_length(self, pack: Pack) -> int:
        return 2 if pack.prefix else 1

    def _match_position(
        self, position: int, key: str, shortcut: Shortcut, pack: Pack
    ) -> bool:
        if pack.prefix and position == 0:
            return matches(key, [pack.prefix], self._aliases)
        return matches(key, shortcut.keys, self._aliases)

    def _evaluate_chord(
        self, buffer: list[str], shortcut: Shortcut, pack: Pack
    ) -> bool:
        if len(buffer) != self._expected_chord_length(pack):
            return False
        return all(
            self._match_position(i, key, shortcut, pack) for i, key in enumerate(buffer)
        )

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="quiz-content"):
            yield Static("", id="progress")
            yield Static("", id="pack-label")
            yield Static("", id="prompt")
            yield KeyCombo(id="your-combo")
            yield Static("", id="verdict")
            with Horizontal(id="auto-advance-dots"):
                yield Static("", id="dot-1", classes="dot")
                yield Static("", id="dot-2", classes="dot")
                yield Static("", id="dot-3", classes="dot")
            yield Static("", id="expected-label")
            yield KeyCombo(id="expected-combo")
            yield Static("", id="demo-label")
            yield Horizontal(id="demo-row")
            yield Static("", id="hint")
        yield Footer()

    def on_mount(self) -> None:
        self._begin_card()

    def on_unmount(self) -> None:
        self._cancel_auto_advance()
        # Restore tmux prefix if it was swapped to enter this pack.
        self.app.tmux_swap.deactivate()

    def _current(self) -> tuple[Shortcut, Pack] | None:
        if self._index >= len(self._session):
            return None
        return self._session[self._index]

    def _begin_card(self) -> None:
        self._cancel_auto_advance()
        self._state = QuizState.ASKING
        self._last_pressed_seq = []
        self._chord_buffer = []
        self._start_ns = time.monotonic_ns() if self._current() else None
        self._first_key_ns = None
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
            # Only update the dots; don't re-render the whole state (would destroy
            # and remount the demo widget every tick, killing its animation cycle).
            for i in (1, 2, 3):
                cell = self.query_one(f"#dot-{i}", Static)
                cell.update(self.DOT_CHAR if self._auto_advance_step >= i else "")

    def _render_state(self) -> None:
        current = self._current()
        progress = self.query_one("#progress", Static)
        pack_label = self.query_one("#pack-label", Static)
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
        demo_label = self.query_one("#demo-label", Static)
        demo_row = self.query_one("#demo-row", Horizontal)
        demo_label.update("")
        demo_row.remove_children()

        if current is None:
            progress.update("")
            pack_label.update("")
            prompt.update("Session complete")
            hint.update("Press Enter to return home")
            return

        shortcut, pack = current
        progress.update(f"{self._index + 1} / {len(self._session)}")
        if len(self._packs) > 1:
            color = PACK_COLORS.get(pack.id, "white")
            pack_label.update(f"[bold reverse {color}] {pack.name} [/]")
        else:
            pack_label.update("")
        prompt_text = shortcut.action
        if shortcut.shared_id and not shortcut.shared_id.startswith(f"{pack.id}:"):
            ns = shortcut.shared_id.split(":", 1)[0]
            prompt_text += f"  [$text-muted i](shared with {ns})[/]"
        prompt.update(prompt_text)

        if self._state is QuizState.ASKING:
            if self._chord_buffer:
                your_combo.set_combo(list(self._chord_buffer))
                hint.update("Now press the next key...")
            else:
                hint.update(
                    "Press the shortcut · Space if you don't know · F4 to skip forever"
                )
            return

        expected_seq = self._expected_seq(shortcut, pack)

        if self._state is QuizState.CORRECT_DONE:
            your_combo.set_combo(expected_seq, chip_class="correct")
            verdict.update("Correct")
            verdict.add_class("correct")
            for i in (1, 2, 3):
                cell = self.query_one(f"#dot-{i}", Static)
                cell.update(self.DOT_CHAR if self._auto_advance_step >= i else "")
            if shortcut.demo_before and shortcut.demo_after:
                demo_label.update("What it does:")
                demo_row.mount(
                    TextBufferDemo(shortcut.demo_before, shortcut.demo_after)
                )
            hint.update("Press Enter to continue · F4 to skip forever")
            return

        # WRONG_PRACTICE
        verdict.update("Wrong" if self._last_pressed_seq else "Don't know")
        verdict.add_class("wrong")
        expected_label.update("Try this:")
        expected_combo.set_combo(expected_seq, chip_class="correct")
        if shortcut.demo_before and shortcut.demo_after:
            demo_label.update("What it does:")
            demo_row.mount(TextBufferDemo(shortcut.demo_before, shortcut.demo_after))
        if self._chord_buffer:
            your_combo.set_combo(list(self._chord_buffer))
            hint.update("Now press the next key...")
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
        current = self._current()
        assert current is not None
        shortcut, pack = current

        if event.key == "space" and not self._chord_buffer:
            self._pending_elapsed_ms = self._elapsed_ms()
            self._last_pressed_seq = []
            self._state = QuizState.WRONG_PRACTICE
            self._render_state()
            return

        if self._first_key_ns is None:
            self._first_key_ns = time.monotonic_ns()

        self._chord_buffer.append(event.key)

        position = len(self._chord_buffer) - 1
        if not self._match_position(position, event.key, shortcut, pack):
            self._pending_elapsed_ms = self._elapsed_ms()
            self._last_pressed_seq = list(self._chord_buffer)
            self._chord_buffer = []
            self._state = QuizState.WRONG_PRACTICE
            self._render_state()
            return

        if len(self._chord_buffer) < self._expected_chord_length(pack):
            self._render_state()
            return

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
        current = self._current()
        assert current is not None
        shortcut, pack = current

        if not self._chord_buffer and event.key == "y":
            event.stop()
            self._remember_alias_seq(
                self._last_pressed_seq, self._expected_seq(shortcut, pack)
            )
            self._finalize(correct=True)
            return

        if not self._chord_buffer and event.key == "enter":
            event.stop()
            self._finalize(correct=False)
            return

        self._chord_buffer.append(event.key)

        position = len(self._chord_buffer) - 1
        if not self._match_position(position, event.key, shortcut, pack):
            self._last_pressed_seq = list(self._chord_buffer)
            self._chord_buffer = []
            self._render_state()
            return

        if len(self._chord_buffer) < self._expected_chord_length(pack):
            self._render_state()
            return

        event.stop()
        self._chord_buffer = []
        self._finalize(correct=False)

    def _remember_alias_seq(
        self, pressed_seq: list[str], expected_seq: list[str]
    ) -> None:
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
        current = self._current()
        if current is not None:
            shortcut, pack = current
            self._record_answer(
                shortcut,
                pack,
                correct=correct,
                response_time_ms=self._pending_elapsed_ms,
            )
        self._advance()

    def _advance(self) -> None:
        self._index += 1
        self._begin_card()

    def _elapsed_ms(self) -> int:
        if self._start_ns is None:
            return 0
        return (time.monotonic_ns() - self._start_ns) // 1_000_000

    def _first_key_elapsed_ms(self) -> int | None:
        if self._start_ns is None or self._first_key_ns is None:
            return None
        return (self._first_key_ns - self._start_ns) // 1_000_000

    def _record_answer(
        self, shortcut: Shortcut, pack: Pack, *, correct: bool, response_time_ms: int
    ) -> None:
        shortcut_id = pack.shortcut_id(shortcut)
        card = self._cards.get(shortcut_id, Card())
        updated, log = review(
            card,
            correct=correct,
            response_time_ms=int(response_time_ms),
            thresholds=self._thresholds,
        )
        self._cards[shortcut_id] = updated
        self._storage.save_cards(self._cards)
        signals: dict[str, int | None] = {
            "response_time_ms": response_time_ms,
            "time_to_first_keystroke_ms": self._first_key_elapsed_ms(),
        }
        self._storage.append_review(shortcut_id, log, signals=signals)
        pack_sid = f"{pack.id}::{shortcut_id}"
        if pack_sid not in self._seen:
            self._seen.add(pack_sid)
            self._storage.save_seen(self._seen)

    def action_dismiss_card(self) -> None:
        current = self._current()
        if current is None:
            return
        shortcut, pack = current
        self._cancel_auto_advance()
        self._disabled.add(pack.shortcut_id(shortcut))
        self._storage.save_disabled(self._disabled)
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

    def get_driver_class(self) -> type[Driver]:
        # Force the legacy ESC-prefix keyboard parser instead of kitty protocol.
        # Without this, Alt+Enter (and a handful of other modified-special-key
        # combos) gets reported as plain `enter` in some terminal stacks.
        return LegacyKeyboardDriver

    def on_mount(self) -> None:
        match darkdetect.theme():
            case "Light":
                self.theme = "solarized-light"
            case "Dark":
                self.theme = "solarized-dark"
        self.push_screen(HomeScreen(self.packs, self.storage))


def main() -> None:
    KeypalApp().run()


if __name__ == "__main__":
    main()
