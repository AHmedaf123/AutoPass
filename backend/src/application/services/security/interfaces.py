"""
Security Service Interfaces
Encryption and credential management
"""
from abc import ABC, abstractmethod


class IEncryptionService(ABC):
    """Encryption service interface"""
    
    @abstractmethod
    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext string"""
        pass
    
    @abstractmethod
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt ciphertext string"""
        pass
