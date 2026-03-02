“””
tui.py — Curses TUI for stepping through report changes one at a time.

Layout:
┌─────────────────────────────────────────────────────┐
│  HEADER: filename + change info                      │
├─────────────────────────────────────────────────────┤
│                                                      │
│  FILE VIEW (scrollable, target region highlighted)  │
│                                                      │
├─────────────────────────────────────────────────────┤
│  CHANGE PANEL: action + code from report            │
├─────────────────────────────────────────────────────┤
│  STATUS BAR + KEY HINTS                              │
└─────────────────────────────────────────────────────┘

Keys:
[A] Apply change     [S] Skip change     [Q] Quit
[↑/↓] Scroll file    [J/K] also scroll
“””

import curses
import textwrap
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass

from report import FileChange, Change
from finder import find_files
from matcher import find_block, find_insert_line, MatchResult
from editor import apply_insert, apply_remove

# ── Colour pair IDs ──────────────────────────────────────────────────────────

C_NORMAL      = 0
C_HEADER      = 1
C_HIGHLIGHT   = 2   # target region in file view
C_INSERT_CODE = 3   # code-to-insert in change panel
C_REMOVE_CODE = 4   # code-to-remove in change panel
C_STATUS_OK   = 5
C_STATUS_WARN = 6
C_STATUS_ERR  = 7
C_DIM         = 8
C_LINENO      = 9

def _init_colors():
curses.start_color()
curses.use_default_colors()
curses.init_pair(C_HEADER,      curses.COLOR_BLACK,  curses.COLOR_CYAN)
curses.init_pair(C_HIGHLIGHT,   curses.COLOR_BLACK,  curses.COLOR_YELLOW)
curses.init_pair(C_INSERT_CODE, curses.COLOR_GREEN,  -1)
curses.init_pair(C_REMOVE_CODE, curses.COLOR_RED,    -1)
curses.init_pair(C_STATUS_OK,   curses.COLOR_BLACK,  curses.COLOR_GREEN)
curses.init_pair(C_STATUS_WARN, curses.COLOR_BLACK,  curses.COLOR_YELLOW)
curses.init_pair(C_STATUS_ERR,  curses.COLOR_WHITE,  curses.COLOR_RED)
curses.init_pair(C_DIM,         curses.COLOR_WHITE,  -1)
curses.init_pair(C_LINENO,      curses.COLOR_CYAN,   -1)

@dataclass
class Session:
file_changes: list[FileChange]
file_map: dict[str, Path | None]
search_root: str
results: list[dict]   # log of what was applied/skipped

def run_tui(session: Session):
curses.wrapper(_tui_main, session)

def _tui_main(stdscr, session: Session):
_init_colors()
curses.curs_set(0)
stdscr.keypad(True)

