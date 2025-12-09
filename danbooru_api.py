
import requests
import os
from urllib.parse import urlencode
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class DanbooruClient:
    BASE_URL = "https://danbooru.donmai.us"

    def __init__(self, username=None, api_key=None, nickname=None, email=None):
        self.auth = (username, api_key) if username and api_key else None
        
        self.nickname = nickname or "DanbooruDownloader"
        self.email = email or "unknown@example.com"
        
        self.headers = {
            "User-Agent": f"{self.nickname}/1.0 ({self.email})"
        }
        
        self.session = requests.Session()
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def fetch_posts(self, tags, limit=20, page=1):
        """
        Fetch posts from Danbooru API.
        """
        params = {
            "tags": tags,
            "limit": limit,
            "page": page
        }
        
        url = f"{self.BASE_URL}/posts.json"
        try:
            response = self.session.get(url, params=params, auth=self.auth, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching posts: {e}")
            return []

    def get_post_counts(self, tags):
        """
        Fetch the count of posts for the given tags.
        """
        params = {"tags": tags}
        url = f"{self.BASE_URL}/counts/posts.json"
        try:
            response = self.session.get(url, params=params, auth=self.auth, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("counts", {}).get("posts", 0)
        except Exception as e:
            print(f"Error fetching counts: {e}")
            return 0

    # get_post_count was duplicate of get_post_counts
    # Removed for cleanup
