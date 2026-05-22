"""
Convert messy server logs into clean and usable data.

Real log files often contain mixed timestamp formats, missing values,
JSON entries, and broken lines. This module safely parses different log
formats and stores invalid lines separately instead of crashing.
"""

import json
import re
from datetime import datetime, timezone
from typing import Optional


_RE_ISO = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z?$")

# 2026/05/22 14:23:01
_RE_SLASH = re.compile(r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})$")

# 22-May-2026 14:23:01
_RE_DMY = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2}:\d{2}$")

_RE_EPOCH = re.compile(r"^\d{10}$")

# response time: 142ms | 0.142s | 142
_RE_RESPONSE = re.compile(r"^(\d+(?:\.\d+)?)(ms|s)?$", re.IGNORECASE)


def _parse_timestamp(raw: str) -> Optional[tuple[datetime, str]]:
    """Try every known format; return (datetime, format_name) or None."""
    raw = raw.strip()

    if _RE_EPOCH.match(raw):
        return datetime.fromtimestamp(int(raw), tz=timezone.utc), "epoch"

    if _RE_ISO.match(raw):
        return datetime.strptime(raw.rstrip("Z"), "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc
        ), "iso"

    if _RE_SLASH.match(raw):
        return datetime.strptime(raw, "%Y/%m/%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        ), "slash"

    if _RE_DMY.match(raw):
        return datetime.strptime(raw, "%d-%b-%Y %H:%M:%S").replace(
            tzinfo=timezone.utc
        ), "dmy"

    return None


def _parse_response_ms(raw: str) -> Optional[float]:
    """Convert '142ms', '0.142s', or '142' to a float number of milliseconds."""
    m = _RE_RESPONSE.match(raw.strip())
    if not m:
        return None
    value = float(m.group(1))
    unit = (m.group(2) or "ms").lower()
    return value * 1000 if unit == "s" else value


def _parse_plain_line(tokens: list[str]) -> Optional[dict]:
    """
    Walk the token list and try to extract a structured log entry.

    The tricky part is that some timestamp formats contain a space
    ("2026/05/22 14:23:01"), so after splitting on whitespace the timestamp
    occupies two slots instead of one. We try width=1 first, then width=2,
    and go with whichever actually parses.
    """
    if len(tokens) < 6:
        return None

    for ts_width in (1, 2):
        ts_raw = " ".join(tokens[:ts_width])
        result = _parse_timestamp(ts_raw)
        if result is None:
            continue
        ts, ts_fmt = result

        rest = tokens[ts_width:]
        if len(rest) < 5:
            return None

        ip, method, path, status_raw, response_raw = rest[:5]
        extra_tokens = rest[5:]

        status: Optional[int] = None
        if status_raw != "-":
            try:
                status = int(status_raw)
            except ValueError:
                return None

        response_ms = _parse_response_ms(response_raw)
        if response_ms is None:
            return None

        extra_fields = _collect_extra_fields(extra_tokens)

        return {
            "timestamp": ts,
            "ts_format": ts_fmt,
            "ip": ip,
            "method": method,
            "path": path,
            "status": status,
            "response_ms": response_ms,
            "extra_fields": extra_fields,
        }

    return None


def _collect_extra_fields(tokens: list[str]) -> list:
    """
    Reassemble quoted strings that whitespace-splitting tore apart.
    '"Mozilla/5.0 (Windows NT)"' becomes one item, not four.
    """
    fields = []
    buf = []
    in_quote = False

    for tok in tokens:
        if not in_quote:
            if tok.startswith('"') and not tok.endswith('"'):
                in_quote = True
                buf = [tok]
            else:
                fields.append(tok)
        else:
            buf.append(tok)
            if tok.endswith('"'):
                fields.append(" ".join(buf))
                buf = []
                in_quote = False

    if buf:  # quote was never closed keep the fragments rather than silently drop them
        fields.extend(buf)

    return fields


def _parse_json_line(raw: str) -> Optional[dict]:
    """
    Pull fields out of a JSON log line and map them to our schema.
    Different loggers use different key names, so we check a few aliases
    for each field. Returns None if we can't find timestamp + method + path.Extract data from a JSON log line and convert it into our standard format.

    Some log files use different field names, so the parser checks multiple
    possible keys for each value. Returns None if important fields like
    timestamp, method, or path are missing.
    """
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(obj, dict):
        return None

    # loggers disagree on the key name — check the common ones
    ts_raw = obj.get("timestamp") or obj.get("time") or obj.get("ts")
    if ts_raw is None:
        return None
    ts_result = _parse_timestamp(str(ts_raw))
    if ts_result is None:
        return None
    ts, ts_fmt = ts_result

    method = obj.get("method")
    path = obj.get("path") or obj.get("url") or obj.get("uri")
    if not method or not path:
        return None

    status_raw = obj.get("status") or obj.get("status_code")
    status: Optional[int] = None
    if status_raw is not None and str(status_raw) != "-":
        try:
            status = int(status_raw)
        except (ValueError, TypeError):
            pass

    # some loggers write a plain number in ms, others write "142ms" as a string
    rt = obj.get("response_time_ms") or obj.get("duration_ms") or obj.get("latency_ms")
    response_ms: Optional[float] = None
    if rt is not None:
        try:
            response_ms = float(rt)
        except (ValueError, TypeError):
            pass
    if response_ms is None:
        # fall back to the string form if the numeric key wasn't present
        rt_str = obj.get("response_time") or obj.get("duration")
        if rt_str:
            response_ms = _parse_response_ms(str(rt_str))

    if response_ms is None:
        response_ms = 0.0

    ip = obj.get("ip") or obj.get("remote_addr") or obj.get("client_ip") or ""

    # preserve any fields we didn't explicitly map — the analyzer might want them
    core = {"timestamp", "time", "ts", "method", "path", "url", "uri",
            "status", "status_code", "response_time_ms", "duration_ms",
            "latency_ms", "response_time", "duration", "ip",
            "remote_addr", "client_ip"}
    leftover = {k: v for k, v in obj.items() if k not in core}
    extra_fields = [f"{k}={v}" for k, v in leftover.items()] if leftover else []

    return {
        "timestamp": ts,
        "ts_format": ts_fmt,
        "ip": ip,
        "method": method,
        "path": path,
        "status": status,
        "response_ms": response_ms,
        "extra_fields": extra_fields,
    }


def parse_file(path: str) -> tuple[list[dict], list[str]]:
    """
    Read a log file and return parsed log entries and skipped lines.

    The parser tries to handle every line safely. Invalid or broken lines like
    blank entries, partial logs, or stack traces are added to skipped_lines
    instead of crashing the program.
    """
    parsed: list[dict] = []
    skipped: list[str] = []

    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError as exc:
        # can't open the file at all surface the reason rather than a bare crash
        skipped.append(f"[OPEN ERROR] {exc}")
        return parsed, skipped

    with fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n")

            # no point trying to parse whitespace
            if not line.strip():
                skipped.append(line)
                continue

            try:
                entry = _try_parse_line(line)
            except Exception:
                # shouldn't happen, but one bad line shouldn't take down the whole file
                entry = None

            if entry is not None:
                parsed.append(entry)
            else:
                skipped.append(line)

    return parsed, skipped


def _try_parse_line(line: str) -> Optional[dict]:
    """JSON lines start with '{', so we can avoid the regex overhead for most lines."""
    stripped = line.strip()

    if stripped.startswith("{"):
        result = _parse_json_line(stripped)
        if result is not None:
            return result

    tokens = stripped.split()
    return _parse_plain_line(tokens)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: python src/parser.py <log-file>")
        sys.exit(1)

    entries, skipped = parse_file(sys.argv[1])
    total = len(entries) + len(skipped)

    print(f"file      : {sys.argv[1]}")
    print(f"total     : {total}")
    print(f"parsed    : {len(entries)}  ({len(entries)/total*100:.1f}%)" if total else "parsed    : 0")
    print(f"skipped   : {len(skipped)}  ({len(skipped)/total*100:.1f}%)" if total else "skipped   : 0")

    if skipped:
        print("\nfirst 5 skipped lines:")
        for line in skipped[:5]:
            print(f"  {line!r}")
