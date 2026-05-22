"""
Analyze parsed log data and generate useful summaries.

This module helps find slow endpoints, common errors,
busy IP addresses, traffic patterns, and parse quality.
Everything is designed to fail safely on messy input.
"""

from collections import defaultdict
from datetime import datetime

try:
    from src.parser import parse_file
except ImportError:
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
    from src.parser import parse_file


def _bucket_key(ts: datetime, bucket: str) -> str:
    """Round a timestamp down to the chosen granularity for grouping."""
    if bucket == "hour":
        return ts.strftime("%Y-%m-%d %H:00")
    return ts.strftime("%Y-%m-%d %H:%M")


def top_slow_endpoints(
    entries: list[dict],
    n: int = 10,
) -> list[tuple[str, float, float, int]]:
    """
    Find endpoints with the slowest average response times.
    """

    if not entries:
        return []

    # Store all response times grouped by endpoint path
    totals: dict[str, list[float]] = defaultdict(list)

    for entry in entries:

        path = entry["path"]
        response_ms = entry["response_ms"]

        totals[path].append(response_ms)

    results = []

    for path, times in totals.items():

        avg_ms = sum(times) / len(times)

        results.append(
            (
                path,
                avg_ms,
                max(times),
                len(times),
            )
        )

    # Highest average response time first
    results.sort(key=lambda x: x[1], reverse=True)

    return results[:n]


def error_summary(entries: list[dict]) -> dict[str, int]:
    """
    Count client and server errors in the logs.
    """

    counts: dict[str, int] = defaultdict(int)

    for entry in entries:

        status = entry["status"]

        if status is None:

            counts["missing"] += 1

        elif 400 <= status <= 599:

            counts[str(status)] += 1

    return dict(counts)


def traffic_by_ip(
    entries: list[dict],
    n: int = 10,
) -> list[tuple[str, int]]:
    """
    Find which IP addresses made the most requests.
    """

    if not entries:
        return []

    counts: dict[str, int] = defaultdict(int)

    for entry in entries:

        ip = entry.get("ip") or "unknown"

        counts[ip] += 1

    ranked = sorted(
        counts.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    return ranked[:n]


def requests_over_time(
    entries: list[dict],
    bucket: str = "minute",
) -> list[tuple[str, int]]:
    """
    Group requests by minute or hour.
    """

    if not entries:
        return []

    # Fallback safely if wrong bucket value is passed
    if bucket not in ("minute", "hour"):
        bucket = "minute"

    counts: dict[str, int] = defaultdict(int)

    for entry in entries:

        timestamp = entry.get("timestamp")

        # Ignore broken timestamps safely
        if not isinstance(timestamp, datetime):
            continue

        key = _bucket_key(timestamp, bucket)

        counts[key] += 1

    # Time strings already sort correctly
    return sorted(counts.items())


def parse_quality_report(
    entries: list[dict],
    skipped_lines: list[str],
) -> dict:
    """
    Show how much of the log file was parsed successfully.
    """

    total_lines = len(entries) + len(skipped_lines)

    # Return safe defaults for empty files
    if total_lines == 0:

        return {
            "total_lines": 0,
            "parsed": 0,
            "skipped": 0,
            "skipped_pct": 0.0,
            "json_lines": 0,
            "alt_timestamp_formats": 0,
        }

    # JSON log entries usually leave extra key=value fields
    def looks_like_json(entry: dict) -> bool:

        extra_fields = entry.get("extra_fields", [])

        return any("=" in str(field) for field in extra_fields)

    json_count = sum(
        1
        for entry in entries
        if looks_like_json(entry)
    )

    skipped_pct = round(
        len(skipped_lines) / total_lines * 100,
        1,
    )

    return {
        "total_lines": total_lines,
        "parsed": len(entries),
        "skipped": len(skipped_lines),
        "skipped_pct": skipped_pct,
        "json_lines": json_count,

        # Original timestamp format is lost after parsing
        "alt_timestamp_formats": 0,
    }


# Quick local testing without running the full CLI
if __name__ == "__main__":

    import os
    import sys

    log_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "sample.log"
    )

    if not os.path.exists(log_path):

        print(f"Could not find file: {log_path}")
        print("Generate a sample log first using generate_logs.py")

        sys.exit(1)

    entries, skipped = parse_file(log_path)

    print(f"\nLoaded {len(entries)} log entries from {log_path}")

    print("\nTop slow endpoints:\n")

    for path, avg, peak, count in top_slow_endpoints(entries, n=5):

        print(
            f"{path:<30} "
            f"avg={avg:.1f}ms   "
            f"max={peak:.1f}ms   "
            f"requests={count}"
        )

    print("\nError summary:\n")

    errors = error_summary(entries)

    if errors:

        for code, count in sorted(errors.items()):

            print(f"{code:<10} {count}")

    else:
        print("No server/client errors found")

    print("\nMost active IP addresses:\n")

    for ip, count in traffic_by_ip(entries, n=5):

        print(f"{ip:<18} {count} requests")

    print("\nRequests over time:\n")

    buckets = requests_over_time(entries)

    for timestamp, count in buckets[:10]:

        print(f"{timestamp} -> {count} requests")

    if len(buckets) > 10:

        print(f"... plus {len(buckets) - 10} more time buckets")

    print("\nParse quality report:\n")

    report = parse_quality_report(entries, skipped)

    for key, value in report.items():

        print(f"{key:<24} {value}")