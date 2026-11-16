import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken


class SecretVault:
    """Шифрование секретов в покое (AES-256 через Fernet) и маскирование для UI."""

    def __init__(self, master_key: str) -> None:
        if not master_key:
            raise ValueError("MASTER_KEY must not be empty")
        digest = hashlib.sha256(master_key.encode("utf-8")).digest()
        fernet_key = base64.urlsafe_b64encode(digest)
        self._cipher = Fernet(fernet_key)

    def encrypt_secret(self, plain_secret: str) -> str:
        if not plain_secret:
            return ""
        token = self._cipher.encrypt(plain_secret.encode("utf-8"))
        return token.decode("utf-8")

    def decrypt_secret(self, encrypted_secret: str) -> str:
        if not encrypted_secret:
            return ""
        try:
            plain = self._cipher.decrypt(encrypted_secret.encode("utf-8"))
            return plain.decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Failed to decrypt secret: invalid token or MASTER_KEY") from exc

    @staticmethod
    def mask_secret(plain_secret: str) -> str:
        """Возвращает безопасную маску ключа для отображения в UI (Zero-Frontend Secrets)."""
        if not plain_secret:
            return ""
        length = len(plain_secret)
        if length <= 6:
            return "*" * length
        return f"{plain_secret[:3]}{'*' * min(length - 5, 12)}{plain_secret[-2:]}"
