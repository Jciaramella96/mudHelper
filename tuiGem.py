import curses
import curses.textpad
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
                    files_to_launch.append({"filepath": correct_path, "content": content, "chunks": report_data[original_full_path]})
                except Exception: continue
    return files_to_launch

# ---------------------------------------------------------------------
# 2. THE CURSES TUI APPLICATION
# ---------------------------------------------------------------------

def draw_panel(window, title, color_pair):
    window.erase(); window.border(); window.addstr(0, 2, f" {title} ", color_pair)

def main(stdscr, file_data):
    # This will hold the content if we decide to save
    final_content_to_save = None
    
    curses.curs_set(1); stdscr.nodelay(False); stdscr.keypad(True)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_YELLOW)

    # For this simplified example, we'll just edit the first file.
    # A full implementation would let you choose a file first.
    if not file_data:
        return

    active_file = file_data[0]
    screen_height, screen_width = stdscr.getmaxyx()
    
    # Create the editing window
    edit_win = stdscr.derwin(screen_height - 2, screen_width - 2, 1, 1)
    edit_win.border()
    
    # Put the initial file content into the window
    for i, line in enumerate(active_file['content'].split('\n')):
        if i < screen_height - 3:
            edit_win.addstr(i + 1, 1, line)
    
    stdscr.addstr(0, 1, f"EDITING: {os.path.basename(active_file['filepath'])} | Ctrl+S to Save & Exit | Ctrl+G to Exit without Saving", curses.color_pair(6))
    stdscr.refresh()

    # --- THE NEW ARCHITECTURE ---
    # 1. Create the Textbox widget associated with our window
    box = curses.textpad.Textbox(edit_win, insert_mode=True)

    # 2. Define the validator to intercept keystrokes
    def validator(ch):
        # The Ctrl+S save command
        if ch == 19: # ASCII for Ctrl+S
            return curses.ascii.BEL # Signal to stop editing
        # The Ctrl+G quit command
        if ch == 7: # ASCII for Ctrl+G (bell)
            return curses.ascii.BEL # Also signal to stop, but we'll handle it differently
        # Allow all other keys
        return ch

    # 3. Start the editing loop. This blocks until the validator returns BEL.
    # The 'box.edit()' method handles all cursor movement, typing, and backspacing.
    content = box.edit(validator)

    # 4. After the loop ends, decide whether to save.
    # We check the last key pressed to see if it was our save command.
    last_key = stdscr.getch() # This might catch the final key if needed
    
    # This is a simple check. If the user quits via Ctrl+S, the intent is to save.
    # In a real app, you might use a more complex state-passing mechanism.
    # For now, we assume if the content changed, and user didn't explicitly cancel, they meant to save.
    # A simple way to check is if the exit key was BEL from Ctrl-S
    # This part is tricky as `edit` consumes the key. A simple heuristic:
    # If we exited, let's assume we want to save unless we add a specific cancel state.
    # Let's refine: We will only save if the exit key was explicitly Ctrl+S.
    # But since `edit` consumes it, we'll set a global flag inside the validator.
    
    # A better approach: The validator sets a flag, then returns BEL.
    # Let's make the main function scope accessible to the validator.
    nonlocal final_content_to_save
    
    # Re-define validator with access to outer scope
    should_save = False
    def better_validator(ch):
        nonlocal should_save
        if ch == 19: # Ctrl+S
            should_save = True
            return curses.ascii.BEL
        if ch == 7: # Ctrl+G
            should_save = False
            return curses.ascii.BEL
        return ch

    # We need to re-run the edit with the better validator.
    # The previous `box.edit` was just for demonstration of the flow.
    # In a real app, you'd only have the second one.
    
    # Reset window content before re-editing
    edit_win.erase()
    edit_win.border()
    for i, line in enumerate(active_file['content'].split('\n')):
        if i < screen_height - 3:
            edit_win.addstr(i + 1, 1, line)
    edit_win.refresh()

    content = box.edit(better_validator)

    if should_save:
        final_content_to_save = content.strip()

    # The curses.wrapper will now exit and restore the terminal
    return active_file['filepath'], final_content_to_save


if __name__ == "__main__":
    report_data = parse_report(MUD_REPORT_PATH)
    if not report_data:
        print("Exiting: No data parsed from the report.")
        exit()

    file_list_for_tui = prepare_file_data(report_data)
    if not file_list_for_tui:
        print("Exiting: No files from report were found.")
        exit()

    # --- THE FINAL STEP: Separate UI from I/O ---
    filepath_to_save, content_to_save = curses.wrapper(main, file_data=file_list_for_tui)

    # 5. After the TUI has completely shut down, perform the file write.
    if content_to_save is not None:
        try:
            with open(filepath_to_save, 'w', encoding='utf-8') as f:
                f.write(content_to_save)
            print(f"\n✅ File saved successfully: {filepath_to_save}")
        except Exception as e:
            print(f"\n❌ Error saving file: {e}")
    else:
        print("\n🚫 Save cancelled. No changes were written to disk.")

