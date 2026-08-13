"""One-command end-to-end demo. Run from the repo root:

    python demo/run_demo.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sdf.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["demo"]))
