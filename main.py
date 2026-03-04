#!/usr/bin/env python3

# main.py - Entry point for report-editor.

# 

# Usage:

# python main.py <report_file> <search_root>

# 

# Arguments:

# report_file   Path to the freeform report file

# search_root   Root directory to search for files listed in the report

# 

# Options:

# -h, –help         Show this help message

# –dry-run          Preview changes without applying (skip TUI, print summary)

# –no-backup        Disable automatic .bak file creation before edits

# –log-file PATH    Write session log to PATH (default: next to report file)

# –no-log           Disable log file writing entirely

# 

# Example:

# python main.py changes.txt /var/www/myapp

# python main.py changes.txt /var/www/myapp –log-file /var/log/report_editor.log

import argparse
import sys
from datetime import datetime
from pathlib import Path

from report import parse_report
from finder import find_files
from tui import run_tui, Session
from logger import write_log

# Print a plain-text preview of what would happen - no files are touched

def dry_run_summary(file_changes, file_map):
from matcher import find_block, find_insert_line

```
print("\n=== DRY RUN SUMMARY ===\n")
for fc in file_changes:
    fp = file_map.get(fc.filepath)
    status = f"FOUND -> {fp}" if fp else "NOT FOUND"
    print(f"  {fc.filepath}")
    print(f"    {status}")
    for ch in fc.changes:
        verb = "INSERT" if ch.action == "insert" else "REMOVE"
        if fp:
            file_lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
            if ch.action == "remove":
                mr = find_block(file_lines, ch.lines, ch.line_start, ch.line_end)
                loc = (f"lines {mr.line_start}-{mr.line_end} ({int(mr.confidence*100)}% confidence, {mr.method})"
                       if mr.found else "NOT LOCATED")
            else:
                il = find_insert_line(file_lines, ch.line_start)
                loc = f"before line {il}"
        else:
            loc = "N/A (file not found)"
        print(f"    [{verb}] report hint lines {ch.line_start}-{ch.line_end} -> {loc}")
        for ln in ch.lines[:3]:
            print(f"        | {ln}")
        if len(ch.lines) > 3:
            print(f"        | ... ({len(ch.lines) - 3} more lines)")
    print()
```

def main():
parser = argparse.ArgumentParser(
description=“Interactive TUI for applying report-driven file changes.”,
)
parser.add_argument(“report_file”, help=“Path to the report file”)
parser.add_argument(“search_root”, help=“Root directory to search for files”)
parser.add_argument(”–dry-run”, action=“store_true”,
help=“Print what would be done without running TUI”)
parser.add_argument(”–no-backup”, action=“store_true”,
help=“Disable .bak file creation before edits”)
parser.add_argument(”–log-file”, metavar=“PATH”,
help=“Write session log to this path (default: next to report file)”)
parser.add_argument(”–no-log”, action=“store_true”,
help=“Disable log file writing entirely”)

```
args = parser.parse_args()

report_path = Path(args.report_file)
if not report_path.exists():
    print(f"ERROR: Report file not found: {report_path}", file=sys.stderr)
    sys.exit(1)

search_root = Path(args.search_root)
if not search_root.is_dir():
    print(f"ERROR: Search root is not a directory: {search_root}", file=sys.stderr)
    sys.exit(1)

started_at = datetime.now()

print(f"Parsing report: {report_path}")
file_changes = parse_report(report_path)

if not file_changes:
    print("No file changes found in report.")
    sys.exit(0)

print(f"Found {len(file_changes)} file(s) with changes. Searching under {search_root}...")
file_map = find_files(file_changes, search_root)

found   = sum(1 for v in file_map.values() if v)
missing = len(file_map) - found
print(f"Located {found}/{len(file_map)} file(s). {missing} not found.")

total_changes = sum(len(fc.changes) for fc in file_changes)

if args.dry_run:
    dry_run_summary(file_changes, file_map)
    return

# Disable backups if requested
if args.no_backup:
    import editor as _ed
    _orig_insert = _ed.apply_insert
    _orig_remove = _ed.apply_remove
    _ed.apply_insert = lambda fp, at, lines, backup=False: _orig_insert(fp, at, lines, backup=False)
    _ed.apply_remove = lambda fp, s, e, backup=False: _orig_remove(fp, s, e, backup=False)

session = Session(
    file_changes=file_changes,
    file_map=file_map,
    search_root=str(search_root),
    results=[],
)

run_tui(session)

ended_at = datetime.now()
applied  = sum(1 for r in session.results if r["action"] == "applied")
skipped  = sum(1 for r in session.results if r["action"] == "skipped")
errors   = sum(1 for r in session.results if r["action"] == "error")

print(f"\nDone. Applied: {applied}  Skipped: {skipped}  Errors: {errors}")

# Write session log
if not args.no_log:
    log_path = Path(args.log_file) if args.log_file else None
    meta = {
        "report_file":   str(report_path.resolve()),
        "search_root":   str(search_root.resolve()),
        "started_at":    started_at,
        "ended_at":      ended_at,
        "total_changes": total_changes,
        "files_found":   found,
        "files_missing": missing,
    }
    written = write_log(meta, session.results, log_path)
    print(f"Log written: {written}")
```

if **name** == “**main**”:
main()