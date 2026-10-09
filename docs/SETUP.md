# Setup

Requirements: **Python 3.11 or newer** and an internet connection for the first install.
No API keys, database or paid services are needed. Run every command from the repository root
(the folder that contains `pyproject.toml`).

## Linux / macOS / WSL

```bash
python3 --version                    # must be 3.11+
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On Debian/Ubuntu/WSL, if `python3 -m venv` fails, install the venv module first:
`sudo apt install python3-venv`.

## Windows PowerShell

```powershell
py --version                         # must be 3.11+; use "python" if the py launcher is missing
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If activation fails with *"running scripts is disabled on this system"*, allow local scripts
for your user once, then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

> **One environment per OS.** A `.venv` created in WSL/Linux does not work from Windows
> PowerShell, and the reverse is also true. If you switch, delete `.venv` and create it again.

## Verify the installation

These commands are the same on every platform once the virtual environment is active:

```bash
ai-eval --version
ai-eval validate --data-dir data/examples
ai-eval score    --data-dir data/examples
ai-eval compare  --data-dir data/examples
ai-eval report   --data-dir data/examples --output-dir reports
python -m pytest
ruff check .
```

Expected results:

| Command | Expected outcome |
|---|---|
| `validate` | `OK: data/examples is valid (5 prompts, 10 responses, 10 evaluations, 5 preferences); 0 warning(s).` and exit code 0 |
| `score` | A table of 10 evaluations, 4 of them flagged for review |
| `compare` | 5 decisions, each labelled *Human-recorded preference* and *System-generated score suggestion* |
| `report` | Writes `evaluation_results.csv`, `evaluation_results.json`, `pairwise_results.csv` and `summary.md` into `reports/` |
| `pytest` | All tests pass |
| `ruff check .` | `All checks passed!` |

`report` refuses to replace existing report files. To regenerate them, add `--overwrite`:

```bash
ai-eval report --data-dir data/examples --output-dir reports --overwrite
```

`python -m ai_response_eval ...` works the same way as `ai-eval ...` if the script is not on your `PATH`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | The input data failed validation (or `validate --strict` found warnings) |
| 2 | Usage, configuration or file-system error, e.g. a missing config or report files that already exist |

## Troubleshooting

- **`ai-eval: command not found`**: the virtual environment is not active. Activate it again, or
  use `python -m ai_response_eval`.
- **`scoring config not found: config/scoring.json`**: run from the repository root, or pass
  `--config path/to/scoring.json`.
- **Hashes in `summary.md` differ between Windows and Linux**: the repository's `.gitattributes`
  forces LF line endings so hashes match. Files edited outside git may still contain CRLF line
  endings; re-save them with LF.
