import curses
import os
import re

# --- Configuration ---
REPO_SEARCH_PATH = "/opt/osi/osi_cust"  # <--- IMPORTANT: SET THIS
MUD_REPORT_PATH = "./rc.diff" # <--- IMPORTANT: SET THIS
COMPILE_ID = "12345" # Placeholder

# ---------------------------------------------------------------------
# 1. CORE PARSING LOGIC (Unchanged)
# ---------------------------------------------------------------------

def parse_report(report_path):
    # ... (code is identical to previous version)
    all_edits = {}
    try:
        with open(report_path, 'r', encoding='utf-8') as f: report_content = f.read()
        file_sections = re.split(r'^(.+?\.(?:rc|py|sql|java|js|txt|c|cpp|h|cs|rb|go|sh|bat|ps1|yaml|yml|json|xml|html|css|php|ts|jsx|tsx|vue|swift|kt|rs|scala|lua|pl|r|dart|gradle|md):)\s*$', report_content, flags=re.MULTILINE)
        for i in range(1, len(file_sections), 2):
            if i + 1 >= len(file_sections): break
            current_filepath = file_sections[i].rstrip(':').strip()
            section_content = file_sections[i + 1]
            all_edits[current_filepath] = []
            chunk_pattern = r'(Added|Removed)\s*\(lines\s+(\d+-\d+)\):\s*\n((?:(?!(?:Added|Removed)\s*\(lines).)*)'
            chunk_matches = re.finditer(chunk_pattern, section_content, re.DOTALL)
            for match in chunk_matches:
                action, line_info, code_block = match.groups()
                if code_block.strip():
                    all_edits[current_filepath].append({"action": action, "lines": line_info, "code": code_block})
        return {k: v for k, v in all_edits.items() if v}
    except Exception: return None

def find_files_in_repo(filenames_to_find, repo_path):
    # ... (code is identical to previous version)
    found_map, repo_file_map = {}, {}
    for root, _, files in os.walk(repo_path):
        for name in files:
            if '.' in name:
                base_name = name.rsplit('.', 1)[0]
                full_path = os.path.join(root, name)
                if base_name not in repo_file_map: repo_file_map[base_name] = []
                repo_file_map[base_name].append(full_path)
    for report_filename in filenames_to_find:
        if report_filename in repo_file_map:
            found_map[report_filename] = repo_file_map[report_filename]
    return found_map

def prepare_file_data(report_data):
    # ... (code is identical to previous version)
    if not REPO_SEARCH_PATH or not os.path.isdir(REPO_SEARCH_PATH): return []
    filenames = [os.path.basename(p) for p in report_data.keys()]
    found_files_map = find_files_in_repo(filenames, REPO_SEARCH_PATH)
    files_to_launch, original_path_map = [], {os.path.basename(p): p for p in report_data.keys()}
    for filename, correct_paths_list in found_files_map.items():
        if original_full_path := original_path_map.get(filename):
            for correct_path in correct_paths_list:
                try:
                    with open(correct_path, 'r', encoding='utf-8') as f: content = f.read()
                    files_to_launch.append({"filepath": correct_path, "content": content, "chunks": report_data[original_full_path]})
                except Exception: continue
    return files_to_launch

# ---------------------------------------------------------------------
# 2. THE CURSES TUI APPLICATION
# ---------------------------------------------------------------------

def draw_panel(window, title, color_pair):
    """Draws a border and title on a curses window."""
    window.erase()
    window.border()
    window.addstr(0, 2, f" {title} ", color_pair)

