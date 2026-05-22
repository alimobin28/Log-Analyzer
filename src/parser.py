import json
import re
from datetime import datetime, timezone
from typing import Optional, Tuple, List, Dict, Any


_RE_ISO = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z?$")
_RE_SLASH = re.compile(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}$")
_RE_DMY = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2}:\d{2}$")
_RE_EPOCH = re.compile(r"^\d{10}(\d{3})?$")
_RE_RESPONSE = re.compile(r"^(\d+(?:\.\d+)?)(ms|s)?$", re.IGNORECASE)


def _parse_timestamp(raw: str) -> Optional[Tuple[datetime, str]]:
    raw = raw.strip()

    try:
        if _RE_EPOCH.match(raw):
            ts = int(raw)
            if len(raw) == 13:
                ts //= 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc), "epoch"

        if _RE_ISO.match(raw):
            dt = datetime.strptime(raw.rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
            return dt.replace(tzinfo=timezone.utc), "iso"

        if _RE_SLASH.match(raw):
            dt = datetime.strptime(raw, "%Y/%m/%d %H:%M:%S")
            return dt.replace(tzinfo=timezone.utc), "slash"

        if _RE_DMY.match(raw):
            dt = datetime.strptime(raw, "%d-%b-%Y %H:%M:%S")
            return dt.replace(tzinfo=timezone.utc), "dmy"

    except Exception:
        return None

    return None


def _parse_response_ms(raw: str) -> Optional[float]:
    m = _RE_RESPONSE.match(raw.strip())
    if not m:
        return None

    value = float(m.group(1))
    unit = (m.group(2) or "ms").lower()

    return value * 1000 if unit == "s" else value


def _collect_extra_fields(tokens: List[str]) -> List[str]:
    fields = []
    buffer = []
    in_quote = False

    for tok in tokens:
        if not in_quote:
            if tok.startswith('"') and not tok.endswith('"'):
                in_quote = True
                buffer = [tok]
            else:
                fields.append(tok)
        else:
            buffer.append(tok)
            if tok.endswith('"'):
                fields.append(" ".join(buffer))
                buffer = []
                in_quote = False

    if buffer:
        fields.extend(buffer)

    return fields


def _parse_plain_line(tokens: List[str]) -> Optional[Dict[str, Any]]:
    if len(tokens) < 6:
        return None

    for ts_width in (1, 2):
        ts_raw = " ".join(tokens[:ts_width])
        ts_result = _parse_timestamp(ts_raw)

        if not ts_result:
            continue

        ts, ts_fmt = ts_result
        rest = tokens[ts_width:]

        if len(rest) < 5:
            return None

        ip, method, path, status_raw, response_raw = rest[:5]
        extra_tokens = rest[5:]

        # status
        status: Optional[int] = None
        if status_raw != "-":
            try:
                status = int(status_raw)
            except ValueError:
                return None

        # response time
        response_ms = _parse_response_ms(response_raw)
        if response_ms is None:
            return None

        return {
            "timestamp": ts,
            "ts_format": ts_fmt,
            "source": "plain",
            "ip": ip,
            "method": method,
            "path": path,
            "status": status,
            "response_ms": response_ms,
            "extra_fields": _collect_extra_fields(extra_tokens),
        }

    return None


def _parse_json_line(raw: str) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            return None
    except Exception:
        return None

    # timestamp
    ts_raw = obj.get("timestamp") or obj.get("time") or obj.get("ts")
    if not ts_raw:
        return None

    ts_result = _parse_timestamp(str(ts_raw))
    if not ts_result:
        return None

    ts, ts_fmt = ts_result

    # method/path
    method = obj.get("method")
    path = obj.get("path") or obj.get("url") or obj.get("uri")

    if not method or not path:
        return None

    # status
    status: Optional[int] = None
    status_raw = obj.get("status") or obj.get("status_code")
    if status_raw not in (None, "-"):
        try:
            status = int(status_raw)
        except Exception:
            status = None

    # response time (SAFE FIXED VERSION)
    response_ms: Optional[float] = None

    for k in ("response_time_ms", "duration_ms", "latency_ms"):
        if k in obj:
            try:
                response_ms = float(obj[k])
                break
            except Exception:
                pass

    if response_ms is None:
        for k in ("response_time", "duration"):
            if k in obj:
                response_ms = _parse_response_ms(str(obj[k]))
                if response_ms is not None:
                    break

    if response_ms is None:
        response_ms = 0.0  # safe default for analytics

    ip = obj.get("ip") or obj.get("remote_addr") or obj.get("client_ip") or ""

    core_keys = {
        "timestamp", "time", "ts",
        "method", "path", "url", "uri",
        "status", "status_code",
        "response_time_ms", "duration_ms", "latency_ms",
        "response_time", "duration",
        "ip", "remote_addr", "client_ip"
    }

    extra_fields = [
        f"{k}={v}" for k, v in obj.items() if k not in core_keys
    ]

    return {
        "timestamp": ts,
        "ts_format": ts_fmt,
        "source": "json",
        "ip": ip,
        "method": method,
        "path": path,
        "status": status,
        "response_ms": response_ms,
        "extra_fields": extra_fields,
    }


def _try_parse_line(line: str) -> Optional[Dict[str, Any]]:
    stripped = line.strip()

    if not stripped:
        return None

    if stripped.startswith("{"):
        return _parse_json_line(stripped)

    return _parse_plain_line(stripped.split())


def parse_file(path: str) -> tuple[list[dict], list[str]]:
    parsed: list[dict] = []
    skipped: list[str] = []

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")

                try:
                    entry = _try_parse_line(line)
                except Exception:
                    entry = None

                if entry:
                    parsed.append(entry)
                else:
                    skipped.append(line)

    except OSError as e:
        skipped.append(f"[OPEN ERROR] {e}")

    return parsed, skipped