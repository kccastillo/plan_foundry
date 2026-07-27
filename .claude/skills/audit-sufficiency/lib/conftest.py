# conftest.py — makes `lib/` importable as the working directory for pytest
# when running:  python -m pytest .claude/skills/audit-sufficiency/lib/
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
