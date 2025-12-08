import os
import time
import shutil
import ctypes

class ThumbnailCache:
    def __init__(self, cache_dir=".danbooru_cache", max_days=7, max_size_mb=500):
        self.cache_dir = os.path.abspath(cache_dir)
        self.max_days = max_days
        self.max_size_mb = max_size_mb
        
        if self.max_days > 0:
            self._ensure_cache_dir()

    def _ensure_cache_dir(self):
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
            # Hide the folder on Windows
            try:
                FILE_ATTRIBUTE_HIDDEN = 0x02
                ctypes.windll.kernel32.SetFileAttributesW(self.cache_dir, FILE_ATTRIBUTE_HIDDEN)
            except Exception as e:
                print(f"Failed to hide cache dir: {e}")

    def get(self, post_id):
        if self.max_days == 0:
            return None
            
        file_path = os.path.join(self.cache_dir, f"{post_id}.jpg")
        if os.path.exists(file_path):
            # Update access time (touch)
            try:
                os.utime(file_path, None)
            except:
                pass
            return file_path
        return None

    def save(self, post_id, image_data):
        if self.max_days == 0:
            return
            
        self._ensure_cache_dir()
        file_path = os.path.join(self.cache_dir, f"{post_id}.jpg")
        try:
            with open(file_path, "wb") as f:
                f.write(image_data.getbuffer())
        except Exception as e:
            print(f"Failed to save cache: {e}")

    def cleanup(self):
        if self.max_days == 0:
            # If disabled, maybe we should clear everything? 
            # For now, let's just not use it. But user might expect cleanup.
            # Let's clear if it exists to free space.
            if os.path.exists(self.cache_dir):
                try:
                    shutil.rmtree(self.cache_dir)
                except:
                    pass
            return

        if not os.path.exists(self.cache_dir):
            return

        # 1. Time-based cleanup
        now = time.time()
        max_age = self.max_days * 86400
        
        files = []
        total_size = 0
        
        for f in os.listdir(self.cache_dir):
            path = os.path.join(self.cache_dir, f)
            try:
                stat = os.stat(path)
                if now - stat.st_atime > max_age:
                    os.remove(path)
                    continue
                
                files.append((path, stat.st_atime, stat.st_size))
                total_size += stat.st_size
            except:
                pass

        # 2. Size-based cleanup (LRU)
        max_size_bytes = self.max_size_mb * 1024 * 1024
        
        if total_size > max_size_bytes:
            # Sort by access time (oldest first)
            files.sort(key=lambda x: x[1])
            
            for path, _, size in files:
                try:
                    os.remove(path)
                    total_size -= size
                    if total_size <= max_size_bytes:
                        break
                except:
                    pass

    def clear_all(self):
        if os.path.exists(self.cache_dir):
            try:
                shutil.rmtree(self.cache_dir)
                self._ensure_cache_dir()
            except Exception as e:
                print(f"Failed to clear cache: {e}")

    def clear_all(self):
        if os.path.exists(self.cache_dir):
            try:
                shutil.rmtree(self.cache_dir)
                self._ensure_cache_dir()
            except Exception as e:
                print(f"Failed to clear cache: {e}")
