"""Run this file to generate a streamed PROSAIL Sentinel-2 lookup table.

No command-line arguments are required. Adjust the four settings below only
when you want a different dataset size, satellite, or output file.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path


# ========================= SETTINGS =========================
# Start with 25,000 rows. Increase this when you are ready.
TOTAL_SAMPLES = 600_000
BATCH_SIZE = 10_000
WORKERS = 6  # Conservative setting for this laptop; do not exceed 6 initially.
PLATFORM = "S2A"  # Choose "S2A", "S2B", or "S2C".
OUTPUT_FILE = f"output/prosail_sentinel2_lut_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
ADD_REFLECTANCE_NOISE = True
# ============================================================


SOURCE_DIRECTORY = Path(__file__).resolve().parent
PROJECT_ROOT = SOURCE_DIRECTORY.parents[1]


def main() -> None:
    """Configure and launch the streaming LUT generator."""
    os.chdir(PROJECT_ROOT)
    sys.path.insert(0, str(SOURCE_DIRECTORY))

    from generate_lut import main as generate_lut_main

    arguments = [
        "generate_lut.py",
        "--samples", str(TOTAL_SAMPLES),
        "--batch-size", str(BATCH_SIZE),
        "--workers", str(WORKERS),
        "--platform", PLATFORM,
        "--output", str(PROJECT_ROOT / OUTPUT_FILE),
    ]
    if not ADD_REFLECTANCE_NOISE:
        arguments.append("--no-noise")

    sys.argv = arguments
    generate_lut_main()


if __name__ == "__main__":
    main()
