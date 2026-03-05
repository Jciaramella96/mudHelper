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
                    # We will manage content as a list of strings (the buffer)
                    files_to_launch.append({"filepath": correct_path, "buffer": content.split('\n'), "chunks": report_data[original_full_path]})
                except Exception: continue
    return files_to_launch

# ---------------------------------------------------------------------
# 2. NEW ARCHITECTURE: Classes for Cursor and Window
# ---------------------------------------------------------------------

class Cursor:
    def __init__(self, y=0, x=0): self.y, self.x = y, x

class EditorWindow:
    def __init__(self, y=0): self.y = y # Only vertical scroll for now

    def scroll(self, cursor, height):
        if cursor.y < self.y: self.y = cursor.y
        if cursor.y >= self.y + height: self.y = cursor.y - height + 1

# ---------------------------------------------------------------------
# 3. THE MAIN APPLICATION
# ---------------------------------------------------------------------

def draw_panel(window, title, color_pair):
    window.erase(); window.border(); window.addstr(0, 2, f" {title} ", color_pair)

def main(stdscr, file_data):
    curses.curs_set(0); stdscr.nodelay(True); stdscr.keypad(True)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK); curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK); curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_CYAN); curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    
    state = { "active_panel": "files", "selected_file_idx": 0, "selected_chunk_idx": 0,
              "scroll_pos": {"files": 0, "chunks": 0}, "unsaved_changes": False }
    
    # Editor-specific state using the new classes
    active_file_idx = 0
    buffer = file_data[active_file_idx]["buffer"]
    cursor = Cursor()
    editor_window = EditorWindow()

    while True:
        screen_height, screen_width = stdscr.getmaxyx(); panel_height = screen_height - 3
        if screen_width < 20: stdscr.erase(); stdscr.addstr(0,0,"Window too narrow!"); stdscr.refresh(); time.sleep(0.1); continue

        l_w, r_w = int(screen_width*0.25), int(screen_width*0.25); c_w = screen_width - l_w - r_w
        l_p, c_p, r_p = stdscr.derwin(screen_height-1,l_w,1,0), stdscr.derwin(screen_height-1,c_w,1,l_w), stdscr.derwin(screen_height-1,r_w,1,l_w+c_w)
        
        status_text = "Arrows: Navigate | Enter: Select/Edit | Tab: Switch | Ctrl+S: Save | Ctrl+Q: Quit"
        if state["active_panel"] == "editor": status_text = "EDIT MODE | Arrows: Cursor | PgUp/PgDn: Scroll | Tab to Exit"
        if state["unsaved_changes"]: status_text += " [UNSAVED*]"
        stdscr.addstr(0, 0, status_text.ljust(screen_width), curses.color_pair(6))

        draw_panel(l_p, "Files", curses.color_pair(1) if state["active_panel"] == "files" else curses.color_pair(2))
        draw_panel(c_p, f"Editor: {os.path.basename(file_data[active_file_idx]['filepath'])}", curses.color_pair(1) if state["active_panel"] == "editor" else curses.color_pair(2))
        draw_panel(r_p, "Chunks", curses.color_pair(1) if state["active_panel"] == "chunks" else curses.color_pair(2))
        
        # Left Panel (Files)
        for i in range(panel_height):
            idx=state["scroll_pos"]["files"]+i;
            if idx<len(file_data):l_p.addstr(i+1,1,os.path.basename(file_data[idx]['filepath']).ljust(l_w-2)[:l_w-2],curses.color_pair(5)if idx==state["selected_file_idx"]else curses.color_pair(2))
        
        # Center Panel (Editor) - uses the robust class-based logic
        total_lines = len(buffer); gutter_width = max(4,math.ceil(math.log10(total_lines+1))if total_lines>0 else 4)
        for i in range(panel_height):
            idx=editor_window.y+i
            if idx<total_lines:c_p.addstr(i+1,1,f"{idx+1:{gutter_width}d} | {buffer[idx]}"[:c_w-2],curses.color_pair(2))

        # Right Panel (Chunks)
        active_chunks = file_data[active_file_idx]["chunks"]; chunk_draw_list=[]
        for i,c in enumerate(active_chunks):
            header_style=curses.color_pair(5)if i==state["selected_chunk_idx"]and state["active_panel"]=="chunks"else(curses.color_pair(3)if c["action"]=="Added"else curses.color_pair(4))
            chunk_draw_list.append((f"Chunk {i+1}: {c['action']} ({c['lines']})",header_style))
            chunk_draw_list.extend([(f"  > {l}",curses.color_pair(2))for l in c['code'].split('\n')[:3]]);chunk_draw_list.append(("",curses.color_pair(2)))
        for i in range(panel_height):
            idx=state["scroll_pos"]["chunks"]+i
            if idx<len(chunk_draw_list):line,style=chunk_draw_list[idx];r_p.addstr(i+1,1,line[:r_w-2],style)
        
        # Cursor and Refresh Logic
        if state["active_panel"] == "editor":
            curses.curs_set(1)
            c_p.move(cursor.y - editor_window.y + 1, cursor.x + gutter_width + 3)
        else:
            curses.curs_set(0)
        stdscr.refresh();l_p.refresh();c_p.refresh();r_p.refresh()

        # Input Handling
        key = stdscr.getch()
        if key == 17: break # Ctrl+Q
        if key == -1: continue

        if key == 19: # Ctrl+S
            file_data[active_file_idx]["buffer"] = buffer
            with open(file_data[active_file_idx]["filepath"], 'w', encoding='utf-8') as f: f.write('\n'.join(buffer))
            state["unsaved_changes"] = False
        elif key == ord('\t'):
            state["active_panel"] = ["files", "editor", "chunks"][(["files", "editor", "chunks"].index(state["active_panel"]) + 1) % 3]
        
        elif state["active_panel"] == "files":
            delta=-1 if key==curses.KEY_UP else 1
            if key in[curses.KEY_UP,curses.KEY_DOWN]:state["selected_file_idx"]=max(0,min(len(file_data)-1,state["selected_file_idx"]+delta))
            elif key in[curses.KEY_ENTER,10]:
                active_file_idx, state["selected_chunk_idx"] = state["selected_file_idx"], 0
                buffer = file_data[active_file_idx]["buffer"]
                cursor, editor_window = Cursor(), EditorWindow()
        
        elif state["active_panel"] == "chunks":
            delta=-1 if key==curses.KEY_UP else 1
            if key in[curses.KEY_UP,curses.KEY_DOWN]:state["selected_chunk_idx"]=max(0,min(len(active_chunks)-1,state["selected_chunk_idx"]+delta))
            elif key in[curses.KEY_ENTER,10]:
                chunk = active_chunks[state["selected_chunk_idx"]]
                if chunk["action"] == "Added":
                    header, footer = f"# {'-'*10} insert from {COMPILE_ID} {'-'*10}", f"# {'-'*10} end insert {'-'*10}"
                    block = [header] + chunk["code"].split('\n') + [footer]
                    buffer[cursor.y:cursor.y] = block; state["unsaved_changes"]=True
        
        elif state["active_panel"] == "editor":
            is_backspace=key in[curses.KEY_BACKSPACE,127,8]
            if key in[curses.KEY_UP,curses.KEY_DOWN,curses.KEY_LEFT,curses.KEY_RIGHT]: cursor.move(key,buffer)
            elif key==curses.KEY_PPAGE: cursor.y=max(0,cursor.y-panel_height)
            elif key==curses.KEY_NPAGE: cursor.y=min(len(buffer)-1,cursor.y+panel_height)
            elif is_backspace:
                state["unsaved_changes"]=True
                if cursor.x>0:buffer[cursor.y]=buffer[cursor.y][:cursor.x-1]+buffer[cursor.y][cursor.x:];cursor.move(curses.KEY_LEFT,buffer)
                elif cursor.y>0:
                    prev_len=len(buffer[cursor.y-1]);buffer[cursor.y-1]+=buffer[cursor.y];del buffer[cursor.y];cursor.move(curses.KEY_UP,buffer);cursor.x=prev_len
            elif key==10: # Enter
                state["unsaved_changes"]=True
                line_rest=buffer[cursor.y][cursor.x:];buffer[cursor.y]=buffer[cursor.y][:cursor.x]
                buffer.insert(cursor.y+1,line_rest);cursor.move(curses.KEY_DOWN,buffer);cursor.x=0
            elif 32<=key<=126:
                state["unsaved_changes"]=True;buffer[cursor.y]=buffer[cursor.y][:cursor.x]+chr(key)+buffer[cursor.y][cursor.x:];cursor.move(curses.KEY_RIGHT,buffer)
            
            editor_window.scroll(cursor, panel_height)

if __name__ == "__main__":
    report_data = parse_report(MUD_REPORT_PATH)
    if not report_data: print("Exiting: No data parsed from the report."); exit()
    file_list_for_tui = prepare_file_data(report_data)
    if not file_list_for_tui: print("Exiting: No files from report were found."); exit()
    curses.wrapper(main, file_data=file_list_for_tui)
    print("TUI exited gracefully.")

