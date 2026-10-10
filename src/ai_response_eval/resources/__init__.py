"""Files shipped inside the package so an installed ``ai-eval`` works from any directory.

Contents (each is a byte-identical copy of the repository file noted; a test enforces it):

* ``scoring.json``   <- ``config/scoring.json``      default scoring configuration
* ``rubric_v1.md``   <- ``rubrics/rubric_v1.md``     rubric fingerprinted in reports
* ``examples/``      <- ``data/examples/``          synthetic demonstration dataset
* ``templates/``     <- ``templates/``              JSON templates for manual records
"""

from __future__ import annotations

import atexit
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path

SCORING_CONFIG = "scoring.json"
RUBRIC = "rubric_v1.md"
EXAMPLES_DIR = "examples"
TEMPLATES_DIR = "templates"

_extracted = ExitStack()
atexit.register(_extracted.close)


def resource_path(*parts: str) -> Path:
    """Filesystem path of a packaged resource.

    Regular installs (wheel, editable) keep resources on disk. For the rare zipped
    install, the file is extracted to a temporary location for the life of the process.
    """
    ref = files(__name__).joinpath(*parts)
    if isinstance(ref, Path):
        return ref
    return _extracted.enter_context(as_file(ref))  # pragma: no cover - zipped installs only


def default_config_path() -> Path:
    return resource_path(SCORING_CONFIG)


def default_rubric_path() -> Path:
    return resource_path(RUBRIC)
