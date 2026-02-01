import os
import subprocess
import shutil
from pathlib import Path

import socket

# Configuration
SOURCE_DIRS = [
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Downloads"),
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Movies"),
    os.path.expanduser("~/Music")
]

WEBDAV_URL = "https://file.kabizhu.heiyu.space/dav/CloudRelay"
MOUNT_POINT = "/Volumes/CloudRelay"
DEVICE_NAME = socket.gethostname().split('.')[0] # e.g., "tetsuya-mac"

def get_file_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0

def format_size(size):
    if size == 0: return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024

def list_large_items(limit=20):
    print("\n" + "="*50)
    print("🔍 SCANNING DIRECTORIES FOR LARGE ITEMS")
    print("="*50)
    
    all_files = []
    dir_sizes = {}
    
    for source in SOURCE_DIRS:
        if not os.path.exists(source):
            continue
        print(f"Scanning: {source}...")
        for root, dirs, filenames in os.walk(source):
            current_dir_size = 0
            for f in filenames:
                file_path = os.path.join(root, f)
                size = get_file_size(file_path)
                if size > 1024 * 1024: # Only track files > 1MB
                    all_files.append((file_path, size))
                current_dir_size += size
            
            # Accumulate size for current dir and all parents up to 'source'
            temp_path = root
            while True:
                dir_sizes[temp_path] = dir_sizes.get(temp_path, 0) + current_dir_size
                if temp_path == source or temp_path == os.path.dirname(source):
                    break
                temp_path = os.path.dirname(temp_path)
    
    # Sort files
    all_files.sort(key=lambda x: x[1], reverse=True)
    
    # Sort all directories by size
    raw_sorted_dirs = sorted(
        [(d, s) for d, s in dir_sizes.items() if any(d.startswith(src) and d != src for src in SOURCE_DIRS)],
        key=lambda x: x[1],
        reverse=True
    )
    
    # Deduplicate: If a parent is already in the list, skip its children
    # This avoids listing A, A/B, A/B/C separately when they are all "large"
    deduped_dirs = []
    for d_path, d_size in raw_sorted_dirs:
        # Check if any parent of d_path is already in deduped_dirs
        is_redundant = False
        for existing_path, _ in deduped_dirs:
            if d_path.startswith(existing_path + os.sep) or d_path == existing_path:
                is_redundant = True
                break
        if not is_redundant:
            deduped_dirs.append((d_path, d_size))
        if len(deduped_dirs) >= limit:
            break
    
    print(f"\n🔝 TOP {limit} LARGEST FILES:")
    for i, (path, size) in enumerate(all_files[:limit], 1):
        print(f"F{i:02d}. [{format_size(size):>10}] {path}")
        
    print(f"\n📂 TOP {limit} LARGEST DIRECTORIES (Deduplicated):")
    for i, (path, size) in enumerate(deduped_dirs, 1):
        print(f"D{i:02d}. [{format_size(size):>10}] {path}")
    
    return all_files[:limit], deduped_dirs

def is_mounted():
    return os.path.ismount(MOUNT_POINT)

def ensure_mounted():
    if is_mounted():
        return True
    
    print(f"\n⚠️  {MOUNT_POINT} is NOT mounted.")
    print(f"Trying to mount: {WEBDAV_URL}")
    
    try:
        # Using AppleScript to mount is the most reliable way on macOS
        # as it triggers the native "Connect to Server" dialog and handles Keychain.
        mount_cmd = f'tell application "Finder" to mount volume "{WEBDAV_URL}"'
        subprocess.run(["osascript", "-e", mount_cmd], check=True)
        print("\nSent native mount request (AppleScript).")
        print("Please check for the 'Connect to Server' dialog if it appears.")
        
        while True:
            choice = input(f"Waiting for mount at {MOUNT_POINT}... (Ready? [y]/Retry [r]/Cancel [c]): ").lower()
            if choice == 'y' or choice == '':
                if is_mounted():
                    print("✅ Successfully mounted!")
                    return True
                else:
                    print("❌ Still not mounted. Please check Finder.")
            elif choice == 'r':
                continue
            else:
                return False
    except Exception as e:
        print(f"Error during mounting: {e}")
        return False

