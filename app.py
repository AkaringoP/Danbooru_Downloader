import customtkinter as ctk
import tkinter.messagebox
import threading
import os
import re
from PIL import Image, ImageTk
from io import BytesIO
import requests
from dotenv import load_dotenv, set_key
from danbooru_api import DanbooruClient
from downloader import DownloadManager
from cache_manager import ThumbnailCache
from security import SecurityManager

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

import json

class ResumeManager:
    def __init__(self, download_path, security_manager):
        self.file_path = os.path.join(download_path, ".danbooru_resume.json")
        self.security = security_manager
        self.state = self.load()

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    encrypted_data = f.read()
                    decrypted_data = self.security.decrypt(encrypted_data)
                    return json.loads(decrypted_data)
            except:
                pass
        return {}

    def save(self, query, top_id, last_page, is_complete):
        data = {
            "query": query,
            "top_id": top_id,
            "last_page": last_page,
            "is_complete": is_complete,
            "updated_at": str(os.path.getmtime(self.file_path)) if os.path.exists(self.file_path) else None
        }
        try:
            json_str = json.dumps(data, indent=2)
            encrypted_data = self.security.encrypt(json_str)
            with open(self.file_path, 'w', encoding='utf-8') as f:
                f.write(encrypted_data)
        except Exception as e:
            print(f"Error saving resume state: {e}")

    def get_query(self):
        return self.state.get("query")

    def get_state(self):
        return {
            "top_id": self.state.get("top_id"),
            "last_page": self.state.get("last_page", 1),
            "is_complete": self.state.get("is_complete", False)
        }

class PostFrame(ctk.CTkFrame):
    def __init__(self, master, post, cache, selection_callback=None, on_load_finish=None, **kwargs):
        super().__init__(master, **kwargs)
        self.post = post
        self.cache = cache
        self.on_load_finish = on_load_finish
        self.id = post['id']
        self.url = post.get('file_url')
        self.preview_url = post.get('preview_file_url') or post.get('large_file_url') or self.url
        self.selection_callback = selection_callback
        
        self.grid_columnconfigure(2, weight=1)
        
        # Checkbox
        self.checkbox = ctk.CTkCheckBox(self, text="", width=24, command=self.on_select)
        self.checkbox.grid(row=0, column=0, rowspan=2, padx=5, pady=5, sticky="ns")

        # Thumbnail Container (for overlay)
        self.preview_container = ctk.CTkFrame(self, fg_color="transparent")
        self.thumb_label = ctk.CTkLabel(self.preview_container, text="Loading...", width=100, height=100, fg_color="gray20")
        self.thumb_label.pack(expand=True, fill="both")
        
        # Magnify Button (Overlay)
        self.magnify_btn = ctk.CTkButton(self.preview_container, text="🔍", width=20, height=20, 
                                         fg_color="gray20", hover_color="gray30", 
                                         command=self.open_viewer)
        self.magnify_btn.place(relx=1.0, rely=1.0, anchor="se", x=0, y=0)

        # Info Container
        self.info_frame = ctk.CTkFrame(self, fg_color="transparent")
        
        # Row 0: ID | Date | Rating | Score | Favs
        created_at = post.get('created_at', '')[:10]
        score = post.get('score', 0)
        fav_count = post.get('fav_count', 0)
        rating = post.get('rating', '?').upper()
        info_text = f"ID: {self.id} | {created_at} | Rating: {rating} | Score: {score} | Favs: {fav_count}"
        self.info_label = ctk.CTkLabel(self.info_frame, text=info_text, anchor="w", font=ctk.CTkFont(size=12, weight="bold"))
        self.info_label.pack(fill="x", anchor="w")

        # Helper for truncation
        def truncate(text, limit=60):
            return (text[:limit] + '...') if len(text) > limit else text

        # Optimize: Combine details into one label to reduce widget count (critical for scroll performance)
        artist = truncate(post.get('tag_string_artist', 'Unknown'))
        copyright_ = truncate(post.get('tag_string_copyright', 'Unknown'))
        character = truncate(post.get('tag_string_character', 'Unknown'))
        
        details_text = f"Artist: {artist}\nCopyright: {copyright_}\nCharacter: {character}"
        
        self.details_label = ctk.CTkLabel(self.info_frame, text=details_text, anchor="w", justify="left", font=ctk.CTkFont(size=14))
        self.details_label.pack(fill="x", anchor="w", pady=(2,0))

        # Row 4: Tags Toggle
        # Optimize: Reorder tags (Artist -> Copyright -> Character -> General)
        t_artist = post.get('tag_string_artist', '')
        t_copy = post.get('tag_string_copyright', '')
        t_char = post.get('tag_string_character', '')
        t_gen = post.get('tag_string_general', '')
        
        # Fallback if specific keys are missing (though standard Danbooru has them)
        if not any([t_artist, t_copy, t_char, t_gen]):
             self.tags_text = post.get('tag_string', '')
        else:
             self.tags_text = f"{t_artist}\n{t_copy}\n{t_char}\n{t_gen}".strip()
             # Remove multiple newlines if some are empty
             while "\n\n" in self.tags_text:
                 self.tags_text = self.tags_text.replace("\n\n", "\n")
        self.tags_btn = ctk.CTkLabel(self.info_frame, text="[View All Tags]", text_color="cyan", cursor="hand2", font=ctk.CTkFont(size=14))
        self.tags_btn.pack(fill="x", anchor="w")
        self.tags_btn.bind("<Button-1>", self.toggle_tags)
        
        self.tags_display = None

        # Status
        self.status_label = ctk.CTkLabel(self, text="", width=60)
        self.status_label.grid(row=0, column=4, rowspan=2, padx=5)

        self.is_loaded = False
        self.is_loading = False
        
        # Layout
        self.preview_container.grid(row=0, column=1, rowspan=2, padx=5, pady=5, sticky="n")
        self.info_frame.grid(row=0, column=2, rowspan=2, sticky="nsew", padx=5, pady=5)

    def open_viewer(self):
        # Use large_file_url if available, else file_url, else fallback to preview
        target_url = self.post.get('large_file_url') or self.post.get('file_url') or self.preview_url
        ImageViewer(self.winfo_toplevel(), target_url, self.id)

    def toggle_tags(self, event=None):
        if self.tags_display:
            self.tags_display.destroy()
            self.tags_display = None
            self.tags_btn.configure(text="[View All Tags]")
            # Restore row span or just leave it, grid handles flexible height
        else:
            self.tags_display = ctk.CTkLabel(self, text=self.tags_text, wraplength=400, justify="left", text_color="gray70", font=ctk.CTkFont(size=14))
            # Grid below tags button
            self.tags_display.grid(row=2, column=2, padx=5, pady=5, sticky="w")
            self.tags_btn.configure(text="[Hide Tags]")

    def on_select(self):
        if self.selection_callback:
            self.selection_callback()
            
    def set_status(self, text, color):
        self.status_label.configure(text=text, text_color=color)
        
    def update_progress(self, value):
        pass

    def load_thumbnail(self):
        if self.is_loaded or self.is_loading: return
        self.is_loading = True
        threading.Thread(target=self._download_thumbnail, daemon=True).start()

    def _download_thumbnail(self):
        try:
            # Check cache first
            cached_img = self.cache.load(self.id)
            if cached_img:
                cached_img.thumbnail((100, 100))
                ctk_img = ctk.CTkImage(light_image=cached_img, dark_image=cached_img, size=cached_img.size)
                self.after(0, lambda: self._update_thumb_ui(ctk_img))
                if self.on_load_finish: self.after(0, self.on_load_finish)
                return

            response = requests.get(self.preview_url, timeout=10)
            if response.status_code == 200:
                img_data = BytesIO(response.content)
                
                # Save to cache
                self.cache.save(self.id, img_data)
                
                img = Image.open(img_data)
                img.thumbnail((100, 100))
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                
                self.after(0, lambda: self._update_thumb_ui(ctk_img))
                if self.on_load_finish: self.after(0, self.on_load_finish)
                return
        except Exception as e:
            print(f"Thumbnail error: {e}")
        
        self.is_loading = False
        self.after(0, lambda: self.thumb_label.configure(text="Error"))
        if self.on_load_finish: self.after(0, self.on_load_finish)

    def _update_thumb_ui(self, ctk_img):
        try:
            if self.winfo_exists():
                self.thumb_label.configure(image=ctk_img, text="")
                self.is_loaded = True
                self.is_loading = False
        except:
            pass

