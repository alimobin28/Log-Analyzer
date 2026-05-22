"""
Generate realistic server logs with occasional malformed and
mixed-format entries for testing the log analyzer parser.
"""

import argparse
import json
import random
import sys
from datetime import datetime, timezone, timedelta

# things we randomly pick from when building each log line

METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]
PATHS = [
    "/api/users", "/api/users/1", "/api/users/42", "/api/products",
    "/api/products/7", "/api/orders", "/api/orders/99", "/api/auth/login",
    "/api/auth/logout", "/api/search", "/health", "/metrics",
    "/api/reports/monthly", "/api/settings", "/api/notifications",
]


# weighted so the distribution roughly matches what a real API looks like —
# mostly 200s, a handful of client errors, the odd 5xx


STATUS_CODES = (
    [200] * 60 + [201] * 10 + [204] * 5 +
    [301] * 2 + [304] * 3 +
    [400] * 5 + [401] * 3 + [403] * 2 + [404] * 6 + [422] * 2 +
    [500] * 1 + [502] * 1
)
USER_AGENTS = [
    '"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"',
    '"curl/7.68.0"',
    '"python-requests/2.28.1"',
    '"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/537.36"',
    '"PostmanRuntime/7.29.0"',
    '"Go-http-client/1.1"',
]
REFERRERS = [
    '"https://example.com/dashboard"',
    '"https://app.internal/reports"',
    '"-"',
    '"https://google.com/search?q=api+docs"',
]
STACK_TRACE_LINES = [
    "ERROR: NullPointerException at line 42",
    "FATAL: SegmentationFault in module core.request (line 117)",
    "WARN:  TimeoutException: read timed out after 30000ms",
    "ERROR: Connection refused to db-primary:5432",
    "Traceback (most recent call last): File 'app.py', line 88, in handle",
    "java.lang.RuntimeException: Unexpected EOF at parser.Parser.parse(Parser.java:201)",
]
PARTIAL_WRITES = [
    "2026-05-22T14:2",
    "192.168.1.",
    "GET /api/use",
    "2026-05-22T14:23:01Z 10.0.0.5",
    "",  # the blank line is intentional mimics a logger that flushed mid-write
]


EPOCH_BASE = datetime(2026, 5, 22, 0, 0, 0, tzinfo=timezone.utc)


def random_ip() -> str:
    return f"192.168.{random.randint(0, 5)}.{random.randint(1, 254)}"


def random_ts(offset_minutes: int) -> datetime:
    return EPOCH_BASE + timedelta(minutes=offset_minutes, seconds=random.randint(0, 59))


def fmt_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt_slash(dt: datetime) -> str:
    return dt.strftime("%Y/%m/%d %H:%M:%S")


def fmt_dmy(dt: datetime) -> str:
    return dt.strftime("%d-%b-%Y %H:%M:%S")


def fmt_epoch(dt: datetime) -> str:
    return str(int(dt.timestamp()))


def random_response_ms() -> int:
    # 90% of requests are fast; the other 10% simulate slow queries or upstream timeouts
    if random.random() < 0.9:
        return random.randint(5, 800)
    return random.randint(800, 8000)


def fmt_ms_normal(ms: int) -> str:
    return f"{ms}ms"


def fmt_ms_seconds(ms: int) -> str:
    return f"{ms / 1000:.3f}s"


def fmt_ms_bare(ms: int) -> str:
    return str(ms)


# each builder takes the same arguments and returns one formatted log line

def build_normal(dt: datetime, ip: str, method: str, path: str,
                 status: int, ms: int) -> str:
    return f"{fmt_iso(dt)} {ip} {method} {path} {status} {fmt_ms_normal(ms)}"


def build_alt_timestamp(dt: datetime, ip: str, method: str, path: str,
                         status: int, ms: int) -> str:
    fmt = random.choice([fmt_slash, fmt_dmy, fmt_epoch])
    return f"{fmt(dt)} {ip} {method} {path} {status} {fmt_ms_normal(ms)}"


def build_alt_response_unit(dt: datetime, ip: str, method: str, path: str,
                             status: int, ms: int) -> str:
    fmt = random.choice([fmt_ms_seconds, fmt_ms_bare])
    return f"{fmt_iso(dt)} {ip} {method} {path} {status} {fmt(ms)}"


def build_missing_status(dt: datetime, ip: str, method: str, path: str,
                          _status: int, ms: int) -> str:
    return f"{fmt_iso(dt)} {ip} {method} {path} - {fmt_ms_normal(ms)}"


def build_extra_fields(dt: datetime, ip: str, method: str, path: str,
                        status: int, ms: int) -> str:
    extra = random.choice(USER_AGENTS + REFERRERS)
    return f"{fmt_iso(dt)} {ip} {method} {path} {status} {fmt_ms_normal(ms)} {extra}"


def build_json_line(dt: datetime, ip: str, method: str, path: str,
                    status: int, ms: int) -> str:
    record = {
        "timestamp": fmt_iso(dt),
        "ip": ip,
        "method": method,
        "path": path,
        "status": status,
        "response_time_ms": ms,
    }
    return json.dumps(record, separators=(",", ":"))


def build_malformed(_dt, _ip, _method, _path, _status, _ms) -> str:
    return random.choice(STACK_TRACE_LINES + PARTIAL_WRITES)


# maps a short name (used in the summary) to the builder that produces it
DEVIATIONS = [
    ("alt_timestamp",     build_alt_timestamp),
    ("alt_response_unit", build_alt_response_unit),
    ("missing_status",    build_missing_status),
    ("extra_fields",      build_extra_fields),
    ("json_line",         build_json_line),
    ("malformed",         build_malformed),
]

# kept around in case you want to tune individual deviation weights later
DEVIATION_PROB = 1 / len(DEVIATIONS)



def generate(n_lines: int, output_path: str) -> None:
    counts: dict[str, int] = {name: 0 for name, _ in DEVIATIONS}
    counts["normal"] = 0

    with open(output_path, "w", encoding="utf-8") as fh:
        for i in range(n_lines):
            dt = random_ts(i)  # one minute per line so the log reads as a real time-series
            ip = random_ip()
            method = random.choice(METHODS)
            path = random.choice(PATHS)
            status = random.choice(STATUS_CODES)
            ms = random_response_ms()

            # roll the dice — roughly 1 in 14 lines gets a deviation
            if random.random() < 0.07:
                name, builder = random.choice(DEVIATIONS)
                line = builder(dt, ip, method, path, status, ms)
                counts[name] += 1
            else:
                line = build_normal(dt, ip, method, path, status, ms)
                counts["normal"] += 1

            fh.write(line + "\n")

    total = sum(counts.values())
    print(f"Generated {total} lines -> {output_path}\n")
    print(f"  {'normal':<22} {counts['normal']:>6}  ({counts['normal']/total*100:.1f}%)")
    print()
    for name, _ in DEVIATIONS:
        n = counts[name]
        print(f"  {'deviation: ' + name:<22} {n:>6}  ({n/total*100:.1f}%)")
    total_devs = total - counts["normal"]
    print(f"\n  {'TOTAL deviations':<22} {total_devs:>6}  ({total_devs/total*100:.1f}%)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a realistic server log file with injected deviations."
    )
    parser.add_argument("--lines", type=int, default=1000,
                        help="Number of log lines to generate (default: 1000)")
    parser.add_argument("--output", default="sample.log",
                        help="Output file path (default: sample.log)")
    args = parser.parse_args()

    if args.lines < 1:
        print("--lines must be at least 1", file=sys.stderr)
        sys.exit(1)

    generate(args.lines, args.output)


if __name__ == "__main__":
    main()
