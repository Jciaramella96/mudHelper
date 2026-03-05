import curses
import os
import re
import math

# --- Configuration ---
REPO_SEARCH_PATH = "/opt/osi/osi_cust"  # <--- IMPORTANT: SET THIS
MUD_REPORT_PATH = "./rc.diff" # <--- IMPORTANT: SET THIS
COMPILE_ID = "12345"

# ---------------------------------------------------------------------
# 1. CORE PARSING LOGIC (Unchanged)
# ---------------------------------------------------------------------
def parse_report(report_path):
    all_edits = {};
    try:
        with open(report_path, 'r', encoding='utf-8') as f: report_content = f.read()
        file_sections = re.split(r'^(.+?\.(?:rc|py|sql|java|js|txt|c|cpp|h|cs|rb|go|sh|bat|ps1|yaml|yml|json|xml|html|css|php|ts|jsx|tsx|vue|swift|kt|rs|scala|lua|pl|r|dart|gradle|md):)\s*$', report_content, flags=re.MULTILINE)
        for i in range(1, len(file_sections), 2):
            if i + 1 >= len(file_sections): break
            current_filepath, section_content = file_sections[i].rstrip(':').strip(), file_sections[i + 1]
            all_edits[current_filepath] = []
            chunk_pattern = r'(Added|Removed)\s*\(lines\s+(\d+-\d+)\):\s*\n((?:(?!(?:Added|Removed)\s*\(lines).)*)'
            for match in re.finditer(chunk_pattern, section_content, re.DOTALL):
                action, line_info, code_block = match.groups()
                if code_block.strip(): all_edits[current_filepath].append({"action": action, "lines": line_info, "code": code_block})
        return {k: v for k, v in all_edits.items() if v}
    except Exception: return None

def find_files_in_repo(filenames_to_find, repo_path):
    found_map, repo_file_map = {}, {}
    for root, _, files in os.walk(repo_path):
        for name in files:
            if '.' in name:
                base_name, full_path = name.rsplit('.', 1)[0], os.path.join(root, name)
                if base_name not in repo_file_map: repo_file_map[base_name] = []
                repo_file_map[base_name].append(full_path)
    for report_filename in filenames_to_find:
        if report_filename in repo_file_map: found_map[report_filename] = repo_file_map[report_filename]
    return found_map

def prepare_file_data(report_data):
    if not REPO_SEARCH_PATH or not os.path.isdir(REPO_SEARCH_PATH): return []
    filenames = [os.path.basename(p) for p in report_data.keys()]
    found_files_map = find_files_in_repo(filenames, REPO_SEARCH_PATH)
    files_to_launch, original_path_map = [], {os.path.basename(p): p for p in report_data.keys()}
    for filename, correct_paths_list in found_files_map.items():
        if original_full_path := original_path_map.get(filename):
            for correct_path in correct_paths_list:
                try:
                    with open(correct_path, 'r', encoding='utf-8') as f: content = f.read()
                    files_to_launch.append({"filepath": correct_path, "content": content.split('\n'), "chunks": report_data[original_full_path]})
                except Exception: continue
    return files_to_launch

# ---------------------------------------------------------------------
# 2. NEW ARCHITECTURE: Classes for Editor, Cursor, and Window
# ---------------------------------------------------------------------

class Cursor:
    def __init__(self, y=0, x=0):
        self.y, self.x = y, x

    def move(self, key, buffer):
        if key == curses.KEY_UP: self.y = max(0, self.y - 1)
        elif key == curses.KEY_DOWN: self.y = min(len(buffer) - 1, self.y + 1)
        elif key == curses.KEY_LEFT: self.x = max(0, self.x - 1)
        elif key == curses.KEY_RIGHT: self.x = min(len(buffer[self.y]), self.x + 1)
        # Ensure cursor x is not out of bounds of the current line
        self.x = min(len(buffer[self.y]), self.x)

class EditorWindow:
    def __init__(self, y=0, x=0):
        self.y, self.x = y, x

    def scroll(self, cursor, height, width):
        # Vertical scroll
        if cursor.y < self.y: self.y = cursor.y
        if cursor.y >= self.y + height: self.y = cursor.y - height + 1
        # Horizontal scroll (future implementation)

def main(stdscr, file_data):
    curses.curs_set(1); stdscr.nodelay(False); stdscr.keypad(True)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_YELLOW)

    if not file_data: return
    
    # --- State Initialization ---
    active_file = file_data[0]
    buffer = active_file['content'] # The buffer is just a list of strings
    cursor = Cursor()
    window = EditorWindow()

    while True:
        screen_height, screen_width = stdscr.getmaxyx()
        
        # --- Drawing Logic ---
        stdscr.erase()
        status_bar = f"EDIT MODE | File: {os.path.basename(active_file['filepath'])} | Line: {cursor.y+1}, Col: {cursor.x+1} | Ctrl+Q to Quit"
        stdscr.addstr(0, 0, status_bar.ljust(screen_width), curses.color_pair(6))

        # Render the "viewport" of the buffer
        for i in range(screen_height - 1):
            buffer_y = window.y + i
            if buffer_y < len(buffer):
                stdscr.addstr(i + 1, 0, buffer[buffer_y][:screen_width])

        # Position the actual curses cursor
        stdscr.move(cursor.y - window.y + 1, cursor.x - window.x)
        stdscr.refresh()

        # --- Input Handling ---
        key = stdscr.getch()
        if key == 17: # Ctrl+Q
            break
            
        # THE FIX: Let the Cursor and Window objects manage their own state
        is_backspace = key in [curses.KEY_BACKSPACE, 127, 8]

        if key in [curses.KEY_UP, curses.KEY_DOWN, curses.KEY_LEFT, curses.KEY_RIGHT]:
            cursor.move(key, buffer)
        elif is_backspace:
            if cursor.x > 0:
                buffer[cursor.y] = buffer[cursor.y][:cursor.x-1] + buffer[cursor.y][cursor.x:]
                cursor.move(curses.KEY_LEFT, buffer)
            elif cursor.y > 0:
                prev_line_len = len(buffer[cursor.y-1])
                buffer[cursor.y-1] += buffer[cursor.y]
                del buffer[cursor.y]
                cursor.move(curses.KEY_UP, buffer)
                cursor.x = prev_line_len
        elif key == 10: # Enter
            line_rest = buffer[cursor.y][cursor.x:]
            buffer[cursor.y] = buffer[cursor.y][:cursor.x]
            buffer.insert(cursor.y + 1, line_rest)
            cursor.move(curses.KEY_DOWN, buffer)
            cursor.x = 0
        elif 32 <= key <= 126: # Printable characters
            buffer[cursor.y] = buffer[cursor.y][:cursor.x] + chr(key) + buffer[cursor.y][cursor.x:]
            cursor.move(curses.KEY_RIGHT, buffer)
        
        # Tell the window to scroll if the cursor moved off-screen
        window.scroll(cursor, screen_height - 1, screen_width)


if __name__ == "__main__":
    report_data = parse_report(MUD_REPORT_PATH)
    if not report_data: print("Exiting: No data parsed from the report."); exit()
    file_list_for_tui = prepare_file_data(report_data)
    if not file_list_for_tui: print("Exiting: No files from report were found."); exit()
    curses.wrapper(main, file_data=file_list_for_tui)
    print("Editor exited.")
