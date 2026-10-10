# Contributing

Thank you for your interest in improving LLM Response Evaluation Lab. Bug reports, documentation
fixes, and focused code changes are welcome.

## Development setup

```bash
git clone https://github.com/chimdaX/LLM_response_evaluation_lab.git
cd LLM_response_evaluation_lab
python -m venv .venv
source .venv/bin/activate              # Windows: .\.venv\Scripts\Activate.ps1 or .venv\Scripts\activate.bat
python -m pip install -e ".[dev]"
```

Python 3.11–3.13 is supported. See [docs/SETUP.md](docs/SETUP.md) for platform details.

## Checks to run before opening a pull request

```bash
ruff check .                  # lint
ruff format --check .         # formatting (run `ruff format .` to fix)
python -m pytest              # full test suite: offline, no API keys
ai-eval validate --data-dir data/examples --strict
python scripts/verify_install.py   # optional locally; CI runs it on every pull request
```

CI runs the same checks on Ubuntu, Windows, and macOS. A pull request should pass all of them.

## Guidelines

- **Keep it small and offline.** Runtime code depends only on Pydantic and must not make
  network calls. Do not add a dependency without discussing it in an issue first.
- **Test what you change.** Add tests for new behaviour and for failure cases. Tests must not
  depend on the network, the current date, or the contents of `data/benchmark/`. Use the
  fixtures in `tests/conftest.py`, including `fresh_benchmark` for an isolated copy of the
  benchmark prompts.
- **Don't weaken a test to make it pass.** If a test encodes behaviour you are deliberately
  changing, explain the change in the pull request and in `CHANGELOG.md`.
- **Keep data backward compatible.** Schema changes must only add optional fields under a new
  `schema_version`, and older records must stay valid. Changes to dimensions, anchors, or error
  labels need a new **rubric** version (`rubrics/rubric_vN.md` and `rubric.py`).
- **Keep built-in resources in sync.** `config/scoring.json`, `rubrics/rubric_v1.md`,
  `data/examples/*.json`, and `templates/*.json` have byte-identical copies in
  `src/ai_response_eval/resources/`. Update both; `tests/test_packaging.py` fails if they differ.
- **Protect integrity.** Never present synthetic or AI-generated content as human annotations
  or real model outputs, and never commit credentials or personal data.
  `ai-eval validate` scans for common patterns, but it is not a guarantee.
- **Update the docs** that describe any behaviour you change, and add an entry under
  `[Unreleased]` in `CHANGELOG.md`.

## Benchmark data

`data/benchmark/` contains the maintainer's in-progress human benchmark. Please don't modify
it in pull requests. If you find a factual problem in a prompt's reference notes, open an
issue that cites a reliable source.

## Reporting bugs and requesting features

Use the issue templates. For bugs, include:
- the `ai-eval --version` output;
- your operating system and Python version;
- the exact command and its full output;
- a minimal dataset that reproduces the problem, if possible (`ai-eval init DIR --example` is a
  good starting point).

## Commit messages

Use short, imperative subjects with a type prefix, for example:
`feat: add --json output to compare`, `fix: handle empty prompts.json`,
`docs: clarify revision chains`, `test: cover CRLF input`, `data: evaluate B002-A`.