def main(stdscr, file_data):
    """The main function for the curses application."""
    curses.curs_set(0); stdscr.nodelay(True); stdscr.keypad(True)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK) # Active Panel Title
    curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK) # Normal Text
    curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK) # Added Chunk
    curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)   # Removed Chunk
    curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_CYAN) # Highlighted Item
    curses.init_pair(6, curses.COLOR_YELLOW, curses.COLOR_BLACK) # Status Bar
    
    # --- NEW: State management ---
    state = {
        "file_data": file_data,
        "active_panel": "files", # files, editor, or chunks
        "active_file_idx": 0,    # The file currently loaded in the editor
        "selected_file_idx": 0,  # The file highlighted in the left panel
        "scroll_pos": {"files": 0, "editor": 0, "chunks": 0}
    }

    while True:
        screen_height, screen_width = stdscr.getmaxyx()
        
        # Define panel dimensions
        left_panel_width = int(screen_width * 0.25)
        right_panel_width = int(screen_width * 0.25)
        center_panel_width = screen_width - left_panel_width - right_panel_width
        
        # Create windows for each panel (must be done in loop for resizing)
        left_panel = stdscr.derwin(screen_height - 1, left_panel_width, 1, 0)
        center_panel = stdscr.derwin(screen_height - 1, center_panel_width, 1, left_panel_width)
        right_panel = stdscr.derwin(screen_height - 1, right_panel_width, 1, left_panel_width + center_panel_width)
        
        # Set active panel title color
        file_title_color = curses.color_pair(1) if state["active_panel"] == "files" else curses.color_pair(2)
        editor_title_color = curses.color_pair(1) if state["active_panel"] == "editor" else curses.color_pair(2)
        chunks_title_color = curses.color_pair(1) if state["active_panel"] == "chunks" else curses.color_pair(2)

        # Draw UI
        status_bar_text = "Navigate: Arrows | Load File: Enter | Switch Panels: Tab | Quit: q"
        stdscr.addstr(0, 0, status_bar_text.ljust(screen_width), curses.color_pair(6))
        draw_panel(left_panel, "Files", file_title_color)
        draw_panel(center_panel, f"Editor: {os.path.basename(state['file_data'][state['active_file_idx']]['filepath'])}", editor_title_color)
        draw_panel(right_panel, "Chunks", chunks_title_color)
        
        panel_height = screen_height - 3
        
        # --- Populate Left Panel (Files) ---
        scroll = state["scroll_pos"]["files"]
        for i in range(panel_height):
            idx = scroll + i
            if idx >= len(state["file_data"]): break
            filename = os.path.basename(state["file_data"][idx]['filepath'])
            style = curses.color_pair(5) if idx == state["selected_file_idx"] else curses.color_pair(2)
            left_panel.addstr(i + 1, 1, filename.ljust(left_panel_width-2)[:left_panel_width-2], style)

        # --- Populate Center Panel (Editor) ---
        active_file_content = state["file_data"][state["active_file_idx"]]["content"].split('\n')
        scroll = state["scroll_pos"]["editor"]
        for i in range(panel_height):
            idx = scroll + i
            if idx >= len(active_file_content): break
            line = active_file_content[idx]
            display_line = f"{idx+1:4d} | {line}"
            center_panel.addstr(i + 1, 1, display_line[:center_panel_width-2], curses.color_pair(2))

        # --- Populate Right Panel (Chunks) ---
        active_file_chunks = state["file_data"][state["active_file_idx"]]["chunks"]
        # This is more complex, so we'll build a list of lines to draw first
        chunk_draw_lines = []
        for i, chunk in enumerate(active_file_chunks):
            action = chunk['action']; color = curses.color_pair(3) if action == "Added" else curses.color_pair(4)
            chunk_draw_lines.append( (f"Chunk {i+1}: {action}", color) )
            for line in chunk['code'].split('\n'):
                chunk_draw_lines.append( (f"  > {line}", curses.color_pair(2)) )
            chunk_draw_lines.append( ("", curses.color_pair(2)) ) # Spacer

        scroll = state["scroll_pos"]["chunks"]
        for i in range(panel_height):
            idx = scroll + i
            if idx >= len(chunk_draw_lines): break
            line, color = chunk_draw_lines[idx]
            right_panel.addstr(i + 1, 1, line[:right_panel_width-2], color)

        # Refresh screens
        stdscr.refresh(); left_panel.refresh(); center_panel.refresh(); right_panel.refresh()

        # --- Handle Input ---
        key = stdscr.getch()
        if key == ord('q'): break
        
        if key == ord('\t'): # Tab
            panels = ["files", "editor", "chunks"]
            current_idx = panels.index(state["active_panel"])
            state["active_panel"] = panels[(current_idx + 1) % len(panels)]

        elif key == curses.KEY_UP:
            if state["active_panel"] == "files":
                state["selected_file_idx"] = max(0, state["selected_file_idx"] - 1)
                # Auto-scroll the view up
                if state["selected_file_idx"] < state["scroll_pos"]["files"]:
                    state["scroll_pos"]["files"] = state["selected_file_idx"]
            else:
                state["scroll_pos"][state["active_panel"]] = max(0, state["scroll_pos"][state["active_panel"]] - 1)

        elif key == curses.KEY_DOWN:
            active_panel = state["active_panel"]
            if active_panel == "files":
                state["selected_file_idx"] = min(len(file_data) - 1, state["selected_file_idx"] + 1)
                # Auto-scroll the view down
                if state["selected_file_idx"] >= state["scroll_pos"]["files"] + panel_height:
                    state["scroll_pos"]["files"] = state["selected_file_idx"] - panel_height + 1
            else:
                # A simple scroll for editor and chunks
                state["scroll_pos"][active_panel] += 1
        
        elif key == curses.KEY_ENTER or key == 10:
            if state["active_panel"] == "files":
                state["active_file_idx"] = state["selected_file_idx"]
                # Reset scroll positions when loading a new file
                state["scroll_pos"]["editor"] = 0
                state["scroll_pos"]["chunks"] = 0

# ---------------------------------------------------------------------
# 3. MAIN EXECUTION BLOCK
# ---------------------------------------------------------------------

if __name__ == "__main__":
    report_data = parse_report(MUD_REPORT_PATH)
    if not report_data: print("Exiting: No data parsed from the report."); exit()
    file_list_for_tui = prepare_file_data(report_data)
    if not file_list_for_tui: print("Exiting: No files from report were found."); exit()
    curses.wrapper(main, file_data=file_list_for_tui)
