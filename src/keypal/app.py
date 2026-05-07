import time
from enum import Enum

import darkdetect
from fsrs import Card
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, ListItem, ListView, Static

from keypal.keys import matches, normalize, prettify_combo
from keypal.models import Pack, Shortcut, builtin_packs
from keypal.scheduler import review
from keypal.storage import Storage


CSS = """
Screen {
    align: center middle;
}

#home-content, #quiz-content {
    width: 60;
    max-width: 100%;
    height: auto;
}

#home-prompt, #progress, #prompt, #verdict, #hint, #expected-label {
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

#home-prompt {
    text-style: bold;
    margin-bottom: 1;
}

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

.hidden {
    display: none;
}

ListView {
    width: 60;
    height: auto;
    border: round $primary;
}

ListItem {
    padding: 0 2;
}
"""


class QuizState(Enum):
    ASKING = "asking"
    CORRECT_DONE = "correct_done"
    WRONG_PRACTICE = "wrong_practice"


class KeyChip(Static):
    pass


class KeyCombo(Horizontal):
    def set_combo(self, combo: str, *, chip_class: str = "") -> None:
        self.remove_children()
        widgets = []
        for i, part in enumerate(prettify_combo(combo)):
            if i > 0:
                widgets.append(Static("+", classes="key-plus"))
            chip = KeyChip(part)
            if chip_class:
                chip.add_class(chip_class)
            widgets.append(chip)
        self.mount(*widgets)

    def clear(self) -> None:
        self.remove_children()


class HomeScreen(Screen):
    BINDINGS = [
        ("q", "app.quit", "Quit"),
        ("d", "diagnostics", "Test keys"),
    ]

    def action_diagnostics(self) -> None:
        self.app.push_screen(DiagnosticScreen())

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
                        Static(f"{pack.name} — {len(pack.shortcuts)} shortcuts"),
                        id=f"pack-{pack.id}",
                    )
                    for pack in self._packs
                )
            )
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        prefix = "pack-"
        if event.item.id is None or not event.item.id.startswith(prefix):
            return
        pack_id = event.item.id[len(prefix):]
        pack = next((p for p in self._packs if p.id == pack_id), None)
        if pack is not None:
            self.app.push_screen(QuizScreen(pack, self.app.storage))


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


class QuizScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back to home")]

    def __init__(self, pack: Pack, storage: Storage) -> None:
        super().__init__()
        self._pack = pack
        self._storage = storage
        self._cards: dict[str, Card] = storage.load_cards()
        self._aliases: dict[str, set[str]] = storage.load_aliases()
        self._shortcuts: list[Shortcut] = list(pack.shortcuts)
        self._index = 0
        self._state: QuizState = QuizState.ASKING
        self._start_ns: int | None = None
        self._last_pressed: str | None = None
        self._pending_elapsed_ms: int = 0

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

    def _current(self) -> Shortcut | None:
        if self._index >= len(self._shortcuts):
            return None
        return self._shortcuts[self._index]

    def _begin_card(self) -> None:
        self._state = QuizState.ASKING
        self._last_pressed = None
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
            hint.update("Press Esc to return")
            return

        progress.update(f"{self._index + 1} / {len(self._shortcuts)}")
        prompt.update(shortcut.action)

        if self._state is QuizState.ASKING:
            hint.update("Press the shortcut · Space if you don't know")
            return

        if self._state is QuizState.CORRECT_DONE:
            assert self._last_pressed is not None
            your_combo.set_combo(self._last_pressed, chip_class="correct")
            verdict.update("Correct")
            verdict.add_class("correct")
            hint.update("Press Enter to continue")
            return

        # WRONG_PRACTICE
        if self._last_pressed is not None:
            your_combo.set_combo(self._last_pressed, chip_class="wrong")
            verdict.update("Wrong")
        else:
            verdict.update("Don't know")
        verdict.add_class("wrong")
        expected_label.update("Try this:")
        expected_combo.set_combo(shortcut.keys[0], chip_class="correct")
        hint.update("Press the shortcut · Y if you actually had it · Enter to skip")

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            return  # let binding handle
        if self._current() is None:
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

        self._pending_elapsed_ms = self._elapsed_ms()
        self._last_pressed = None if event.key == "space" else event.key

        correct = event.key != "space" and matches(event.key, shortcut.keys, self._aliases)
        self._state = QuizState.CORRECT_DONE if correct else QuizState.WRONG_PRACTICE
        self._render_state()

    def _handle_correct_done(self, event: events.Key) -> None:
        if event.key == "enter":
            event.stop()
            self._finalize(correct=True)

    def _handle_wrong_practice(self, event: events.Key) -> None:
        shortcut = self._current()
        assert shortcut is not None
        if event.key == "y":
            # Override: user claims the terminal mistranslated their keypress.
            # Remember the mistranslation so future presses match without needing 'y'.
            event.stop()
            if self._last_pressed is not None:
                self._remember_alias(shortcut, self._last_pressed)
            self._finalize(correct=True)
        elif event.key == "enter" or matches(event.key, shortcut.keys, self._aliases):
            event.stop()
            self._finalize(correct=False)

    def _remember_alias(self, shortcut: Shortcut, pressed: str) -> None:
        try:
            normalized_pressed = normalize(pressed)
            normalized_expected = normalize(shortcut.keys[0])
        except ValueError:
            return
        if normalized_pressed == normalized_expected:
            return
        self._aliases.setdefault(normalized_expected, set()).add(normalized_pressed)
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

    def on_mount(self) -> None:
        if darkdetect.theme() == "Light":
            self.theme = "textual-light"
        self.push_screen(HomeScreen(self.packs))


def main() -> None:
    KeypalApp().run()


if __name__ == "__main__":
    main()
