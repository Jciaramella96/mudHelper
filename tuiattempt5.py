import curses
import os
import re
import math
import time

# --- Configuration ---
REPO_SEARCH_PATH = "/opt/osi/osi_cust"  # <--- IMPORTANT: SET THIS
MUD_REPORT_PATH = "./rc.diff" # <--- IMPORTANT: SET THIS
COMPILE_ID = "12345"

# ---------------------------------------------------------------------
# 1. CORE PARSING LOGIC (UNTOUCHED, AS YOU PROVIDED)
# ---------------------------------------------------------------------

def parse_report(report_path):
    all_edits = {};
    try:
        with open(report_path, 'r', encoding='utf-8') as f: report_content = f.read()
        file_sections = re.split(r'^(.+?\\.(?:rc|py|sql|java|js|txt|c|cpp|h|cs|rb|go|sh|bat|ps1|yaml|yml|json|xml|html|css|php|ts|jsx|tsx|vue|swift|kt|rs|scala|lua|pl|r|dart|gradle|md):)\\s*$', report_content, flags=re.MULTILINE)
        for i in range(1, len(file_sections), 2):
            if i + 1 >= len(file_sections): break
            current_filepath, section_content = file_sections[i].rstrip(':').strip(), file_sections[i + 1]
            all_edits[current_filepath] = []
            chunk_pattern = r'(Added|Removed)\\s*\\(lines\\s+(\\d+-\\d+)\\):\\s*\\n((?:(?!(?:Added|Removed)\\s*\\(lines).)*)'
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
    # This is your exact parsing logic, which you said works correctly.
    for report_filename in filenames_to_find:
        base_name_from_report = os.path.splitext(os.path.basename(report_filename))[0]
        if base_name_from_report in repo_file_map:
            found_map[report_filename] = repo_file_map[base_name_from_report]
    return found_map

def prepare_file_data(report_data):
    if not REPO_SEARCH_PATH or not os.path.isdir(REPO_SEARCH_PATH): return []
    filenames = list(report_data.keys()) # Use the keys directly from report_data
    found_files_map = find_files_in_repo(filenames, REPO_SEARCH_PATH)
    files_to_launch = []
    for original_full_path, correct_paths_list in found_files_map.items():
        for correct_path in correct_paths_list:
            try:
                with open(correct_path, 'r', encoding='utf-8') as f: content = f.read()
                lines = content.split('\n')
                if original_full_path in report_data:
                    files_to_launch.append({"filepath": correct_path, "buffer": list(lines), "original_buffer": list(lines), "chunks": report_data[original_full_path]})
            except Exception: continue
    return files_to_launch

# ---------------------------------------------------------------------
# 2. ROBUST ARCHITECTURE: Self-Contained Editor Class (UNTOUCHED)
# ---------------------------------------------------------------------
class Editor:
    def __init__(self, buffer):
        self.buffer = list(buffer)
        if not self.buffer: self.buffer = [""]
        self.y, self.x, self.window_y = 0, 0, 0

    def handle_input(self, key, panel_height):
        is_backspace = key in [curses.KEY_BACKSPACE, 127, 8]
        if key == curses.KEY_UP: self.y = max(0, self.y - 1)
        elif key == curses.KEY_DOWN: self.y = min(len(self.buffer) - 1, self.y + 1)
        elif key == curses.KEY_LEFT: self.x = max(0, self.x - 1)
        elif key == curses.KEY_RIGHT: self.x = min(len(self.buffer[self.y]), self.x + 1)
        elif key == curses.KEY_PPAGE: self.y=max(0,self.y-panel_height);self.window_y=max(0,self.window_y-panel_height)
        elif key == curses.KEY_NPAGE: self.y=min(len(self.buffer)-1,self.y+panel_height);self.window_y=min(len(self.buffer)-1-panel_height,self.window_y+panel_height)
        elif is_backspace:
            if self.x > 0: self.buffer[self.y]=self.buffer[self.y][:self.x-1]+self.buffer[self.y][self.x:];self.x-=1
            elif self.y > 0: prev_len=len(self.buffer[self.y-1]);self.buffer[self.y-1]+=self.buffer[self.y];del self.buffer[self.y];self.y-=1;self.x=prev_len
        elif key == 10: line_rest=self.buffer[self.y][self.x:];self.buffer[self.y]=self.buffer[self.y][:self.x];self.buffer.insert(self.y+1,line_rest);self.y+=1;self.x=0
        elif 32 <= key <= 126: self.buffer[self.y]=self.buffer[self.y][:self.x]+chr(key)+self.buffer[self.y][self.x:];self.x+=1
        
        self.y=max(0,min(len(self.buffer)-1,self.y));self.x=max(0,min(len(self.buffer[self.y]),self.x))
        if self.y<self.window_y:self.window_y=self.y
        if self.y>=self.window_y+panel_height:self.window_y=self.y-panel_height+1
        return True

    def insert_chunk(self, chunk_text):
        header, footer = f"# {'-'*10} code insert from {COMPILE_ID} {'-'*10}", f"# {'-'*10} end insert {'-'*10}"
        self.buffer[self.y:self.y] = [header] + chunk_text.split('\n') + [footer]
        
    def draw(self, window):
        panel_height, panel_width = window.getmaxyx(); panel_height -= 2
        total_lines = len(self.buffer); gutter_width = max(4, math.ceil(math.log10(total_lines + 1)) if total_lines > 0 else 4)
        for i in range(panel_height):
            buffer_idx = self.window_y + i
            if buffer_idx < total_lines:
                line_to_draw = self.buffer[buffer_idx].replace('\t', '    ')
                window.addstr(i+1, 1, f"{buffer_idx+1:<{gutter_width}} | {line_to_draw}"[:panel_width-2])
        cursor_y, cursor_x = self.y - self.window_y + 1, self.x + gutter_width + 3 + (self.buffer[self.y][:self.x].count('\t') * 3)
        if 1 <= cursor_y < panel_height + 1: window.move(cursor_y, cursor_x)

