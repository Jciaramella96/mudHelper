import curses
import os
import re

# --- Configuration ---
REPO_SEARCH_PATH = "/path/to/your/repo"  # <--- IMPORTANT: SET THIS
MUD_REPORT_PATH = "/path/to/your/rc.diff" # <--- IMPORTANT: SET THIS
COMPILE_ID = "12345" # Placeholder for now

# ---------------------------------------------------------------------
# 1. CORE PARSING LOGIC (Identical to before)
# ---------------------------------------------------------------------

def parse_report(report_path):
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

def draw_panel(window, title):
    """Draws a border and title on a curses window."""
    window.erase()
    window.border()
    window.addstr(0, 2, f" {title} ")

def main(stdscr, file_data):
    """The main function for the curses application."""
    # Initialization
    curses.curs_set(0) # Hide the cursor
    stdscr.nodelay(True) # Don't block waiting for input
    stdscr.keypad(True) # Enable keypad mode for arrow keys etc.

    # Setup Colors
    curses.start_color()
    curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK) # Border/Title
    curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK) # Normal Text
    curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK) # Added Chunk
    curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK) # Removed Chunk

    # Get screen dimensions
    screen_height, screen_width = stdscr.getmaxyx()

    # Define panel dimensions
    left_panel_width = int(screen_width * 0.25)
    right_panel_width = int(screen_width * 0.25)
    center_panel_width = screen_width - left_panel_width - right_panel_width
    
    # Create windows for each panel
    left_panel = stdscr.derwin(screen_height - 1, left_panel_width, 1, 0)
    center_panel = stdscr.derwin(screen_height - 1, center_panel_width, 1, left_panel_width)
    right_panel = stdscr.derwin(screen_height - 1, right_panel_width, 1, left_panel_width + center_panel_width)

    # --- For this first step, we'll just use the first file ---
    current_file = file_data[0] if file_data else None

    # Main application loop (for now, it just draws once and waits for 'q')
    while True:
        # Draw the base UI
        stdscr.addstr(0, 0, "File Editor TUI - Press 'q' to quit", curses.color_pair(1))
        draw_panel(left_panel, "Files")
        draw_panel(center_panel, f"Editor: {os.path.basename(current_file['filepath']) if current_file else 'No file'}")
        draw_panel(right_panel, "Code Chunks")

        # --- Populate Left Panel (Files) ---
        y = 1
        for i, file_item in enumerate(file_data):
            if y < screen_height - 2:
                filename = os.path.basename(file_item['filepath'])
                left_panel.addstr(y, 1, f" {i+1}: {filename[:left_panel_width-4]}", curses.color_pair(2))
                y += 1
        
        # --- Populate Center Panel (Editor) ---
        if current_file:
            lines = current_file['content'].split('\n')
            for i, line in enumerate(lines):
                if i + 1 < screen_height - 2:
                    # Add line numbers
                    display_line = f"{i+1:4d} | {line}"
                    center_panel.addstr(i + 1, 1, display_line[:center_panel_width-2], curses.color_pair(2))
        
        # --- Populate Right Panel (Chunks) ---
        if current_file:
            y = 1
            for i, chunk in enumerate(current_file['chunks']):
                if y >= screen_height - 2: break
                
                action = chunk['action']
                color = curses.color_pair(3) if action == "Added" else curses.color_pair(4)
                
                right_panel.addstr(y, 1, f"Chunk {i+1}: {action}", color)
                y += 1
                
                # Display first few lines of the chunk
                for line in chunk['code'].split('\n')[:3]:
                    if y >= screen_height - 3: break
                    right_panel.addstr(y, 2, f"> {line[:right_panel_width-5]}", curses.color_pair(2))
                    y += 1
                y += 1 # Add a blank line between chunks

        # Refresh the screen to show changes
        stdscr.refresh()
        left_panel.refresh()
        center_panel.refresh()
        right_panel.refresh()
        
        # Wait for user input
        key = stdscr.getch()
        if key == ord('q'):
            break

# ---------------------------------------------------------------------
# 3. MAIN EXECUTION BLOCK
# ---------------------------------------------------------------------

if __name__ == "__main__":
    report_data = parse_report(MUD_REPORT_PATH)
    if not report_data:
        print("Exiting: No data parsed from the report."); exit()

    file_list_for_tui = prepare_file_data(report_data)
    if not file_list_for_tui:
        print("Exiting: No files from the report were found in the repository."); exit()

    # curses.wrapper handles all the terminal setup and teardown for us
    curses.wrapper(main, file_data=file_list_for_tui)
