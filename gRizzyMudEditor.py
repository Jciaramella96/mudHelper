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
    Parses the human-readable report file using a more robust content-capturing method.
    """
    report = {}
    current_file = None
    
    action_regex = re.compile(r'^\s*(Added|Removed)\s*\([Ll]ines\s*(\d+)\s*-\s*(\d+)\s*\):', re.IGNORECASE)

    with open(report_path, 'r') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i]
        
        file_match = re.match(r'^(?P<filepath>\S+):$', line.strip())
        if file_match:
            current_file = file_match.group('filepath')
            if current_file not in report:
                report[current_file] = []
            i += 1
            continue
            
        if re.match(r'^Only in New: \S+', line.strip()):
            current_file = None 
            i += 1
            continue

        action_match = action_regex.match(line)
        if action_match and current_file:
            action_type = action_match.group(1).lower()
            start_line = int(action_match.group(2))
            end_line = int(action_match.group(3))
            
            i += 1
            
            # --- NEW LOGIC START ---
            
            # 1. Capture the raw lines of the content block first
            raw_content_lines = []
            while (i < len(lines) and 
                   not action_regex.match(lines[i]) and 
                   not re.match(r'^\S+:$', lines[i].strip()) and 
                   not re.match(r'^Only in New:', lines[i].strip())):
                raw_content_lines.append(lines[i].rstrip('\n'))
                i += 1

            # 2. Determine the base indentation from the first non-empty line
            base_indent = 0
            for l in raw_content_lines:
                if l.strip(): # Find the first line with actual content
                    base_indent = len(l) - len(l.lstrip())
                    break
            
            # 3. Process the raw lines to build the final content, stripping only the base indent
            content_block = []
            for l in raw_content_lines:
                # Strip the base indentation. If a line is indented less, it becomes left-aligned.
                # This preserves all relative indentation within the block.
                if len(l) > base_indent:
                    content_block.append(l[base_indent:])
                else:
                    content_block.append(l) # Append blank lines as-is
            
            # --- NEW LOGIC END ---

            change = {
                'action': action_type,
                'lines': (start_line, end_line),
                'content': content_block
            }
            report[current_file].append(change)
        else:
            i += 1
            
    return report

def find_file(relative_path, search_directory):
    """Finds the full path of a file, matching the relative path from the report."""
    normalized_path = os.path.join(*relative_path.split('/'))
    full_path = os.path.join(search_directory, normalized_path)
    if os.path.exists(full_path):
        return full_path
    return None

def create_backup(file_path):
    """Creates a backup of a file."""
    backup_path = f"{file_path}.bak"
    try:
        shutil.copy2(file_path, backup_path)
        return f"Created backup: {backup_path}"
    except Exception as e:
        return f"Error creating backup for {file_path}: {e}"

def apply_changes(file_path, changes):
    """Interactively applies a list of changes to a single file."""
    
    print(f"\n--- Processing file: {file_path} ---")
    try:
        with open(file_path, 'r') as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        print(f"  [ERROR] File not found: {file_path}. Skipping.")
        return

    removals = sorted([c for c in changes if c['action'] == 'remove'], key=lambda x: x['lines'][0], reverse=True)
    additions = sorted([c for c in changes if c['action'] == 'add'], key=lambda x: x['lines'][0], reverse=True)

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
    """Main function to run the tool."""
    args = parse_arguments()

    try:
        report_data = parse_report(args.report_file)
    except FileNotFoundError:
        print(f"Error: Report file not found at '{args.report_file}'")
        return
    except Exception as e:
        print(f"An error occurred while parsing the report: {e}")
        return

    print("--- File Analysis ---")
    files_to_process = []
    for rel_path, changes in report_data.items():
        if not changes: continue
        full_path = find_file(rel_path, args.search_directory)
        if full_path:
            # Only add to list if there are actual changes to apply
            if any(c['content'] for c in changes):
                 print(f"  [FOUND] {rel_path} at {full_path}")
                 files_to_process.append({'path': full_path, 'changes': changes})
            else:
                 print(f"  [FOUND] {rel_path} at {full_path} (No valid changes parsed)")
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
