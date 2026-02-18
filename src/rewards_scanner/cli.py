"""CLI entry point for table dependency scanner."""

import argparse
import sys

from .models import Confidence
from .runner import run


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="table-scan",
        description="Scan a Rails codebase for references to a database table.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--repo", help="GitHub repo to clone (e.g. org/repo)")
    source.add_argument("--local-path", help="Path to already-cloned repo")

    parser.add_argument("--output", help="Output CSV file (default: stdout)")
    parser.add_argument(
        "--keep-clone", action="store_true", help="Don't delete temp clone"
    )
    parser.add_argument(
        "--min-confidence",
        choices=["HIGH", "MEDIUM", "LOW"],
        default="LOW",
        help="Minimum confidence level to include (default: LOW)",
    )
    parser.add_argument(
        "--table-name", default="rewards", help="Table name to scan for (default: rewards)"
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    min_confidence = Confidence[args.min_confidence]
    try:
        run(
            repo=args.repo,
            local_path=args.local_path,
            output=args.output,
            keep_clone=args.keep_clone,
            min_confidence=min_confidence,
            table_name=args.table_name,
        )
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
