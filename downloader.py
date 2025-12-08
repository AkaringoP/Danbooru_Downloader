import os
import requests
import threading
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class DownloadManager:
    def __init__(self, max_workers=8):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.active_downloads = []
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set() # Start unpaused (set means go)
        self.session = requests.Session()
        
        retries = Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear() # Pause
            return True # Paused
        else:
            self.pause_event.set() # Resume
            return False # Resumed

    def download_image(self, url, save_path, callback_progress=None, callback_complete=None, callback_error=None):
        if self.stop_event.is_set():
            return

        try:
            if os.path.exists(save_path):
                if callback_complete:
                    callback_complete(save_path, skipped=True)
                return

            response = self.session.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0

            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if self.stop_event.is_set():
                        # We need to break to close the file via 'with' context
                        break
                    
                    # Wait if paused
                    self.pause_event.wait()
                    
                    # Check stop again in case we were paused and then cancelled
                    if self.stop_event.is_set():
                        break

                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if callback_progress and total_size > 0:
                            progress = downloaded_size / total_size
                            callback_progress(progress)
            
            # Outside 'with' block, file is closed. Check if we stopped.
            if self.stop_event.is_set():
                if os.path.exists(save_path):
                    try:
                        os.remove(save_path)
                    except:
                        pass
                return

            if callback_complete:
                callback_complete(save_path, skipped=False)

        except Exception as e:
            if callback_error:
                callback_error(str(e))

    def start_download_batch(self, posts, output_dir, callbacks):
        """
        posts: list of post dicts
        callbacks: dict of functions {'on_progress': fn, 'on_complete': fn, 'on_error': fn}
        """
        # self.stop_event.clear() # Removed: Caller should handle clearing
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        futures = []
        for post in posts:
            if self.stop_event.is_set():
                break
            
            file_url = post.get('file_url')
            if not file_url:
                continue
                
            file_ext = post.get('file_ext', 'jpg')
            file_name = f"{post['id']}.{file_ext}"
            save_path = os.path.join(output_dir, file_name)

            # Create a closure to capture specific post info if needed, 
            # but for now passing generic callbacks
            future = self.executor.submit(
                self.download_image, 
                file_url, 
                save_path, 
                callbacks.get('on_progress'), 
                callbacks.get('on_complete'),
                callbacks.get('on_error')
            )
            futures.append(future)
        
        return futures

    def stop_all(self):
        self.stop_event.set()
        self.pause_event.set() # Unpause so waiting threads can check stop_event and exit
        # Do not shutdown executor, so it can be reused.
        # self.executor.shutdown(wait=False)
