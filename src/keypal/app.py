import time
from datetime import datetime, timedelta, timezone
from enum import Enum

from fsrs import Card, State
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from keypal.keys import matches, normalize, prettify_combo, qt_event_to_combo
from keypal.models import Pack, Shortcut, builtin_packs
from keypal.scheduler import (
    PERSONAL_LOOKBACK_DAYS,
    Thresholds,
    get_thresholds,
    review,
    select_multi_session,
)
from keypal.storage import Settings, Storage


PACK_COLORS = {
    "readline": "#2e7d32",
    "python_repl": "#1565c0",
    "tmux": "#f9a825",
    "obsidian": "#7b1fa2",
}


class QuizState(Enum):
    ASKING = "asking"
    CORRECT_DONE = "correct_done"
    WRONG_PRACTICE = "wrong_practice"


class KeyChip(QLabel):
    def __init__(self, text: str, state: str = "", parent=None):
        super().__init__(text, parent)
        self.setProperty("chipState", state)
        self.setStyleSheet(self._style_for(state))
        self.setContentsMargins(8, 4, 8, 4)

    @staticmethod
    def _style_for(state: str) -> str:
        base = (
            "QLabel { font-weight: bold; font-size: 18px; "
            "border: 2px solid palette(mid); border-radius: 4px; "
            "padding: 4px 8px; }"
        )
        if state == "correct":
            base = (
                "QLabel { font-weight: bold; font-size: 18px; "
                "border: 2px solid #2e7d32; border-radius: 4px; "
                "padding: 4px 8px; background-color: rgba(46, 125, 50, 0.15); }"
            )
        elif state == "wrong":
            base = (
                "QLabel { font-weight: bold; font-size: 18px; "
                "border: 2px solid #c62828; border-radius: 4px; "
                "padding: 4px 8px; background-color: rgba(198, 40, 40, 0.15); }"
            )
        return base


class KeyCombo(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_combo(self, combo: str | list[str], chip_class: str = "") -> None:
        self.clear()
        if isinstance(combo, str):
            seq = [combo]
        else:
            seq = combo
        for i, part in enumerate(seq):
            if i > 0:
                arrow = QLabel("  then  ")
                arrow.setStyleSheet("color: gray; font-size: 16px;")
                self._layout.addWidget(arrow)
            try:
                tokens = prettify_combo(part)
            except ValueError:
                tokens = [part]
            for j, token in enumerate(tokens):
                if j > 0:
                    plus = QLabel("+")
                    plus.setStyleSheet("color: gray; font-size: 16px;")
                    self._layout.addWidget(plus)
                chip = KeyChip(token, state=chip_class)
                self._layout.addWidget(chip)

    def clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class TextBufferDemo(QLabel):
    CYCLE_MS = 1500

    def __init__(self, before: str, after: str, parent=None):
        super().__init__(parent)
        self._before = before.replace("│", "█")
        self._after = after.replace("│", "█")
        self._showing_before = True
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "QLabel { font-family: monospace; font-size: 18px; "
            "border: 1px solid palette(mid); border-radius: 4px; padding: 4px 8px; }"
        )
        self.setText(self._before)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._toggle)
        self._timer.start(self.CYCLE_MS)

    def _toggle(self) -> None:
        self._showing_before = not self._showing_before
        self.setText(self._before if self._showing_before else self._after)


def _format_relative(td: timedelta) -> str:
    seconds = int(td.total_seconds())
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    return f"{days}d"


