# logger.py - Write a structured session log after a report-editor run.

# 

# Log is plain text, human-readable.

# Written next to the report file by default:

# report_editor_YYYYMMDD_HHMMSS.log

from datetime import datetime
from pathlib import Path

# Write session log. Returns the path it was written to.

# 

# session_meta keys:

# report_file   str

# search_root   str

# started_at    datetime

# ended_at      datetime

# total_changes int

# files_found   int

# files_missing int

# 

# Each result dict has:

# action        ‘applied’ | ‘skipped’ | ‘error’

# file          str   (report path)

# resolved_path str   (actual path on disk, or ‘NOT FOUND’)

# change        str   (human summary)

# operation     ‘insert’ | ‘remove’

# hint_start    int

# hint_end      int

# actual_start  int | None

# actual_end    int | None

# confidence    float | None

# match_method  str | None

# backup_file   str | None

# error_msg     str | None

# timestamp     datetime

def write_log(
session_meta: dict,
results: list[dict],
log_path: Path | None = None,
) -> Path:
now = session_meta.get(“ended_at”, datetime.now())
ts = now.strftime(”%Y%m%d_%H%M%S”)

```
if log_path is None:
    report_dir = Path(session_meta["report_file"]).parent
    log_path = report_dir / f"report_editor_{ts}.log"

applied = [r for r in results if r.get("action") == "applied"]
skipped = [r for r in results if r.get("action") == "skipped"]
errors  = [r for r in results if r.get("action") == "error"]

lines = []

def w(s=""):
    lines.append(s)

# Header
w("=" * 72)
w("  REPORT-EDITOR SESSION LOG")
w("=" * 72)
w(f"  Started     : {session_meta.get('started_at', 'unknown')}")
w(f"  Ended       : {now}")
duration = (now - session_meta["started_at"]).seconds if "started_at" in session_meta else "?"
w(f"  Duration    : {duration}s")
w(f"  Report file : {session_meta.get('report_file', 'unknown')}")
w(f"  Search root : {session_meta.get('search_root', 'unknown')}")
w(f"  Files found : {session_meta.get('files_found', '?')} / {session_meta.get('files_found', 0) + session_meta.get('files_missing', 0)}")
w(f"  Total changes in report : {session_meta.get('total_changes', '?')}")
w()
w(f"  [OK] Applied : {len(applied)}")
w(f"  . Skipped : {len(skipped)}")
w(f"  [X] Errors  : {len(errors)}")
w("=" * 72)
w()

if applied:
    w("APPLIED CHANGES")
    w("-" * 72)
    for r in applied:
        _write_entry(w, r)
    w()

if skipped:
    w("SKIPPED CHANGES")
    w("-" * 72)
    for r in skipped:
        _write_entry(w, r)
    w()

if errors:
    w("ERRORS")
    w("-" * 72)
    for r in errors:
        _write_entry(w, r)
    w()

# Per-file summary
w("FILE SUMMARY")
w("-" * 72)
by_file: dict[str, list[dict]] = {}
for r in results:
    by_file.setdefault(r.get("file", "unknown"), []).append(r)

for filepath, file_results in by_file.items():
    n_applied = sum(1 for r in file_results if r.get("action") == "applied")
    n_skipped = sum(1 for r in file_results if r.get("action") == "skipped")
    n_err     = sum(1 for r in file_results if r.get("action") == "error")
    resolved  = file_results[0].get("resolved_path", "NOT FOUND")
    w(f"  {filepath}")
    w(f"    Resolved : {resolved}")
    w(f"    Applied={n_applied}  Skipped={n_skipped}  Errors={n_err}")
    for bk in [r["backup_file"] for r in file_results if r.get("backup_file")]:
        w(f"    Backup   : {bk}")
    w()

w("=" * 72)
w(f"  Log written : {log_path}")
w("=" * 72)

log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
return log_path
```

def _write_entry(w, r: dict):
action_icon = {“applied”: “[OK]”, “skipped”: “.”, “error”: “[X]”}.get(r.get(“action”, “”), “?”)
ts = r.get(“timestamp”)
ts_str = ts.strftime(”%H:%M:%S”) if isinstance(ts, datetime) else str(ts or “”)

```
w(f"  {action_icon} [{ts_str}] {r.get('change', '?')}")
w(f"      File     : {r.get('file', '?')}")
w(f"      On disk  : {r.get('resolved_path', 'NOT FOUND')}")

op      = r.get("operation", "?")
hint_s  = r.get("hint_start")
hint_e  = r.get("hint_end")
actual_s = r.get("actual_start")
actual_e = r.get("actual_end")

if op == "remove" and actual_s is not None:
    conf = r.get("confidence")
    method = r.get("match_method", "?")
    conf_str = f"{int(conf * 100)}%" if conf is not None else "?"
    w(f"      Operation: REMOVE  hint={hint_s}-{hint_e}  actual={actual_s}-{actual_e}  match={conf_str} ({method})")
elif op == "insert" and actual_s is not None:
    w(f"      Operation: INSERT  hint={hint_s}  inserted before line {actual_s}")
else:
    w(f"      Operation: {op.upper() if op else '?'}  hint={hint_s}-{hint_e}")

if r.get("backup_file"):
    w(f"      Backup   : {r['backup_file']}")
if r.get("error_msg"):
    w(f"      ERROR    : {r['error_msg']}")
w()
```