"""Repository cloning and cleanup via gh CLI."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def clone_repo(repo: str) -> Path:
    """Clone a GitHub repo into a temp directory. Returns the path."""
    tmp = Path(tempfile.mkdtemp(prefix="rewards-scan-"))
    dest = tmp / "repo"
    print(f"Cloning {repo} into {dest} ...", file=sys.stderr)
    result = subprocess.run(
        ["gh", "repo", "clone", repo, str(dest)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Clone failed: {result.stderr.strip()}", file=sys.stderr)
        cleanup(tmp)
        sys.exit(1)
    print("Clone complete.", file=sys.stderr)
    return dest


def cleanup(path: Path):
    """Remove a directory tree, ignoring errors."""
    try:
        shutil.rmtree(path)
    except OSError as e:
        print(f"Warning: cleanup failed for {path}: {e}", file=sys.stderr)
