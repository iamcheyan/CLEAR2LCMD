import os
import subprocess
import shutil
from pathlib import Path

# Configuration
SOURCE_DIRS = [
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Downloads"),
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Movies"),
    os.path.expanduser("~/Music")
]

WEBDAV_URL = "https://file.kabizhu.heiyu.space/dav/TemporaryFiles"
MOUNT_POINT = "/Volumes/TemporaryFiles"

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

def list_large_files(limit=30):
    print("\n" + "="*50)
    print("🔍 SCANNING DIRECTORIES FOR LARGE FILES")
    print("="*50)
    
    files = []
    for source in SOURCE_DIRS:
        if not os.path.exists(source):
            continue
        print(f"Scanning: {source}...")
        for root, dirs, filenames in os.walk(source):
            for f in filenames:
                file_path = os.path.join(root, f)
                size = get_file_size(file_path)
                if size > 1024 * 1024: # Only list files > 1MB for clarity
                    files.append((file_path, size))
    
    # Sort by size descending
    files.sort(key=lambda x: x[1], reverse=True)
    
    print(f"\nTop {limit} largest files found:")
    for i, (path, size) in enumerate(files[:limit], 1):
        print(f"{i:2d}. [{format_size(size):>10}] {path}")
    
    return files[:limit]

def is_mounted():
    return os.path.ismount(MOUNT_POINT)

def ensure_mounted():
    if is_mounted():
        return True
    
    print(f"\n⚠️  {MOUNT_POINT} is NOT mounted.")
    print(f"Trying to mount: {WEBDAV_URL}")
    
    try:
        # On macOS, using 'open' with a dav:// or https:// URL can trigger the Finder mount dialog
        # WebDAV needs 'davs://' for HTTPS
        dav_url = WEBDAV_URL.replace("https://", "davs://").replace("http://", "dav://")
        subprocess.run(["open", dav_url], check=True)
        print("\nSent mount request to Finder.")
        print("Please check for a login window if it appears.")
        
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
            
        # Target directory structure: /Volumes/TemporaryFiles/MacBackup/Documents/...
        target_base = os.path.join(MOUNT_POINT, "MacBackup")
        if not os.path.exists(target_base):
            os.makedirs(target_base, exist_ok=True)
            
        target_dir = os.path.join(target_base, os.path.basename(source))
        print(f"\nSyncing: {source} -> {target_dir}")
        
        # rsync flags:
        # -a: archive (preserve permissions, timestamps, etc.)
        # -v: verbose
        # -z: compress during transfer
        # -h: human readable numbers
        # --progress: show progress
        # --delete: delete files in target that are not in source (sync) - maybe NOT for backup? 
        # User said "incremental", usually rsync -a is enough.
        
        try:
            cmd = ["rsync", "-avzh", "--progress", source + "/", target_dir]
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error backing up {source}: {e}")
            
    print("\n✅ Backup finished successfully!")
    return True

def pre_backup_cleanup(scanned_files):
    """Allows user to delete files BEFORE backup starts."""
    current_files = list(scanned_files)
    
    while True:
        if not current_files:
            print("\n✅ All listed files have been processed or deleted.")
            break

        print("\n" + "="*50)
        print("📋 CURRENT LARGE FILES LIST")
        print("="*50)
        for i, (path, size) in enumerate(current_files, 1):
            print(f"{i:2d}. [{format_size(size):>10}] {path}")

        print("\n" + "-"*30)
        print("🗑️  PRE-BACKUP CLEANUP")
        print("Commands:")
        print("1. Enter numbers (e.g., 1, 2, 5) to delete specific files.")
        print("2. Enter extension (e.g., .dmg, .iso) to delete all matching files.")
        print("3. Enter 'done' to proceed to backup.")
        print("-"*30)
        
        cmd = input("Command: ").strip().lower()
        
        if cmd == 'done':
            break
        
        valid_indices = []
        
        # Check if it's an extension command
        if cmd.startswith('.'):
            valid_indices = [i for i, (path, size) in enumerate(current_files) if path.lower().endswith(cmd)]
            if not valid_indices:
                print(f"⚠️  No files found with extension: {cmd}")
                continue
        else:
            try:
                # Handle multiple indices like "1, 2, 3"
                indices = [int(i.strip()) - 1 for i in cmd.replace(',', ' ').split()]
                valid_indices = [i for i in indices if 0 <= i < len(current_files)]
            except ValueError:
                print("Invalid input. Please enter numbers, extension (e.g. .dmg), or 'done'.")
                continue
            
        if not valid_indices:
            print("⚠️  No valid files selected.")
            continue
            
        print(f"\n⚠️  Targeting {len(valid_indices)} files for immediate deletion:")
        for i in valid_indices:
            print(f"   - {current_files[i][0]}")
        
        confirm = input("\nConfirm deletion? (Type 'YES' to delete): ")
        if confirm == 'YES':
            # Sort indices in reverse to avoid index shifting during removal
            for i in sorted(valid_indices, reverse=True):
                path, size = current_files[i]
                try:
                    if os.path.isfile(path) or os.path.islink(path):
                        os.remove(path)
                    elif os.path.isdir(path):
                        shutil.rmtree(path)
                    print(f"✅ Deleted: {path}")
                    current_files.pop(i) # Remove from our local list
                except Exception as e:
                    print(f"❌ Error deleting {path}: {e}")
        else:
            print("Deletion cancelled.")

    return current_files

def cleanup_files(remaining_files):
    """Allows user to delete files AFTER backup is completed."""
    if not remaining_files:
        return

    print("\n" + "="*50)
    print("🧹 POST-BACKUP CLEANUP")
    print("="*50)
    print("The following files have been backed up to WebDAV. Do you want to remove them from your Mac to free space?")
    
    for i, (path, size) in enumerate(remaining_files, 1):
        print(f"{i:2d}. [{format_size(size):>10}] {path}")
        
    print("\nOptions:")
    print("1. Delete specific files (enter numbers)")
    print("2. Delete ALL listed files")
    print("3. Skip")
    
    choice = input("\nSelect option (1-3): ")
    
    to_delete = []
    if choice == '1':
        idx_str = input("Enter numbers (e.g. 1, 2, 5): ")
        try:
            indices = [int(i.strip()) - 1 for i in idx_str.replace(',', ' ').split()]
            to_delete = [remaining_files[i] for i in indices if 0 <= i < len(remaining_files)]
        except:
            print("Invalid input.")
    elif choice == '2':
        to_delete = remaining_files
    
    if to_delete:
        print(f"\n⚠️  Ready to delete {len(to_delete)} files.")
        if input("Confirm? (Type 'YES'): ") == 'YES':
            for path, _ in to_delete:
                try:
                    if os.path.isfile(path) or os.path.islink(path): os.remove(path)
                    elif os.path.isdir(path): shutil.rmtree(path)
                    print(f"✅ Deleted: {path}")
                except Exception as e:
                    print(f"❌ Error: {e}")

def main():
    large_files = list_large_files()
    if not large_files:
        print("No large files found to manage.")
        # We can still offer backup of the whole directories
    
    # New Step: Pre-backup cleanup
    remaining_files = pre_backup_cleanup(large_files)
    
    do_backup = input("\nProceed with incremental backup to WebDAV? (y/n): ")
    if do_backup.lower() == 'y':
        if backup_incremental():
            # After backup, offer to delete the files that were moved
            cleanup_files(remaining_files)
    else:
        print("Process ended.")

if __name__ == "__main__":
    main()
