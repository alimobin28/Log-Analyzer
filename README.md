# Log Analyzer

A command-line tool that parses server log files and produces a clear, actionable terminal report — built to handle messy, real-world logs gracefully.

---

## Features

- Parses standard and non-standard log formats (multiple timestamp styles, alternate response time units, JSON-formatted lines)
- Skips malformed lines without crashing — reports a count of what was dropped and why
- Reports the **10 slowest endpoints** by average and peak response time
- Summarizes **4xx/5xx error distribution** across your log
- Shows **top IPs by traffic volume**
- Renders an **ASCII traffic chart** bucketed by minute or hour
- Outputs a **parse quality summary** so you always know how much data was actually usable

---

## Requirements

- Python 3.9 or higher
- [`rich`](https://github.com/Textualize/rich) for terminal output (installed via `requirements.txt`)

---

## Quickstart (Fresh Machine)

```bash
# 1. Clone the repo
git clone https://github.com/alimobin28/log-analyzer.git
cd log-analyzer

# 2. Install dependencies
pip install -r requirements.txt

# 3. Generate a sample log file
python scripts/generate_logs.py --lines 5000 --output sample.log

# 4. Run the analyzer
python main.py sample.log
```

---

## Usage

```bash
python main.py <path-to-log-file> [options]
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--top N` | `10` | Number of results to show for slow endpoints and top IPs |
| `--bucket [minute\|hour]` | `minute` | Time bucket size for the traffic chart |

### Examples

```bash
# Basic run against any log file
python main.py /var/log/app/access.log

# Show top 20 slowest endpoints, bucketed by hour
python main.py sample.log --top 20 --bucket hour

# Run against a file with a different name — the tool doesn't care
python main.py production-2026-05-22.log --top 5
```

---

## Generating Test Data

The repo includes a log generator that produces files matching the expected shape — including intentional deviations.

```bash
python scripts/generate_logs.py --lines 10000 --output sample.log
```

| Flag | Default | Description |
|------|---------|-------------|
| `--lines N` | `1000` | Number of log lines to generate |
| `--output FILE` | `sample.log` | Output file path |

The generator injects the following deviations at roughly 5–10% of lines:
- Alternate timestamp formats (`2026/05/22 14:23:01`, `15-Mar-2026 14:23:01`, Unix epoch)
- Response times in different units (`0.142s`, bare integer `142`)
- Missing or `-` status codes
- Extra appended fields (quoted user-agent strings, referrers with spaces)
- Fully malformed lines (partial writes, blank lines, fake stack traces)
- JSON-formatted log lines mixed in

After generation it prints a breakdown of how many of each deviation type were injected.

---

## Project Structure

```
log-analyzer/
├── scripts/
│   └── generate_logs.py    # Generates representative test log files
├── src/
│   ├── parser.py           # Parses log lines, handles all format variations
│   ├── analyzer.py         # Aggregation and analysis functions
│   └── reporter.py         # Formats and prints the terminal 

├── main.py                 # CLI entry point
├── requirements.txt
├── README.md
└── ANSWERS.md
```

## License

MIT