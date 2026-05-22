"""
CLI entry point for Log Analyzer.
It only handles user input, file existence checks, and then
hands everything to parser + reporter modules.
"""

import argparse
import os
import sys

from src.analyzer import (
    error_summary,
    parse_quality_report,
    requests_over_time,
    top_slow_endpoints,
    traffic_by_ip,
)
from src.parser import parse_file
from src.reporter import print_report


def _build_parser() -> argparse.ArgumentParser:
    """
    Define CLI arguments in one place so main() stays clean.
    """

    parser = argparse.ArgumentParser(
        description="Run log analyzer on a server log file",
        epilog="Example: python main.py sample.log --top 10 --bucket minute",
    )

    parser.add_argument(
        "log_file",
        help="Path to the log file",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Show top N slow endpoints and IPs (must be 1 or more)",
    )

    parser.add_argument(
        "--bucket",
        choices=["minute", "hour"],
        default="minute",
        help="Time grouping for traffic chart",
    )

    return parser


def main() -> None:
    args = _build_parser().parse_args()

    if not os.path.isfile(args.log_file):
        msg = "Not a file" if os.path.exists(args.log_file) else "File not found"
        print(f"{msg}: {args.log_file}", file=sys.stderr)
        print("Please check the path and try again.", file=sys.stderr)
        sys.exit(1)

    if args.top < 1:
        print("--top must be 1 or greater.", file=sys.stderr)
        sys.exit(1)

    entries, skipped = parse_file(args.log_file)

    quality = parse_quality_report(entries, skipped)
    errors  = error_summary(entries)
    missing = errors.pop("missing", 0)

    stats = {
        "total_lines":    quality["total_lines"],
        "parsed":         quality["parsed"],
        "skipped":        quality["skipped"],
        "slow_endpoints": top_slow_endpoints(entries, n=args.top),
        "error_codes":    errors,
        "missing_status": missing,
        "top_ips":        traffic_by_ip(entries, n=args.top),
        "timeline":       dict(requests_over_time(entries, bucket=args.bucket)),
    }

    print_report(stats)


if __name__ == "__main__":
    main()