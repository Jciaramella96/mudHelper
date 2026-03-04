import argparse
import os
import shutil
import re

def parse_arguments():
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(description="A command-line tool to apply changes to files from a text report.")
    parser.add_argument("report_file", help="Path to the text report file.")
    parser.add_argument("search_directory", help="Directory to search for files to modify.")
    parser.add_argument("--dry-run", action="store_true", help="List files that would be modified without making changes.")
    return parser.parse_args()

def parse_report(report_path):
    """
    A simple and robust line-by-line parser for the report file.
    """
    report = {}
    current_file = None
    
    # Regex to find "Added (lines X-Y)" or "Removed (lines X-Y)"
    action_regex = re.compile(r'^\s*(Added|Removed)\s*\([Ll]ines\s*(\d+)\s*-\s*(\d+)\s*\):', re.IGNORECASE)

    try:
        with open(report_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Report file not found at '{report_path}'")
        return {}

    i = 0
    while i < len(lines):
        line = lines[i]
        line_stripped = line.strip()

        # --- Rule 1: Is this line a new file path? ---
        if line_stripped.endswith(':') and not action_regex.match(line):
             # A simple check to ensure it's not a label within code
            if ' ' not in line_stripped:
                current_file = line_stripped.rstrip(':')
                if current_file not in report:
                    report[current_file] = []
                i += 1
                continue

        # --- Rule 2: Is this line an "Only in New" line? ---
        if line_stripped.startswith("Only in New:"):
            current_file = None # Invalidate current file to ignore subsequent blocks
            i += 1
            continue

        # --- Rule 3: Is this line an "Added" or "Removed" action? ---
        action_match = action_regex.match(line)
        if action_match and current_file:
            action_type = action_match.group(1).lower()
            start_line = int(action_match.group(2))
            end_line = int(action_match.group(3))
            
            i += 1 # Move to the first line of the content block
            
            # --- Capture the content block ---
            content_lines_raw = []
            while i < len(lines):
                # The block ends when we see a new file or a new action
                if lines[i].strip().endswith(':') and ' ' not in lines[i].strip():
                    break
                if action_regex.match(lines[i]):
                    break
                
                content_lines_raw.append(lines[i])
                i += 1

            # --- Process indentation ---
            if content_lines_raw:
                # Find the indentation of the first line that has actual text
                base_indent_len = -1
                for l in content_lines_raw:
                    if l.strip():
                        base_indent_len = len(l) - len(l.lstrip())
                        break
                
                # If the block was not empty, strip the base indentation from all lines
                if base_indent_len != -1:
                    processed_content = [l[base_indent_len:].rstrip('\r\n') for l in content_lines_raw]
                    
                    change = {
                        'action': action_type,
                        'lines': (start_line, end_line),
                        'content': processed_content
                    }
                    report[current_file].append(change)
        else:
            # Not a file, not an action, just move to the next line
            i += 1
            
    return {k: v for k, v in report.items() if v}

# --- The rest of the script is unchanged ---

def find_file(relative_path, search_directory):
    normalized_path = os.path.join(*relative_path.split('/'))
    full_path = os.path.join(search_directory, normalized_path)
    if os.path.exists(full_path):
        return full_path
    return None

def create_backup(file_path):
    backup_path = f"{file_path}.bak"
    try:
        shutil.copy2(file_path, backup_path)
        return f"Created backup: {backup_path}"
    except Exception as e:
        return f"Error creating backup for {file_path}: {e}"

def apply_changes(file_path, changes):
    print(f"\n--- Processing file: {file_path} ---")
    try:
        with open(file_path, 'r') as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        print(f"  [ERROR] File not found: {file_path}. Skipping.")
        return

    removals = sorted([c for c in changes if c['action'] == 'remove'], key=lambda x: x['lines'][0], reverse=True)
    additions = sorted([c for c in changes if c['action'] == 'add'], key=lambda x: x['lines'][0], reverse=True)

    if not removals and not additions:
        print("  (No valid changes were parsed for this file.)")
        return

    for change in removals:
        start_line_num, end_line_num = change['lines']
        start_index = start_line_num - 1
        end_index = end_line_num
        
        print("\n--- Proposed Change: Remove ---")
        print(f"Lines {start_line_num}-{end_line_num}:")
        for line_to_remove in lines[start_index:end_index]:
            print(f"  - {line_to_remove}")
        
        user_input = input("Apply this change? (y/n): ").lower()
        if user_input == 'y':
            del lines[start_index:end_index]
            print("  Change applied.")
        else:
            print("  Change skipped.")

    for change in additions:
        start_line_num, _ = change['lines']
        insert_index = start_line_num - 1
        content = change['content']
        
        print("\n--- Proposed Change: Add ---")
        print(f"Insert before line {start_line_num}:")
        for line_to_add in content:
            print(f"  + {line_to_add}")

        user_input = input("Apply this change? (y/n): ").lower()
        if user_input == 'y':
            lines[insert_index:insert_index] = content
            print("  Change applied.")
        else:
            print("  Change skipped.")

    try:
        with open(file_path, 'w') as f:
            f.write('\n'.join(lines) + '\n')
        print(f"\nFinished processing. Saved changes to {file_path}")
    except Exception as e:
        print(f"  [ERROR] Could not write to file {file_path}: {e}")

def main():
    args = parse_arguments()
    report_data = parse_report(args.report_file)

    if not report_data:
        print("\nCould not parse any valid files or changes from the report.")
        return

    print("--- File Analysis ---")
    files_to_process = []
    for rel_path, changes in report_data.items():
        full_path = find_file(rel_path, args.search_directory)
        if full_path:
            print(f"  [FOUND] {rel_path} at {full_path}")
            files_to_process.append({'path': full_path, 'changes': changes})
        else:
            print(f"  [NOT FOUND] {rel_path} in '{args.search_directory}'")

    if args.dry_run:
        print("\nDry run complete. No changes were made.")
        return

    if not files_to_process:
        print("\nNo files found to process.")
        return
    
    print("\nStarting interactive session to apply changes...")
    
    for file_info in files_to_process:
        backup_msg = create_backup(file_info['path'])
        print(backup_msg)
        apply_changes(file_info['path'], file_info['changes'])

    print("\n--- All changes processed. ---")

if __name__ == "__main__":
    main()
