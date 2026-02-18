#!/usr/bin/env python3
"""Launch the Table Dependency Scanner web UI."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from rewards_scanner.server import main

main()
