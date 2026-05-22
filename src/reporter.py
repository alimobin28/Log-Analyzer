"""
Format and print the log analysis results in the terminal.

Each section is independent, so missing data (no errors, no IPs, etc.)
shows a short note rather than an empty table or a crash.
"""

try:
    from src.analyzer import (
        top_slow_endpoints,
        error_summary,
        traffic_by_ip,
        requests_over_time,
        parse_quality_report,
    )

except ImportError:

    import os
    import sys

    sys.path.insert(
        0,
        os.path.join(os.path.dirname(__file__), "..")
    )

    from src.analyzer import (
        top_slow_endpoints,
        error_summary,
        traffic_by_ip,
        requests_over_time,
        parse_quality_report,
    )


LINE_WIDTH = 70
BAR_CHAR = "#"
BAR_WIDTH = 40


def _header(title: str) -> None:

    print(f"\n{'=' * LINE_WIDTH}")
    print(title)
    print(f"{'=' * LINE_WIDTH}")


# Turns a request count into a proportional bar of # characters
def _make_bar(count: int, max_count: int) -> str:

    if max_count == 0:
        return ""

    filled = round(count / max_count * BAR_WIDTH)

    return BAR_CHAR * filled


def print_report(
    entries: list,
    skipped: list,
    top: int = 10,
    bucket: str = "minute",
) -> None:
    """
    Print the full log analysis report.
    """

    # Parse quality 

    _header("Parse Quality")

    quality = parse_quality_report(entries, skipped)

    parsed_pct = round(
        100 - quality["skipped_pct"],
        1,
    )

    print(f"Total lines : {quality['total_lines']}")
    print(f"Parsed      : {quality['parsed']} ({parsed_pct}%)")
    print(f"Skipped     : {quality['skipped']} ({quality['skipped_pct']}%)")

    #Slow endpoints 

    _header(f"Top {top} Slow Endpoints")

    slow = top_slow_endpoints(entries, n=top)

    if slow:

        path_width = min(
            max(len(path) for path, _, _, _ in slow),
            40,
        )

        print(
            f"{'Path':<{path_width}}  "
            f"{'Avg ms':>8}  "
            f"{'Max ms':>8}  "
            f"{'Requests':>8}"
        )

        print(
            f"{'-' * path_width}  "
            f"{'-' * 8}  "
            f"{'-' * 8}  "
            f"{'-' * 8}"
        )

        for path, avg, peak, count in slow:

            display_path = path

            if len(display_path) > path_width:
                display_path = display_path[:path_width - 2] + ".."

            print(
                f"{display_path:<{path_width}}  "
                f"{avg:>8.1f}  "
                f"{peak:>8.1f}  "
                f"{count:>8}"
            )

    else:
        print("No endpoint timing data found")

    # Error summary

    _header("Error Summary")

    errors = error_summary(entries)

    if errors:

        missing = errors.pop("missing", 0)

        if errors:

            print(f"{'Status':>8}  {'Count':>8}")
            print(f"{'-' * 8}  {'-' * 8}")

            for code, count in sorted(errors.items()):

                print(f"{code:>8}  {count:>8}")

        if missing:

            print(f"\nMissing status codes : {missing}")

    else:
        print("No 4xx or 5xx errors found")

    # ---------------- Top IPs ----------------

    _header(f"Top {top} IP Addresses")

    ips = traffic_by_ip(entries, n=top)

    if ips:

        ip_width = max(len(ip) for ip, _ in ips)

        print(f"{'IP Address':<{ip_width}}  {'Requests':>8}")
        print(f"{'-' * ip_width}  {'-' * 8}")

        for ip, count in ips:

            print(f"{ip:<{ip_width}}  {count:>8}")

    else:
        print("No IP traffic data found")

    # ---------------- Traffic over time ----------------

    _header(f"Traffic Over Time ({bucket})")

    timeline = requests_over_time(entries, bucket=bucket)

    # Only show latest 20 buckets to keep output readable
    buckets = (
        timeline[-20:]
        if len(timeline) > 20
        else timeline
    )

    if buckets:

        max_count = max(count for _, count in buckets)

        label_width = max(len(ts) for ts, _ in buckets)

        for timestamp, count in buckets:

            bar = _make_bar(count, max_count)

            print(
                f"{timestamp:<{label_width}} "
                f"|{bar:<{BAR_WIDTH}} "
                f"{count}"
            )

    else:
        print("No traffic timeline data found")

    print(f"\n{'=' * LINE_WIDTH}\n")