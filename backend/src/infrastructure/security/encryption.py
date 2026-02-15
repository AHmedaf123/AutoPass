"""
Fernet Encryption Service
For encrypting sensitive credentials (LinkedIn passwords, etc.)
"""
from cryptography.fernet import Fernet
from loguru import logger

from core.config import settings
from application.services.security.interfaces import IEncryptionService


class FernetEncryptionService(IEncryptionService):
    """Fernet symmetric encryption"""
    
    def __init__(self):
        # Use configured key or generate for development
        if settings.FERNET_KEY:
            self.cipher = Fernet(settings.FERNET_KEY.encode())
        else:
            # Generate key for development
            key = Fernet.generate_key()
            self.cipher = Fernet(key)
            logger.warning(f"Generated Fernet key for development: {key.decode()}")
            logger.warning("Set FERNET_KEY in production!")
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt string"""
        encrypted = self.cipher.encrypt(plaintext.encode())
        return encrypted.decode()
    
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt string"""
        decrypted = self.cipher.decrypt(ciphertext.encode())
        return decrypted.decode()
