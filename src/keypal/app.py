from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, ListItem, ListView

from keypal.models import Pack, builtin_packs
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


class KeypalApp(App):
    TITLE = "keypal"

    def __init__(self) -> None:
        super().__init__()
        self.packs = builtin_packs()
        self.storage = Storage()

    def on_mount(self) -> None:
        self.push_screen(HomeScreen(self.packs))


def main() -> None:
    KeypalApp().run()


if __name__ == "__main__":
    main()
