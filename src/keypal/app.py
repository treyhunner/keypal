import time

import darkdetect
from fsrs import Card
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, ListItem, ListView, Static

from keypal.keys import matches, prettify_combo
from keypal.models import Pack, Shortcut, builtin_packs
from keypal.scheduler import review
from keypal.storage import Storage


CSS = """
Screen {
    align: center middle;
}

#home-content, #quiz-content {
    width: auto;
    height: auto;
    align: center middle;
}

#home-prompt, #progress, #prompt, #verdict, #hint, #expected-label {
    width: auto;
    text-align: center;
}

#progress {
    color: $text-muted;
    margin-bottom: 1;
}

#prompt {
    text-style: bold;
    margin-bottom: 2;
}

#verdict {
    text-style: bold;
    margin-top: 1;
}

#verdict.correct {
    color: $success;
}

#verdict.wrong {
    color: $error;
}

#expected-label {
    color: $text-muted;
    margin-top: 1;
}

#hint {
    color: $text-muted;
    margin-top: 2;
}

#home-prompt {
    text-style: bold;
    margin-bottom: 1;
}

KeyCombo {
    width: auto;
    height: auto;
    align: center middle;
}

KeyChip {
    border: round $primary;
    padding: 0 1;
    height: 3;
    width: auto;
    color: $primary;
    background: $surface;
}

KeyChip.correct {
    border: round $success;
    color: $success;
}

KeyChip.wrong {
    border: round $error;
    color: $error;
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
    BINDINGS = [("q", "app.quit", "Quit")]

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


class QuizScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back to home")]

    def __init__(self, pack: Pack, storage: Storage) -> None:
        super().__init__()
        self._pack = pack
        self._storage = storage
        self._cards: dict[str, Card] = storage.load_cards()
        self._shortcuts: list[Shortcut] = list(pack.shortcuts)
        self._index = 0
        self._awaiting_continue = False
        self._start_ns: int | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="quiz-content"):
            yield Static("", id="progress")
            yield Static("", id="prompt")
            yield KeyCombo(id="your-combo")
            yield Static("", id="verdict")
            yield Static("Try this:", id="expected-label", classes="hidden")
            yield KeyCombo(id="expected-combo")
            yield Static("", id="hint")
        yield Footer()

    def on_mount(self) -> None:
        self._render_prompt()

    def _current(self) -> Shortcut | None:
        if self._index >= len(self._shortcuts):
            return None
        return self._shortcuts[self._index]

    def _render_prompt(self) -> None:
        shortcut = self._current()
        progress = self.query_one("#progress", Static)
        prompt = self.query_one("#prompt", Static)
        verdict = self.query_one("#verdict", Static)
        hint = self.query_one("#hint", Static)
        your_combo = self.query_one("#your-combo", KeyCombo)
        expected_combo = self.query_one("#expected-combo", KeyCombo)
        expected_label = self.query_one("#expected-label", Static)

        # Reset answer area
        your_combo.clear()
        expected_combo.clear()
        expected_label.add_class("hidden")
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
        hint.update("Press the shortcut")
        self._start_ns = time.monotonic_ns()

    def on_key(self, event: events.Key) -> None:
        if self._awaiting_continue:
            if event.key in {"space", "enter"}:
                event.stop()
                self._awaiting_continue = False
                self._index += 1
                self._render_prompt()
            return

        shortcut = self._current()
        if shortcut is None:
            return
        if event.key == "escape":
            return  # let binding handle it
        event.stop()

        elapsed_ms = (time.monotonic_ns() - (self._start_ns or time.monotonic_ns())) // 1_000_000
        correct = matches(event.key, shortcut.keys)

        shortcut_id = self._pack.shortcut_id(shortcut)
        card = self._cards.get(shortcut_id, Card())
        updated, log = review(card, correct=correct, response_time_ms=int(elapsed_ms))
        self._cards[shortcut_id] = updated
        self._storage.save_cards(self._cards)
        self._storage.append_review(shortcut_id, log)

        your_combo = self.query_one("#your-combo", KeyCombo)
        verdict = self.query_one("#verdict", Static)
        hint = self.query_one("#hint", Static)
        your_combo.set_combo(event.key, chip_class="correct" if correct else "wrong")

        if correct:
            verdict.update("Correct")
            verdict.add_class("correct")
        else:
            verdict.update("Wrong")
            verdict.add_class("wrong")
            expected_label = self.query_one("#expected-label", Static)
            expected_combo = self.query_one("#expected-combo", KeyCombo)
            expected_label.remove_class("hidden")
            # Show first expected combo (could show all eventually)
            expected_combo.set_combo(shortcut.keys[0], chip_class="correct")

        hint.update("Press Space to continue")
        self._awaiting_continue = True


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
