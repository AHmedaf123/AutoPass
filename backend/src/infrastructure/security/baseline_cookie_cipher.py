"""
AES-256-GCM envelope encryption for baseline LinkedIn cookies.
- Encrypts baseline cookie profile payloads using a data key wrapped by a master key.
- Master key is supplied via env (BASELINE_COOKIES_MASTER_KEY) and must be 32 bytes base64-encoded.
- Output is a base64-encoded JSON envelope, suitable for storage in persistent_browser_profile.
"""
import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from loguru import logger

from core.config import settings


_ENVELOPE_VERSION = 1
_DATA_AAD = b"baseline_cookies_v1"
_WRAP_AAD = b"baseline_key_wrap_v1"


class BaselineCookieCipherError(Exception):
    """Raised when cookie encryption/decryption fails."""


@dataclass(frozen=True)
class BaselineCookieEnvelope:
    version: int
    alg: str
    nonce: str
    ciphertext: str
    wrap_nonce: str
    wrapped_key: str

    @staticmethod
    def from_json(payload: Dict[str, Any]) -> "BaselineCookieEnvelope":
        required = {"v", "alg", "nonce", "ciphertext", "wrap_nonce", "wrapped_key"}
        if not required.issubset(payload.keys()):
            raise BaselineCookieCipherError("Invalid envelope: missing fields")
        return BaselineCookieEnvelope(
            version=int(payload["v"]),
            alg=str(payload["alg"]),
            nonce=str(payload["nonce"]),
            ciphertext=str(payload["ciphertext"]),
            wrap_nonce=str(payload["wrap_nonce"]),
            wrapped_key=str(payload["wrapped_key"]),
        )

    def to_json(self) -> Dict[str, Any]:
        return {
            "v": self.version,
            "alg": self.alg,
            "nonce": self.nonce,
            "ciphertext": self.ciphertext,
            "wrap_nonce": self.wrap_nonce,
            "wrapped_key": self.wrapped_key,
        }


class BaselineCookieCipher:
    """Encrypts/decrypts baseline cookies using AES-256-GCM envelope."""

    def __init__(self, master_key_b64: Optional[str] = None) -> None:
        key_b64 = master_key_b64 or settings.BASELINE_COOKIES_MASTER_KEY
        if not key_b64:
            raise BaselineCookieCipherError(
                "BASELINE_COOKIES_MASTER_KEY is required for cookie encryption"
            )

        try:
            self.master_key = base64.b64decode(key_b64)
        except Exception as exc:  # pragma: no cover - defensive
            raise BaselineCookieCipherError("Failed to decode master key") from exc

        if len(self.master_key) != 32:
            raise BaselineCookieCipherError(
                "BASELINE_COOKIES_MASTER_KEY must decode to 32 bytes for AES-256-GCM"
            )

    def encrypt_profile(self, profile: Dict[str, Any]) -> str:
        """Encrypt a profile dict and return a base64-encoded envelope."""
        try:
            plaintext = json.dumps({"version": 1, **profile}).encode()
        except Exception as exc:
            raise BaselineCookieCipherError("Failed to serialize profile") from exc

        data_key = AESGCM.generate_key(bit_length=256)
        data_cipher = AESGCM(data_key)
        data_nonce = os.urandom(12)

        ciphertext = data_cipher.encrypt(data_nonce, plaintext, _DATA_AAD)

        wrap_cipher = AESGCM(self.master_key)
        wrap_nonce = os.urandom(12)
        wrapped_key = wrap_cipher.encrypt(wrap_nonce, data_key, _WRAP_AAD)

        envelope = BaselineCookieEnvelope(
            version=_ENVELOPE_VERSION,
            alg="AES-256-GCM",
            nonce=base64.b64encode(data_nonce).decode(),
            ciphertext=base64.b64encode(ciphertext).decode(),
            wrap_nonce=base64.b64encode(wrap_nonce).decode(),
            wrapped_key=base64.b64encode(wrapped_key).decode(),
        )

        payload_bytes = json.dumps(envelope.to_json()).encode()
        return base64.b64encode(payload_bytes).decode()

    def decrypt_profile(self, encrypted_blob: str) -> Dict[str, Any]:
        """Decrypt an encrypted envelope or fall back to plaintext JSON for legacy data."""
        if not encrypted_blob:
            raise BaselineCookieCipherError("Empty blob")

        # Attempt envelope decode
        try:
            envelope_bytes = base64.b64decode(encrypted_blob)
            payload = json.loads(envelope_bytes)
            envelope = BaselineCookieEnvelope.from_json(payload)
        except Exception:
            # Legacy plaintext JSON stored directly
            try:
                return json.loads(encrypted_blob)
            except Exception as exc:
                raise BaselineCookieCipherError("Invalid cookie payload") from exc

        if envelope.version != _ENVELOPE_VERSION:
            raise BaselineCookieCipherError(f"Unsupported envelope version {envelope.version}")

        data_nonce = base64.b64decode(envelope.nonce)
        ciphertext = base64.b64decode(envelope.ciphertext)
        wrap_nonce = base64.b64decode(envelope.wrap_nonce)
        wrapped_key = base64.b64decode(envelope.wrapped_key)

        wrap_cipher = AESGCM(self.master_key)
        try:
            data_key = wrap_cipher.decrypt(wrap_nonce, wrapped_key, _WRAP_AAD)
        except Exception as exc:
            raise BaselineCookieCipherError("Failed to unwrap data key") from exc

        data_cipher = AESGCM(data_key)
        try:
            plaintext = data_cipher.decrypt(data_nonce, ciphertext, _DATA_AAD)
        except Exception as exc:
            raise BaselineCookieCipherError("Failed to decrypt cookie payload") from exc

        try:
            return json.loads(plaintext.decode())
        except Exception as exc:
            raise BaselineCookieCipherError("Failed to parse decrypted cookie payload") from exc

def try_decrypt_profile(self, encrypted_blob: Optional[str]) -> Optional[Dict[str, Any]]:
    """Best-effort decrypt that returns None on failure without raising."""
    if not encrypted_blob:
        return None
    try:
        return self.decrypt_profile(encrypted_blob)
    except Exception as exc:
        logger.warning(f"Failed to decrypt baseline cookies: {exc}")
        return None