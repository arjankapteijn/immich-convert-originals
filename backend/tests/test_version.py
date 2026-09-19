"""Guards against version drift between the package and pyproject.toml."""

import tomllib
from pathlib import Path

from app import __version__

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_version_matches_pyproject():
    with (_REPO_ROOT / "pyproject.toml").open("rb") as fh:
        pyproject = tomllib.load(fh)
    assert __version__ == pyproject["project"]["version"]
