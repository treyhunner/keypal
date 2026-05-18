import pytest
from PySide6.QtCore import Qt

from keypal.app import (
    BrowseScreen,
    DiagnosticScreen,
    HomeScreen,
    KeypalApp,
    QuizScreen,
    QuizState,
    SettingsScreen,
    StatsScreen,
)
from keypal.models import Pack, Shortcut
from keypal.storage import Storage


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


@pytest.fixture
def app(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("KEYPAL_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("keypal.app.builtin_packs", lambda: (_pack(TEST_SHORTCUTS),))
    storage = Storage(base_dir=tmp_path)
    monkeypatch.setattr("keypal.app.Storage", lambda: storage)
    window = KeypalApp()
    qtbot.addWidget(window)
    window.show()
    return window


def test_home_screen_shows_pack_name(app):
    current = app._stack.currentWidget()
    assert isinstance(current, HomeScreen)
    card = current._cards[0]
    assert "Test Pack" in card._name_label.text()


def test_home_screen_shows_new_count(app):
    current = app._stack.currentWidget()
    card = current._cards[0]
    assert "3 new" in card._counts_label.text()


def test_practice_enters_quiz(app, qtbot):
    qtbot.keyClick(app._stack.currentWidget(), Qt.Key.Key_P)
    current = app._stack.currentWidget()
    assert isinstance(current, QuizScreen)


def test_quiz_shows_first_shortcut_prompt(app, qtbot):
    qtbot.keyClick(app._stack.currentWidget(), Qt.Key.Key_P)
    quiz = app._stack.currentWidget()
    assert isinstance(quiz, QuizScreen)
    assert "Move to start" in quiz._prompt.text()


def test_correct_answer_shows_correct(app, qtbot):
    qtbot.keyClick(app._stack.currentWidget(), Qt.Key.Key_P)
    quiz = app._stack.currentWidget()
    qtbot.keyClick(quiz, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert quiz._state is QuizState.CORRECT_DONE
    assert "Correct" in quiz._verdict.text()


def test_wrong_answer_shows_wrong(app, qtbot):
    qtbot.keyClick(app._stack.currentWidget(), Qt.Key.Key_P)
    quiz = app._stack.currentWidget()
    qtbot.keyClick(quiz, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    assert quiz._state is QuizState.WRONG_PRACTICE
    assert "Wrong" in quiz._verdict.text()


def test_space_shows_dont_know(app, qtbot):
    qtbot.keyClick(app._stack.currentWidget(), Qt.Key.Key_P)
    quiz = app._stack.currentWidget()
    qtbot.keyClick(quiz, Qt.Key.Key_Space)
    assert quiz._state is QuizState.WRONG_PRACTICE
    assert "Don't know" in quiz._verdict.text()


def test_enter_after_correct_advances(app, qtbot):
    qtbot.keyClick(app._stack.currentWidget(), Qt.Key.Key_P)
    quiz = app._stack.currentWidget()
    qtbot.keyClick(quiz, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert quiz._index == 0
    qtbot.keyClick(quiz, Qt.Key.Key_Return)
    assert quiz._index == 1


def test_enter_after_wrong_advances(app, qtbot):
    qtbot.keyClick(app._stack.currentWidget(), Qt.Key.Key_P)
    quiz = app._stack.currentWidget()
    qtbot.keyClick(quiz, Qt.Key.Key_Space)
    assert quiz._index == 0
    qtbot.keyClick(quiz, Qt.Key.Key_Return)
    assert quiz._index == 1


def test_escape_returns_home(app, qtbot):
    qtbot.keyClick(app._stack.currentWidget(), Qt.Key.Key_P)
    quiz = app._stack.currentWidget()
    assert isinstance(quiz, QuizScreen)
    qtbot.keyClick(quiz, Qt.Key.Key_Escape)
    current = app._stack.currentWidget()
    assert isinstance(current, HomeScreen)


def test_f4_dismisses_card(app, qtbot):
    qtbot.keyClick(app._stack.currentWidget(), Qt.Key.Key_P)
    quiz = app._stack.currentWidget()
    assert quiz._index == 0
    qtbot.keyClick(quiz, Qt.Key.Key_F4)
    assert quiz._index == 1
    disabled = app.storage.load_disabled()
    assert len(disabled) > 0


def test_browse_screen_opens(app, qtbot):
    home = app._stack.currentWidget()
    qtbot.keyClick(home, Qt.Key.Key_B)
    current = app._stack.currentWidget()
    assert isinstance(current, BrowseScreen)


def test_stats_screen_opens(app, qtbot):
    qtbot.keyClick(app._stack.currentWidget(), Qt.Key.Key_S)
    current = app._stack.currentWidget()
    assert isinstance(current, StatsScreen)


def test_settings_screen_opens(app, qtbot):
    qtbot.keyClick(app._stack.currentWidget(), Qt.Key.Key_C)
    current = app._stack.currentWidget()
    assert isinstance(current, SettingsScreen)


def test_diagnostic_screen_opens(app, qtbot):
    qtbot.keyClick(app._stack.currentWidget(), Qt.Key.Key_D)
    current = app._stack.currentWidget()
    assert isinstance(current, DiagnosticScreen)


def test_session_complete_enter_returns_home(app, qtbot):
    qtbot.keyClick(app._stack.currentWidget(), Qt.Key.Key_P)
    quiz = app._stack.currentWidget()
    # Answer all 3 cards correctly + advance each
    for _ in range(3):
        shortcut, pack = quiz._session[quiz._index]
        key_combo = shortcut.keys[0]
        # Simulate the correct key
        if key_combo == "ctrl+a":
            qtbot.keyClick(quiz, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        elif key_combo == "ctrl+e":
            qtbot.keyClick(quiz, Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)
        elif key_combo == "ctrl+w":
            qtbot.keyClick(quiz, Qt.Key.Key_W, Qt.KeyboardModifier.ControlModifier)
        qtbot.keyClick(quiz, Qt.Key.Key_Return)
    assert quiz._current() is None
    assert "Session complete" in quiz._prompt.text()
    qtbot.keyClick(quiz, Qt.Key.Key_Return)
    assert isinstance(app._stack.currentWidget(), HomeScreen)


def test_y_in_wrong_practice_saves_alias(app, qtbot):
    qtbot.keyClick(app._stack.currentWidget(), Qt.Key.Key_P)
    quiz = app._stack.currentWidget()
    # Press wrong key
    qtbot.keyClick(quiz, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    assert quiz._state is QuizState.WRONG_PRACTICE
    # Press Y to claim it was right
    qtbot.keyClick(quiz, Qt.Key.Key_Y)
    # Should have advanced
    assert quiz._index == 1
    aliases = app.storage.load_aliases()
    assert len(aliases) > 0


def test_chord_pack_prefix_then_key(qtbot, tmp_path, monkeypatch):
    shortcuts = [_shortcut("Next window", keys=("n",))]
    pack = _pack(shortcuts, pack_id="tmux", prefix="ctrl+b")

    monkeypatch.setenv("KEYPAL_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("keypal.app.builtin_packs", lambda: (pack,))
    storage = Storage(base_dir=tmp_path)
    monkeypatch.setattr("keypal.app.Storage", lambda: storage)

    window = KeypalApp()
    qtbot.addWidget(window)
    window.show()

    home = window._stack.currentWidget()
    qtbot.keyClick(home, Qt.Key.Key_P)
    quiz = window._stack.currentWidget()
    assert isinstance(quiz, QuizScreen)

    # First press: prefix
    qtbot.keyClick(quiz, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    assert quiz._state is QuizState.ASKING
    assert len(quiz._chord_buffer) == 1

    # Second press: the actual key
    qtbot.keyClick(quiz, Qt.Key.Key_N)
    assert quiz._state is QuizState.CORRECT_DONE


def test_auto_repeat_ignored_during_chord(qtbot, tmp_path, monkeypatch):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    shortcuts = [_shortcut("Next window", keys=("n",))]
    pack = _pack(shortcuts, pack_id="tmux", prefix="ctrl+a")

    monkeypatch.setenv("KEYPAL_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("keypal.app.builtin_packs", lambda: (pack,))
    storage = Storage(base_dir=tmp_path)
    monkeypatch.setattr("keypal.app.Storage", lambda: storage)

    window = KeypalApp()
    qtbot.addWidget(window)
    window.show()

    qtbot.keyClick(window._stack.currentWidget(), Qt.Key.Key_P)
    quiz = window._stack.currentWidget()

    qtbot.keyClick(quiz, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert quiz._state is QuizState.ASKING
    assert len(quiz._chord_buffer) == 1

    auto_repeat = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_A,
        Qt.KeyboardModifier(0),
        "a",
        autorep=True,
    )
    quiz.keyPressEvent(auto_repeat)
    assert quiz._state is QuizState.ASKING
    assert len(quiz._chord_buffer) == 1


def test_correct_answer_auto_advances(app, qtbot):
    qtbot.keyClick(app._stack.currentWidget(), Qt.Key.Key_P)
    quiz = app._stack.currentWidget()
    qtbot.keyClick(quiz, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert quiz._state is QuizState.CORRECT_DONE
    assert quiz._index == 0
    qtbot.wait(5000)
    assert quiz._index == 1