class ImageViewer(ctk.CTkToplevel):
    def __init__(self, parent, image_url, post_id):
        super().__init__(parent)
        self.title(f"Image Viewer - {post_id}")
        self.geometry("800x800")
        
        self.image_url = image_url
        self.post_id = post_id
        
        self.canvas = ctk.CTkCanvas(self, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        self.original_image = None
        self.tk_image = None
        self.scale = 1.0
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.click_start_x = 0
        self.click_start_y = 0
        self.offset_x = 0
        self.offset_y = 0
        self.is_zoomed = False # Toggle state

        # Bindings
        self.bind("<Escape>", lambda e: self.destroy())
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Configure>", self.on_resize)
        
        # Ensure window gets focus
        self.after(100, lambda: self.lift())
        self.after(100, lambda: self.focus_force())
        
        threading.Thread(target=self.load_image, daemon=True).start()

    def load_image(self):
        try:
            response = requests.get(self.image_url, stream=True, timeout=30)
            response.raise_for_status()
            
            img_data = BytesIO(response.content)
            self.original_image = Image.open(img_data)
            
            self.after(0, self.fit_to_window)
            
        except Exception as e:
            print(f"Error loading image: {e}")

    def fit_to_window(self, event=None):
        if not self.original_image or self.is_zoomed: return
        
        # Calculate scale to fit
        win_w = self.canvas.winfo_width()
        win_h = self.canvas.winfo_height()
        
        if win_w <= 1 or win_h <= 1: return # Wait for valid geometry
        
        img_w, img_h = self.original_image.size
        scale_w = win_w / img_w
        scale_h = win_h / img_h
        self.scale = min(scale_w, scale_h)
        
        self.offset_x = (win_w - img_w * self.scale) / 2
        self.offset_y = (win_h - img_h * self.scale) / 2
        
        self.redraw()

    def redraw(self):
        if not self.original_image: return
        
        img_w = int(self.original_image.width * self.scale)
        img_h = int(self.original_image.height * self.scale)
        
        if img_w <= 0 or img_h <= 0: return
        
        resized = self.original_image.resize((img_w, img_h), Image.Resampling.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(resized)
        
        self.canvas.delete("all")
        self.canvas.create_image(self.offset_x, self.offset_y, anchor="nw", image=self.tk_image)

    def on_click(self, event):
        self.focus_set()
        self.pan_start_x = event.x
        self.pan_start_y = event.y
        self.click_start_x = event.x
        self.click_start_y = event.y

    def on_drag(self, event):
        if self.is_zoomed:
            dx = event.x - self.pan_start_x
            dy = event.y - self.pan_start_y
            self.offset_x += dx
            self.offset_y += dy
            self.pan_start_x = event.x
            self.pan_start_y = event.y
            self.redraw()

    def on_release(self, event):
        # If moved less than 5 pixels from INITIAL click, treat as click
        if abs(event.x - self.click_start_x) < 5 and abs(event.y - self.click_start_y) < 5:
            # Check if click is within image bounds
            if self.original_image:
                img_w = self.original_image.width * self.scale
                img_h = self.original_image.height * self.scale
                
                if (self.offset_x <= event.x <= self.offset_x + img_w) and \
                   (self.offset_y <= event.y <= self.offset_y + img_h):
                    self.toggle_zoom(event)

    def toggle_zoom(self, event):
        self.is_zoomed = not self.is_zoomed
        
        if self.is_zoomed:
            # Zoom in (100% or larger)
            self.scale = 1.0 
            # Center on click? For now just center image
            win_w = self.canvas.winfo_width()
            win_h = self.canvas.winfo_height()
            img_w, img_h = self.original_image.size
            
            # Center the image
            self.offset_x = (win_w - img_w) / 2
            self.offset_y = (win_h - img_h) / 2
            
            # If image is smaller than window, maybe zoom more? 
            # But user said "enlarge", so 100% is usually good start.
            
        else:
            # Fit to window
            self.fit_to_window()
            
        self.redraw()

    def on_resize(self, event):
        if not self.is_zoomed:
            self.fit_to_window()

    def on_resize(self, event):
        if not self.is_zoomed:
            self.fit_to_window()

class ConfirmationDialog(ctk.CTkToplevel):
    def __init__(self, parent, title, message):
        super().__init__(parent)
        self.title(title)
        self.geometry("400x250")
        self.resizable(False, False)
        
        self.result = False
        self.dont_ask_again = False
        
        # UI
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Message
        self.msg_label = ctk.CTkLabel(self, text=message, wraplength=350, font=ctk.CTkFont(size=14))
        self.msg_label.grid(row=0, column=0, padx=20, pady=20)
        
        # Checkbox
        self.checkbox_var = ctk.BooleanVar(value=False)
        self.checkbox = ctk.CTkCheckBox(self, text="Don't ask again", variable=self.checkbox_var)
        self.checkbox.grid(row=1, column=0, padx=20, pady=(0, 20))
        
        # Buttons
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.grid(row=2, column=0, padx=20, pady=20, sticky="ew")
        self.btn_frame.grid_columnconfigure((0, 1), weight=1)
        
        self.yes_btn = ctk.CTkButton(self.btn_frame, text="Yes", command=self.on_yes, fg_color="green", width=100)
        self.yes_btn.grid(row=0, column=0, padx=10)
        
        self.no_btn = ctk.CTkButton(self.btn_frame, text="No", command=self.on_no, fg_color="darkred", width=100)
        self.no_btn.grid(row=0, column=1, padx=10)
        
        self.transient(parent)
        self.grab_set()
        self.focus_force()
        self.wait_window()
        
    def on_yes(self):
        self.result = True
        self.dont_ask_again = self.checkbox_var.get()
        self.destroy()
        
    def on_no(self):
        self.result = False
        self.destroy()

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, current_username, current_apikey, current_path, current_limit, current_safe_search, current_cache_days, current_cache_size, current_email):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("400x550")
        self.parent = parent
        
        self.grid_columnconfigure(1, weight=1)

        # Username
        ctk.CTkLabel(self, text="Username:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.username_entry = ctk.CTkEntry(self)
        self.username_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        if current_username:
            self.username_entry.insert(0, current_username)

        # Email
        ctk.CTkLabel(self, text="Email (for User-Agent):").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.email_entry = ctk.CTkEntry(self)
        self.email_entry.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        if current_email:
            self.email_entry.insert(0, current_email)

        # API Key
        ctk.CTkLabel(self, text="API Key:").grid(row=2, column=0, padx=10, pady=10, sticky="w")
        self.apikey_entry = ctk.CTkEntry(self, show="*")
        self.apikey_entry.grid(row=2, column=1, padx=10, pady=10, sticky="ew")
        if current_apikey:
            self.apikey_entry.insert(0, current_apikey)

        # Download Path
        ctk.CTkLabel(self, text="Download Path:").grid(row=3, column=0, padx=10, pady=10, sticky="w")
        self.path_entry = ctk.CTkEntry(self)
        self.path_entry.grid(row=3, column=1, padx=10, pady=10, sticky="ew")
        if current_path:
            self.path_entry.insert(0, current_path)
        
        self.browse_btn = ctk.CTkButton(self, text="Browse", width=60, command=self.browse_path)
        self.browse_btn.grid(row=3, column=2, padx=10, pady=10)

        # Post Limit
        ctk.CTkLabel(self, text="Post Limit (Max 30):").grid(row=4, column=0, padx=10, pady=10, sticky="w")
        self.limit_entry = ctk.CTkEntry(self)
        self.limit_entry.grid(row=4, column=1, padx=10, pady=10, sticky="ew")
        self.limit_entry.insert(0, str(current_limit))

        # Safe Search
        ctk.CTkLabel(self, text="Safe Search:").grid(row=5, column=0, padx=10, pady=10, sticky="w")
        self.safe_search_var = ctk.BooleanVar(value=current_safe_search)
        self.safe_search_chk = ctk.CTkCheckBox(self, text="Enable", variable=self.safe_search_var)
        self.safe_search_chk.grid(row=5, column=1, padx=10, pady=10, sticky="w")

        # Cache Settings
        ctk.CTkLabel(self, text="Cache Duration (Days, 0=Off):").grid(row=6, column=0, padx=10, pady=10, sticky="w")
        self.cache_days_entry = ctk.CTkEntry(self)
        self.cache_days_entry.grid(row=6, column=1, padx=10, pady=10, sticky="ew")
        self.cache_days_entry.insert(0, str(current_cache_days))

        ctk.CTkLabel(self, text="Cache Size (MB, Max=4096):").grid(row=7, column=0, padx=10, pady=10, sticky="w")
        self.cache_size_entry = ctk.CTkEntry(self)
        self.cache_size_entry.grid(row=7, column=1, padx=10, pady=10, sticky="ew")
        self.cache_size_entry.insert(0, str(current_cache_size))
        
        self.clear_cache_btn = ctk.CTkButton(self, text="Clear", width=60, command=self.clear_cache, fg_color="darkred")
        self.clear_cache_btn.grid(row=7, column=2, padx=10, pady=10)

        # Concurrency
        ctk.CTkLabel(self, text="Max Concurrent Downloads (1-32):").grid(row=8, column=0, padx=10, pady=10, sticky="w")
        self.concurrency_entry = ctk.CTkEntry(self)
        self.concurrency_entry.grid(row=8, column=1, padx=10, pady=10, sticky="ew")
        # Default to 8 if not passed (we will update App to pass it)
        try:
            current_max_workers = self.parent.max_workers
        except:
            current_max_workers = 8
        self.concurrency_entry.insert(0, str(current_max_workers))
        
        self.skip_download_confirmation = os.getenv("DANBOORU_SKIP_CONFIRMATION", "False").lower() == "true"

        # Buttons Frame
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.grid(row=9, column=0, columnspan=3, padx=20, pady=20)

        self.save_btn = ctk.CTkButton(self.btn_frame, text="Confirm", command=self.save_settings, fg_color="green", width=100)
        self.save_btn.pack(side="left", padx=10)

        self.cancel_btn = ctk.CTkButton(self.btn_frame, text="Cancel", command=self.destroy, fg_color="gray", width=100)
        self.cancel_btn.pack(side="right", padx=10)
        
        self.transient(parent)
        # self.grab_set() # Removed to allow closing main app
        self.focus_force()

        # Input Validation Bindings
        self.email_entry.bind("<FocusOut>", self.validate_email)
        self.limit_entry.bind("<FocusOut>", self.validate_limit)
        self.cache_days_entry.bind("<FocusOut>", self.validate_cache_days)
        self.cache_size_entry.bind("<FocusOut>", self.validate_cache_size)
        self.concurrency_entry.bind("<FocusOut>", self.validate_concurrency)

    def validate_email(self, event=None):
        value = self.email_entry.get().strip()
        if not value: return # Allow empty (defaults to unknown)
        # Simple regex for email format
        if not re.match(r"[^@]+@[^@]+\.[^@]+", value):
            tkinter.messagebox.showwarning("Invalid Input", "Please enter a valid email address.")
            self.email_entry.focus_set()

    def validate_limit(self, event=None):
        try:
            val = int(self.limit_entry.get())
            if val < 1 or val > 30:
                raise ValueError
        except ValueError:
            tkinter.messagebox.showwarning("Invalid Input", "Post Limit must be between 1 and 30.")
            self.limit_entry.delete(0, "end")
            self.limit_entry.insert(0, "20") # Default safe value
            # self.limit_entry.focus_set() # Avoid infinite loops

    def validate_cache_days(self, event=None):
        try:
            val = int(self.cache_days_entry.get())
            if val < 0:
                raise ValueError
        except ValueError:
            tkinter.messagebox.showwarning("Invalid Input", "Cache Duration must be 0 or greater (integer).")
            self.cache_days_entry.delete(0, "end")
            self.cache_days_entry.insert(0, "7")

    def validate_cache_size(self, event=None):
        try:
            val = int(self.cache_size_entry.get())
            if val < 0 or val > 4096:
                raise ValueError
        except ValueError:
            tkinter.messagebox.showwarning("Invalid Input", "Cache Size must be between 0 and 4096 MB.")
            self.cache_size_entry.delete(0, "end")
            self.cache_size_entry.insert(0, "500")

    def validate_concurrency(self, event=None):
        try:
            val = int(self.concurrency_entry.get())
            if val < 1 or val > 32:
                raise ValueError
        except ValueError:
            tkinter.messagebox.showwarning("Invalid Input", "Concurrent Downloads must be between 1 and 32.")
            self.concurrency_entry.delete(0, "end")
            self.concurrency_entry.insert(0, "8")

    def browse_path(self):
        folder = ctk.filedialog.askdirectory()
        if folder:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)

    def clear_cache(self):
        if tkinter.messagebox.askyesno("Clear Cache", "Are you sure you want to delete all cached thumbnails?"):
            self.parent.clear_cache()
            tkinter.messagebox.showinfo("Cache Cleared", "Thumbnail cache has been cleared.")

    def save_settings(self):
        username = self.username_entry.get()
        email = self.email_entry.get()
        apikey = self.apikey_entry.get()
        path = self.path_entry.get()
        try:
            limit = int(self.limit_entry.get())
            if limit > 30: limit = 30
            if limit < 1: limit = 1
        except:
            limit = 20
        
        safe_search = self.safe_search_var.get()

        try:
            cache_days = int(self.cache_days_entry.get())
            if cache_days < 0: cache_days = 0
            if cache_days > 30: cache_days = 30
        except:
            cache_days = 7

        try:
            cache_size = int(self.cache_size_entry.get())
            if cache_size < 10: cache_size = 10 # Absolute minimum
            if cache_size > 4096: cache_size = 4096
            
            if cache_size <= 50:
                if not tkinter.messagebox.askokcancel("Low Cache Size", 
                    "Setting the cache size to 50MB or less may cause frequent re-downloads and slower performance.\n\nDo you want to continue?"):
                    return
        except:
            cache_size = 500

        try:
            max_workers = int(self.concurrency_entry.get())
            if max_workers < 1: max_workers = 1
            if max_workers > 32: max_workers = 32
        except:
            max_workers = 8
        self.parent.update_settings(username, apikey, path, limit, safe_search, cache_days, cache_size, max_workers, email)
        self.destroy()

import sys

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class App(ctk.CTk):
    def __init__(self, username=None, apikey=None):
        super().__init__()
        self.title("Danbooru Downloader")
        self.geometry("1000x700")
        try:
            # Use ICO for Windows (Standard & Reliable)
            icon_path = resource_path("icon.ico")
            self.iconbitmap(icon_path)
        except Exception as e:
            print(f"Failed to load icon: {e}")
        
        self.toplevel_window = None
        load_dotenv()
        self.env_file = ".env"
        self.security = SecurityManager()

        self.username = self.security.decrypt(os.getenv("DANBOORU_USERNAME")) or ""
        self.apikey = self.security.decrypt(os.getenv("DANBOORU_APIKEY")) or ""
        self.email = self.security.decrypt(os.getenv("DANBOORU_EMAIL")) or "unknown@example.com"
        
        # Encrypted Path
        encrypted_path = os.getenv("DANBOORU_DOWNLOAD_PATH")
        decrypted_path = self.security.decrypt(encrypted_path)
        self.download_path = decrypted_path if decrypted_path else os.path.join(os.getcwd(), "downloads")

        try:
            self.preview_limit = int(os.getenv("DANBOORU_PREVIEW_LIMIT", "20"))
        except:
            self.preview_limit = 20
        
        # Encrypted Safe Search
        encrypted_safe_search = os.getenv("DANBOORU_SAFE_SEARCH")
        decrypted_safe_search = self.security.decrypt(encrypted_safe_search)
        # Handle default (decrypted_safe_search might be empty if env missing)
        safe_search_str = decrypted_safe_search if decrypted_safe_search else "False"
        self.safe_search = safe_search_str.lower() == "true"
        
        try:
            self.cache_days = int(os.getenv("DANBOORU_CACHE_DAYS", "7"))
            self.cache_size = int(os.getenv("DANBOORU_CACHE_SIZE", "500"))
        except:
            self.cache_days = 7
            self.cache_size = 500


        try:
            self.max_workers = int(os.getenv("DANBOORU_MAX_WORKERS", "8"))
        except:
            self.max_workers = 8

        self.skip_download_confirmation = os.getenv("DANBOORU_SKIP_CONFIRMATION", "False").lower() == "true"

        self.history_file = "search_history.json"
        self.search_history = self.load_history()

        self.cache = ThumbnailCache(max_days=self.cache_days, max_size_mb=self.cache_size)
        threading.Thread(target=self.cache.cleanup, daemon=True).start()

        self.api = DanbooruClient(self.username, self.apikey, self.username, self.email)
        self.downloader = DownloadManager(max_workers=self.max_workers)
        self.posts_frames = {} 
        self.selected_posts_data = {} # Persistence for selections: id -> post_data
        self.current_page = 1
        self.total_pages = 1
        self.total_posts = 0
        self.current_tags = ""


        self.bind("<Button-1>", self.on_global_click)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self._setup_ui()
        self.after(500, self.check_visibility)

    def on_closing(self):
        if self.downloader:
            self.downloader.stop_all()
        self.destroy()

    def on_global_click(self, event):
        try:
            widget = event.widget
            # If clicked widget is not an entry, focus the main window (unfocus entry)
            # CTkEntry internal widget usually contains 'entry' in its name
            if "entry" not in str(widget).lower():
                self.focus()
        except:
            pass

    def check_visibility(self):
        try:
            # Scrollable frame visible area
            view_top = self.scrollable_frame.winfo_rooty()
            view_height = self.scrollable_frame.winfo_height()
            
            if view_top is not None and view_height > 10: # Ensure valid geometry
                view_bottom = view_top + view_height
                
                for frame in list(self.posts_frames.values()):
                    if frame.is_loaded or frame.is_loading:
                        continue
                    
                    # Check if frame is visible
                    try:
                        frame_top = frame.winfo_rooty()
                        frame_height = frame.winfo_height()
                        
                        if frame_top is None: continue
                        
                        frame_bottom = frame_top + frame_height
                        
                        # Simple overlap check with some buffer
                        if (frame_bottom >= view_top - 500) and (frame_top <= view_bottom + 500):
                            threading.Thread(target=frame.load_thumbnail, daemon=True).start()
                    except:
                        pass
        except Exception as e:
            print(f"Visibility check error: {e}")

        self.after(300, self.check_visibility)

    def update_local_file_count(self):
        try:
            if not os.path.exists(self.download_path):
                self.local_files_label.configure(text="Local Files: 0")
                return

            count = 0
            with os.scandir(self.download_path) as entries:
                for entry in entries:
                     if entry.is_file() and re.match(r"^\d+\..+$", entry.name):
                        count += 1
            
            self.after(0, lambda: self.local_files_label.configure(text=f"Local Files: {count}"))
        except Exception as e:
            print(f"Error counting local files: {e}")

    def _setup_ui(self):
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=4, sticky="nsew")

        self.logo_label = ctk.CTkLabel(self.sidebar, text="Danbooru\nDownloader", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.settings_btn = ctk.CTkButton(self.sidebar, text="Settings", command=self.open_settings, fg_color="gray")
        self.settings_btn.grid(row=1, column=0, padx=20, pady=10)

        self.tags_entry = ctk.CTkComboBox(self.sidebar, values=self.search_history)
        if not self.search_history:
            self.tags_entry.set("") # Clear if empty, otherwise it selects first value
        else:
            self.tags_entry.set("") # Or set to empty string to act like placeholder
        self.tags_entry.grid(row=2, column=0, padx=20, pady=10)
        self.tags_entry.bind("<Return>", lambda e: (self.start_search(), "break")[1])
        
        # Bind Down arrow to open dropdown
        try:
            self.tags_entry._entry.bind("<Down>", self.open_history_dropdown)
        except:
            pass
        # ComboBox entry binding is a bit different, we might need to bind to the internal entry
        # But CTkComboBox doesn't expose it easily for binding <Return>. 
        # Actually, CTkComboBox does not support bind directly on the widget for entry events in the same way.
        # We can try to bind to the command or just rely on the button.
        # However, for convenience, let's try to bind to the root and check focus? No, that's messy.
        # Let's just keep the button for now, or try to access the entry.
        # self.tags_entry._entry.bind("<Return>", ...) is possible but private API.
        # Let's stick to standard usage first.

        self.search_btn = ctk.CTkButton(self.sidebar, text="Search", command=self.start_search)
        self.search_btn.grid(row=3, column=0, padx=20, pady=10)
        
        # Spacer to push buttons to bottom
        self.sidebar.grid_rowconfigure(4, weight=1)

        self.download_btn = ctk.CTkButton(self.sidebar, text="Download", command=self.start_download_selected, state="disabled", fg_color="green")
        self.download_btn.grid(row=5, column=0, padx=20, pady=10)

        self.open_folder_btn = ctk.CTkButton(self.sidebar, text="Open Folder", command=self.open_download_folder, fg_color="gray")
        self.open_folder_btn.grid(row=6, column=0, padx=20, pady=10)

        # Global Key Bindings
        self.bind("q", self.focus_tags_entry)
        self.bind("Q", self.focus_tags_entry)

        self.path_label = ctk.CTkLabel(self.sidebar, text=f"Path: ...{self.download_path[-20:]}", font=ctk.CTkFont(size=10))
        self.path_label.grid(row=7, column=0, padx=5, pady=5)

        # Top Bar
        self.top_bar = ctk.CTkFrame(self, height=50, corner_radius=0)
        self.top_bar.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        self.top_bar.grid_columnconfigure(2, weight=1)

        self.select_all_var = ctk.BooleanVar(value=False)
        self.select_all_chk = ctk.CTkCheckBox(self.top_bar, text="Select All", variable=self.select_all_var, command=self.toggle_select_all)
        self.select_all_chk.grid(row=0, column=0, padx=10, pady=10)

        self.repair_mode_var = ctk.BooleanVar(value=False)
        self.repair_mode_chk = ctk.CTkCheckBox(self.top_bar, text="Full Scan / Repair", variable=self.repair_mode_var)
        self.repair_mode_chk.grid(row=0, column=1, padx=10, pady=10)

        self.local_files_label = ctk.CTkLabel(self.top_bar, text="Local Files: ...")
        self.local_files_label.grid(row=0, column=2, padx=10, pady=10)

        self.bulk_download_btn = ctk.CTkButton(self.top_bar, text="Download All", command=self.start_bulk_download, fg_color="darkred", width=120)
        self.bulk_download_btn.grid(row=0, column=3, padx=10, pady=10)

        # Main Area
        self.scrollable_frame = ctk.CTkScrollableFrame(self, label_text="Results")
        self.scrollable_frame.grid(row=1, column=1, sticky="nsew", padx=10, pady=5)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Bottom Bar
        self.bottom_bar = ctk.CTkFrame(self, height=50, corner_radius=0)
        self.bottom_bar.grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        self.bottom_bar.grid_columnconfigure(1, weight=1) # Center weight
        
        # Pagination Controls
        self.pagination_frame = ctk.CTkFrame(self.bottom_bar, fg_color="transparent")
        self.pagination_frame.grid(row=0, column=1, padx=10, pady=5)
        
        self.prev_btn = ctk.CTkButton(self.pagination_frame, text="< Prev", command=self.prev_page, width=60, state="disabled")
        self.prev_btn.pack(side="left", padx=5)
        
        self.go_btn = ctk.CTkButton(self.pagination_frame, text="Go", command=self.go_to_page, width=40)
        self.go_btn.pack(side="left", padx=5)

        self.page_entry = ctk.CTkEntry(self.pagination_frame, width=50, justify="center")
        self.page_entry.pack(side="left", padx=5)
        self.page_entry.bind("<Return>", lambda e: (self.go_to_page(), "break")[1])
        
        self.total_pages_label = ctk.CTkLabel(self.pagination_frame, text="/ 1", width=40)
        self.total_pages_label.pack(side="left", padx=5)
        
        self.next_btn = ctk.CTkButton(self.pagination_frame, text="Next >", command=self.next_page, width=60, state="disabled")
        self.next_btn.pack(side="left", padx=5)

        # Status Panel
        self.status_frame = ctk.CTkFrame(self.bottom_bar, fg_color="transparent")
        self.status_frame.grid(row=0, column=2, padx=10, pady=5, sticky="e")

        self.progress_label = ctk.CTkLabel(self.status_frame, text="")
        self.progress_label.pack(side="left", padx=10)

        self.pause_btn = ctk.CTkButton(self.status_frame, text="Pause", command=self.toggle_pause, width=60, state="disabled", fg_color="orange")
        self.pause_btn.pack(side="left", padx=5)

        self.cancel_btn = ctk.CTkButton(self.status_frame, text="Cancel", command=self.cancel_download, width=60, state="disabled", fg_color="red")
        self.cancel_btn.pack(side="left", padx=5)

        # Loading Overlay (Initially hidden)
        self.loading_overlay = ctk.CTkFrame(self, fg_color="transparent") # Transparent container
        # Use a large font for the spinner
        self.loading_label = ctk.CTkLabel(self.loading_overlay, text="⠋", font=ctk.CTkFont(size=48),
                                          fg_color=("white", "gray20"), corner_radius=10, width=80, height=80)
        self.loading_label.place(relx=0.5, rely=0.5, anchor="center")
        
        self.spinner_running = False
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_idx = 0
        
    def start_spinner(self):
        if not self.spinner_running:
            self.spinner_running = True
            self.loading_overlay.grid(row=1, column=1, sticky="nsew")
            self.loading_label.lift()
            self.animate_spinner()
            
    def stop_spinner(self):
        self.spinner_running = False
        self.loading_overlay.grid_forget()
        
    def animate_spinner(self):
        if not self.spinner_running: return
        
        self.loading_label.configure(text=self.spinner_chars[self.spinner_idx])
        self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_chars)
        self.after(80, self.animate_spinner)

    def open_history_dropdown(self, event=None):
        try:
            self.tags_entry._open_dropdown_menu()
        except Exception as e:
            print(f"Error opening dropdown: {e}")

    def open_settings(self):
        if self.toplevel_window is None or not self.toplevel_window.winfo_exists():
            self.toplevel_window = SettingsDialog(self, self.username, self.apikey, self.download_path, self.preview_limit, self.safe_search, self.cache_days, self.cache_size, self.email)
        else:
            self.toplevel_window.focus()

    def update_settings(self, username, apikey, path, limit, safe_search, cache_days, cache_size, max_workers, email):
        self.username = username
        self.apikey = apikey
        self.download_path = path
        self.preview_limit = limit
        self.safe_search = safe_search
        self.cache_days = cache_days
        self.cache_size = cache_size
        self.email = email
        
        # Update cache settings
        self.cache.max_days = cache_days
        self.cache.max_size_mb = cache_size
        
        display_path = path if len(path) < 20 else f"...{path[-20:]}"
        self.path_label.configure(text=f"Path: {display_path}")
        self.update_local_file_count()
        
        self.api = DanbooruClient(self.username, self.apikey, self.username, self.email)

        # Update Downloader if max_workers changed
        if max_workers != self.max_workers:
            self.max_workers = max_workers
            self.downloader = DownloadManager(max_workers=self.max_workers)

        if not os.path.exists(self.env_file):
            open(self.env_file, 'w').close()
        
        if username: set_key(self.env_file, "DANBOORU_USERNAME", self.security.encrypt(username))
        if apikey: set_key(self.env_file, "DANBOORU_APIKEY", self.security.encrypt(apikey))
        if email: set_key(self.env_file, "DANBOORU_EMAIL", self.security.encrypt(email))
        if path: set_key(self.env_file, "DANBOORU_DOWNLOAD_PATH", self.security.encrypt(path))
        set_key(self.env_file, "DANBOORU_PREVIEW_LIMIT", str(limit))
        set_key(self.env_file, "DANBOORU_SAFE_SEARCH", self.security.encrypt(str(safe_search)))
        set_key(self.env_file, "DANBOORU_CACHE_DAYS", str(cache_days))
        set_key(self.env_file, "DANBOORU_CACHE_SIZE", str(cache_size))
        set_key(self.env_file, "DANBOORU_MAX_WORKERS", str(max_workers))
        
        # Also update the skip confirmation setting while we are here, to be safe, 
        # although it's usually updated separately.
        self.update_settings_confirmation_skip(self.skip_download_confirmation)

    def update_settings_confirmation_skip(self, skip):
        """Helper to update just the skip confirmation setting in .env"""
        try:
            env_path = os.path.join(os.getcwd(), ".env")
            lines = []
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            
            new_lines = []
            found = False
            for line in lines:
                if line.startswith("DANBOORU_SKIP_CONFIRMATION="):
                    new_lines.append(f"DANBOORU_SKIP_CONFIRMATION={skip}\n")
                    found = True
                else:
                    new_lines.append(line)
            
            if not found:
                new_lines.append(f"DANBOORU_SKIP_CONFIRMATION={skip}\n")
                
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
                
        except Exception as e:
            print(f"Failed to save confirmation setting: {e}")

    def load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    encrypted_data = f.read()
                    
                    # Try decrypting (handling legacy plain JSON)
                    try:
                        decrypted_data = self.security.decrypt(encrypted_data)
                        return json.loads(decrypted_data)
                    except:
                         # Fallback for migration: try loading as plain JSON
                        f.seek(0)
                        return json.load(f)
            except:
                pass
        return []

    def save_history(self):
        try:
            json_str = json.dumps(self.search_history, ensure_ascii=False, indent=2)
            encrypted_data = self.security.encrypt(json_str)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                f.write(encrypted_data)
        except Exception as e:
            print(f"Error saving history: {e}")

    def update_history(self, query):
        if not query: return
        
        # Remove if exists to move to top
        if query in self.search_history:
            self.search_history.remove(query)
        
        self.search_history.insert(0, query)
        
        # Keep max 5
        if len(self.search_history) > 5:
            self.search_history = self.search_history[:5]
            
        self.tags_entry.configure(values=self.search_history)
        self.save_history()

    def open_download_folder(self):
        if os.path.exists(self.download_path):
            os.startfile(self.download_path)



    def toggle_select_all(self):
        val = self.select_all_var.get()
        for frame in self.posts_frames.values():
            if val:
                if not frame.checkbox.get():
                    frame.checkbox.select()
                    self.on_post_select(frame.post, True)
            else:
                if frame.checkbox.get():
                    frame.checkbox.deselect()
                    self.on_post_select(frame.post, False)
        self.update_download_button_state()

    def on_post_select(self, post, is_selected):
        if is_selected:
            self.selected_posts_data[post['id']] = post
        else:
            self.selected_posts_data.pop(post['id'], None)
        self.update_download_button_state()

    def update_download_button_state(self):
        if len(self.selected_posts_data) > 0:
            self.download_btn.configure(state="normal", text=f"Download ({len(self.selected_posts_data)})")
        else:
            self.download_btn.configure(state="disabled", text="Download")

    def clear_cache(self):
        self.cache.clear_all()
        # Reload visible thumbnails? Maybe not necessary, they will just reload if needed.

    def start_search(self):
        self.current_tags = self.tags_entry.get().lower().strip()
        self.update_history(self.current_tags)
        
        if self.safe_search:
            self.current_tags += " is:sfw "
            
        self.current_page = 1
        self.selected_posts_data.clear() 
        self.select_all_chk.deselect()
        self.update_download_button_state()
        
        self._clear_results()
        self.scrollable_frame.configure(label_text="Results")
        self.download_btn.configure(state="disabled")
        
        self.prev_btn.configure(state="disabled")
        self.next_btn.configure(state="disabled")
        self.page_entry.delete(0, "end")
        self.page_entry.insert(0, "1")
        self.total_pages_label.configure(text="/ ...")

        self.update_local_file_count()
        
        threading.Thread(target=self._search_thread_init, daemon=True).start()

    def _search_thread_init(self):
        # Fetch count first
        try:
            total_posts = self.api.get_post_counts(self.current_tags)
            self.total_posts = total_posts
            import math
            self.total_pages = math.ceil(total_posts / self.preview_limit)
            if self.total_pages < 1: self.total_pages = 1
            self.after(0, lambda: self.total_pages_label.configure(text=f"/ {self.total_pages}"))
        except:
            self.total_pages = 1
            self.after(0, lambda: self.total_pages_label.configure(text="/ ?"))

        self._search_thread()

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._load_page()

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._load_page()

    def go_to_page(self):
        try:
            page = int(self.page_entry.get())
            if 1 <= page <= self.total_pages:
                self.current_page = page
                self._load_page()
            else:
                self.page_entry.delete(0, "end")
                self.page_entry.insert(0, str(self.current_page))
        except:
            self.page_entry.delete(0, "end")
            self.page_entry.insert(0, str(self.current_page))

    def _load_page(self):
        self.prev_btn.configure(state="disabled")
        self.next_btn.configure(state="disabled")
        self.go_btn.configure(state="disabled")
        self.page_entry.delete(0, "end")
        self.page_entry.insert(0, str(self.current_page))
        
        # self.bulk_download_btn.configure(text="Download All Results") # Removed dynamic text change
        
        self.selected_posts_data.clear() # Clear selections on new search
        self._clear_results()
        
        # Scroll to top
        try:
            self.scrollable_frame._parent_canvas.yview_moveto(0)
        except:
            pass

        threading.Thread(target=self._search_thread, daemon=True).start()

    def _clear_results(self):
        # Cancel pending render task if any
        if hasattr(self, 'render_task') and self.render_task:
            try:
                self.after_cancel(self.render_task)
            except:
                pass
            self.render_task = None

        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.posts_frames.clear()

    def on_image_load_finish(self):
        self.images_loaded_count += 1
        self.loading_label.configure(text=f"Loading images... ({self.images_loaded_count}/{self.images_to_load_total})")
        
        if self.images_loaded_count >= self.images_to_load_total:
            self.loading_overlay.grid_forget()

    def _search_thread(self):
        try:
            posts = self.api.fetch_posts(self.current_tags, limit=self.preview_limit, page=self.current_page)
            
            # Filter posts that have file_url (others are skipped in display)
            valid_posts = [p for p in posts if 'file_url' in p]
            self.images_to_load_total = len(valid_posts)
            self.images_loaded_count = 0
            
            if self.images_to_load_total == 0:
                 self.after(0, lambda: self.loading_overlay.grid_forget())

            self.after(0, self._display_results, posts)
        except Exception as e:
            print(f"Search error: {e}")
            self.after(0, lambda: self.loading_overlay.grid_forget())

    def _display_results(self, posts):
        self._clear_results()
        # Incremental Rendering to prevent UI freeze
        # Render a small batch, then schedule the next batch
        
        # Enable UI immediately to allow interaction
        self.search_btn.configure(text="Search", state="normal")
        
        # Pagination - Update state immediately
        if self.current_page > 1:
            self.prev_btn.configure(state="normal")
        else:
            self.prev_btn.configure(state="disabled")
            
        if self.current_page < self.total_pages:
            self.next_btn.configure(state="normal")
        else:
            self.next_btn.configure(state="disabled")
        self.go_btn.configure(state="normal")
        
        # Start rendering
        self._render_batch(posts, 0)
        
    def _render_batch(self, posts, index, batch_size=5):
        # Stop if index is out of bounds
        if index >= len(posts):
            self.render_task = None
            self.scrollable_frame.configure(label_text=f"Results ({self.total_posts:,})")
            return

        end_index = min(index + batch_size, len(posts))
        batch = posts[index:end_index]
        
        # Render current batch
        for post in batch:
            if 'file_url' not in post:
                continue
            
            # Safety check
            if not self.scrollable_frame.winfo_exists(): return

            frame = PostFrame(self.scrollable_frame, post=post, cache=self.cache, 
                            selection_callback=lambda p=post, f=None: self.on_post_select(p, self.posts_frames[p['id']].checkbox.get()),
                            on_load_finish=self.on_image_load_finish)
            frame.pack(fill="x", padx=5, pady=5)
            self.posts_frames[post['id']] = frame
            
            frame.load_thumbnail()
        
        # Update progress label
        self.loading_label.configure(text=f"Loading images... ({self.images_loaded_count}/{self.images_to_load_total})")

        # Schedule next batch and store ID for cancellation
        # 10ms delay
        self.render_task = self.after(10, self._render_batch, posts, end_index, batch_size)
            
        self.update_download_button_state()
        self.update_idletasks()
        self.after(100, self.check_visibility)

    def start_download_selected(self):
        selected_posts = list(self.selected_posts_data.values())
        
        if not selected_posts:
            return

        # Query Mismatch Check for Selected Download
        resume_mgr = ResumeManager(self.download_path)
        stored_query = resume_mgr.get_query()
        if stored_query and stored_query.lower() != self.current_tags.lower():
            if not tkinter.messagebox.askyesno("Query Mismatch", 
                f"Warning: The current query '{self.current_tags}' differs from the stored resume query '{stored_query}'.\n\n"
                "Mixing results in the same folder is not recommended.\n"
                "Do you want to continue anyway?"):
                return

        self.download_btn.configure(state="disabled")
        threading.Thread(target=self._download_thread, args=(selected_posts,), daemon=True).start()

    def focus_tags_entry(self, event):
        try:
            focused = self.focus_get()
            # If focus is already on an entry (typing), ignore
            if focused and "entry" in str(focused).lower():
                return
            
            self.tags_entry.focus_set()
            return "break" # Prevent 'q' from being typed
        except:
            pass

    def start_bulk_download(self):
        # Determine tags: Always use entry text to allow "Direct Download" from changed query
        tags = self.tags_entry.get()
        # If entry is empty but we have current_tags (e.g. user cleared entry?), fallback or just use empty check
        if not tags and self.current_tags:
            tags = self.current_tags
        
        if not tags or not tags.strip():
            tkinter.messagebox.showwarning("Input Error", "Please enter tags to download.")
            return
        
        # Always fetch count for confirmation
        count = self.api.get_post_count(tags)
        if count == 0:
            tkinter.messagebox.showinfo("No Posts", "No posts found for these tags.")
            return
            
        # Skip Confirmation Logic
        if not getattr(self, "skip_download_confirmation", False):
             dialog = ConfirmationDialog(self, "Confirm Download", f"Query: {tags}\nTotal Posts: {count:,}\n\nDo you want to proceed with the download?")
             if not dialog.result:
                 return
             
             if dialog.dont_ask_again:
                 self.skip_download_confirmation = True
                 self.update_settings_confirmation_skip(True)

        # Query Mismatch Check (Moved from thread)
        resume_mgr = ResumeManager(self.download_path, self.security)
        stored_query = resume_mgr.get_query()
        if stored_query and stored_query.lower() != tags.lower():
            if not tkinter.messagebox.askyesno("Query Mismatch", 
                f"Warning: The current query '{tags}' differs from the stored resume query '{stored_query}'.\n\n"
                "Mixing results in the same folder is not recommended.\n"
                "Do you want to continue anyway?"):
                return

        # If we started from entry (no current_tags), set it now
        if not self.current_tags:
            self.current_tags = tags
            # self.bulk_download_btn.configure(text="Download All Results") # No need
            
        # Bulk download logic: fetch all pages in background
        self.bulk_download_btn.configure(state="disabled", text="Starting...")
        threading.Thread(target=self._bulk_download_thread, daemon=True).start()

    def toggle_pause(self):
        is_paused = self.downloader.toggle_pause()
        if is_paused:
            self.pause_btn.configure(text="Resume", fg_color="green")
        else:
            self.pause_btn.configure(text="Pause", fg_color="orange")

    def cancel_download(self):
        self.downloader.stop_all()
        self.download_btn.configure(state="normal")
        self.bulk_download_btn.configure(state="normal", text="Download All")
        self.pause_btn.configure(state="disabled", text="Pause", fg_color="orange")
        self.cancel_btn.configure(state="disabled")
        self.progress_label.configure(text="Cancelled")

    def clear_all_selections(self):
        self.selected_posts_data.clear()
        self.select_all_chk.deselect()
        for frame in self.posts_frames.values():
            if frame.checkbox.get():
                frame.checkbox.deselect()
        self.update_download_button_state()

    def _download_thread(self, posts_to_download):
        self.downloader.stop_event.clear() # Reset stop flag
        self.after(0, lambda: self.pause_btn.configure(state="normal"))
        self.after(0, lambda: self.cancel_btn.configure(state="normal"))
        
        total = len(posts_to_download)
        completed = 0
        
        futures = []
        for post in posts_to_download:
            if self.downloader.stop_event.is_set(): break
            
            pid = post['id']
            frame = self.posts_frames.get(pid)
            if not frame: continue
            
            file_url = post.get('file_url')
            file_ext = post.get('file_ext', 'jpg')
            save_path = os.path.join(self.download_path, f"{pid}.{file_ext}")
            
            frame.set_status("Downloading...", "orange")
            
            def on_progress(p, f=frame):
                f.after(0, f.update_progress, p)
                
            def on_complete(path, skipped, f=frame):
                nonlocal completed
                completed += 1
                status = "Skipped" if skipped else "Done"
                color = "yellow" if skipped else "green"
                f.after(0, f.set_status, status, color)
                f.after(0, f.update_progress, 1.0)
                # Update button and status label
                self.after(0, lambda c=completed, t=total: self.download_btn.configure(text=f"Download ({c}/{t})"))
                self.after(0, lambda c=completed, t=total: self.progress_label.configure(text=f"Downloaded: {c}/{t}"))

            def on_error(err, f=frame):
                nonlocal completed
                completed += 1
                f.after(0, f.set_status, "Error", "red")
                print(f"Error downloading {pid}: {err}")
                self.after(0, lambda c=completed, t=total: self.download_btn.configure(text=f"Download ({c}/{t})"))
                self.after(0, lambda c=completed, t=total: self.progress_label.configure(text=f"Downloaded: {c}/{t}"))

            future = self.downloader.executor.submit(
                self.downloader.download_image,
                file_url,
                save_path,
                on_progress,
                on_complete,
                on_error
            )
            futures.append(future)

        for f in futures:
            f.result()
            
        self.after(0, lambda: self.download_btn.configure(state="normal", text=f"Download ({len(self.selected_posts_data)})"))
        self.after(0, lambda: self.pause_btn.configure(state="disabled"))
        self.after(0, lambda: self.cancel_btn.configure(state="disabled"))
        if not self.downloader.stop_event.is_set():
             self.after(0, lambda: self.progress_label.configure(text=f"Completed: {completed} files"))
             self.after(0, self.clear_all_selections)
             self.update_local_file_count()

    def _bulk_download_thread(self):
        self.downloader.stop_event.clear() # Reset stop flag
        self.after(0, lambda: self.pause_btn.configure(state="normal"))
        self.after(0, lambda: self.cancel_btn.configure(state="normal"))
        
        resume_mgr = ResumeManager(self.download_path, self.security)
        stored_query = resume_mgr.get_query()
        saved_state = resume_mgr.get_state()
        saved_top_id = saved_state.get("top_id")
        saved_last_page = saved_state.get("last_page")
        saved_is_complete = saved_state.get("is_complete")
        
        saved_last_page = saved_state.get("last_page")
        saved_is_complete = saved_state.get("is_complete")
        
        # Query Mismatch Check REMOVED (Handled in start_bulk_download)

        repair_mode = self.repair_mode_var.get()
        page = 1
        limit = 100 
        downloaded_count = 0
        
        # Runtime State
        current_run_top_id = None
        gap_bridged = False
        
        # If repair mode is ON, we ignore resume logic and scan everything.
        # If repair mode is OFF, we use Smart Resume.
        
        if not repair_mode and saved_last_page and saved_last_page > 1:
            # We start at page 1 to check for new posts, but we know we have a jump target.
            pass
        elif not repair_mode and saved_is_complete:
            # We just check for new posts.
            pass
        
        def on_item_complete(path, skipped):
            nonlocal downloaded_count
            downloaded_count += 1
            self.after(0, lambda: self.bulk_download_btn.configure(text=f"Downloading ({downloaded_count})"))
            self.after(0, lambda: self.progress_label.configure(text=f"Page: {page} | Downloaded: {downloaded_count}"))

        def on_item_error(err):
            print(f"Bulk download error: {err}")

        while True:
            if self.downloader.stop_event.is_set(): break
            
            self.after(0, lambda p=page, c=downloaded_count: self.bulk_download_btn.configure(text=f"Downloading ({c})"))
            self.after(0, lambda p=page, c=downloaded_count: self.progress_label.configure(text=f"Page: {p} | Downloaded: {c}"))
            
            try:
                posts = self.api.fetch_posts(self.current_tags, limit=limit, page=page)
                if not posts:
                    # End of results
                    if not repair_mode:
                        # Mark as complete only if we reached the end naturally
                        resume_mgr.save(self.current_tags, current_run_top_id or saved_top_id, page, True)
                    break
                
                # Capture top_id of this run (first post of first page)
                if current_run_top_id is None and len(posts) > 0:
                    current_run_top_id = posts[0]['id']

                # Smart Resume Logic (Gap Bridge)
                if not repair_mode and not gap_bridged and saved_top_id:
                    # Check if we bridged the gap
                    bridge_index = -1
                    for i, post in enumerate(posts):
                        if post['id'] == saved_top_id:
                            bridge_index = i
                            break
                    
                    if bridge_index != -1:
                        print(f"Gap bridged at ID {saved_top_id} (Page {page})")
                        gap_bridged = True
                        
                        # If we were already complete, we can stop here (after downloading new posts)
                        if saved_is_complete:
                            # Download new posts (before the bridge)
                            new_posts = posts[:bridge_index]
                            if new_posts:
                                batch_futures = self.downloader.start_download_batch(
                                    new_posts, 
                                    self.download_path, 
                                    {'on_progress': None, 'on_complete': on_item_complete, 'on_error': on_item_error}
                                )
                                for f in batch_futures: f.result()
                            
                            print("Already complete, stopping.")
                            # Update top_id to new one
                            resume_mgr.save(self.current_tags, current_run_top_id, saved_last_page, True)
                            break
                        else:
                            # Not complete, so we download new posts, then JUMP.
                            new_posts = posts[:bridge_index]
                            if new_posts:
                                batch_futures = self.downloader.start_download_batch(
                                    new_posts, 
                                    self.download_path, 
                                    {'on_progress': None, 'on_complete': on_item_complete, 'on_error': on_item_error}
                                )
                                for f in batch_futures: f.result()
                            
                            # JUMP
                            if saved_last_page > page:
                                msg = f"Gap found! Jumping to page {saved_last_page}..."
                                print(msg)
                                self.after(0, lambda m=msg: self.progress_label.configure(text=m))
                                page = saved_last_page
                                continue
                            
                # Normal Download
                batch_futures = self.downloader.start_download_batch(
                    posts, 
                    self.download_path, 
                    {'on_progress': None, 'on_complete': on_item_complete, 'on_error': on_item_error}
                )
                for f in batch_futures: 
                    if self.downloader.stop_event.is_set(): break
                    f.result()
                
                # Save state after each page
                if not repair_mode:
                    resume_mgr.save(self.current_tags, current_run_top_id or saved_top_id, page, False)
                
                page += 1
                
            except Exception as e:
                print(f"Bulk download loop error: {e}")
                break

        self.after(0, lambda: self.bulk_download_btn.configure(state="normal", text="Download All"))
        self.after(0, lambda: self.pause_btn.configure(state="disabled"))
        self.after(0, lambda: self.cancel_btn.configure(state="disabled"))
        if not self.downloader.stop_event.is_set():
             self.after(0, lambda: self.progress_label.configure(text=f"Completed: {downloaded_count} files"))
             self.after(0, self.clear_all_selections)
             self.update_local_file_count()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", help="Danbooru Username")
    parser.add_argument("--apikey", help="Danbooru API Key")
    args = parser.parse_args()

    app = App(username=args.username, apikey=args.apikey)
    app.mainloop()
