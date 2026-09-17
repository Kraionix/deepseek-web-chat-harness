# Contributing

## Development install

```powershell
git clone https://github.com/Kraionix/deepseek-web-chat-harness
cd deepseek-web-chat-harness
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

`[dev]` adds `ruff`, `pytest`, and `pytest-cov`. No other setup is
needed: the test suite uses a real filesystem and a real `git` in
temporary directories, and never hits the network.

## Checks

```powershell
ruff check .
ruff format --check .
pytest -q
```

All three must pass. CI runs the same on Python 3.11 and 3.12.

## Coverage

`pytest --cov=dwch -q` prints a coverage report. There is no
enforced threshold yet; write tests that assert behaviour, not
coverage numbers.

## Style

- English only: code, comments, docstrings, commits.
- `from __future__ import annotations` at module top.
- `logging.getLogger(__name__)` at module level in library code.
- One concept per module. No `utils.py`, `helpers.py`, `base.py`.
- `X | None`, not `Optional[X]`. `list[X]`, not `List[X]`.
- Conventional Commits, no scope, prose body.

## Tests

- Real adapters on `tmp_path` for filesystem and git. No
  `InMemoryFilesystem`.
- Small fakes for clipboard, process, and tokenizer live in
  `tests/fakes.py`.
- One file per module under test. Cross-module scenarios go in
  `tests/integration/`.
- Docstring on every test, one line, saying what is checked.

## Architecture invariants

Do not break these without discussion:

- `domain` imports only stdlib.
- `application` imports `domain`, `shared`, its own submodules.
  Never `adapters`, never `cli`.
- `adapters` import `shared`, `application.ports`, and siblings.
  Never `application.commands`, never `cli`.
- `cli` imports everything.
- Ports are `Protocol`. Adapters satisfy them structurally.
- No Pydantic. Dataclasses for domain models.
- `apply` and `close` are atomic: validate everything before any
  write; rollback on partial failure.
- `save_state` is atomic: write temp, then rename.
