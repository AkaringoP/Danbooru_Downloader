import os
from cryptography.fernet import Fernet
import keyring

class SecurityManager:
    def __init__(self, key_file=".secret.key"):
        self.key_file = key_file
        self.service_name = "DanbooruDownloader"
        self.key_username = "encryption_key"
        self.key = self._load_or_generate_key()
        self.cipher = Fernet(self.key)

    def _load_or_generate_key(self):
        # 1. Try to load from Keyring
        stored_key = keyring.get_password(self.service_name, self.key_username)
        if stored_key:
            return stored_key.encode()

        # 2. Migration: Check for legacy key file
        if os.path.exists(self.key_file):
            with open(self.key_file, "rb") as f:
                key = f.read()
            # Migrate to Keyring
            try:
                keyring.set_password(self.service_name, self.key_username, key.decode())
                os.remove(self.key_file) # Secure delete
                print("Migrated encryption key to OS Keyring.")
            except Exception as e:
                print(f"Failed to migrate key to Keyring: {e}")
            return key
        
        # 3. Generate New Key
        key = Fernet.generate_key()
        try:
            keyring.set_password(self.service_name, self.key_username, key.decode())
        except Exception as e:
             # Fallback to file if keyring fails (e.g. headless linux without dbus)
            print(f"Keyring failed ({e}), falling back to file.")
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
