import curses
import os
import re

# --- Configuration ---
REPO_SEARCH_PATH = "/path/to/your/repo"  # <--- IMPORTANT: SET THIS
MUD_REPORT_PATH = "/path/to/your/rc.diff" # <--- IMPORTANT: SET THIS
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
                    files_to_launch.append({"filepath": correct_path, "content": content.split('\n'), "chunks": report_data[original_full_path], "backup_content": None})
                except Exception: continue
    return files_to_launch

# ---------------------------------------------------------------------
# 2. THE CURSES TUI APPLICATION
# ---------------------------------------------------------------------

def draw_panel(window, title, color_pair):
    window.erase(); window.border(); window.addstr(0, 2, f" {title} ", color_pair)

def get_normalized_string(input_string):
    trimmed = input_string.strip()
    if trimmed.startswith("#"): return trimmed[1:].strip()
    return trimmed

def find_text_robustly(editor_lines, text_to_find):
    chunk_lines = [get_normalized_string(line) for line in text_to_find.split('\n')]
    for i in range(len(editor_lines) - len(chunk_lines) + 1):
        if get_normalized_string(editor_lines[i]) == chunk_lines[0]:
            is_full_match = all(get_normalized_string(editor_lines[i + j]) == chunk_lines[j] for j in range(1, len(chunk_lines)))
            if is_full_match: return i
    return -1

