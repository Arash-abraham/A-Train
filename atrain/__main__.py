"""Entry point for ``python -m atrain``."""

from __future__ import annotations

import sys

from atrain.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