class PackCard(QWidget):
    def __init__(self, pack: Pack, checked: bool, color: str, parent=None):
        super().__init__(parent)
        self.pack = pack
        self.setStyleSheet(
            f"PackCard {{ background: palette(base); border: 1px solid palette(mid);"
            f" border-left: 4px solid {color}; border-radius: 4px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(8)
        self._checkbox = QCheckBox()
        self._checkbox.setChecked(checked)
        self._checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header.addWidget(self._checkbox)
        self._name_label = QLabel(pack.name)
        self._name_label.setStyleSheet(
            f"font-weight: bold; color: {color}; font-size: 16px;"
        )
        header.addWidget(self._name_label)
        header.addStretch()
        layout.addLayout(header)

        self._desc_label = QLabel(pack.description)
        self._desc_label.setStyleSheet("color: gray; font-size: 13px;")
        layout.addWidget(self._desc_label)

        self._counts_label = QLabel()
        self._counts_label.setStyleSheet("font-size: 13px;")
        layout.addWidget(self._counts_label)

    @property
    def checked(self) -> bool:
        return self._checkbox.isChecked()

    @checked.setter
    def checked(self, value: bool) -> None:
        self._checkbox.setChecked(value)

    def set_counts(self, text: str) -> None:
        self._counts_label.setText(text)

    def set_selected(self, selected: bool) -> None:
        if selected:
            self.setStyleSheet(self.styleSheet().replace("border: 1px", "border: 2px"))
        else:
            self.setStyleSheet(self.styleSheet().replace("border: 2px", "border: 1px"))


class HomeScreen(QWidget):
    def __init__(self, app: "KeypalApp"):
        super().__init__()
        self._app = app
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        content = QVBoxLayout()
        content.setSpacing(10)
        content.setContentsMargins(20, 20, 20, 20)

        self._practice_btn = QPushButton("Practice")
        self._practice_btn.setStyleSheet("font-size: 18px; padding: 8px;")
        self._practice_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._practice_btn.clicked.connect(self._start_practice)
        content.addWidget(self._practice_btn)

        self._selected: set[str] = set()
        saved = app.storage.load_selected_packs()
        if saved is None:
            self._selected = {p.id for p in app.packs}
        else:
            self._selected = saved & {p.id for p in app.packs}

        self._cards: list[PackCard] = []
        self._selected_index = 0
        for pack in app.packs:
            color = PACK_COLORS.get(pack.id, "gray")
            card = PackCard(pack, pack.id in self._selected, color)
            card.set_counts(self._pack_counts(pack))
            card._checkbox.toggled.connect(self._on_checkbox_toggled)
            card.mousePressEvent = lambda e, c=card, p=pack: self._on_card_clicked(
                p, toggle=True
            )
            card.mouseDoubleClickEvent = lambda e, p=pack: self._start_quiz((p,))
            self._cards.append(card)
            content.addWidget(card)

        self._update_selection_highlight()

        hint = QLabel(
            "P practice | B browse | S stats | C settings | D diagnostic | Q quit"
        )
        hint.setStyleSheet("color: gray; font-size: 12px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(hint)

        layout.addLayout(content)

    def on_resume(self) -> None:
        for card in self._cards:
            card.set_counts(self._pack_counts(card.pack))

    def _update_selection_highlight(self) -> None:
        for i, card in enumerate(self._cards):
            card.set_selected(i == self._selected_index)

    def _on_card_clicked(self, pack: Pack, *, toggle: bool = False) -> None:
        for i, card in enumerate(self._cards):
            if card.pack.id == pack.id:
                self._selected_index = i
                if toggle:
                    card._checkbox.toggle()
                break
        self._update_selection_highlight()

    def _on_checkbox_toggled(self, checked: bool) -> None:
        self._selected = set()
        for card in self._cards:
            if card.checked:
                self._selected.add(card.pack.id)
        self._app.storage.save_selected_packs(self._selected)

    def _pack_counts(self, pack: Pack) -> str:
        cards = self._app.storage.load_cards()
        disabled = self._app.storage.load_disabled()
        now = datetime.now(timezone.utc)
        due = 0
        new = 0
        shared_known = 0
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
                return f"all caught up - next due in {_format_relative(min(upcoming) - now)}"
            return "all caught up"
        parts = []
        if due:
            parts.append(f"{due} due")
        if new:
            parts.append(f"{new} new")
        if shared_known:
            parts.append(f"{shared_known} shared")
        return " | ".join(parts)

    def _highlighted_pack(self) -> Pack | None:
        if 0 <= self._selected_index < len(self._cards):
            return self._cards[self._selected_index].pack
        return None

    def _start_practice(self) -> None:
        selected = tuple(p for p in self._app.packs if p.id in self._selected)
        if selected:
            self._start_quiz(selected)

    def _start_quiz(self, packs: tuple[Pack, ...]) -> None:
        settings = self._app.settings
        cards = self._app.storage.load_cards()
        disabled = self._app.storage.load_disabled()
        seen = self._app.storage.load_seen()
        session = select_multi_session(
            packs,
            cards,
            disabled=disabled,
            seen=seen,
            new_per_session=settings.new_per_session,
        )
        if not session:
            QMessageBox.information(
                self, "keypal", "All caught up -- nothing to practice right now"
            )
            return
        self._app.push_screen(QuizScreen(self._app, packs, self._app.storage))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Q:
            self._app.close()
        elif key == Qt.Key.Key_P:
            self._start_practice()
        elif key == Qt.Key.Key_X:
            card = self._cards[self._selected_index] if self._cards else None
            if card:
                card.checked = not card.checked
        elif key == Qt.Key.Key_B:
            pack = self._highlighted_pack()
            if pack:
                self._app.push_screen(BrowseScreen(self._app, pack, self._app.storage))
        elif key == Qt.Key.Key_S:
            self._app.push_screen(
                StatsScreen(self._app, self._app.packs, self._app.storage)
            )
        elif key == Qt.Key.Key_C:
            self._app.push_screen(SettingsScreen(self._app, self._app.storage))
        elif key == Qt.Key.Key_D:
            self._app.push_screen(DiagnosticScreen(self._app))
        elif key == Qt.Key.Key_Up:
            if self._selected_index > 0:
                self._selected_index -= 1
                self._update_selection_highlight()
        elif key == Qt.Key.Key_Down:
            if self._selected_index < len(self._cards) - 1:
                self._selected_index += 1
                self._update_selection_highlight()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._start_practice()
        else:
            super().keyPressEvent(event)


class QuizScreen(QWidget):
    DOT_CHAR = "●"

    def __init__(
        self,
        app: "KeypalApp",
        packs: tuple[Pack, ...],
        storage: Storage,
        force: list[Shortcut] | None = None,
    ):
        super().__init__()
        self._app = app
        self._packs = packs
        self._storage = storage
        self._settings = storage.load_settings()
        self._cards: dict[str, Card] = storage.load_cards()
        self._aliases: dict[str, set[str]] = storage.load_aliases()
        self._disabled: set[str] = storage.load_disabled()
        self._seen: set[str] = storage.load_seen()
        self._thresholds = self._compute_thresholds()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        if force is not None:
            self._session = [(s, packs[0]) for s in force]
        else:
            self._session = select_multi_session(
                packs,
                self._cards,
                disabled=self._disabled,
                seen=self._seen,
                new_per_session=self._settings.new_per_session,
            )
        self._index = 0
        self._state: QuizState = QuizState.ASKING
        self._start_ns: int | None = None
        self._first_key_ns: int | None = None
        self._last_pressed_seq: list[str] = []
        self._chord_buffer: list[str] = []
        self._pending_elapsed_ms: int = 0
        self._auto_advance_step = 0
        self._auto_advance_timer: QTimer | None = None
        auto_secs = self._settings.auto_advance_secs
        self._auto_advance_interval_ms = int(auto_secs / 4 * 1000)
        self._auto_advance_ticks = 4

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        self._progress = QLabel()
        self._progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress.setStyleSheet("color: gray;")
        layout.addWidget(self._progress)

        self._pack_label = QLabel()
        self._pack_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pack_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._pack_label)

        self._prompt = QLabel()
        self._prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._prompt.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(self._prompt)

        self._your_combo = KeyCombo()
        layout.addWidget(self._your_combo)

        self._verdict = QLabel()
        self._verdict.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._verdict.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(self._verdict)

        self._dots = QLabel()
        self._dots.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dots.setStyleSheet("font-size: 18px;")
        layout.addWidget(self._dots)

        self._expected_label = QLabel()
        self._expected_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._expected_label.setStyleSheet("color: gray;")
        layout.addWidget(self._expected_label)

        self._expected_combo = KeyCombo()
        layout.addWidget(self._expected_combo)

        self._demo_label = QLabel()
        self._demo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._demo_label.setStyleSheet("color: gray;")
        layout.addWidget(self._demo_label)

        self._demo_container = QHBoxLayout()
        self._demo_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(self._demo_container)

        self._hint = QLabel()
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setStyleSheet("color: gray; font-size: 13px;")
        layout.addWidget(self._hint)

        self._begin_card()

    def _compute_thresholds(self) -> Thresholds:
        fixed = Thresholds(
            fast_ms=self._settings.fast_ms,
            slow_ms=self._settings.slow_ms,
        )
        if not self._settings.auto_adjust_thresholds:
            return fixed
        cutoff = datetime.now(timezone.utc) - timedelta(days=PERSONAL_LOOKBACK_DAYS)
        recent_signals = [
            signals
            for _sid, log, signals in self._storage.read_reviews()
            if datetime.fromisoformat(log.to_dict()["review_datetime"]) >= cutoff
        ]
        return get_thresholds(recent_signals, defaults=fixed)

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
        self._auto_advance_timer = QTimer(self)
        self._auto_advance_timer.timeout.connect(self._tick_auto_advance)
        self._auto_advance_timer.start(self._auto_advance_interval_ms)

    def _cancel_auto_advance(self) -> None:
        if self._auto_advance_timer is not None:
            self._auto_advance_timer.stop()
            self._auto_advance_timer = None
        self._auto_advance_step = 0

    def _tick_auto_advance(self) -> None:
        self._auto_advance_step += 1
        if self._auto_advance_step >= self._auto_advance_ticks:
            self._cancel_auto_advance()
            self._finalize(correct=True)
        else:
            self._dots.setText(
                " ".join(
                    self.DOT_CHAR if i < self._auto_advance_step else "○"
                    for i in range(3)
                )
            )

    def _render_state(self) -> None:
        current = self._current()
        self._your_combo.clear()
        self._expected_combo.clear()
        self._expected_label.setText("")
        self._verdict.setText("")
        self._verdict.setStyleSheet("font-size: 18px; font-weight: bold;")
        self._dots.setText("")
        self._demo_label.setText("")
        while self._demo_container.count():
            item = self._demo_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if current is None:
            self._progress.setText("")
            self._pack_label.setText("")
            self._prompt.setText("Session complete")
            self._hint.setText("Press Enter to return home")
            return

        shortcut, pack = current
        self._progress.setText(f"{self._index + 1} / {len(self._session)}")
        color = PACK_COLORS.get(pack.id, "gray")
        self._pack_label.setText(pack.name)
        self._pack_label.setStyleSheet(f"font-weight: bold; color: {color};")

        prompt_text = shortcut.action
        if shortcut.shared_id and not shortcut.shared_id.startswith(f"{pack.id}:"):
            ns = shortcut.shared_id.split(":", 1)[0]
            prompt_text += f"  (shared with {ns})"
        self._prompt.setText(prompt_text)

        if self._state is QuizState.ASKING:
            if self._chord_buffer:
                self._your_combo.set_combo(list(self._chord_buffer))
                self._hint.setText("Now press the next key...")
            else:
                self._hint.setText(
                    "Press the shortcut | Space if you don't know | F4 to skip forever"
                )
            return

        expected_seq = self._expected_seq(shortcut, pack)

        if self._state is QuizState.CORRECT_DONE:
            self._your_combo.set_combo(expected_seq, chip_class="correct")
            self._verdict.setText("Correct")
            self._verdict.setStyleSheet(
                "font-size: 18px; font-weight: bold; color: #2e7d32;"
            )
            self._dots.setText(
                " ".join(
                    self.DOT_CHAR if i < self._auto_advance_step else "○"
                    for i in range(3)
                )
            )
            if shortcut.demo_before and shortcut.demo_after:
                self._demo_label.setText("What it does:")
                demo = TextBufferDemo(shortcut.demo_before, shortcut.demo_after)
                self._demo_container.addWidget(demo)
            self._hint.setText("Press Enter to continue | F4 to skip forever")
            return

        # WRONG_PRACTICE
        self._verdict.setText("Wrong" if self._last_pressed_seq else "Don't know")
        self._verdict.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #c62828;"
        )
        self._expected_label.setText("Try this:")
        self._expected_combo.set_combo(expected_seq, chip_class="correct")
        if shortcut.demo_before and shortcut.demo_after:
            self._demo_label.setText("What it does:")
            demo = TextBufferDemo(shortcut.demo_before, shortcut.demo_after)
            self._demo_container.addWidget(demo)
        if self._chord_buffer:
            self._your_combo.set_combo(list(self._chord_buffer))
            self._hint.setText("Now press the next key...")
        else:
            if self._last_pressed_seq:
                self._your_combo.set_combo(self._last_pressed_seq, chip_class="wrong")
            self._hint.setText(
                "Y if you had it | Enter to skip once | F4 to skip forever"
            )

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat():
            return
        combo = qt_event_to_combo(event)
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._cancel_auto_advance()
            self._app.pop_screen()
            return
        if key == Qt.Key.Key_F4:
            self._action_dismiss_card()
            return

        if combo is None:
            return

        if self._current() is None:
            if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                self._app.pop_screen()
            return

        if self._state is QuizState.ASKING:
            self._handle_asking(combo, event)
        elif self._state is QuizState.CORRECT_DONE:
            self._handle_correct_done(combo, event)
        else:
            self._handle_wrong_practice(combo, event)

    def _handle_asking(self, combo: str, event: QKeyEvent) -> None:
        current = self._current()
        assert current is not None
        shortcut, pack = current

        if event.key() == Qt.Key.Key_Space and not self._chord_buffer:
            self._pending_elapsed_ms = self._elapsed_ms()
            self._last_pressed_seq = []
            self._state = QuizState.WRONG_PRACTICE
            self._render_state()
            return

        if self._first_key_ns is None:
            self._first_key_ns = time.monotonic_ns()

        self._chord_buffer.append(combo)

        position = len(self._chord_buffer) - 1
        if not self._match_position(position, combo, shortcut, pack):
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

    def _handle_correct_done(self, combo: str, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._cancel_auto_advance()
            self._finalize(correct=True)

    def _handle_wrong_practice(self, combo: str, event: QKeyEvent) -> None:
        current = self._current()
        assert current is not None
        shortcut, pack = current

        if not self._chord_buffer and event.key() == Qt.Key.Key_Y:
            self._remember_alias_seq(
                self._last_pressed_seq, self._expected_seq(shortcut, pack)
            )
            self._finalize(correct=True)
            return

        if not self._chord_buffer and event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        ):
            self._finalize(correct=False)
            return

        self._chord_buffer.append(combo)

        position = len(self._chord_buffer) - 1
        if not self._match_position(position, combo, shortcut, pack):
            self._last_pressed_seq = list(self._chord_buffer)
            self._chord_buffer = []
            self._render_state()
            return

        if len(self._chord_buffer) < self._expected_chord_length(pack):
            self._render_state()
            return

        self._chord_buffer = []
        self._finalize(correct=False)

    def _remember_alias_seq(
        self, pressed_seq: list[str], expected_seq: list[str]
    ) -> None:
        if not pressed_seq or len(pressed_seq) != len(expected_seq):
            return
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

    def _action_dismiss_card(self) -> None:
        current = self._current()
        if current is None:
            return
        shortcut, pack = current
        self._cancel_auto_advance()
        self._disabled.add(pack.shortcut_id(shortcut))
        self._storage.save_disabled(self._disabled)
        self._advance()


