"""
Encrypted Credential Storage Service
Handles secure storage of Indeed/Glassdoor credentials using encryption
"""
from typing import Optional
from loguru import logger

from infrastructure.security.encryption import FernetEncryptionService
from core.config import settings


class CredentialEncryptionService:
    """Service for encrypting/decrypting user credentials"""
    
    def __init__(self):
        self.encryption_service = FernetEncryptionService()
    
    def encrypt_credential(self, plain_credential: str) -> str:
        """
        Encrypt a credential for secure storage
        
        Args:
            plain_credential: Plain text credential
            
        Returns:
            Encrypted credential as base64 string
        """
        try:
            return self.encryption_service.encrypt(plain_credential)
        except Exception as e:
            logger.error(f"Failed to encrypt credential: {e}")
            raise
    
    def decrypt_credential(self, encrypted_credential: str) -> str:
        """
        Decrypt a credential for use
        
        Args:
            encrypted_credential: Encrypted credential
            
        Returns:
            Plain text credential
        """
        try:
            return self.encryption_service.decrypt(encrypted_credential)
        except Exception as e:
            logger.error(f"Failed to decrypt credential: {e}")
            raise
    
    def encrypt_indeed_credentials(self, username: str, password: str) -> tuple[str, str]:
        """
        Encrypt Indeed credentials
        
        Returns:
            Tuple of (encrypted_username, encrypted_password)
        """
        return (
            self.encrypt_credential(username),
            self.encrypt_credential(password)
        )
    
    def encrypt_glassdoor_credentials(self, username: str, password: str) -> tuple[str, str]:
        """
        Encrypt Glassdoor credentials
        
        Returns:
            Tuple of (encrypted_username, encrypted_password)
        """
        return (
            self.encrypt_credential(username),
            self.encrypt_credential(password)
        )
    
    def decrypt_indeed_credentials(self, encrypted_username: str, encrypted_password: str) -> tuple[str, str]:
        """
        Decrypt Indeed credentials
        
        Returns:
            Tuple of (plain_username, plain_password)
        """
        return (
            self.decrypt_credential(encrypted_username),
            self.decrypt_credential(encrypted_password)
        )
    
    def decrypt_glassdoor_credentials(self, encrypted_username: str, encrypted_password: str) -> tuple[str, str]:
        """
        Decrypt Glassdoor credentials
        
        Returns:
            Tuple of (plain_username, plain_password)
        """
        return (
            self.decrypt_credential(encrypted_username),
            self.decrypt_credential(encrypted_password)
        )


# Global instance
credential_encryption = CredentialEncryptionService()