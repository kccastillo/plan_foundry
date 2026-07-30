# conftest.py - makes `_shared/` importable when running:
#   python -m pytest .claude/skills/_shared/lib/
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # adds _shared/ to path
