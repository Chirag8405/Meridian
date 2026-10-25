import sys
from pathlib import Path

# Render's root directory is backend/, so tests import modules the same way.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
