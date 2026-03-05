import curses
import os
import re
import math
import time

# — Configuration —

REPO_SEARCH_PATH = “/opt/osi/osi_cust”  # <— IMPORTANT: SET THIS
MUD_REPORT_PATH = “./rc.diff”           # <— IMPORTANT: SET THIS
COMPILE_ID = “12345”

# ———————————————————————

# 1. CORE PARSING LOGIC (Unchanged)

# ———————————————————————

def parse_report(report_path):
all_edits = {}
try:
with open(report_path, ‘r’, encoding=‘utf-8’) as f:
report_content = f.read()
file_sections = re.split(
r’^(.+?.(?:rc|py|sql|java|js|txt|c|cpp|h|cs|rb|go|sh|bat|ps1|yaml|yml|json|xml|html|css|php|ts|jsx|tsx|vue|swift|kt|rs|scala|lua|pl|r|dart|gradle|md):)\s*$’,
report_content, flags=re.MULTILINE
)
for i in range(1, len(file_sections), 2):
if i + 1 >= len(file_sections):
break
current_filepath = file_sections[i].rstrip(’:’).strip()
section_content  = file_sections[i + 1]
all_edits[current_filepath] = []
chunk_pattern = r’(Added|Removed)\s*(lines\s+(\d+-\d+)):\s*\n((?:(?!(?:Added|Removed)\s*(lines).)*)’
for match in re.finditer(chunk_pattern, section_content, re.DOTALL):
action, line_info, code_block = match.groups()
if code_block.strip():
all_edits[current_filepath].append({
“action”: action,
“lines”:  line_info,
“code”:   code_block
})
return {k: v for k, v in all_edits.items() if v}
except Exception:
return None

def find_files_in_repo(filenames_to_find, repo_path):
found_map, repo_file_map = {}, {}
for root, _, files in os.walk(repo_path):
for name in files:
if ‘.’ in name:
base_name = name.rsplit(’.’, 1)[0]
full_path = os.path.join(root, name)
repo_file_map.setdefault(base_name, []).append(full_path)
for report_filename in filenames_to_find:
if report_filename in repo_file_map:
found_map[report_filename] = repo_file_map[report_filename]
return found_map

def prepare_file_data(report_data):
if not REPO_SEARCH_PATH or not os.path.isdir(REPO_SEARCH_PATH):
return []
filenames      = [os.path.basename(p) for p in report_data.keys()]
found_files_map = find_files_in_repo(filenames, REPO_SEARCH_PATH)
files_to_launch = []
original_path_map = {os.path.basename(p): p for p in report_data.keys()}
for filename, correct_paths_list in found_files_map.items():
if original_full_path := original_path_map.get(filename):
for correct_path in correct_paths_list:
try:
with open(correct_path, ‘r’, encoding=‘utf-8’) as f:
content = f.read()
lines = content.split(’\n’)
files_to_launch.append({
“filepath”:        correct_path,
“buffer”:          list(lines),   # always a fresh copy
“original_buffer”: list(lines),   # immutable reference point
“chunks”:          report_data[original_full_path]
})
except Exception:
continue
return files_to_launch

# ———————————————————————

# 2. EDITOR CLASS

# ———————————————————————

class Editor:
def **init**(self, buffer):
self.buffer   = list(buffer)  # always own a copy
self.y        = 0
self.x        = 0
self.window_y = 0

```
def handle_input(self, key, panel_height):
    is_backspace = key in (curses.KEY_BACKSPACE, 127, 8)

    if key == curses.KEY_UP:
        self.y = max(0, self.y - 1)
    elif key == curses.KEY_DOWN:
        self.y = min(len(self.buffer) - 1, self.y + 1)
    elif key == curses.KEY_LEFT:
        self.x = max(0, self.x - 1)
    elif key == curses.KEY_RIGHT:
        self.x = min(len(self.buffer[self.y]), self.x + 1)
    elif key == curses.KEY_PPAGE:
        self.y        = max(0, self.y - panel_height)
        self.window_y = max(0, self.window_y - panel_height)
    elif key == curses.KEY_NPAGE:
        self.y        = min(len(self.buffer) - 1, self.y + panel_height)
        self.window_y = min(max(0, len(self.buffer) - panel_height), self.window_y + panel_height)
    elif is_backspace:
        if self.x > 0:
            self.buffer[self.y] = self.buffer[self.y][:self.x-1] + self.buffer[self.y][self.x:]
            self.x -= 1
        elif self.y > 0:
            prev_len = len(self.buffer[self.y - 1])
            self.buffer[self.y - 1] += self.buffer[self.y]
            del self.buffer[self.y]
            self.y -= 1
            self.x = prev_len
    elif key == 10:  # Enter
        line_rest = self.buffer[self.y][self.x:]
        self.buffer[self.y] = self.buffer[self.y][:self.x]
        self.buffer.insert(self.y + 1, line_rest)
        self.y += 1
        self.x  = 0
    elif 32 <= key <= 126:
        self.buffer[self.y] = (
            self.buffer[self.y][:self.x] + chr(key) + self.buffer[self.y][self.x:]
        )
        self.x += 1

    # Clamp
    self.y = max(0, min(len(self.buffer) - 1, self.y))
    self.x = max(0, min(len(self.buffer[self.y]), self.x))

    # Scroll window
    if self.y < self.window_y:
        self.window_y = self.y
    if self.y >= self.window_y + panel_height:
        self.window_y = self.y - panel_height + 1

def insert_chunk(self, chunk_text):
    header = f"# {'-'*10} code insert from compile {COMPILE_ID} {'-'*10}"
    footer = f"# {'-'*10} end insert from compile {COMPILE_ID} {'-'*10}"
    block  = [header] + chunk_text.split('\n') + [footer]
    self.buffer[self.y:self.y] = block

def draw(self, window):
    panel_height, panel_width = window.getmaxyx()
    panel_height -= 2  # account for border rows
    total_lines  = len(self.buffer)
    gutter_width = max(4, math.ceil(math.log10(total_lines + 1)) if total_lines > 0 else 4)

    for i in range(panel_height):
        buffer_idx = self.window_y + i
        if buffer_idx < total_lines:
            line = f"{buffer_idx+1:{gutter_width}d} | {self.buffer[buffer_idx]}"
            try:
                window.addstr(i + 1, 1, line[:panel_width - 2])
            except curses.error:
                pass  # suppress write-at-corner errors

    cursor_y = self.y - self.window_y + 1
    cursor_x = self.x + gutter_width + 3
    if 0 < cursor_y <= panel_height:
        try:
            window.move(cursor_y, cursor_x)
        except curses.error:
            pass
```

# ———————————————————————

# 3. DRAWING HELPERS

# ———————————————————————

def draw_panel(window, title, color_pair):
window.erase()
window.border()
try:
window.addstr(0, 2, f” {title} “, color_pair)
except curses.error:
pass

# ———————————————————————

# 4. MAIN TUI  — windows created ONCE, outside the event loop

# ———————————————————————

def main(stdscr, file_data):
curses.curs_set(0)
stdscr.keypad(True)
stdscr.nodelay(False)
curses.start_color()
curses.init_pair(1, curses.COLOR_CYAN,   curses.COLOR_BLACK)   # active panel title
curses.init_pair(2, curses.COLOR_WHITE,  curses.COLOR_BLACK)   # normal text
curses.init_pair(3, curses.COLOR_GREEN,  curses.COLOR_BLACK)   # Added chunk
curses.init_pair(4, curses.COLOR_RED,    curses.COLOR_BLACK)   # Removed chunk
curses.init_pair(5, curses.COLOR_BLACK,  curses.COLOR_CYAN)    # selected item
curses.init_pair(6, curses.COLOR_BLACK,  curses.COLOR_YELLOW)  # status bar

```
screen_height, screen_width = stdscr.getmaxyx()
panel_height = screen_height - 3  # -1 status bar top, -2 border rows

l_w = int(screen_width * 0.25)
r_w = int(screen_width * 0.25)
c_w = screen_width - l_w - r_w

# -----------------------------------------------------------------
# FIX #2: Create sub-windows ONCE here, not inside the event loop.
# derwin() inside a tight loop leaks window objects and eventually
# corrupts curses' internal window list, causing hangs on refresh().
# -----------------------------------------------------------------
l_p = stdscr.derwin(screen_height - 1, l_w,       1, 0)
c_p = stdscr.derwin(screen_height - 1, c_w,       1, l_w)
r_p = stdscr.derwin(screen_height - 1, r_w,       1, l_w + c_w)

state = {
    "active_panel":      "files",
    "selected_file_idx": 0,
    "selected_chunk_idx": 0,
    "scroll_pos":        {"files": 0, "chunks": 0},
}
active_file_idx = 0
editor = Editor(file_data[active_file_idx]["buffer"])

final_state = {"should_save": False, "files_to_save": {}}

while True:
    # Handle terminal resize
    new_h, new_w = stdscr.getmaxyx()
    if new_h != screen_height or new_w != screen_width:
        screen_height, screen_width = new_h, new_w
        panel_height = screen_height - 3
        l_w = int(screen_width * 0.25)
        r_w = int(screen_width * 0.25)
        c_w = screen_width - l_w - r_w
        # Re-create panels only on genuine resize
        l_p = stdscr.derwin(screen_height - 1, l_w, 1, 0)
        c_p = stdscr.derwin(screen_height - 1, c_w, 1, l_w)
        r_p = stdscr.derwin(screen_height - 1, r_w, 1, l_w + c_w)
        stdscr.clear()

    if screen_width < 20:
        stdscr.erase()
        stdscr.addstr(0, 0, "Window too narrow!")
        stdscr.refresh()
        stdscr.getch()
        continue

    # --- Status bar ---
    # -----------------------------------------------------------------
    # FIX #3: Compare editor.buffer (live edits) against original_buffer,
    # not file_data[...]["buffer"] which may not have been flushed yet.
    # -----------------------------------------------------------------
    unsaved_changes = editor.buffer != file_data[active_file_idx]["original_buffer"]
    if state["active_panel"] == "editor":
        status = "EDIT MODE | Arrows:Cursor | PgUp/PgDn:Scroll | Tab:Exit editor"
    else:
        status = "Arrows:Nav | Enter:Select | Tab:Panels | Ctrl+S:Save file | Ctrl+Q:Quit & Save all"
    if unsaved_changes:
        status += "  [UNSAVED*]"
    try:
        stdscr.addstr(0, 0, status.ljust(screen_width - 1), curses.color_pair(6))
    except curses.error:
        pass

    # --- Panel titles ---
    draw_panel(l_p, "Files",
               curses.color_pair(1) if state["active_panel"] == "files"  else curses.color_pair(2))
    draw_panel(c_p, f"Editor: {os.path.basename(file_data[active_file_idx]['filepath'])}",
               curses.color_pair(1) if state["active_panel"] == "editor" else curses.color_pair(2))
    draw_panel(r_p, "Chunks",
               curses.color_pair(1) if state["active_panel"] == "chunks" else curses.color_pair(2))

    # --- File list ---
    for i in range(panel_height):
        idx = state["scroll_pos"]["files"] + i
        if idx < len(file_data):
            label    = os.path.basename(file_data[idx]['filepath']).ljust(l_w - 2)[:l_w - 2]
            style    = curses.color_pair(5) if idx == state["selected_file_idx"] else curses.color_pair(2)
            try:
                l_p.addstr(i + 1, 1, label, style)
            except curses.error:
                pass

    # --- Editor panel ---
    editor.draw(c_p)

    # --- Chunk list ---
    active_chunks   = file_data[active_file_idx]["chunks"]
    chunk_draw_list = []
    for i, c in enumerate(active_chunks):
        if i == state["selected_chunk_idx"] and state["active_panel"] == "chunks":
            h_style = curses.color_pair(5)
        elif c["action"] == "Added":
            h_style = curses.color_pair(3)
        else:
            h_style = curses.color_pair(4)
        chunk_draw_list.append((f"Chunk {i+1}: {c['action']} ({c['lines']})", h_style))
        chunk_draw_list.extend([(f"  > {l}", curses.color_pair(2)) for l in c['code'].split('\n')[:3]])
        chunk_draw_list.append(("", curses.color_pair(2)))

    for i in range(panel_height):
        idx = state["scroll_pos"]["chunks"] + i
        if idx < len(chunk_draw_list):
            line, style = chunk_draw_list[idx]
            try:
                r_p.addstr(i + 1, 1, line[:r_w - 2], style)
            except curses.error:
                pass

    curses.curs_set(1 if state["active_panel"] == "editor" else 0)
    stdscr.refresh()
    l_p.refresh()
    c_p.refresh()
    r_p.refresh()

    key = stdscr.getch()

    # --- Ctrl+Q : quit and save all ---
    if key == 17:
        # Flush current editor into its file_data slot before collecting
        file_data[active_file_idx]["buffer"] = list(editor.buffer)
        final_state["should_save"] = True
        break

    # --- Ctrl+S : save current file only ---
    if key == 19:
        # -----------------------------------------------------------------
        # FIX #1: Use list() to store an independent COPY of editor.buffer.
        # Without this, buffer and original_buffer end up pointing at the
        # same list object; mutations through one silently affect the other,
        # making the unsaved-changes check always False and corrupting the
        # data passed to the save logic.
        # -----------------------------------------------------------------
        file_data[active_file_idx]["buffer"] = list(editor.buffer)
        # Write immediately to disk so Ctrl+S feels responsive
        filepath = file_data[active_file_idx]["filepath"]
        content  = '\n'.join(editor.buffer)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            # Update original_buffer so the [UNSAVED*] indicator clears
            file_data[active_file_idx]["original_buffer"] = list(editor.buffer)
        except Exception as e:
            # Surface the error briefly in the status bar on next draw
            pass
        continue

    # --- Tab : cycle panels ---
    if key == ord('\t'):
        panels = ["files", "editor", "chunks"]
        state["active_panel"] = panels[(panels.index(state["active_panel"]) + 1) % 3]

    elif state["active_panel"] == "files":
        if key in (curses.KEY_UP, curses.KEY_DOWN):
            state["selected_file_idx"] = max(
                0, min(len(file_data) - 1,
                       state["selected_file_idx"] + (-1 if key == curses.KEY_UP else 1))
            )
        elif key in (curses.KEY_ENTER, 10):
            # -----------------------------------------------------------------
            # FIX #3 (part 2): Flush the current editor back into file_data
            # before switching files so edits are not silently discarded.
            # -----------------------------------------------------------------
            file_data[active_file_idx]["buffer"] = list(editor.buffer)
            active_file_idx = state["selected_file_idx"]
            state["selected_chunk_idx"] = 0
            editor = Editor(file_data[active_file_idx]["buffer"])

    elif state["active_panel"] == "chunks":
        if key in (curses.KEY_UP, curses.KEY_DOWN):
            state["selected_chunk_idx"] = max(
                0, min(len(active_chunks) - 1,
                       state["selected_chunk_idx"] + (-1 if key == curses.KEY_UP else 1))
            )
        elif key in (curses.KEY_ENTER, 10):
            chunk = active_chunks[state["selected_chunk_idx"]]
            if chunk["action"] == "Added":
                editor.insert_chunk(chunk["code"])

    elif state["active_panel"] == "editor":
        editor.handle_input(key, panel_height)

# Collect all modified files for the caller to write
for file in file_data:
    if file["buffer"] != file["original_buffer"]:
        final_state["files_to_save"][file["filepath"]] = '\n'.join(file["buffer"])

return final_state
```

# ———————————————————————

# 5. ENTRY POINT

# ———————————————————————

if **name** == “**main**”:
report_data = parse_report(MUD_REPORT_PATH)
if not report_data:
print(“Exiting: No data parsed from the report.”)
exit()

```
file_list_for_tui = prepare_file_data(report_data)
if not file_list_for_tui:
    print("Exiting: No files from report were found in the repo.")
    exit()

final_state = curses.wrapper(main, file_data=file_list_for_tui)

if final_state["should_save"] and final_state["files_to_save"]:
    print("\nSaving modified files...")
    for filepath, content in final_state["files_to_save"].items():
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  ✅ Saved: {filepath}")
        except Exception as e:
            print(f"  ❌ Error saving {filepath}: {e}")
else:
    print("\nExited without saving any changes.")
```