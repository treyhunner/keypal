import pytest
from textual.widgets import Checkbox, Input, Static

from keypal.app import (
    BrowseScreen,
    HomeScreen,
    KeypalApp,
    QuizScreen,
    QuizState,
    SettingsScreen,
)
from keypal.models import Pack, Shortcut
from keypal.storage import Settings, Storage


def _shortcut(action, keys=("ctrl+a",), **kwargs):
    return Shortcut(action=action, keys=keys, **kwargs)


def _pack(shortcuts, pack_id="test", name="Test Pack", prefix=None):
    return Pack(
        id=pack_id,
        name=name,
        description="A test pack",
        shortcuts=tuple(shortcuts),
        prefix=prefix,
    )


TEST_SHORTCUTS = [
    _shortcut("Move to start", keys=("ctrl+a",)),
    _shortcut("Move to end", keys=("ctrl+e",)),
    _shortcut("Delete word", keys=("ctrl+w",)),
]


class FakeApp(KeypalApp):
    """App wired to a single test pack with tmp-dir storage."""

    def __init__(self, packs, storage):
        super().__init__()
        self.packs = packs
        self.storage = storage


def make_app(tmp_path, shortcuts=None, packs=None):
    storage = Storage(base_dir=tmp_path)
    if packs is None:
        packs = (_pack(shortcuts or TEST_SHORTCUTS),)
    app = FakeApp(packs, storage)
    return app


