"""Run the CPU streaming trace on one held-out turbine-year.

Thin wrapper. All logic lives in ``src/faultline``; this file exists so the trace can be
driven without the console script on the path.
"""

from __future__ import annotations

import sys

from faultline.cli import app

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "model", "stream-trace", *sys.argv[1:]]
    app()
