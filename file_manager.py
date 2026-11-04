"""
Filesystem Helper for ESP32 MicroPython
Provides safe directory listing, storage capacity metrics, path sanitization,
and file operations with traversal attack protection.
"""

import os
import gc


def get_storage_info(path="/"):
    """
    Query filesystem storage metrics using os.statvfs.
    Returns dictionary with total, used, free bytes and percentage used.
    """
    try:
        stat = os.statvfs(path)
        block_size = stat[0]
        total_blocks = stat[2]
        free_blocks = stat[3]

        total_bytes = total_blocks * block_size
        free_bytes = free_blocks * block_size
        used_bytes = total_bytes - free_bytes

        used_pct = round((used_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0

        return {
            "total_bytes": total_bytes,
            "free_bytes": free_bytes,
            "used_bytes": used_bytes,
            "used_pct": used_pct,
            "total_mb": round(total_bytes / (1024 * 1024), 2),
            "free_mb": round(free_bytes / (1024 * 1024), 2),
            "used_mb": round(used_bytes / (1024 * 1024), 2)
        }
    except Exception as e:
        print("[FS] Failed to query storage: {}".format(e))
        return {
            "total_bytes": 0, "free_bytes": 0, "used_bytes": 0,
            "used_pct": 0, "total_mb": 0, "free_mb": 0, "used_mb": 0
        }


def normalize_path(path):
    """
    Normalize path to prevent directory traversal (e.g. '../').
    Always returns a clean, canonical absolute path starting with '/'.
    """
    if not path or path == "/":
        return "/"

    # Replace backslashes with forward slashes
    clean = path.replace("\\", "/")

    # Split into components and filter out empty and '.' segments
    parts = []
    for part in clean.split("/"):
        if not part or part == ".":
            continue
        elif part == "..":
            # Prevent ascending above root
            if parts:
                parts.pop()
        else:
            parts.append(part)

    return "/" + "/".join(parts)


def join_path(base, child):
    """Safely combine a directory path and a child filename or subfolder."""
    base_clean = normalize_path(base)
    child_clean = child.strip("/\\")
    if base_clean == "/":
        return "/" + child_clean
    return base_clean + "/" + child_clean


def get_parent_dir(path):
    """Return the parent directory for a given path."""
    target = normalize_path(path)
    if target == "/":
        return "/"
    parts = target.rstrip("/").split("/")
    if len(parts) <= 2:
        return "/"
    return "/".join(parts[:-1])


def list_directory(path="/"):
    """
    List contents of a directory.
    Returns a sorted list of dictionaries: [{'name': ..., 'is_dir': ..., 'size': ...}]
    Directories appear first, followed alphabetically by files.
    """
    target = normalize_path(path)
    entries = []

    try:
        # MicroPython os.ilistdir yields (name, type, inode[, size])
        # type 0x4000 (16384) is directory, 0x8000 (32768) is regular file
        for item in os.ilistdir(target):
            name = item[0]
            entry_type = item[1]
            is_dir = (entry_type == 0x4000)

            # Determine file size
            size = 0
            if not is_dir:
                if len(item) > 3:
                    size = item[3]
                else:
                    try:
                        full_path = join_path(target, name)
                        size = os.stat(full_path)[6]
                    except Exception:
                        size = 0

            entries.append({
                "name": name,
                "is_dir": is_dir,
                "size": size
            })
    except Exception as e:
        print("[FS] Error reading directory '{}': {}".format(target, e))
        return None

    # Sort directories first, then alphabetical by name
    entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    gc.collect()
    return entries


def ensure_directory(path):
    """
    Recursively verify or create each directory component of a path.
    """
    target = normalize_path(path)
    if target == "/":
        return True

    segments = target.split("/")[1:]
    current = ""
    for seg in segments:
        current += "/" + seg
        try:
            stat = os.stat(current)
            # 0x4000 indicates directory
            if not (stat[0] & 0x4000):
                print("[FS] Path segment '{}' is a file, not a directory.".format(current))
                return False
        except OSError:
            # Segment does not exist, create it
            try:
                os.mkdir(current)
                print("[FS] Created directory '{}'".format(current))
            except Exception as e:
                print("[FS] Failed to create directory '{}': {}".format(current, e))
                return False
    return True


def delete_item(path):
    """
    Safely delete a file or empty directory.
    Returns True on success, False on failure.
    """
    target = normalize_path(path)
    if target == "/":
        print("[FS] Cannot delete root directory.")
        return False

    try:
        stat = os.stat(target)
        is_dir = (stat[0] & 0x4000) != 0

        if is_dir:
            os.rmdir(target)
            print("[FS] Removed directory '{}'".format(target))
        else:
            os.remove(target)
            print("[FS] Removed file '{}'".format(target))
        return True
    except OSError as e:
        print("[FS] Failed to delete '{}': {}".format(target, e))
        return False


if __name__ == "__main__":
    print("=== ESP32 Filesystem Helper Self-Test ===")
    
    # 1. Storage Query
    storage = get_storage_info()
    print("Flash Storage: {} MB total | {} MB free ({}% used)".format(
        storage["total_mb"], storage["free_mb"], storage["used_pct"]
    ))

    # 2. Directory Listing
    print("\nRoot Directory Listing ('/'):")
    files = list_directory("/")
    if files is not None:
        for f in files:
            kind = "[DIR] " if f["is_dir"] else "[FILE]"
            size_str = "" if f["is_dir"] else " ({} bytes)".format(f["size"])
            print("  {} {}{}".format(kind, f["name"], size_str))

    # 3. Path Normalization Test
    print("\nPath Traversal Protection Test:")
    test_paths = ["/lib/../config.json", "///data/../../", "foo/bar/test.txt"]
    for p in test_paths:
        print("  '{}' -> '{}'".format(p, normalize_path(p)))
    
    print("\n=== Self-Test Completed ===")

