#!/usr/bin/env python3
"""Backward-compatible shim; use `python -m methyl_worker` or `methyl-worker` instead."""

from methyl_worker.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
