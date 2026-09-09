"""Run script entry points in separate processes, including plain assertions."""
from pathlib import Path
import subprocess
import sys


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    for check in sorted((root / "tests").glob("test_*.py")):
        subprocess.run([sys.executable, "-m", f"tests.{check.stem}"], cwd=root, check=True)