@pytest.mark.asyncio
async def test_home_screen_shows_pack_name(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test():
        screen = app.screen
        assert isinstance(screen, HomeScreen)
        assert "Test Pack" in screen.query_one(".pack-name", Static).render().plain


@pytest.mark.asyncio
async def test_home_screen_shows_new_count(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test():
        summary = app.screen.query_one(".pack-summary", Static).render().plain
        assert "3 new" in summary


@pytest.mark.asyncio
async def test_practice_enters_quiz(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("p")
        assert isinstance(app.screen, QuizScreen)


@pytest.mark.asyncio
async def test_quiz_shows_first_shortcut_prompt(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("p")
        prompt = app.screen.query_one("#prompt", Static).render().plain
        assert "Move to start" in prompt


@pytest.mark.asyncio
async def test_correct_answer_shows_correct_verdict(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("p")
        await pilot.press("ctrl+a")
        verdict = app.screen.query_one("#verdict", Static).render().plain
        assert "Correct" in verdict
        assert app.screen._state is QuizState.CORRECT_DONE


@pytest.mark.asyncio
async def test_wrong_answer_shows_wrong_verdict(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("p")
        await pilot.press("ctrl+x")
        verdict = app.screen.query_one("#verdict", Static).render().plain
        assert "Wrong" in verdict
        assert app.screen._state is QuizState.WRONG_PRACTICE


@pytest.mark.asyncio
async def test_space_shows_dont_know(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("p")
        await pilot.press("space")
        verdict = app.screen.query_one("#verdict", Static).render().plain
        assert "know" in verdict.lower()
        assert app.screen._state is QuizState.WRONG_PRACTICE


@pytest.mark.asyncio
async def test_correct_then_enter_advances(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("p")
        await pilot.press("ctrl+a")
        await pilot.press("enter")
        prompt = app.screen.query_one("#prompt", Static).render().plain
        assert "Move to end" in prompt


@pytest.mark.asyncio
async def test_wrong_then_enter_advances(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("p")
        await pilot.press("ctrl+x")
        await pilot.press("enter")
        prompt = app.screen.query_one("#prompt", Static).render().plain
        assert "Move to end" in prompt


@pytest.mark.asyncio
async def test_session_complete_shows_message(tmp_path):
    shortcuts = [_shortcut("Only one", keys=("ctrl+a",))]
    app = make_app(tmp_path, shortcuts=shortcuts)
    async with app.run_test() as pilot:
        await pilot.press("p")
        await pilot.press("ctrl+a")
        await pilot.press("enter")
        prompt = app.screen.query_one("#prompt", Static).render().plain
        assert "Session complete" in prompt


@pytest.mark.asyncio
async def test_session_complete_enter_returns_home(tmp_path):
    shortcuts = [_shortcut("Only one", keys=("ctrl+a",))]
    app = make_app(tmp_path, shortcuts=shortcuts)
    async with app.run_test() as pilot:
        await pilot.press("p")
        await pilot.press("ctrl+a")
        await pilot.press("enter")
        await pilot.press("enter")
        assert isinstance(app.screen, HomeScreen)


@pytest.mark.asyncio
async def test_f4_dismisses_shortcut(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("p")
        prompt_before = app.screen.query_one("#prompt", Static).render().plain
        assert "Move to start" in prompt_before
        await pilot.press("f4")
        prompt_after = app.screen.query_one("#prompt", Static).render().plain
        assert "Move to end" in prompt_after
    storage = Storage(base_dir=tmp_path)
    assert "test:Move to start" in storage.load_disabled()


@pytest.mark.asyncio
async def test_f4_persists_across_sessions(tmp_path):
    shortcuts = [_shortcut("A", keys=("ctrl+a",)), _shortcut("B", keys=("ctrl+b",))]
    app = make_app(tmp_path, shortcuts=shortcuts)
    async with app.run_test() as pilot:
        await pilot.press("p")
        await pilot.press("f4")

    app2 = make_app(tmp_path, shortcuts=shortcuts)
    async with app2.run_test() as pilot:
        await pilot.press("p")
        prompt = app2.screen.query_one("#prompt", Static).render().plain
        assert "B" in prompt


@pytest.mark.asyncio
async def test_y_override_saves_alias_and_advances_correct(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("p")
        await pilot.press("ctrl+x")
        assert app.screen._state is QuizState.WRONG_PRACTICE
        await pilot.press("y")
        prompt = app.screen.query_one("#prompt", Static).render().plain
        assert "Move to end" in prompt
    storage = Storage(base_dir=tmp_path)
    aliases = storage.load_aliases()
    assert "ctrl+a" in aliases
    assert "ctrl+x" in aliases["ctrl+a"]


@pytest.mark.asyncio
async def test_escape_returns_to_home_from_quiz(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("p")
        assert isinstance(app.screen, QuizScreen)
        await pilot.press("escape")
        assert isinstance(app.screen, HomeScreen)


@pytest.mark.asyncio
async def test_review_persisted_after_correct(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("p")
        await pilot.press("ctrl+a")
        await pilot.press("enter")
    storage = Storage(base_dir=tmp_path)
    reviews = list(storage.read_reviews())
    assert len(reviews) == 1
    assert reviews[0][0] == "test:Move to start"


@pytest.mark.asyncio
async def test_review_persisted_after_wrong(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("p")
        await pilot.press("ctrl+x")
        await pilot.press("enter")
    storage = Storage(base_dir=tmp_path)
    reviews = list(storage.read_reviews())
    assert len(reviews) == 1
    assert reviews[0][0] == "test:Move to start"


# --- Chord (prefix) packs ---


@pytest.mark.asyncio
async def test_chord_correct_requires_prefix_then_key(tmp_path, monkeypatch):
    monkeypatch.setattr("keypal.app.inside_tmux", lambda: False)
    shortcuts = [_shortcut("Split pane", keys=("x",))]
    packs = (_pack(shortcuts, pack_id="tmux", name="Tmux", prefix="ctrl+a"),)
    app = make_app(tmp_path, packs=packs)
    async with app.run_test() as pilot:
        await pilot.press("p")
        assert app.screen._state is QuizState.ASKING
        await pilot.press("ctrl+a")
        assert app.screen._state is QuizState.ASKING
        await pilot.press("x")
        assert app.screen._state is QuizState.CORRECT_DONE


@pytest.mark.asyncio
async def test_chord_wrong_prefix_is_wrong(tmp_path, monkeypatch):
    monkeypatch.setattr("keypal.app.inside_tmux", lambda: False)
    shortcuts = [_shortcut("Split pane", keys=("x",))]
    packs = (_pack(shortcuts, pack_id="tmux", name="Tmux", prefix="ctrl+a"),)
    app = make_app(tmp_path, packs=packs)
    async with app.run_test() as pilot:
        await pilot.press("p")
        await pilot.press("ctrl+b")
        assert app.screen._state is QuizState.WRONG_PRACTICE


@pytest.mark.asyncio
async def test_chord_wrong_second_key_is_wrong(tmp_path, monkeypatch):
    monkeypatch.setattr("keypal.app.inside_tmux", lambda: False)
    shortcuts = [_shortcut("Split pane", keys=("x",))]
    packs = (_pack(shortcuts, pack_id="tmux", name="Tmux", prefix="ctrl+a"),)
    app = make_app(tmp_path, packs=packs)
    async with app.run_test() as pilot:
        await pilot.press("p")
        await pilot.press("ctrl+a")
        await pilot.press("z")
        assert app.screen._state is QuizState.WRONG_PRACTICE


# --- Browse screen ---


@pytest.mark.asyncio
async def test_browse_opens_with_b(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        lv = app.screen.query_one("ListView")
        lv.index = 0
        lv.focus()
        await pilot.pause()
        await pilot.press("b")
        assert isinstance(app.screen, BrowseScreen)


@pytest.mark.asyncio
async def test_browse_lists_shortcuts(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        lv = app.screen.query_one("ListView")
        lv.index = 0
        lv.focus()
        await pilot.pause()
        await pilot.press("b")
        found = any(
            "Move to start" in w.render().plain for w in app.screen.query("Static")
        )
        assert found


@pytest.mark.asyncio
async def test_browse_enter_practices_shortcut(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        lv = app.screen.query_one("ListView")
        lv.index = 0
        lv.focus()
        await pilot.pause()
        await pilot.press("b")
        await pilot.press("enter")
        assert isinstance(app.screen, QuizScreen)


@pytest.mark.asyncio
async def test_browse_escape_returns_home(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        lv = app.screen.query_one("ListView")
        lv.index = 0
        lv.focus()
        await pilot.pause()
        await pilot.press("b")
        assert isinstance(app.screen, BrowseScreen)
        await pilot.press("escape")
        assert isinstance(app.screen, HomeScreen)


# --- Multi-pack & checkboxes ---


@pytest.mark.asyncio
async def test_toggle_pack_checkbox(tmp_path):
    packs = (
        _pack([_shortcut("A", keys=("ctrl+a",))], pack_id="p1", name="Pack 1"),
        _pack([_shortcut("B", keys=("ctrl+b",))], pack_id="p2", name="Pack 2"),
    )
    app = make_app(tmp_path, packs=packs)
    async with app.run_test() as pilot:
        lv = app.screen.query_one("ListView")
        lv.index = 0
        lv.focus()
        await pilot.pause()
        cb = app.screen.query_one("#check-p1", Checkbox)
        assert cb.value is True
        await pilot.press("x")
        assert cb.value is False
    storage = Storage(base_dir=tmp_path)
    saved = storage.load_selected_packs()
    assert saved is not None
    assert "p1" not in saved
    assert "p2" in saved


@pytest.mark.asyncio
async def test_multi_pack_quiz_shows_pack_label(tmp_path):
    packs = (
        _pack([_shortcut("A", keys=("ctrl+a",))], pack_id="p1", name="Pack 1"),
        _pack([_shortcut("B", keys=("ctrl+b",))], pack_id="p2", name="Pack 2"),
    )
    app = make_app(tmp_path, packs=packs)
    async with app.run_test() as pilot:
        await pilot.press("p")
        pack_label = app.screen.query_one("#pack-label", Static).render().plain
        assert pack_label.strip() != ""


# --- Wrong practice retry ---


@pytest.mark.asyncio
async def test_wrong_practice_correct_retry_advances(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("p")
        await pilot.press("ctrl+x")
        assert app.screen._state is QuizState.WRONG_PRACTICE
        await pilot.press("ctrl+a")
        prompt = app.screen.query_one("#prompt", Static).render().plain
        assert "Move to end" in prompt


# --- Empty session guard ---


@pytest.mark.asyncio
async def test_practice_with_no_due_cards_stays_on_home(tmp_path):
    shortcuts = [_shortcut("A", keys=("ctrl+a",))]
    app = make_app(tmp_path, shortcuts=shortcuts)
    async with app.run_test(notifications=True) as pilot:
        await pilot.press("p")
        await pilot.press("ctrl+a")
        await pilot.press("enter")
        await pilot.press("enter")
        assert isinstance(app.screen, HomeScreen)
        await pilot.press("p")
        assert isinstance(app.screen, HomeScreen)


# --- Re-enable dismissed shortcuts ---


@pytest.mark.asyncio
async def test_browse_shows_skipped_label(tmp_path):
    shortcuts = [_shortcut("A", keys=("ctrl+a",)), _shortcut("B", keys=("ctrl+b",))]
    storage = Storage(base_dir=tmp_path)
    storage.save_disabled({"test:A"})
    app = make_app(tmp_path, shortcuts=shortcuts)
    async with app.run_test() as pilot:
        lv = app.screen.query_one("ListView")
        lv.index = 0
        lv.focus()
        await pilot.pause()
        await pilot.press("b")
        assert isinstance(app.screen, BrowseScreen)
        labels = [w.render().plain for w in app.screen.query("#browse-list Static")]
        a_label = next(text for text in labels if "A" in text)
        b_label = next(text for text in labels if "B" in text)
        assert "skipped" in a_label.lower()
        assert "skipped" not in b_label.lower()


@pytest.mark.asyncio
async def test_f4_in_browse_re_enables_shortcut(tmp_path):
    shortcuts = [_shortcut("A", keys=("ctrl+a",)), _shortcut("B", keys=("ctrl+b",))]
    storage = Storage(base_dir=tmp_path)
    storage.save_disabled({"test:A"})
    app = make_app(tmp_path, shortcuts=shortcuts)
    async with app.run_test() as pilot:
        lv = app.screen.query_one("ListView")
        lv.index = 0
        lv.focus()
        await pilot.pause()
        await pilot.press("b")
        await pilot.press("f4")
    storage2 = Storage(base_dir=tmp_path)
    assert "test:A" not in storage2.load_disabled()


@pytest.mark.asyncio
async def test_f4_in_browse_disables_shortcut(tmp_path):
    shortcuts = [_shortcut("A", keys=("ctrl+a",)), _shortcut("B", keys=("ctrl+b",))]
    app = make_app(tmp_path, shortcuts=shortcuts)
    async with app.run_test() as pilot:
        lv = app.screen.query_one("ListView")
        lv.index = 0
        lv.focus()
        await pilot.pause()
        await pilot.press("b")
        await pilot.press("f4")
    storage = Storage(base_dir=tmp_path)
    assert "test:A" in storage.load_disabled()


# --- Settings screen ---


@pytest.mark.asyncio
async def test_settings_opens_with_c(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("c")
        assert isinstance(app.screen, SettingsScreen)


@pytest.mark.asyncio
async def test_settings_shows_current_values(tmp_path):
    storage = Storage(base_dir=tmp_path)
    storage.save_settings(Settings(new_per_session=3))
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("c")
        value = app.screen.query_one("#setting-new_per_session", Input).value
        assert value == "3"


@pytest.mark.asyncio
async def test_settings_escape_returns_home(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("c")
        assert isinstance(app.screen, SettingsScreen)
        await pilot.press("escape")
        assert isinstance(app.screen, HomeScreen)
