# Show available commands
_default:
    @just --list --unsorted

# Run the app
run *ARGS:
    uv run keypal {{ARGS}}

# Run the test suite
test *ARGS:
    uv run pytest {{ARGS}}

# Run tests, drop into pdb on failure
pdb *ARGS:
    uv run pytest --pdb --maxfail=1 {{ARGS}}

# Format, lint, and test
qa:
    uv run ruff format .
    uv run ruff check . --fix
    uv run pytest

# Bump version (usage: just bump patch|minor|major)
bump value:
    uv version --bump {{ value }}

# Build the package
build:
    uv sync
    uv build --clear

# Publish to PyPI
publish:
    uv publish