class BrowseScreen(QWidget):
    def __init__(self, app: "KeypalApp", pack: Pack, storage: Storage):
        super().__init__()
        self._app = app
        self._pack = pack
        self._storage = storage
        self._disabled: set[str] = storage.load_disabled()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title = QLabel(pack.name)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        desc = QLabel(pack.description)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: gray;")
        layout.addWidget(desc)

        if pack.prefix:
            pretty = "+".join(prettify_combo(pack.prefix))
            prefix_label = QLabel(f"All shortcuts shown after prefix {pretty}")
            prefix_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            prefix_label.setStyleSheet("color: gray; font-style: italic;")
            layout.addWidget(prefix_label)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list)

        for i, shortcut in enumerate(pack.shortcuts):
            item = QListWidgetItem(self._browse_label(shortcut))
            item.setData(Qt.ItemDataRole.UserRole, i)
            self._list.addItem(item)

        hint = QLabel("Enter to practice | F4 to toggle skip | Esc to go back")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(hint)

    def _browse_label(self, shortcut: Shortcut) -> str:
        action = shortcut.action
        keys = "  /  ".join("+".join(prettify_combo(k)) for k in shortcut.keys)
        sid = self._pack.shortcut_id(shortcut)
        skipped = "  (skipped)" if sid in self._disabled else ""
        shared = ""
        if shortcut.shared_id and not shortcut.shared_id.startswith(
            f"{self._pack.id}:"
        ):
            ns = shortcut.shared_id.split(":", 1)[0]
            shared = f"  (common with {ns})"
        return f"{action}    {keys}{shared}{skipped}"

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        idx = item.data(Qt.ItemDataRole.UserRole)
        shortcut = self._pack.shortcuts[idx]
        self._app.push_screen(
            QuizScreen(self._app, (self._pack,), self._storage, force=[shortcut])
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._app.pop_screen()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self._list.currentItem()
            if item:
                idx = item.data(Qt.ItemDataRole.UserRole)
                shortcut = self._pack.shortcuts[idx]
                self._app.push_screen(
                    QuizScreen(
                        self._app, (self._pack,), self._storage, force=[shortcut]
                    )
                )
        elif key == Qt.Key.Key_F4:
            item = self._list.currentItem()
            if item:
                idx = item.data(Qt.ItemDataRole.UserRole)
                shortcut = self._pack.shortcuts[idx]
                sid = self._pack.shortcut_id(shortcut)
                if sid in self._disabled:
                    self._disabled.discard(sid)
                else:
                    self._disabled.add(sid)
                self._storage.save_disabled(self._disabled)
                item.setText(self._browse_label(shortcut))
        else:
            super().keyPressEvent(event)


class StatsScreen(QWidget):
    def __init__(self, app: "KeypalApp", packs: tuple[Pack, ...], storage: Storage):
        super().__init__()
        self._app = app
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Stats")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        body = QLabel(self._render_stats(packs, storage))
        body.setStyleSheet("font-family: monospace;")
        layout.addWidget(body)

        hint = QLabel("Esc to go back")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(hint)

    def _render_stats(self, packs: tuple[Pack, ...], storage: Storage) -> str:
        cards = storage.load_cards()
        disabled = storage.load_disabled()
        review_count = sum(1 for _ in storage.read_reviews())
        now = datetime.now(timezone.utc)

        state_counts = {state: 0 for state in State}
        for card in cards.values():
            state_counts[card.state] = state_counts.get(card.state, 0) + 1

        pack_lines = []
        for pack in packs:
            active_ids = [
                pack.shortcut_id(s)
                for s in pack.shortcuts
                if pack.shortcut_id(s) not in disabled
            ]
            tracked = len(set(active_ids) & cards.keys())
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

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._app.pop_screen()
        else:
            super().keyPressEvent(event)


SETTING_FIELDS = [
    (
        "new_per_session",
        "New cards per session",
        "How many new shortcuts to introduce each session",
    ),
    (
        "auto_advance_secs",
        "Auto-advance delay (seconds)",
        "Seconds to wait before advancing after a correct answer",
    ),
]

THRESHOLD_FIELDS = [
    (
        "fast_ms",
        "Fast threshold (ms)",
        "Correct answers faster than this are rated Easy",
    ),
    (
        "slow_ms",
        "Slow threshold (ms)",
        "Correct answers slower than this are rated Hard",
    ),
]


class SettingsScreen(QWidget):
    def __init__(self, app: "KeypalApp", storage: Storage):
        super().__init__()
        self._app = app
        self._storage = storage
        self._settings = storage.load_settings()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        title = QLabel("Settings")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        self._inputs: dict[str, QLineEdit] = {}
        for field_name, label, desc in SETTING_FIELDS + THRESHOLD_FIELDS:
            row = QVBoxLayout()
            row.setSpacing(2)
            lbl = QLabel(label)
            lbl.setStyleSheet("font-weight: bold;")
            row.addWidget(lbl)
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet("color: gray; font-size: 12px;")
            row.addWidget(desc_lbl)
            inp = QLineEdit(str(getattr(self._settings, field_name)))
            self._inputs[field_name] = inp
            row.addWidget(inp)
            layout.addLayout(row)

        self._auto_adjust = QCheckBox("Auto-adjust thresholds based on my timing")
        self._auto_adjust.setChecked(self._settings.auto_adjust_thresholds)
        self._auto_adjust.toggled.connect(self._on_auto_adjust_toggled)
        layout.addWidget(self._auto_adjust)

        self._on_auto_adjust_toggled(self._settings.auto_adjust_thresholds)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(save_btn)
        reset_btn = QPushButton("Reset to defaults")
        reset_btn.clicked.connect(self._reset)
        btn_layout.addWidget(reset_btn)
        layout.addLayout(btn_layout)

        path_label = QLabel(f"Stored in {storage.settings_path}")
        path_label.setStyleSheet("color: gray; font-size: 11px;")
        path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(path_label)

        hint = QLabel("Esc to go back")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(hint)

    def _on_auto_adjust_toggled(self, checked: bool) -> None:
        for field_name, _, _ in THRESHOLD_FIELDS:
            self._inputs[field_name].setEnabled(not checked)

    def _save(self) -> None:
        try:
            kwargs = {}
            for field_name, _, _ in SETTING_FIELDS + THRESHOLD_FIELDS:
                raw = self._inputs[field_name].text()
                if field_name == "auto_advance_secs":
                    kwargs[field_name] = float(raw)
                else:
                    kwargs[field_name] = int(raw)
            kwargs["auto_adjust_thresholds"] = self._auto_adjust.isChecked()
            settings = Settings(**kwargs)
        except ValueError, TypeError:
            QMessageBox.warning(self, "Invalid input", "All values must be numbers")
            return
        self._settings = settings
        self._storage.save_settings(settings)
        self._app.settings = settings
        self._app.statusBar().showMessage("Settings saved", 3000)

    def _reset(self) -> None:
        self._settings = Settings()
        self._storage.save_settings(self._settings)
        self._app.settings = self._settings
        for field_name, _, _ in SETTING_FIELDS + THRESHOLD_FIELDS:
            self._inputs[field_name].setText(str(getattr(self._settings, field_name)))
        self._auto_adjust.setChecked(self._settings.auto_adjust_thresholds)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._app.pop_screen()
        else:
            super().keyPressEvent(event)


class DiagnosticScreen(QWidget):
    def __init__(self, app: "KeypalApp"):
        super().__init__()
        self._app = app
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        title = QLabel("Key Diagnostic")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        prompt = QLabel("Press any key combo")
        prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(prompt)

        self._combo_display = KeyCombo()
        layout.addWidget(self._combo_display)

        self._raw_label = QLabel()
        self._raw_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._raw_label.setStyleSheet("color: gray; font-family: monospace;")
        layout.addWidget(self._raw_label)

        self._normalized_label = QLabel()
        self._normalized_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._normalized_label)

        hint = QLabel("Esc to return")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(hint)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._app.pop_screen()
            return

        combo = qt_event_to_combo(event)
        if combo is None:
            return

        self._combo_display.clear()
        try:
            self._combo_display.set_combo(combo)
        except ValueError:
            pass

        key_enum = Qt.Key(event.key())
        enum_name = key_enum.name
        if isinstance(enum_name, bytes):
            enum_name = enum_name.decode()
        mods = event.modifiers()
        mod_parts = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            mod_parts.append("Ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            mod_parts.append("Alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            mod_parts.append("Shift")
        if mods & Qt.KeyboardModifier.MetaModifier:
            mod_parts.append("Meta")
        raw = f"Qt: {enum_name} | mods: {'+'.join(mod_parts) or 'none'} | text: {event.text()!r}"
        self._raw_label.setText(raw)
        self._normalized_label.setText(f"Normalized: {combo}")


class KeypalApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("keypal")
        self.setMinimumSize(500, 400)
        self.resize(600, 500)
        self.setStyleSheet("QWidget { font-size: 14px; }")

        self.packs = builtin_packs()
        self.storage = Storage()
        self.settings = self.storage.load_settings()

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)
        self._screen_stack: list[QWidget] = []

        self._home = HomeScreen(self)
        self.push_screen(self._home)

    def push_screen(self, screen: QWidget) -> None:
        self._stack.addWidget(screen)
        self._stack.setCurrentWidget(screen)
        self._screen_stack.append(screen)
        screen.setFocus()

    def pop_screen(self) -> None:
        if len(self._screen_stack) <= 1:
            return
        old = self._screen_stack.pop()
        self._stack.removeWidget(old)
        old.deleteLater()
        current = self._screen_stack[-1]
        self._stack.setCurrentWidget(current)
        current.setFocus()
        if hasattr(current, "on_resume"):
            current.on_resume()


def main() -> None:
    app = QApplication([])
    window = KeypalApp()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
