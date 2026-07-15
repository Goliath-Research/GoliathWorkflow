#!/usr/bin/env python3
"""Thin wrapper: prefer ``methyl-omega-cluster`` after package install."""

from __future__ import annotations

import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
pkg = repo / "packages" / "methyldeconv"
if str(pkg) not in sys.path:
    sys.path.insert(0, str(pkg))

from methyl_deconv.analysis.omega_cluster_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
