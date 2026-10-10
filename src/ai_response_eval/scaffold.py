"""Create a dataset directory: empty (to start your own) or with the synthetic example.

Used by ``ai-eval init``. Everything is copied from the package's built-in resources,
so it works from an installed wheel without the source repository. Existing files are
never overwritten.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ai_response_eval import resources
from ai_response_eval.validation import DATA_FILES

DATA_FILE_NAMES: tuple[str, ...] = tuple(name for name, _, _ in DATA_FILES.values())
TEMPLATES_SUBDIR = "templates"
REFERENCE_SUBDIR = "reference"


class ScaffoldError(RuntimeError):
    """Raised when the target cannot be initialized; nothing is written."""


def _planned(target: Path) -> list[Path]:
    templates = resources.resource_path(resources.TEMPLATES_DIR)
    return [
        *(target / name for name in DATA_FILE_NAMES),
        *(
            target / TEMPLATES_SUBDIR / t.name
            for t in sorted(templates.iterdir())
            if t.suffix == ".json"
        ),
        target / REFERENCE_SUBDIR / resources.SCORING_CONFIG,
        target / REFERENCE_SUBDIR / resources.RUBRIC,
    ]


def init_dataset(target: Path, *, example: bool) -> list[Path]:
    """Create the four data files, templates and reference copies in ``target``.

    With ``example=True`` the data files are the synthetic demonstration dataset;
    otherwise they are empty JSON arrays ready for your own records.
    """
    if target.exists() and not target.is_dir():
        raise ScaffoldError(f"{target} exists and is not a directory")
    planned = _planned(target)
    clashes = [p for p in planned if p.exists()]
    if clashes:
        names = ", ".join(str(p.relative_to(target)) for p in clashes)
        raise ScaffoldError(f"{target} already contains {names}; nothing was written")

    (target / TEMPLATES_SUBDIR).mkdir(parents=True, exist_ok=True)
    (target / REFERENCE_SUBDIR).mkdir(parents=True, exist_ok=True)
    for name in DATA_FILE_NAMES:
        if example:
            shutil.copyfile(resources.resource_path(resources.EXAMPLES_DIR, name), target / name)
        else:
            (target / name).write_bytes(b"[]\n")
    for path in planned[len(DATA_FILE_NAMES) :]:
        source = (
            resources.resource_path(resources.TEMPLATES_DIR, path.name)
            if path.parent.name == TEMPLATES_SUBDIR
            else resources.resource_path(path.name)
        )
        shutil.copyfile(source, path)
    return planned
