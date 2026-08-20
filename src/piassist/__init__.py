"""Piassist: annotate accidentals in vector music-score PDFs."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("piassist")
except PackageNotFoundError:  # pragma: no cover - source tree without install
    __version__ = "0.0.0"

__all__ = ["__version__"]
