"""Local deployment launcher; no installation of full LoreKit is required."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from xiuxian.http_app import main

if __name__ == "__main__":
    main()
