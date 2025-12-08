import os
from cryptography.fernet import Fernet

class SecurityManager:
    def __init__(self, key_file=".secret.key"):
        self.key_file = key_file
        self.key = self._load_or_generate_key()
        self.cipher = Fernet(self.key)

    def _load_or_generate_key(self):
        if os.path.exists(self.key_file):
            with open(self.key_file, "rb") as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, "wb") as f:
                f.write(key)
            return key

    def encrypt(self, data):
        if not data:
            return ""
        return self.cipher.encrypt(data.encode()).decode()

    def decrypt(self, token):
        if not token:
            return ""
        try:
            return self.cipher.decrypt(token.encode()).decode()
        except Exception:
            # Fallback for plain text (migration support)
            return token
