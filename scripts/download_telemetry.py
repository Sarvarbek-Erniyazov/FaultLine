"""Stage tier-1 telemetry archives from Zenodo with checksum verification.

Thin wrapper. All logic lives in ``src/faultline``; this file exists so the pipeline
can be driven without the console script on the path.
"""

from __future__ import annotations

import sys

from faultline.cli import app

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "download", "telemetry", *sys.argv[1:]]
    app()
