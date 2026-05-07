import time

import darkdetect
from fsrs import Card
from textual import events
from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, ListItem, ListView

from keypal.keys import matches
from keypal.models import Pack, Shortcut, builtin_packs
from keypal.scheduler import review
from keypal.storage import Storage


class HomeScreen(Screen):
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, packs: tuple[Pack, ...]) -> None:
        super().__init__()
        self._packs = packs

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Choose a pack to review:", id="prompt")
        yield ListView(
            *(
                ListItem(
                    Label(f"{pack.name} — {len(pack.shortcuts)} shortcuts"),
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
        yield Label("", id="progress")
        yield Label("", id="prompt")
        yield Label("", id="feedback")
        yield Footer()

    def on_mount(self) -> None:
        self._render_prompt()

    def _current(self) -> Shortcut | None:
        if self._index >= len(self._shortcuts):
            return None
        return self._shortcuts[self._index]

    def _render_prompt(self) -> None:
        shortcut = self._current()
        progress = self.query_one("#progress", Label)
        prompt = self.query_one("#prompt", Label)
        feedback = self.query_one("#feedback", Label)
        if shortcut is None:
            progress.update("")
            prompt.update("Session complete. Press Esc to return.")
            feedback.update("")
            return
        progress.update(f"Card {self._index + 1} / {len(self._shortcuts)}")
        prompt.update(shortcut.action)
        feedback.update("Press the shortcut...")
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

        feedback = self.query_one("#feedback", Label)
        if correct:
            feedback.update(f"Correct ({log.rating.name}). Press Space to continue.")
        else:
            expected = " or ".join(shortcut.keys)
            feedback.update(
                f"Wrong (you pressed {event.key!r}; expected {expected}). Press Space to continue."
            )
        self._awaiting_continue = True


class KeypalApp(App):
    TITLE = "keypal"

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