def backup_incremental():
    if not ensure_mounted():
        print("Aborting: WebDAV volume is required for backup.")
        return False
        
    print("\n" + "="*50)
    print("🚀 STARTING INCREMENTAL BACKUP")
    print("="*50)

    for source in SOURCE_DIRS:
        if not os.path.exists(source):
            continue
            
        # Target directory structure: /Volumes/CloudRelay/Devices/<hostname>/Documents/...
        target_base = os.path.join(MOUNT_POINT, "Devices", DEVICE_NAME)
        if not os.path.exists(target_base):
            os.makedirs(target_base, exist_ok=True)
            
        target_dir = os.path.join(target_base, os.path.basename(source))
        print(f"\nSyncing: {source} -> {target_dir}")
        
        # Ultimate rsync flags for WebDAV compatibility:
        # -r: recursive, -t: preserve times, -v: verbose, -z: compress
        # --inplace: write to files directly (CRITICAL for WebDAV)
        # --size-only: skip checksums, rely on size and time (faster on network)
        # --exclude: strictly ignore macOS noise and heavy dev junk
        
        try:
            cmd = [
                "rsync", "-rtvz", "--inplace", "--size-only", "--progress",
                "--exclude", ".DS_Store",
                "--exclude", "._*",
                "--exclude", ".localized",
                "--exclude", ".TemporaryItems",
                "--exclude", ".Trashes",
                "--exclude", "venv",           # Python Virtual Environments
                "--exclude", ".venv",
                "--exclude", "node_modules",   # JS Dependencies
                "--exclude", "__pycache__",    # Python cache
                "--exclude", ".cache",         # Generic cache
                "--exclude", ".npm",           # NPM cache
                "--exclude", "build",          # Build artifacts
                "--exclude", "dist",
                source + "/", target_dir
            ]
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error backing up {source}: {e}")
            
    print("\n✅ Backup finished successfully!")
    return True

def pre_backup_cleanup(scanned_files, scanned_dirs):
    """Allows user to delete files or directories BEFORE backup starts."""
    current_files = list(scanned_files)
    current_dirs = list(scanned_dirs)
    
    while True:
        if not current_files and not current_dirs:
            print("\n✅ All listed items have been processed or deleted.")
            break

        # Automatically show the items at each step
        print("\n" + "="*50)
        print("📋 CURRENT LARGE ITEMS (Pre-Backup)")
        print("="*50)
        print(f"🔝 FILES:")
        for i, (path, size) in enumerate(current_files, 1):
            print(f"F{i:02d}. [{format_size(size):>10}] {path}")
            
        print(f"\n📂 DIRECTORIES:")
        for i, (path, size) in enumerate(current_dirs, 1):
            print(f"D{i:02d}. [{format_size(size):>10}] {path}")

        print("\n" + "-"*30)
        print("🗑️  PRE-BACKUP CLEANUP")
        print("Commands:")
        print("1. Enter file numbers with 'F' (e.g., F01, F02) to delete files.")
        print("2. Enter dir numbers with 'D' (e.g., D01, D02) to delete directories.")
        print("3. Enter extension (e.g., .dmg) to delete matching files.")
        print("4. Enter 'done' to proceed to backup.")
        print("-"*30)
        
        cmd = input("Command: ").strip().lower()
        
        if cmd == 'done':
            break
        
        to_delete = []
        
        if cmd.startswith('.'):
            # Extension mode
            to_delete = [(path, size, 'file', i) for i, (path, size) in enumerate(current_files) if path.lower().endswith(cmd)]
        else:
            # New improved parser for single numbers and ranges (e.g., F01, F05-F10)
            tokens = cmd.replace(',', ' ').split()
            for token in tokens:
                token = token.strip()
                if not token: continue
                
                prefix = token[0]
                if prefix not in ['f', 'd']: continue
                
                try:
                    num_part = token[1:]
                    if '-' in num_part:
                        start_str, end_str = num_part.split('-')
                        # Handle cases like D05-D10 or D05-10
                        start = int(start_str.strip('fd'))
                        end = int(end_str.strip('fd'))
                        indices = range(start - 1, end)
                    else:
                        indices = [int(num_part) - 1]
                    
                    for idx in indices:
                        if prefix == 'f' and 0 <= idx < len(current_files):
                            to_delete.append((current_files[idx][0], current_files[idx][1], 'file', idx))
                        elif prefix == 'd' and 0 <= idx < len(current_dirs):
                            to_delete.append((current_dirs[idx][0], current_dirs[idx][1], 'dir', idx))
                except:
                    continue
            
        if not to_delete:
            print("⚠️  Invalid input or item not found. Use F01 for files, D01 for dirs.")
            continue
            
        print(f"\n⚠️  Targeting {len(to_delete)} items for IMMEDIATE deletion:")
        for path, size, _, _ in to_delete:
            print(f"   - [{format_size(size):>10}] {path}")
        
        confirm = input("\nConfirm deletion? (Type 'YES'): ")
        if confirm == 'YES':
            # Sort to_delete by index in reverse to pop correctly
            # We process files and dirs separately to maintain list integrity
            file_back_indices = sorted([item[3] for item in to_delete if item[2] == 'file'], reverse=True)
            dir_back_indices = sorted([item[3] for item in to_delete if item[2] == 'dir'], reverse=True)
            
            for f_idx in file_back_indices:
                path = current_files[f_idx][0]
                if os.path.exists(path):
                    if os.path.isfile(path): os.remove(path)
                    elif os.path.isdir(path): shutil.rmtree(path)
                    print(f"✅ Deleted File: {path}")
                current_files.pop(f_idx)
                
            for d_idx in dir_back_indices:
                path = current_dirs[d_idx][0]
                if os.path.exists(path):
                    shutil.rmtree(path)
                    print(f"✅ Deleted Directory: {path}")
                current_dirs.pop(d_idx)
    
    return current_files

