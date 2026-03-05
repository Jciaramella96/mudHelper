import curses
import os
import re

# --- Configuration ---
REPO_SEARCH_PATH = "/path/to/your/repo"  # <--- IMPORTANT: SET THIS
MUD_REPORT_PATH = "/path/to/your/rc.diff" # <--- IMPORTANT: SET THIS
COMPILE_ID = "12345"

# ---------------------------------------------------------------------
# 1. CORE PARSING LOGIC (Unchanged and Correct)
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
              "selected_chunk_idx": 0, "scroll_pos": {"files": 0, "editor": 0, "chunks": 0}, "confirm_delete_line": -1 }

    while True:
        screen_height, screen_width = stdscr.getmaxyx(); panel_height = screen_height - 3
        l_w, r_w = int(screen_width*0.25), int(screen_width*0.25); c_w = screen_width - l_w - r_w
        l_p, c_p, r_p = stdscr.derwin(screen_height-1,l_w,1,0), stdscr.derwin(screen_height-1,c_w,1,l_w), stdscr.derwin(screen_height-1,r_w,1,l_w+c_w)
        
        status_bar = "Up/Down: Navigate | Enter: Select/Action | Tab: Switch | s: Save | u: Undo | q: Quit"
        if state["confirm_delete_line"] != -1: status_bar = f"Confirm deletion of text at line {state['confirm_delete_line'] + 1}? [y/n]"
        stdscr.addstr(0, 0, status_bar.ljust(screen_width), curses.color_pair(6))

        draw_panel(l_p, "Files", curses.color_pair(1) if state["active_panel"] == "files" else curses.color_pair(2))
        draw_panel(c_p, f"Editor: {os.path.basename(state['file_data'][state['active_file_idx']]['filepath'])}", curses.color_pair(1) if state["active_panel"] == "editor" else curses.color_pair(2))
        draw_panel(r_p, "Chunks", curses.color_pair(1) if state["active_panel"] == "chunks" else curses.color_pair(2))
        
        active_file = state["file_data"][state["active_file_idx"]]

        # --- Left Panel (Files) ---
        for i in range(panel_height):
            idx = state["scroll_pos"]["files"] + i
            if idx >= len(state["file_data"]): break
            style = curses.color_pair(5) if idx == state["selected_file_idx"] else curses.color_pair(2)
            l_p.addstr(i+1, 1, os.path.basename(state["file_data"][idx]['filepath']).ljust(l_w-2)[:l_w-2], style)

        # --- Center Panel (Editor) ---
        for i in range(panel_height):
            idx = state["scroll_pos"]["editor"] + i
            if idx >= len(active_file["content"]): break
            style = curses.color_pair(7) if state["confirm_delete_line"] != -1 and idx >= state["confirm_delete_line"] and idx < state["confirm_delete_line"] + state["delete_len"] else curses.color_pair(2)
            c_p.addstr(i+1, 1, f"{idx+1:4d} | {active_file['content'][idx]}"[:c_w-2], style)

        # --- THE FIX: Correctly build the list of lines to draw for the Chunks panel ---
        chunk_draw_list = []
        for i, chunk in enumerate(active_file["chunks"]):
            action_color = curses.color_pair(3) if chunk["action"] == "Added" else curses.color_pair(4)
            # Determine the style for the chunk header based on selection
            header_style = curses.color_pair(5) if i == state["selected_chunk_idx"] and state["active_panel"] == "chunks" else action_color
            
            chunk_draw_list.append( (f"Chunk {i+1}: {chunk['action']}", header_style) )
            for line in chunk['code'].split('\n'):
                chunk_draw_list.append( (f"  > {line}", curses.color_pair(2)) )
            chunk_draw_list.append( ("", curses.color_pair(2)) ) # Spacer

        for i in range(panel_height):
            idx = state["scroll_pos"]["chunks"] + i
            if idx >= len(chunk_draw_list): break
            line, style = chunk_draw_list[idx]
            r_p.addstr(i+1, 1, line[:r_w-2], style)

        stdscr.refresh(); l_p.refresh(); c_p.refresh(); r_p.refresh()

        key = stdscr.getch()
        if key == ord('q'): break
        
        if state["confirm_delete_line"] != -1:
            if key == ord('y'):
                start, length = state["confirm_delete_line"], state["delete_len"]
                active_file["backup_content"] = list(active_file["content"])
                del active_file["content"][start : start + length]
            state["confirm_delete_line"], state["delete_len"] = -1, 0
            continue

        if key == ord('\t'): state["active_panel"] = ["files", "editor", "chunks"][(["files", "editor", "chunks"].index(state["active_panel"]) + 1) % 3]
        elif key == ord('u'):
            if active_file["backup_content"]: active_file["content"] = active_file["backup_content"]; active_file["backup_content"] = None
        elif key == ord('s'):
            with open(active_file["filepath"], 'w', encoding='utf-8') as f: f.write('\n'.join(active_file["content"]))
            stdscr.addstr(0, screen_width - 10, "SAVED!".ljust(9), curses.color_pair(6))

        elif key in [curses.KEY_UP, curses.KEY_DOWN]:
            delta = -1 if key == curses.KEY_UP else 1
            if state["active_panel"] == "files":
                state["selected_file_idx"] = max(0, min(len(file_data)-1, state["selected_file_idx"]+delta))
                if state["selected_file_idx"] < state["scroll_pos"]["files"]: state["scroll_pos"]["files"] = state["selected_file_idx"]
                if state["selected_file_idx"] >= state["scroll_pos"]["files"]+panel_height: state["scroll_pos"]["files"] = state["selected_file_idx"]-panel_height+1
            elif state["active_panel"] == "chunks":
                 state["selected_chunk_idx"] = max(0, min(len(active_file["chunks"])-1, state["selected_chunk_idx"]+delta))
            else: state["scroll_pos"][state["active_panel"]] = max(0, state["scroll_pos"][state["active_panel"]]+delta)

        elif key in [curses.KEY_ENTER, 10]:
            if state["active_panel"] == "files":
                state["active_file_idx"] = state["selected_file_idx"]
                state["scroll_pos"]["editor"], state["scroll_pos"]["chunks"], state["selected_chunk_idx"] = 0, 0, 0
            elif state["active_panel"] == "chunks":
                selected_chunk = active_file["chunks"][state["selected_chunk_idx"]]
                if selected_chunk["action"] == "Added":
                    active_file["backup_content"] = list(active_file["content"])
                    header = [f"# {'-'*10} code insert from compile {COMPILE_ID} {'-'*10}"]
                    footer = [f"# {'-'*10} end insert from compile {COMPILE_ID} {'-'*10}"]
                    block_to_insert = header + selected_chunk["code"].split('\n') + footer
                    insertion_line = state["scroll_pos"]["editor"]
                    active_file["content"][insertion_line:insertion_line] = block_to_insert
                else: # Removed
                    match_line = find_text_robustly(active_file["content"], selected_chunk["code"])
                    if match_line != -1:
                        state["confirm_delete_line"] = match_line
                        state["delete_len"] = len(selected_chunk["code"].split('\n'))
                        state["scroll_pos"]["editor"] = max(0, match_line - 2)

if __name__ == "__main__":
    report_data = parse_report(MUD_REPORT_PATH)
    if not report_data: print("Exiting: No data parsed from the report."); exit()
    file_list_for_tui = prepare_file_data(report_data)
    if not file_list_for_tui: print("Exiting: No files from report were found."); exit()
    curses.wrapper(main, file_data=file_list_for_tui)
