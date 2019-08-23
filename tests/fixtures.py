import os
import contextlib
from pathlib import Path


MINIMAL_PROJ = Path(__file__).parent / "fixtures" / "minimal"


@contextlib.contextmanager
def working_directory(path: Path):
    """Changes working directory and returns to previous on exit."""
    prev_cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev_cwd)
