# Danbooru Downloader

A modern, high-performance desktop application for searching and downloading images from Danbooru. Built with Python and CustomTkinter.

![Danbooru Downloader](https://github.com/AkaringoP/Danbooru_Downloader/assets/placeholder.png)

## Key Features

-   **Modern UI**: Clean, dark-themed interface built with `customtkinter`.
-   **Advanced Security**:
    -   **Credential Protection**: API keys and personal info are encrypted using **Windows Credential Locker** (via `keyring`).
    -   **Privacy-First Cache**: Thumnnail cache files are **obfuscated** (hashed filenames + XOR-scrambled headers) to prevent viewing in Windows Explorer.
    -   **Config Encryption**: Sensitive settings in `.env` (Download Path, Safe Search) are fully encrypted.
-   **Smart Search**:
    -   Incremental rendering for instant search feedback.
    -   Visual tag display with organized metadata (Artist, Copyright, Character, General).
    -   Search history with autocomplete.
-   **High Performance**:
    -   Multi-threaded downloading with customizable concurrency.
    -   Optimized scroll performance with widget flattening.
    -   **Bulk optimized**: "Download All" implicitly maximizes valid API requests (100 posts/page).
-   **Convenience**:
    -   **Input Validation**: Strict checking for settings (e.g., Post Limits capped at 30 for UI smoothness).
    -   "Don't ask again" confirmation setting.
    -   Pause/Resume downloads.
    -   Direct file viewer integration.

## 📥 Download & Installation

### Option 1: Standalone Executable (Recommended)
No Python installation required. Just download and run.
1.  Go to the [Releases Page](https://github.com/AkaringoP/Danbooru_Downloader/releases).
2.  Download the latest `DanbooruDownloader.zip`.
3.  Extract the zip file.
4.  Run `DanbooruDownloader.exe`.

### Option 2: Run from Source (For Developers)
1.  **Clone the repository**:
    ```bash
    git clone https://github.com/AkaringoP/Danbooru_Downloader.git
    cd Danbooru_Downloader
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the application**:
    ```bash
    python app.py
    ```

## Usage

1.  **Start the App**: Run `DanbooruDownloader.exe` (or `python app.py` if running from source).

2.  **Initial Setup**:
    -   Click **Settings** to configure your Danbooru credentials (Username, API Key).
    -   *Note: Providing credentials is recommended for higher API limits.*

3.  **Search & Download**:
    -   Enter tags in the search bar (e.g., `hatsune_miku 1girl`).
    -   Select images to download individually, or click **Download All** to fetch the entire batch.
    -   Use the **Open Folder** button to view your downloaded images.

## Configuration

Settings are stored securely in `.env` and `search_history.json`.
-   **Concurrency**: Adjust `Max Workers` in settings to control download speed.
-   **Preview Limit**: Set the number of images per page (Default: 20, Recommended: 20-50).

## Requirements

-   Python 3.8+
-   Danbooru Account (Optional, for API Key)

## License

This project is open-source and available under the MIT License.
