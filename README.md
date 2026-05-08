# keypal

Spaced-repetition practice for keyboard shortcuts in your terminal. Build muscle memory for the shortcuts you actually use, scheduled with [FSRS](https://github.com/open-spaced-repetition/py-fsrs).

## Why a TUI?

- **Browsers can't capture most shortcuts.** Browsers intercept Ctrl+W, Ctrl+T, Ctrl+N, Ctrl+Q, etc. at the OS level before JavaScript sees them.
- **A raw-mode terminal captures almost everything.** Ctrl+A, Ctrl+E, Ctrl+K, Alt+F, even Ctrl+C come through.
- **Distribution is simple.** One CLI install. No packaging headaches.

## Install

For now, clone and run from source:

```sh
git clone <repo>
cd keypal
uv sync
just run
```

(Pip/pipx packaging is on the TODO list.)

## Built-in packs

- **`readline`**: common bash / readline shortcuts (Ctrl+A, Alt+F, Ctrl+W, etc.)
- **`python_repl`**: Python 3.13+ REPL (F1/F2/F3 modes, Tab autocomplete, plus shared readline overlap)
- **`tmux`**: your live tmux config, parsed from `tmux list-keys` at startup
- **`obsidian`**: your live Obsidian hotkeys, read from `~/.config/obsidian/.../hotkeys.json`

The `tmux` and `obsidian` packs are *hybrid*: a curated list of common shortcuts with friendly descriptions, with **your actual key bindings substituted in** if you have customs. Change a binding in tmux or Obsidian, restart keypal, and the pack reflects it.

A `shared_id` mechanism lets shortcuts in different packs share the same FSRS card. Practice Ctrl+A in `readline` and it counts toward `python_repl` too (since the Python REPL uses readline under the hood).

## Using the app

### Home screen

- Arrow keys: navigate between packs
- Enter: start practicing the highlighted pack
- **B**: browse the highlighted pack (read-only cheat sheet)
- **S**: stats (cards by FSRS state, per-pack progress)
- **D**: diagnostic screen for testing what your terminal is sending
- **Q**: quit

### In a quiz session

- (the shortcut): submit your answer
- Space: "I don't know" (treated as wrong)
- Enter: continue after a correct answer
- Y: after a wrong answer, claim "I actually had it right" (saves an alias for terminal-mistranslated keys)
- **F4**: skip this shortcut forever (won't appear in future sessions)
- Esc: back to home

After a correct answer, three dots fill in left to right over three seconds, then auto-advances. Press Enter any time to skip the wait.

### After a wrong answer

You'll see what you pressed (red), the expected combo (green), and a hint with your options. **Press the correct combo** to advance with practice credit, or use the keys above to skip / claim correct / dismiss.

## Storage

Your data lives in `~/.local/share/keypal/` on Linux (platform-equivalent elsewhere via `platformdirs`):

- `cards.json`: FSRS state for each shortcut you've practiced
- `review_log.jsonl`: append-only log of every review
- `aliases.json`: terminal-mistranslation aliases you've taught keypal
- `disabled.json`: shortcuts you've dismissed with F4

Override the location with the `KEYPAL_DATA_DIR` environment variable.

## Limitations

- **Some Ctrl combos are byte-equivalent** to other keys in terminals: Ctrl+H ≡ Backspace, Ctrl+I ≡ Tab, Ctrl+M ≡ Enter, Ctrl+[ ≡ Esc. keypal accepts both forms automatically.
- **Your terminal emulator may eat some shortcuts** before they reach keypal (GNOME Terminal binds Ctrl+Shift+F to Find, for example). Use the diagnostic screen (D) to confirm. Fix in your terminal's preferences.
- **Inside tmux**, shortcuts that conflict with your tmux prefix won't reach keypal unless you opt in to the per-pack prefix swap (offered automatically when you enter the tmux pack).
- Keys that physically exist on the keyboard but aren't in keypal (rare combos, complex chords beyond two keys) need to be added to a pack manually.

## Custom packs

Drop a `.toml` file in `~/.config/keypal/packs/` (TODO: not yet implemented; for now, edit `src/keypal/packs/`).

Pack format:

```toml
[pack]
id = "my-app"
name = "My App"
description = "Shortcuts for thing I use"
prefix = "ctrl+a"  # optional; for chord shortcuts like tmux

[[shortcuts]]
action = "Open settings"
keys = ["ctrl+,"]
tags = ["meta"]
shared_id = "readline:Open settings"  # optional; shares FSRS card across packs
command = "settings:open"             # optional; for dynamic key substitution from live config
```

## Contributing

See [AGENTS.md](AGENTS.md) for code conventions, project layout, and common gotchas.

```sh
just qa     # format + lint + test
just test   # tests only
```
