# keypal

A terminal app (Textual TUI) for spaced-repetition learning of keyboard shortcuts. Uses FSRS for scheduling.

## Run / test

- `just run`: launch the app
- `just qa`: format, lint, and test
- `just test`: pytest only

`uv` is the only Python tool. Don't install packages globally.

## Project layout

```
src/keypal/
├── app.py              # Textual app + screens (Home, Quiz, Browse, Stats, Diagnostic, ConfirmSwapModal)
├── models.py           # Shortcut, Pack dataclasses; parse_pack/load_pack/builtin_packs
├── keys.py             # normalize/matches/prettify; terminal byte-equivalents; symbol aliases
├── scheduler.py        # classify(correct, response_time_ms); select_session
├── storage.py          # cards.json, review_log.jsonl, aliases.json, disabled.json
├── tmux.py             # TmuxPrefixSwap + apply_tmux_overrides (dynamic provider)
├── obsidian.py         # apply_obsidian_overrides (dynamic provider)
└── packs/              # built-in TOMLs (readline, tmux, obsidian, python_repl)
```

`PLAN.md` and `TODO.md` are intentionally **untracked**. PLAN.md is the design doc; TODO.md tracks pending/resolved/rejected items. Don't commit them.

## Firm design decisions

- **Muscle memory only.** No self-rating mode. If a shortcut can't be captured by Textual, it doesn't belong in a pack.
- **FSRS rating** comes from correctness + response time only (`scheduler.classify`). No Anki-style 1/2/3/4 self-rate.
- **Tmux prefix-swap** is per-pack opt-in with explicit confirmation modal, never app-wide. Activates when entering a pack whose `prefix` matches the user's live tmux prefix; restores on screen pop / app exit.
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

- **Textual Screen BINDINGS may not fire** when `on_key` runs first and consumes the event. For `QuizScreen`, `F4` is handled explicitly in `on_key` AND listed in `BINDINGS` for the footer label. Use the same pattern when adding new screen-level keybinds that need to win against state-machine keypress handling.
- **Terminal byte collisions**: `Ctrl+H ≡ Backspace`, `Ctrl+I ≡ Tab`, `Ctrl+M ≡ Enter`, `Ctrl+[ ≡ Escape`. Handled in `keys.matches()` via `TERMINAL_EQUIVALENTS`.
- **Tmux mistranslates** some Alt+letter combos to Ctrl+arrow inside tmux. The `Y` override in `QuizScreen` saves the mistranslation as an alias for the expected combo so future presses just match.
- **Symbol keys**: Textual reports `event.key="comma"` (the name), not `,` (the character). `keys.SYMBOL_NAMES` maps names → characters in `normalize()`.
- **`+` is both separator and key**. `normalize()` and `_split_normalized()` use a sentinel to handle `"+"`, `"ctrl++"`, etc.
- **Terminal-emulator-level interception** (GNOME Terminal eating Ctrl+Shift+F for "Find", Ctrl+Shift+T for "New Tab", etc.) is not fixable in code. The diagnostic screen (`D` from home) shows what Textual receives, which is useful for telling user vs terminal vs keypal bugs apart.
- **Pack TOMLs**: drop the `command` field on wrapper-style tmux binds (e.g. `command-prompt -I "..."`) to avoid over-matching across multiple shortcuts that all start with `command-prompt`.
- **`textual` `ENABLE_COMMAND_PALETTE = False`** on `KeypalApp` so Ctrl+P reaches the quiz instead of opening Textual's palette.

## Storage layout

Default base dir: `platformdirs.user_data_dir("keypal")` (e.g. `~/.local/share/keypal/` on Linux). `KEYPAL_DATA_DIR` env var overrides for tests.

- `cards.json`: `{shortcut_id: card_dict}` mapping FSRS state. Key is `shared_id` if set, else `{pack.id}:{action}`.
- `review_log.jsonl`: append-only NDJSON-style log; one `{shortcut_id, log}` per line.
- `aliases.json`: `{expected_combo: [pressed_combos]}` saved when user presses Y on a wrong answer.
- `disabled.json`: array of shortcut IDs the user dismissed via F4.

## TUI key conventions

- **Esc**: back / cancel
- **Enter**: confirm / continue / advance from CORRECT_DONE / return from session-complete
- **Space**: "don't know" in quiz (treated as wrong)
- **Y**: in WRONG_PRACTICE, claim "I actually had it right" (saves alias, advances as correct)
- **F4**: skip current shortcut forever (adds to disabled.json)
- **B**: from home, browse the highlighted pack
- **D**: from home, diagnostic screen for testing key reception
- **S**: from home, stats screen

## When making changes

1. Keep commits small.
2. Run `just qa` (or at minimum `uv run pytest`) before claiming a change works.
3. If touching `app.py`, run a smoke test via `App.run_test()` pilot harness (examples in conversation history). UI tests via `pytest-asyncio` are a TODO.
4. If a change affects user data files, add a one-time migration only if other people have data. For the single-user development phase, just rename the file in place and skip the migration code.