def cleanup_files(remaining_files):
    """Summarizes backed up items and offers deletion to free space."""
    if not remaining_files:
        print("\n✅ No specific large files were flagged for post-backup cleanup.")
        return

    # Group files by their source directory
    dir_summary = {}
    total_freed_space = 0
    
    for path, size in remaining_files:
        # Find which source dir this file belongs to
        found_src = "Other"
        for src in SOURCE_DIRS:
            if path.startswith(src):
                found_src = src
                break
        
        dir_summary[found_src] = dir_summary.get(found_src, 0) + size
        total_freed_space += size

    print("\n" + "="*50)
    print("🧹 POST-BACKUP SPACE SAVING SUMMARY")
    print("="*50)
    print("The following large files have been successfully backed up to CloudRelay.")
    print("You can now safely remove them from your Mac to free up space:\n")

    for src_path, size in dir_summary.items():
        # Display folder name (e.g., Downloads) and its removable size
        folder_name = os.path.basename(src_path) if src_path != "Other" else "Other Items"
        print(f"📁 {folder_name:<15} : {format_size(size):>10} can be freed")

    print("-" * 50)
    print(f"🚀 TOTAL POTENTIAL SAVINGS: {format_size(total_freed_space)}")
    print("=" * 50)
    
    confirm = input("\nDo you want to delete ALL these backed-up files from your Mac? (Type 'YES'): ")
    
    if confirm == 'YES':
        deleted_count = 0
        for path, _ in remaining_files:
            if os.path.exists(path):
                try:
                    if os.path.isfile(path): os.remove(path)
                    elif os.path.isdir(path): shutil.rmtree(path)
                    deleted_count += 1
                except Exception as e:
                    print(f"❌ Error deleting {path}: {e}")
        
        print(f"\n✅ Cleanup complete! Deleted {deleted_count} items. Mac is now {format_size(total_freed_space)} lighter.")
    else:
        print("Cleanup skipped. Your files remain on your Mac.")

def main():
    large_files, large_dirs = list_large_items()
    
    # New Step: Pre-backup cleanup supporting both files and dirs
    remaining_files = pre_backup_cleanup(large_files, large_dirs)
    
    do_backup = input("\nProceed with incremental backup to WebDAV? (y/n): ")
    if do_backup.lower() == 'y':
        if backup_incremental():
            cleanup_files(remaining_files)
    else:
        print("Process ended.")

if __name__ == "__main__":
    main()
