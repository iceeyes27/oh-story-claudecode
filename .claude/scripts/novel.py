#!/usr/bin/env python3
"""Compatibility entry point; implementation lives in .novel-kit."""
from pathlib import Path
import sys
_source = Path(__file__).resolve().parents[2] / '.novel-kit' / 'scripts/novel.py'
sys.path.insert(0, str(_source.parent))
__file__ = str(_source)
exec(compile(_source.read_bytes(), str(_source), 'exec'), globals())
