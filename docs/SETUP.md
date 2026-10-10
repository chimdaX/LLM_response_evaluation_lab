# Installation and Setup

Requirements: **Python 3.11, 3.12 or 3.13** and **Git**. An internet connection is needed
only to download dependencies during installation. No API keys, databases, or paid services
are used. For a guided first run, see the [Quick Start](QUICKSTART.md).

## 1. Get the code and create a virtual environment

```bash
git clone https://github.com/chimdaX/LLM_response_evaluation_lab.git
cd LLM_response_evaluation_lab
python -m venv .venv
```

Use `python3` instead of `python` if that is how Python is named on your system (common on
Linux and macOS), and `py` if you use the Windows Python launcher.

## 2. Activate the environment

| Shell | Activate | Deactivate |
|---|---|---|
| Linux / macOS (bash, zsh) | `source .venv/bin/activate` | `deactivate` |
| Windows PowerShell | `.\.venv\Scripts\Activate.ps1` | `deactivate` |
| Windows Command Prompt | `.venv\Scripts\activate.bat` | `deactivate` |

Your prompt shows `(.venv)` while it is active. Activate it in every new terminal.

## 3. Install

| You want to... | Command | Installs |
|---|---|---|
| Use the CLI | `python -m pip install -e .` | `ai-eval` and Pydantic (the only runtime dependency) |
| Develop or run the tests | `python -m pip install -e ".[dev]"` | The above, plus pytest, Ruff and build |

`-e` (editable) means changes to the source take effect without reinstalling. Leave it out
for a regular installation. Users of the CLI never need pytest or Ruff.

The quotes in `".[dev]"` are needed in zsh and harmless elsewhere.

### Installing from a built wheel (without the source tree)

```bash
python -m pip install build
python -m build                                       # creates dist/*.whl and dist/*.tar.gz
python -m pip install dist/llm_response_evaluation_lab-*.whl
```

On Windows Command Prompt, wildcards are not expanded; type the full wheel file name instead.

The wheel contains everything the CLI needs: the default scoring configuration, the rubric,
the synthetic example dataset, and the record templates. `ai-eval init DIR --example` writes
the example dataset anywhere. The documentation, the tests, and the in-progress human
benchmark (`data/benchmark/`) are only in the repository.

## 4. Verify

```bash
ai-eval --version
ai-eval init my-demo --example
ai-eval validate --data-dir my-demo
ai-eval score    --data-dir my-demo
ai-eval compare  --data-dir my-demo
ai-eval report   --data-dir my-demo --output-dir my-reports
```

| Command | Expected outcome |
|---|---|
| `--version` | `ai-eval 0.4.0` |
| `validate` | `OK: my-demo is valid (5 prompts, 10 responses, 10 evaluations, 5 preferences); 0 warning(s).` |
| `score` | A table of 10 evaluations, 4 of them flagged for review |
| `compare` | 5 decisions, each labelled *Human-recorded preference* and *System-generated score suggestion* |
| `report` | Writes 4 files into `my-reports/` |

From a clone you can also use `--data-dir data/examples` directly.

For developers:

```bash
python -m pytest                       # full test suite
ruff check . && ruff format --check .  # lint and formatting
python scripts/verify_install.py       # build, install the wheel in a fresh venv, smoke-test the CLI
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | The input data failed validation (or `validate --strict` found warnings) |
| 2 | Usage, configuration, or file-system problem, e.g. a missing `--data-dir`, a bad argument, or report files that already exist |
| 130 | An interactive session (`collect`, `annotate`, `annotate-pair`) was interrupted; drafts are kept |

## Troubleshooting

| Problem | Fix |
|---|---|
| `ai-eval: command not found` / `'ai-eval' is not recognized` | The virtual environment is not active. Activate it (step 2), or run `python -m ai_response_eval ...` |
| PowerShell: *running scripts is disabled on this system* | Run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` once, then activate again |
| `python -m venv` fails on Debian/Ubuntu/WSL | `sudo apt install python3-venv` |
| `ERROR: Package requires a different Python` | Install Python 3.11 or newer |
| `data directory '...' does not exist` | Check the path, or create a dataset with `ai-eval init DIR` (add `--example` for demo data) |
| `report files already exist` | Choose another `--output-dir`, or add `--overwrite` |
| A `.venv` from WSL does not work in Windows (or vice versa) | A virtual environment belongs to one operating system. Delete `.venv` and create it again in the shell you use |
| Report hashes differ between Windows and Linux | The repository's `.gitattributes` keeps data files at LF line endings. If you edited a file outside Git, re-save it with LF endings |