```
total_changes = sum(len(fc.changes) for fc in session.file_changes)
change_index = 0

# Flatten changes into a list of (FileChange, Change)
flat: list[tuple[FileChange, Change]] = []
for fc in session.file_changes:
    for ch in fc.changes:
        flat.append((fc, ch))

if not flat:
    _show_message(stdscr, "No changes found in report.", C_STATUS_WARN)
    stdscr.getch()
    return

scroll_offset = 0
status_msg = ""
status_color = C_STATUS_OK

while change_index < len(flat):
    fc, change = flat[change_index]
    file_path = session.file_map.get(fc.filepath)

    h, w = stdscr.getmaxyx()

    # Load file lines (or show error if not found)
    if file_path is None:
        file_lines = []
        match_result = None
        insert_line = None
    else:
        file_lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if change.action == "remove":
            match_result = find_block(
                file_lines, change.lines,
                change.line_start, change.line_end,
            )
            insert_line = None
        else:
            match_result = None
            insert_line = find_insert_line(file_lines, change.line_start)

    # Auto-scroll to highlight region
    if match_result and match_result.found:
        target_line = match_result.line_start
    elif insert_line:
        target_line = insert_line
    else:
        target_line = change.line_start

    # Layout heights
    header_h    = 3
    panel_h     = min(len(change.lines) + 4, h // 3)
    status_h    = 1
    file_view_h = max(5, h - header_h - panel_h - status_h - 1)

    # Auto-scroll so target is visible
    if scroll_offset > target_line - 3:
        scroll_offset = max(0, target_line - 3)
    if scroll_offset + file_view_h < target_line + 3:
        scroll_offset = target_line + 3 - file_view_h

    stdscr.erase()

    # ── Header ──────────────────────────────────────────────────────────
    _draw_header(stdscr, w, fc, change, change_index, len(flat), file_path)

    # ── File view ───────────────────────────────────────────────────────
    _draw_file_view(
        stdscr, file_lines,
        top_row=header_h, height=file_view_h, width=w,
        scroll=scroll_offset,
        highlight_start=match_result.line_start if match_result and match_result.found else (insert_line or target_line),
        highlight_end=match_result.line_end if match_result and match_result.found else (insert_line or target_line),
        change_action=change.action,
        file_path=file_path,
    )

    # ── Change panel ────────────────────────────────────────────────────
    panel_top = header_h + file_view_h + 1
    _draw_change_panel(
        stdscr, change, match_result, insert_line,
        top_row=panel_top, height=panel_h, width=w,
    )

    # ── Status bar ──────────────────────────────────────────────────────
    _draw_status(stdscr, h - 1, w, status_msg, status_color)

    stdscr.refresh()
    status_msg = ""
    status_color = C_STATUS_OK

    # ── Input ───────────────────────────────────────────────────────────
    key = stdscr.getch()

    if key in (ord("q"), ord("Q")):
        break

    elif key in (ord("s"), ord("S")):
        session.results.append({
            "action":        "skipped",
            "file":          fc.filepath,
            "resolved_path": str(file_path) if file_path else "NOT FOUND",
            "change":        str(change),
            "operation":     change.action,
            "hint_start":    change.line_start,
            "hint_end":      change.line_end,
            "actual_start":  None,
            "actual_end":    None,
            "confidence":    match_result.confidence if match_result else None,
            "match_method":  match_result.method if match_result else None,
            "backup_file":   None,
            "error_msg":     None,
            "timestamp":     datetime.now(),
        })
        status_msg = f"Skipped: {change}"
        status_color = C_STATUS_WARN
        change_index += 1
        scroll_offset = 0

    elif key in (ord("a"), ord("A")):
        if file_path is None:
            status_msg = "ERROR: File not found — cannot apply."
            status_color = C_STATUS_ERR
            session.results.append({
                "action":        "error",
                "file":          fc.filepath,
                "resolved_path": "NOT FOUND",
                "change":        str(change),
                "operation":     change.action,
                "hint_start":    change.line_start,
                "hint_end":      change.line_end,
                "actual_start":  None,
                "actual_end":    None,
                "confidence":    None,
                "match_method":  None,
                "backup_file":   None,
                "error_msg":     "File not found on disk",
                "timestamp":     datetime.now(),
            })
        else:
            try:
                bak = None
                actual_s = actual_e = None

                if change.action == "insert":
                    bak = apply_insert(file_path, insert_line, change.lines)
                    actual_s = actual_e = insert_line
                    status_msg = f"Inserted at line {insert_line}. Backup: {bak.name if bak else 'none'}"
                else:
                    if match_result and match_result.found:
                        bak = apply_remove(file_path, match_result.line_start, match_result.line_end)
                        actual_s, actual_e = match_result.line_start, match_result.line_end
                        status_msg = f"Removed lines {actual_s}-{actual_e}. Backup: {bak.name if bak else 'none'}"
                    else:
                        status_msg = "ERROR: Could not locate block to remove. Use [S] to skip."
                        status_color = C_STATUS_ERR
                        key = -1  # don't advance

                if status_color == C_STATUS_OK:
                    session.results.append({
                        "action":        "applied",
                        "file":          fc.filepath,
                        "resolved_path": str(file_path),
                        "change":        str(change),
                        "operation":     change.action,
                        "hint_start":    change.line_start,
                        "hint_end":      change.line_end,
                        "actual_start":  actual_s,
                        "actual_end":    actual_e,
                        "confidence":    match_result.confidence if match_result else None,
                        "match_method":  match_result.method if match_result else None,
                        "backup_file":   str(bak) if bak else None,
                        "error_msg":     None,
                        "timestamp":     datetime.now(),
                    })
                    # Brief confirmation flash
                    _show_flash(stdscr, h, w, status_msg, C_STATUS_OK)
                    change_index += 1
                    scroll_offset = 0
                elif key == -1:
                    session.results.append({
                        "action":        "error",
                        "file":          fc.filepath,
                        "resolved_path": str(file_path),
                        "change":        str(change),
                        "operation":     change.action,
                        "hint_start":    change.line_start,
                        "hint_end":      change.line_end,
                        "actual_start":  None,
                        "actual_end":    None,
                        "confidence":    match_result.confidence if match_result else None,
                        "match_method":  match_result.method if match_result else None,
                        "backup_file":   None,
                        "error_msg":     "Block not located with sufficient confidence",
                        "timestamp":     datetime.now(),
                    })
            except Exception as e:
                status_msg = f"ERROR: {e}"
                status_color = C_STATUS_ERR
                session.results.append({
                    "action":        "error",
                    "file":          fc.filepath,
                    "resolved_path": str(file_path),
                    "change":        str(change),
                    "operation":     change.action,
                    "hint_start":    change.line_start,
                    "hint_end":      change.line_end,
                    "actual_start":  None,
                    "actual_end":    None,
                    "confidence":    None,
                    "match_method":  None,
                    "backup_file":   None,
                    "error_msg":     str(e),
                    "timestamp":     datetime.now(),
                })

    elif key in (curses.KEY_UP, ord("k"), ord("K")):
        scroll_offset = max(0, scroll_offset - 1)
    elif key in (curses.KEY_DOWN, ord("j"), ord("J")):
        scroll_offset = min(max(0, len(file_lines) - file_view_h), scroll_offset + 1)
    elif key == curses.KEY_PPAGE:
        scroll_offset = max(0, scroll_offset - file_view_h)
    elif key == curses.KEY_NPAGE:
        scroll_offset = min(max(0, len(file_lines) - file_view_h), scroll_offset + file_view_h)

# ── Summary screen ───────────────────────────────────────────────────────
_draw_summary(stdscr, session.results)
```