def main(stdscr, file_data):
    curses.curs_set(0); stdscr.nodelay(True); stdscr.keypad(True)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK); curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK); curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_CYAN); curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    curses.init_pair(7, curses.COLOR_YELLOW, curses.COLOR_BLACK)

    state = { "file_data": file_data, "active_panel": "files", "active_file_idx": 0, "selected_file_idx": 0,
              "selected_chunk_idx": 0, "scroll_pos": {"files": 0, "editor": 0, "chunks": 0}, 
              "cursor_pos": {"y": 0, "x": 0}, "confirm_delete_line": -1, "unsaved_changes": False }

    while True:
        screen_height, screen_width = stdscr.getmaxyx(); panel_height = screen_height - 3
        l_w, r_w = int(screen_width*0.25), int(screen_width*0.25); c_w = screen_width - l_w - r_w
        l_p, c_p, r_p = stdscr.derwin(screen_height-1,l_w,1,0), stdscr.derwin(screen_height-1,c_w,1,l_w), stdscr.derwin(screen_height-1,r_w,1,l_w+c_w)
        
        status_text = "Arrows: Navigate | Enter: Select | Tab: Panels | PgUp/PgDn: Scroll | Ctrl+S: Save | q: Quit"
        if state["active_panel"] == "editor": status_text = "EDIT MODE | Arrows: Move Cursor | PgUp/PgDn: Scroll Editor"
        if state["confirm_delete_line"] != -1: status_text = f"Confirm deletion at line {state['confirm_delete_line']+1}? [y/n]"
        if state["unsaved_changes"]: status_text += " [UNSAVED*]"
        stdscr.addstr(0, 0, status_text.ljust(screen_width), curses.color_pair(6))

        active_file = state["file_data"][state["active_file_idx"]]
        draw_panel(l_p, "Files", curses.color_pair(1) if state["active_panel"]=="files" else curses.color_pair(2))
        draw_panel(c_p, f"Editor: {os.path.basename(active_file['filepath'])}", curses.color_pair(1) if state["active_panel"]=="editor" else curses.color_pair(2))
        draw_panel(r_p, "Chunks", curses.color_pair(1) if state["active_panel"]=="chunks" else curses.color_pair(2))
        
        # --- Left Panel ---
        for i in range(panel_height):
            idx=state["scroll_pos"]["files"]+i; style=curses.color_pair(5) if idx==state["selected_file_idx"] else curses.color_pair(2)
            if idx<len(state["file_data"]): l_p.addstr(i+1,1,os.path.basename(state["file_data"][idx]['filepath']).ljust(l_w-2)[:l_w-2],style)
        
        # --- Center Panel ---
        for i in range(panel_height):
            idx=state["scroll_pos"]["editor"]+i
            if idx<len(active_file["content"]):
                style=curses.color_pair(7) if state["confirm_delete_line"]!=-1 and idx>=state["confirm_delete_line"] and idx<state["confirm_delete_line"]+state["delete_len"] else curses.color_pair(2)
                c_p.addstr(i+1,1,f"{idx+1:4d} | {active_file['content'][idx]}"[:c_w-2],style)

        # --- Right Panel ---
        chunk_lines=[];
        for i,c in enumerate(active_file["chunks"]): chunk_lines.append(((f"Chunk {i+1}: {c['action']}", curses.color_pair(3) if c["action"]=="Added" else curses.color_pair(4),i)))
        for i in range(panel_height):
            idx=state["scroll_pos"]["chunks"]+i
            if idx<len(chunk_lines):
                line,color,chunk_idx=chunk_lines[idx]
                style=curses.color_pair(5) if chunk_idx==state["selected_chunk_idx"] and state["active_panel"]=="chunks" else color
                r_p.addstr(i+1,1,line[:r_w-2],style)
        
        # --- Cursor Logic ---
        if state["active_panel"] == "editor":
            curses.curs_set(1)
            cursor_y = state["cursor_pos"]["y"] - state["scroll_pos"]["editor"] + 1
            cursor_x = state["cursor_pos"]["x"] + 8 # Account for line number gutter
            if 0 < cursor_y <= panel_height: c_p.move(cursor_y, cursor_x)
        else: curses.curs_set(0)

        stdscr.refresh();l_p.refresh();c_p.refresh();r_p.refresh()

        key=stdscr.getch()
        if key==ord('q'):break
        
        # --- Input Handling ---
        if state["confirm_delete_line"]!=-1:
            if key==ord('y'):
                start,length=state["confirm_delete_line"],state["delete_len"]
                active_file["backup_content"]=list(active_file["content"])
                del active_file["content"][start:start+length]
                state["unsaved_changes"]=True
            state["confirm_delete_line"],state["delete_len"]=-1,0
            continue
        
        # --- Ctrl+S for Saving ---
        if key == 19: # Ctrl+S
            with open(active_file["filepath"],'w',encoding='utf-8') as f: f.write('\n'.join(active_file["content"]))
            state["unsaved_changes"] = False
            continue

        if key==ord('\t'): state["active_panel"]=["files","editor","chunks"][(["files","editor","chunks"].index(state["active_panel"])+1)%3]
        elif key==ord('u'):
            if active_file["backup_content"]: active_file["content"]=active_file["backup_content"];active_file["backup_content"]=None; state["unsaved_changes"]=True

        elif key in [curses.KEY_UP,curses.KEY_DOWN,curses.KEY_LEFT,curses.KEY_RIGHT,curses.KEY_PPAGE,curses.KEY_NPAGE,curses.KEY_BACKSPACE,10,127] or (32<=key<=126):
            ap,delta=state["active_panel"],-1 if key in [curses.KEY_UP,curses.KEY_LEFT] else 1
            if ap=="files":
                state["selected_file_idx"]=max(0,min(len(file_data)-1,state["selected_file_idx"]+delta if key in [curses.KEY_UP,curses.KEY_DOWN] else 0))
                if state["selected_file_idx"]<state["scroll_pos"]["files"]:state["scroll_pos"]["files"]=state["selected_file_idx"]
                if state["selected_file_idx"]>=state["scroll_pos"]["files"]+panel_height:state["scroll_pos"]["files"]=state["selected_file_idx"]-panel_height+1
            elif ap=="chunks": state["selected_chunk_idx"]=max(0,min(len(active_file["chunks"])-1,state["selected_chunk_idx"]+delta if key in [curses.KEY_UP,curses.KEY_DOWN] else 0))
            elif ap=="editor":
                y,x=state["cursor_pos"]["y"],state["cursor_pos"]["x"]
                if key==curses.KEY_UP: state["cursor_pos"]["y"]=max(0,y-1)
                elif key==curses.KEY_DOWN: state["cursor_pos"]["y"]=min(len(active_file["content"])-1,y+1)
                elif key==curses.KEY_LEFT: state["cursor_pos"]["x"]=max(0,x-1)
                elif key==curses.KEY_RIGHT: state["cursor_pos"]["x"]=min(len(active_file["content"][y]),x+1)
                elif key in [curses.KEY_PPAGE,curses.KEY_NPAGE]: state["scroll_pos"]["editor"]=max(0,state["scroll_pos"]["editor"]+(delta*panel_height))
                # Text editing logic
                else:
                    state["unsaved_changes"]=True
                    if key in [curses.KEY_BACKSPACE,127]:
                        if x>0:active_file["content"][y]=active_file["content"][y][:x-1]+active_file["content"][y][x:];state["cursor_pos"]["x"]-=1
                        elif y>0:prev_len=len(active_file["content"][y-1]);del active_file["content"][y];state["cursor_pos"]["y"]-=1;state["cursor_pos"]["x"]=prev_len
                    elif key==10: # Enter
                        active_file["content"].insert(y+1,active_file["content"][y][x:]);active_file["content"][y]=active_file["content"][y][:x];state["cursor_pos"]["y"]+=1;state["cursor_pos"]["x"]=0
                    else: # Printable characters
                        active_file["content"][y]=active_file["content"][y][:x]+chr(key)+active_file["content"][y][x:];state["cursor_pos"]["x"]+=1
                # Ensure cursor x is not out of bounds
                state["cursor_pos"]["x"]=min(len(active_file["content"][state["cursor_pos"]["y"]]),state["cursor_pos"]["x"])
                # Auto-scroll editor with cursor
                if state["cursor_pos"]["y"]<state["scroll_pos"]["editor"]:state["scroll_pos"]["editor"]=state["cursor_pos"]["y"]
                if state["cursor_pos"]["y"]>=state["scroll_pos"]["editor"]+panel_height:state["scroll_pos"]["editor"]=state["cursor_pos"]["y"]-panel_height+1
        
        elif key in [curses.KEY_ENTER,10]:
            if state["active_panel"]=="files":
                if state["unsaved_changes"]: pass # Could add a "save changes?" prompt here in the future
                state["active_file_idx"]=state["selected_file_idx"];state["scroll_pos"]["editor"],state["scroll_pos"]["chunks"],state["selected_chunk_idx"],state["cursor_pos"]=0,0,0,{"y":0,"x":0};state["unsaved_changes"]=False
            elif state["active_panel"]=="chunks":
                chunk=active_file["chunks"][state["selected_chunk_idx"]]; state["unsaved_changes"]=True
                if chunk["action"]=="Added":
                    active_file["backup_content"]=list(active_file["content"])
                    header,footer=[f"# {'-'*10} code insert from compile {COMPILE_ID} {'-'*10}"]*2
                    block=header.split('\n')+chunk["code"].split('\n')+footer.split('\n')
                    active_file["content"][state["cursor_pos"]["y"]:state["cursor_pos"]["y"]]=block
                else: # Removed
                    line=find_text_robustly(active_file["content"],chunk["code"])
                    if line!=-1: state["confirm_delete_line"],state["delete_len"]=line,len(chunk["code"].split('\n'));state["scroll_pos"]["editor"]=max(0,line-2)

if __name__ == "__main__":
    report_data = parse_report(MUD_REPORT_PATH)
    if not report_data: print("Exiting: No data parsed from the report."); exit()
    file_list_for_tui = prepare_file_data(report_data)
    if not file_list_for_tui: print("Exiting: No files from report were found."); exit()
    curses.wrapper(main, file_data=file_list_for_tui)
