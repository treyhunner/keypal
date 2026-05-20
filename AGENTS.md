# keypal

A PySide6 desktop app for spaced-repetition learning of keyboard shortcuts. Uses FSRS for scheduling.

## Run / test

- `just run`: launch the app
- `just qa`: format, lint, and test
- `just test`: pytest only

`uv` is the only Python tool. Don't install packages globally.

## Project layout

```
src/keypal/
├── app.py              # PySide6 app (QMainWindow) + screens (Home, Quiz, Browse, Stats, Settings, Diagnostic)
├── models.py           # Shortcut, Pack dataclasses; parse_pack/load_pack/builtin_packs
├── keys.py             # normalize/matches/prettify for Qt key events
├── scheduler.py        # classify; select_session; select_multi_session; threshold blending
├── storage.py          # cards.json, review_log.jsonl, aliases.json, disabled.json, selected_packs.json
├── tmux.py             # apply_tmux_overrides (dynamic provider)
├── obsidian.py         # apply_obsidian_overrides (dynamic provider)
└── packs/              # built-in TOMLs (readline, tmux, obsidian, python_repl)
```

Pending work is tracked in [GitHub Issues](https://github.com/treyhunner/keypal/issues).

## Firm design decisions

- **Muscle memory only.** No self-rating mode. If a shortcut can't be captured by the app, it doesn't belong in a pack.
- **FSRS rating** comes from correctness + response time only (`scheduler.classify`). No Anki-style 1/2/3/4 self-rate.
- **`shared_id` on a Shortcut** identifies the FSRS card across packs. Two shortcuts in different packs with the same `shared_id` share one card. Used to bridge readline ↔ python_repl, etc.
- **Dynamic packs**: `tmux.toml` and `obsidian.toml` are a static curated baseline + a `command` field that joins to live config (`tmux list-keys -T prefix` and `~/.config/obsidian/.../hotkeys.json`). `apply_tmux_overrides` and `apply_obsidian_overrides` substitute keys at `builtin_packs()` time.

## Conventions

- **Tiny commits.** One logical change per commit, including small refactors. The user explicitly values being able to look back at the step-by-step history.
- **No emojis** anywhere. Per user-level CLAUDE.md.
- **No em dashes** in Python code or markdown. Use `--` only when no equally-readable alternative exists.
- **`uv` for everything Python.** `uv run`, `uvx`, `uv add`. Never `pip install` globally. For one-off scripts, use `#!/usr/bin/env uvrs` shebang with PEP 723 inline metadata.
- **Builtin `open(path)`, never `path.open()`.**
- **Mode keyword arg**: `mode="at"` not `"a"`.
- **File variable named `file`**, not `f`.
- Prefer `tomllib.loads(path.read_text())` over `with open(...) as file: tomllib.load(file)`.
- Default to no comments. Add only when the WHY is non-obvious (a hidden constraint, surprising behavior, intentional workaround).

## Common gotchas

- **CapsLock/NumLock/ScrollLock as modifiers**: Qt fires a separate key event for lock keys before the actual chord. Users who remap CapsLock to Ctrl will see a spurious `capslock` press. These are in `_PURE_MODIFIERS` in keys.py so they're ignored.
- **Auto-repeat during chords**: Releasing a modifier before the letter key generates bare auto-repeat events. `QuizScreen.keyPressEvent` returns early on `event.isAutoRepeat()`.
- **`+` is both separator and key**. `normalize()` and `_split_normalized()` use a sentinel to handle `"+"`, `"ctrl++"`, etc.
- **`SYMBOL_NAMES` in keys.py** is kept for backward compatibility with aliases.json files created during the Textual era (e.g. `"comma"` -> `","`). Qt uses `QKeyEvent` with proper key codes, so new aliases won't use symbol names.
- **Pack TOMLs**: drop the `command` field on wrapper-style tmux binds (e.g. `command-prompt -I "..."`) to avoid over-matching across multiple shortcuts that all start with `command-prompt`.
- **`shared_id` makes `Pack.shortcut_id(shortcut)` return the shared id**, so identical shared_id values across packs collapse to one FSRS card.
- **Demos for shared shortcuts inherit** from the source shortcut at load time (see `_inherit_demos` in `models.py`). Don't duplicate `demo_before`/`demo_after` across packs.

## Storage layout

Default base dir: `platformdirs.user_data_dir("keypal")` (e.g. `~/.local/share/keypal/` on Linux). `KEYPAL_DATA_DIR` env var overrides for tests.

- `cards.json`: `{shortcut_id: card_dict}` mapping FSRS state. Key is `shared_id` if set, else `{pack.id}:{action}`.
- `review_log.jsonl`: append-only NDJSON-style log; one `{shortcut_id, log}` per line.
- `aliases.json`: `{expected_combo: [pressed_combos]}` saved when user presses Y on a wrong answer.
- `disabled.json`: array of shortcut IDs the user dismissed via F4.
- `seen.json`: array of `"{pack_id}::{shortcut_id}"` strings; tracks which shared shortcuts the user has been introduced to in each pack (so a shared shortcut shows once per pack even if its FSRS card isn't due).
- `selected_packs.json`: array of pack IDs the user has checked for multi-pack practice. `None` (missing file) means all packs selected.

## Key conventions

- **Esc**: back / cancel
- **Enter**: confirm / continue / advance from CORRECT_DONE / return from session-complete / practice shortcut from browse
- **Space**: "don't know" in quiz (treated as wrong)
- **Y**: in WRONG_PRACTICE, claim "I actually had it right" (saves alias, advances as correct)
- **F4**: skip current shortcut forever (adds to disabled.json)
- **P**: from home, start multi-pack practice with checked packs
- **X**: from home, toggle pack checkbox for multi-pack selection
- **B**: from home, browse the highlighted pack
- **C**: from home, settings screen
- **D**: from home, diagnostic screen for testing key reception
- **S**: from home, stats screen
- **Arrow keys**: on home, cycle between Practice button and pack list

## When making changes

1. Keep commits small.
2. Run `just qa` (or at minimum `uv run pytest`) before claiming a change works.
3. If touching `app.py`, run existing UI tests (`tests/test_app.py`) and add coverage for new behavior.
4. If a change affects user data files, add a migration path (the package is published and others may have data).
