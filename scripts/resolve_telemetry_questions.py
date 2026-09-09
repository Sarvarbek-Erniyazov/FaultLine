"""Measure the power scale and the DST fingerprint of a staged record.

Thin wrapper. All logic lives in ``src/faultline``; this file exists so the pipeline
can be driven without the console script on the path.
"""

from __future__ import annotations

import sys

from faultline.cli import app

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "inspect", "resolve", *sys.argv[1:]]
    app()
