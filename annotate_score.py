"""Compatibility entry point for running Piassist from the repository root."""

import sys

from piassist.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["annotate", *sys.argv[1:]]))
