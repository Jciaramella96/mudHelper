import curses
import curses.textpad
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
                    files_to_launch.append({"filepath": correct_path, "content": content, "chunks": report_data[original_full_path], "saved_content": content})
                except Exception: continue
    return files_to_launch

# ---------------------------------------------------------------------
# 2. THE CURSES TUI APPLICATION
# ---------------------------------------------------------------------

def draw_panel(window, title, color_pair):
    window.erase(); window.border(); window.addstr(0, 2, f" {title} ", color_pair)

def edit_mode(stdscr, content, filepath):
    """Function to handle editing within a Textbox."""
    screen_height, screen_width = stdscr.getmaxyx()
    edit_win = curses.newwin(screen_height - 2, screen_width - 2, 1, 1)
    
    # THE FIX: Use a mutable dictionary for the exit status
    exit_status = {'save': False}
    
    def validator(ch):
        if ch == 19: # Ctrl+S
            exit_status['save'] = True
            return curses.ascii.BEL # Signal to exit
        if ch == 7: # Ctrl+G
            exit_status['save'] = False
            return curses.ascii.BEL # Signal to exit
        return ch

    stdscr.erase()
    stdscr.addstr(0, 0, f"EDITING: {os.path.basename(filepath)} | Ctrl+S to Save & Exit Edit Mode | Ctrl+G to Cancel".ljust(screen_width), curses.color_pair(6))
    stdscr.refresh()

    # Populate the window before creating the textbox
    for i, line in enumerate(content.split('\n')):
        if i < screen_height - 3:
            edit_win.addstr(i + 1, 1, line)
    edit_win.refresh()
    
    box = curses.textpad.Textbox(edit_win, insert_mode=True)
    
    # This call blocks until the validator signals an exit
    new_content = box.edit(validator)
    
    if exit_status['save']:
        return new_content.strip()
    else:
        return None # Indicate that no save should happen

def main(stdscr, file_data):
    curses.curs_set(0); stdscr.nodelay(True); stdscr.keypad(True)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK); curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK); curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_CYAN); curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    
    state = { "file_data": file_data, "active_panel": "files", "active_file_idx": 0, "selected_file_idx": 0,
              "selected_chunk_idx": 0, "scroll_pos": {"files": 0, "editor": 0, "chunks": 0} }

    while True:
        screen_height, screen_width = stdscr.getmaxyx(); panel_height = screen_height - 3
        if screen_width < 20: stdscr.erase(); stdscr.addstr(0,0,"Window too narrow!"); stdscr.refresh(); time.sleep(0.1); continue

        l_w, r_w = int(screen_width*0.25), int(screen_width*0.25); c_w = screen_width - l_w - r_w
        l_p, c_p, r_p = stdscr.derwin(screen_height-1,l_w,1,0), stdscr.derwin(screen_height-1,c_w,1,l_w), stdscr.derwin(screen_height-1,r_w,1,l_w+c_w)
        
        status_text = "Arrows: Navigate | Enter: Select/Edit | Tab: Switch | Ctrl+Q: Quit"
        stdscr.addstr(0, 0, status_text.ljust(screen_width), curses.color_pair(6))

        active_file = state["file_data"][state["active_file_idx"]]
        draw_panel(l_p, "Files", curses.color_pair(1) if state["active_panel"] == "files" else curses.color_pair(2))
        draw_panel(c_p, f"Editor: {os.path.basename(active_file['filepath'])}", curses.color_pair(1) if state["active_panel"] == "editor" else curses.color_pair(2))
        draw_panel(r_p, "Chunks", curses.color_pair(1) if state["active_panel"] == "chunks" else curses.color_pair(2))
        
        for i in range(panel_height):
            idx = state["scroll_pos"]["files"]+i;
            if idx<len(state["file_data"]):l_p.addstr(i+1,1,os.path.basename(state["file_data"][idx]['filepath']).ljust(l_w-2)[:l_w-2],curses.color_pair(5)if idx==state["selected_file_idx"]else curses.color_pair(2))
        
        editor_content = active_file["content"].split('\n')
        total_lines = len(editor_content); gutter_width = max(4,math.ceil(math.log10(total_lines+1))if total_lines>0 else 4)
        for i in range(panel_height):
            idx=state["scroll_pos"]["editor"]+i;
            if idx<total_lines:c_p.addstr(i+1,1,f"{idx+1:{gutter_width}d} | {editor_content[idx]}"[:c_w-2],curses.color_pair(2))

        chunk_draw_list=[]
        for i,c in enumerate(active_file["chunks"]):
            header_style=curses.color_pair(5)if i==state["selected_chunk_idx"]and state["active_panel"]=="chunks"else(curses.color_pair(3)if c["action"]=="Added"else curses.color_pair(4))
            chunk_draw_list.append((f"Chunk {i+1}: {c['action']} (Lines: {c['lines']})",header_style))
            chunk_draw_list.extend([(f"  > {l}",curses.color_pair(2))for l in c['code'].split('\n')[:3]]);chunk_draw_list.append(("",curses.color_pair(2)))
        for i in range(panel_height):
            idx=state["scroll_pos"]["chunks"]+i;
            if idx<len(chunk_draw_list):line,style=chunk_draw_list[idx];r_p.addstr(i+1,1,line[:r_w-2],style)

        stdscr.refresh();l_p.refresh();c_p.refresh();r_p.refresh()

        key=stdscr.getch()
        if key==17:break # Ctrl+Q to quit
        if key==-1:continue

        if key==ord('\t'):state["active_panel"]=["files","editor","chunks"][(["files","editor","chunks"].index(state["active_panel"])+1)%3]
        
        ap=state["active_panel"]
        if ap=="files":
            delta=-1 if key==curses.KEY_UP else 1
            if key in[curses.KEY_UP,curses.KEY_DOWN]:state["selected_file_idx"]=max(0,min(len(file_data)-1,state["selected_file_idx"]+delta))
            elif key in[curses.KEY_ENTER,10]:state["active_file_idx"]=state["selected_file_idx"];state["scroll_pos"]["editor"],state["scroll_pos"]["chunks"],state["selected_chunk_idx"]=0,0,0
        elif ap=="chunks":
            delta=-1 if key==curses.KEY_UP else 1
            if key in[curses.KEY_UP,curses.KEY_DOWN]:state["selected_chunk_idx"]=max(0,min(len(active_file["chunks"])-1,state["selected_chunk_idx"]+delta))
        elif ap=="editor":
            if key in[curses.KEY_PPAGE,curses.KEY_NPAGE]:state["scroll_pos"]["editor"]=max(0,state["scroll_pos"]["editor"]+(-1 if key==curses.KEY_PPAGE else 1)*panel_height)
            elif key in[curses.KEY_ENTER,10]:
                # --- Enter Edit Mode ---
                new_content=edit_mode(stdscr,active_file["content"],active_file["filepath"])
                if new_content is not None:
                    active_file["content"]=new_content
                    # Save immediately to the file system as per the new architecture
                    with open(active_file["filepath"],'w',encoding='utf-8')as f:f.write(new_content)
                # After edit mode, clear the screen to force a full redraw
                stdscr.clear()

if __name__ == "__main__":
    report_data = parse_report(MUD_REPORT_PATH)
    if not report_data: print("Exiting: No data parsed from the report."); exit()
    file_list_for_tui = prepare_file_data(report_data)
    if not file_list_for_tui: print("Exiting: No files from report were found."); exit()
    curses.wrapper(main, file_data=file_list_for_tui)
    print("TUI exited gracefully.")