def draw_panel(window, title, color_pair):
    window.erase(); window.border(); window.addstr(0, 2, f" {title} ", color_pair)

# ---------------------------------------------------------------------
# 3. MAIN FUNCTION with NON-BLOCKING "GAME LOOP" (ONLY THIS IS MODIFIED)
# ---------------------------------------------------------------------
def main(stdscr, file_data):
    # --- SETUP: Use non-blocking input ---
    stdscr.nodelay(True)
    stdscr.keypad(True)
    curses.curs_set(0)
    curses.start_color()
    curses.init_pair(1,curses.COLOR_CYAN,curses.COLOR_BLACK); curses.init_pair(2,curses.COLOR_WHITE,curses.COLOR_BLACK)
    curses.init_pair(3,curses.COLOR_GREEN,curses.COLOR_BLACK); curses.init_pair(4,curses.COLOR_RED,curses.COLOR_BLACK)
    curses.init_pair(5,curses.COLOR_BLACK,curses.COLOR_CYAN); curses.init_pair(6,curses.COLOR_BLACK,curses.COLOR_YELLOW)
    
    state = {"active_panel": "files", "selected_file_idx": 0, "selected_chunk_idx": 0, "scroll_pos": {"files": 0, "chunks": 0}}
    active_file_idx = 0
    editor = Editor(file_data[active_file_idx]["buffer"])
    
    save_message, save_message_time = "", 0

    while True:
        # --- INPUT HANDLING ---
        key = stdscr.getch()

        # If no key is pressed, sleep and continue. THIS IS THE FIX FOR FREEZING.
        if key == curses.ERR:
            time.sleep(0.01)
        else:
            # --- PROCESS GLOBAL KEYS ---
            if key == 17: # Ctrl+Q
                break
            elif key == curses.KEY_RESIZE:
                pass # The loop will handle redrawing automatically
            elif key == 19: # Ctrl+S
                try:
                    with open(file_data[active_file_idx]['filepath'], 'w', encoding='utf-8') as f:
                        f.write('\n'.join(editor.buffer))
                    file_data[active_file_idx]["original_buffer"] = list(editor.buffer)
                    save_message, save_message_time = "Successfully saved!", time.time()
                except Exception as e:
                    save_message, save_message_time = f"ERROR: {e}", time.time()
            elif key == ord('\t'):
                state["active_panel"] = ["files", "editor", "chunks"][(["files", "editor", "chunks"].index(state["active_panel"]) + 1) % 3]
            
            # --- PROCESS PANEL-SPECIFIC KEYS ---
            else:
                panel_height = stdscr.getmaxyx()[0] - 3
                if state["active_panel"] == "files":
                    if key in [curses.KEY_UP, curses.KEY_DOWN]:
                        state["selected_file_idx"] = max(0, min(len(file_data) - 1, state["selected_file_idx"] + (-1 if key == curses.KEY_UP else 1)))
                    elif key in [curses.KEY_ENTER, 10]:
                        file_data[active_file_idx]["buffer"] = list(editor.buffer)
                        active_file_idx = state["selected_file_idx"]
                        state["selected_chunk_idx"] = 0
                        editor = Editor(file_data[active_file_idx]["buffer"])
                elif state["active_panel"] == "chunks":
                    active_chunks = file_data[active_file_idx]["chunks"]
                    if key in [curses.KEY_UP, curses.KEY_DOWN]:
                        state["selected_chunk_idx"] = max(0, min(len(active_chunks) - 1, state["selected_chunk_idx"] + (-1 if key == curses.KEY_UP else 1)))
                    elif key in [curses.KEY_ENTER, 10] and active_chunks:
                        chunk = active_chunks[state["selected_chunk_idx"]]
                        editor.insert_chunk(chunk["code"])
                elif state["active_panel"] == "editor":
                    editor.handle_input(key, panel_height)

        # --- DRAWING AND REFRESH LOGIC (runs every loop) ---
        stdscr.erase()
        screen_height, screen_width = stdscr.getmaxyx()
        panel_height = screen_height - 3
        
        l_w, r_w = int(screen_width * 0.25), int(screen_width * 0.25); c_w = screen_width - l_w - r_w
        l_p = stdscr.derwin(screen_height - 1, l_w, 1, 0)
        c_p = stdscr.derwin(screen_height - 1, c_w, 1, l_w)
        r_p = stdscr.derwin(screen_height - 1, r_w, 1, l_w + c_w)

        # Draw status bar with save feedback
        unsaved_changes = editor.buffer != file_data[active_file_idx]["original_buffer"]
        status = "Arrows:Nav|Enter:Select|Tab:Panels|Ctrl+S:Save|Ctrl+Q:Quit"
        if state["active_panel"] == "editor": status = "EDIT MODE|Arrows:Cursor|PgUp/PgDn:Scroll|Tab to Exit"
        if unsaved_changes: status += " [UNSAVED*]"
        if save_message and time.time() - save_message_time < 2:
            stdscr.addstr(0, 0, save_message.ljust(screen_width), curses.color_pair(3))
        else:
            save_message = ""; stdscr.addstr(0, 0, status.ljust(screen_width), curses.color_pair(6))

        # Draw panels
        draw_panel(l_p, "Files", curses.color_pair(1) if state["active_panel"] == "files" else 2)
        draw_panel(c_p, f"Editor: {os.path.basename(file_data[active_file_idx]['filepath'])}", curses.color_pair(1) if state["active_panel"] == "editor" else 2)
        draw_panel(r_p, "Chunks", curses.color_pair(1) if state["active_panel"] == "chunks" else 2)
        
        # Draw panel content
        for i in range(panel_height):
            idx = state["scroll_pos"]["files"] + i
            if idx < len(file_data): l_p.addstr(i + 1, 1, os.path.basename(file_data[idx]['filepath']).ljust(l_w - 2)[:l_w - 2], curses.color_pair(5) if idx == state["selected_file_idx"] else 2)
        
        editor.draw(c_p)
        
        active_chunks = file_data[active_file_idx]["chunks"]; chunk_draw_list = []
        for i, c in enumerate(active_chunks):
            h_style = curses.color_pair(5) if i == state["selected_chunk_idx"] and state["active_panel"] == "chunks" else (curses.color_pair(3) if c["action"] == "Added" else 4)
            chunk_draw_list.append((f"Chunk {i+1}: {c['action']} ({c['lines']})", h_style)); chunk_draw_list.extend([(f"  > {l}", 2) for l in c['code'].split('\n')[:3]]); chunk_draw_list.append(("", 2))
        for i in range(panel_height):
            idx = state["scroll_pos"]["chunks"] + i
            if idx < len(chunk_draw_list): line, style = chunk_draw_list[idx]; r_p.addstr(i + 1, 1, line[:r_w - 2], style)
        
        curses.curs_set(1 if state["active_panel"] == "editor" else 0)
        stdscr.refresh(); l_p.refresh(); c_p.refresh(); r_p.refresh()

if __name__ == "__main__":
    report_data = parse_report(MUD_REPORT_PATH)
    if not report_data: print("Exiting: No data parsed from the report."); exit()
    file_list_for_tui = prepare_file_data(report_data)
    if not file_list_for_tui: print("Exiting: No files from report were found."); exit()
    curses.wrapper(main, file_data=file_list_for_tui)
    print("TUI exited gracefully.")
