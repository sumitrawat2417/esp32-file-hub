"""
Storage and Filesystem Subsystem
Provides safe path resolution, storage metrics, directory listing,
and atomic chunked stream operations to protect memory and flash integrity.
"""

import os
import gc


class StorageManager:
    """Encapsulates all filesystem interaction with safety checks and traversal protection."""

    @staticmethod
    def get_metrics(path="/"):
        """Query flash metrics using os.statvfs. Returns bytes, megabytes, and usage percentage."""
        try:
            stat = os.statvfs(path)
            bsize = stat[0]
            total_blocks = stat[2]
            free_blocks = stat[3]

            total_bytes = total_blocks * bsize
            free_bytes = free_blocks * bsize
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
            print("[Storage] Error querying statvfs: {}".format(e))
            return {
                "total_bytes": 0, "free_bytes": 0, "used_bytes": 0,
                "used_pct": 0, "total_mb": 0, "free_mb": 0, "used_mb": 0
            }

    @staticmethod
    def normalize_path(path):
        """Sanitize path to prevent directory traversal attacks (e.g. '../')."""
        if not path or path == "/":
            return "/"

        clean = path.replace("\\", "/")
        parts = []
        for part in clean.split("/"):
            if not part or part == ".":
                continue
            elif part == "..":
                if parts:
                    parts.pop()
            else:
                parts.append(part)

        return "/" + "/".join(parts)

    @staticmethod
    def join(base, child):
        """Join a base directory and a child segment cleanly."""
        base_norm = StorageManager.normalize_path(base)
        child_clean = child.strip("/\\")
        if base_norm == "/":
            return "/" + child_clean
        return base_norm + "/" + child_clean

    @staticmethod
    def get_parent(path):
        """Retrieve parent directory of a path."""
        norm = StorageManager.normalize_path(path)
        if norm == "/":
            return "/"
        parts = norm.rstrip("/").split("/")
        if len(parts) <= 2:
            return "/"
        return "/".join(parts[:-1])

    @staticmethod
    def list_dir(path="/"):
        """
        List directory contents.
        Returns list of dicts: [{'name': ..., 'is_dir': ..., 'size': ...}]
        Folders are sorted first, followed alphabetically by files.
        """
        target = StorageManager.normalize_path(path)
        entries = []

        try:
            for item in os.ilistdir(target):
                name = item[0]
                entry_type = item[1]
                is_dir = (entry_type == 0x4000)

                size = 0
                if not is_dir:
                    if len(item) > 3:
                        size = item[3]
                    else:
                        try:
                            full_path = StorageManager.join(target, name)
                            size = os.stat(full_path)[6]
                        except Exception:
                            size = 0

                entries.append({
                    "name": name,
                    "is_dir": is_dir,
                    "size": size
                })
        except Exception as e:
            print("[Storage] Error reading directory '{}': {}".format(target, e))
            return None

        entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        gc.collect()
        return entries

    @staticmethod
    def make_dir(path):
        """Recursively ensure a directory path exists."""
        target = StorageManager.normalize_path(path)
        if target == "/":
            return True

        segments = target.split("/")[1:]
        current = ""
        for seg in segments:
            current += "/" + seg
            try:
                stat = os.stat(current)
                if not (stat[0] & 0x4000):
                    return False
            except OSError:
                try:
                    os.mkdir(current)
                except Exception as e:
                    print("[Storage] Failed to mkdir '{}': {}".format(current, e))
                    return False
        return True

    @staticmethod
    def _rm_recursive(target):
        """Recursively delete a directory and all nested contents."""
        try:
            stat = os.stat(target)
            if (stat[0] & 0x4000) != 0:
                for item in os.listdir(target):
                    sub = target + "/" + item
                    StorageManager._rm_recursive(sub)
                os.rmdir(target)
            else:
                os.remove(target)
            return True
        except Exception as e:
            print("[Storage] Failed to delete '{}': {}".format(target, e))
            return False

    @staticmethod
    def delete(path):
        """Safely delete a file or directory tree."""
        target = StorageManager.normalize_path(path)
        if target == "/":
            return False

        try:
            return StorageManager._rm_recursive(target)
        finally:
            gc.collect()

    @staticmethod
    def exists(path):
        """Check whether a path exists in the filesystem."""
        target = StorageManager.normalize_path(path)
        try:
            os.stat(target)
            return True
        except OSError:
            return False

    @staticmethod
    def is_dir(path):
        """Check whether a path exists and is a directory."""
        target = StorageManager.normalize_path(path)
        try:
            return (os.stat(target)[0] & 0x4000) != 0
        except OSError:
            return False

    @staticmethod
    def compute_sha256(path):
        """Compute SHA-256 checksum in 1 KB streaming chunks to save ESP32 memory."""
        target = StorageManager.normalize_path(path)
        try:
            try:
                import uhashlib as hashlib
            except ImportError:
                import hashlib
            try:
                import ubinascii as binascii
            except ImportError:
                import binascii

            h = hashlib.sha256()
            with open(target, "rb") as f:
                while True:
                    chunk = f.read(1024)
                    if not chunk:
                        break
                    h.update(chunk)
            digest = binascii.hexlify(h.digest()).decode("utf-8")
            return digest
        except Exception as e:
            print("[Storage] Hash error on '{}': {}".format(target, e))
            return None
        finally:
            gc.collect()

    @staticmethod
    def write_stream(target_path, content_length, sock, initial_chunk=b"", chunk_size=1024):
        """
        Stream incoming bytes directly into a temporary file and atomically commit upon verification.
        Returns (success: bool, bytes_written: int, error_message: str).
        """
        target = StorageManager.normalize_path(target_path)
        parent = StorageManager.get_parent(target)
        if parent != "/" and not StorageManager.make_dir(parent):
            return False, 0, "Failed to create directory structure"

        temp_path = target + ".upload.tmp"
        bytes_written = 0

        try:
            with open(temp_path, "wb") as f:
                if initial_chunk:
                    to_write = initial_chunk[:content_length]
                    f.write(to_write)
                    bytes_written += len(to_write)

                while bytes_written < content_length:
                    remaining = content_length - bytes_written
                    read_size = chunk_size if remaining > chunk_size else remaining
                    chunk = sock.recv(read_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_written += len(chunk)

            if bytes_written == content_length:
                try:
                    os.remove(target)
                except OSError:
                    pass
                os.rename(temp_path, target)
                return True, bytes_written, ""
            else:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
                return False, bytes_written, "Upload interrupted: received {}/{} bytes".format(
                    bytes_written, content_length
                )

        except Exception as e:
            try:
                os.remove(temp_path)
            except OSError:
                pass
            return False, bytes_written, "Storage write error: {}".format(e)
        finally:
            gc.collect()