# ── Drawing helpers ───────────────────────────────────────────────────────────

def _draw_header(stdscr, w, fc: FileChange, change: Change, idx: int, total: int, file_path):
attr = curses.color_pair(C_HEADER) | curses.A_BOLD
line0 = f” report-editor  ·  change {idx+1}/{total} “
line1 = f” {‘✓’ if file_path else ‘✗’} {fc.filepath} “
verb  = “INSERT” if change.action == “insert” else “REMOVE”
line2 = f” {verb} · report hint: lines {change.line_start}–{change.line_end} · {len(change.lines)} line(s) “

```
stdscr.addstr(0, 0, line0.ljust(w), attr)
stdscr.addstr(1, 0, line1[:w].ljust(w), attr)
stdscr.addstr(2, 0, line2[:w].ljust(w), attr)
```

def _draw_file_view(stdscr, file_lines, top_row, height, width, scroll,
highlight_start, highlight_end, change_action, file_path):
# Border line
try:
stdscr.addstr(top_row, 0, “─” * width, curses.color_pair(C_DIM))
except curses.error:
pass

```
if file_path is None:
    msg = "  [ File not found on this system ]"
    try:
        stdscr.addstr(top_row + height // 2, 0, msg[:width], curses.color_pair(C_STATUS_ERR))
    except curses.error:
        pass
    return

lineno_w = 6
content_w = width - lineno_w - 1

for row in range(height - 1):
    file_idx = scroll + row   # 0-based
    screen_row = top_row + 1 + row

    if file_idx >= len(file_lines):
        break

    lineno = file_idx + 1   # 1-based
    is_highlighted = highlight_start <= lineno <= highlight_end

    line_text = file_lines[file_idx]
    # Truncate to fit
    display = line_text[:content_w].ljust(content_w)

    if is_highlighted:
        hl_attr = curses.color_pair(C_HIGHLIGHT) | curses.A_BOLD
        rm_attr = curses.color_pair(C_REMOVE_CODE) | curses.A_BOLD
        ins_attr = curses.color_pair(C_INSERT_CODE) | curses.A_BOLD
        if change_action == "remove":
            line_attr = rm_attr
        else:
            line_attr = ins_attr
        marker = "▶ " if change_action == "insert" else "✕ "
    else:
        line_attr = C_NORMAL
        marker = "  "

    try:
        no_str = f"{lineno:>{lineno_w-1}} "
        stdscr.addstr(screen_row, 0, no_str, curses.color_pair(C_LINENO))
        stdscr.addstr(screen_row, lineno_w, marker + display[:content_w - 2], line_attr)
    except curses.error:
        pass
```

def _draw_change_panel(stdscr, change: Change, match_result: MatchResult | None,
insert_line: int | None, top_row, height, width):
try:
stdscr.addstr(top_row, 0, “─” * width, curses.color_pair(C_DIM))
except curses.error:
pass

```
# Title line
if change.action == "insert":
    verb_attr = curses.color_pair(C_INSERT_CODE) | curses.A_BOLD
    verb = "INSERT"
    loc_str = f"→ insert before line {insert_line}" if insert_line else ""
else:
    verb_attr = curses.color_pair(C_REMOVE_CODE) | curses.A_BOLD
    verb = "REMOVE"
    if match_result and match_result.found:
        conf_pct = int(match_result.confidence * 100)
        loc_str = f"→ found at lines {match_result.line_start}-{match_result.line_end}  [{conf_pct}% match, method: {match_result.method}]"
    else:
        loc_str = "→ BLOCK NOT FOUND (low confidence)"

title = f" {verb} "
try:
    stdscr.addstr(top_row + 1, 0, title, verb_attr)
    stdscr.addstr(top_row + 1, len(title), f" {loc_str}"[:width - len(title)],
                  curses.color_pair(C_DIM))
except curses.error:
    pass

# Code lines
code_attr = curses.color_pair(C_INSERT_CODE if change.action == "insert" else C_REMOVE_CODE)
for i, ln in enumerate(change.lines):
    row = top_row + 2 + i
    if row >= top_row + height:
        break
    prefix = "  + " if change.action == "insert" else "  - "
    try:
        stdscr.addstr(row, 0, (prefix + ln)[:width], code_attr)
    except curses.error:
        pass

# Key hints
hint_row = top_row + height - 1
hints = "  [A] Apply    [S] Skip    [Q] Quit    [↑↓ / J K] Scroll    [PgUp/PgDn]"
try:
    stdscr.addstr(hint_row, 0, hints[:width], curses.color_pair(C_DIM) | curses.A_DIM)
except curses.error:
    pass
```

def _draw_status(stdscr, row, w, msg, color):
attr = curses.color_pair(color) | curses.A_BOLD
try:
stdscr.addstr(row, 0, f” {msg} “.ljust(w)[:w], attr)
except curses.error:
pass

def _show_flash(stdscr, h, w, msg, color):
attr = curses.color_pair(color) | curses.A_BOLD
try:
stdscr.addstr(h - 1, 0, f” ✓ {msg} “.ljust(w)[:w], attr)
stdscr.refresh()
curses.napms(800)
except curses.error:
pass

def _show_message(stdscr, msg, color):
h, w = stdscr.getmaxyx()
attr = curses.color_pair(color) | curses.A_BOLD
try:
stdscr.addstr(h // 2, max(0, (w - len(msg)) // 2), msg[:w], attr)
except curses.error:
pass
stdscr.refresh()

def _draw_summary(stdscr, results: list[dict]):
stdscr.erase()
h, w = stdscr.getmaxyx()
attr_h = curses.color_pair(C_HEADER) | curses.A_BOLD

```
applied = [r for r in results if r["action"] == "applied"]
skipped = [r for r in results if r["action"] == "skipped"]

try:
    stdscr.addstr(0, 0, " Session Summary ".center(w), attr_h)
    stdscr.addstr(2, 2, f"Applied : {len(applied)}", curses.color_pair(C_INSERT_CODE) | curses.A_BOLD)
    stdscr.addstr(3, 2, f"Skipped : {len(skipped)}", curses.color_pair(C_STATUS_WARN) | curses.A_BOLD)
    stdscr.addstr(5, 2, "Changes applied:", curses.A_BOLD)
    for i, r in enumerate(results):
        row = 6 + i
        if row >= h - 2:
            break
        icon = "✓" if r["action"] == "applied" else "·"
        color = C_INSERT_CODE if r["action"] == "applied" else C_DIM
        stdscr.addstr(row, 4, f"{icon} {r['file']}  —  {r['change']}"[:w - 4],
                      curses.color_pair(color))
    stdscr.addstr(h - 1, 0, " Press any key to exit ".ljust(w),
                  curses.color_pair(C_HEADER) | curses.A_BOLD)
except curses.error:
    pass
stdscr.refresh()
stdscr.getch()
```