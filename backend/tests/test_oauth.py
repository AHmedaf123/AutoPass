"""
Tests for Google OAuth Authentication
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4

from application.services.auth.google_oauth import GoogleOAuthService
from application.services.auth.impl import AuthService
from domain.entities import User
from domain.value_objects import Email


class TestGoogleOAuthService:
    """Test Google OAuth service"""

    @pytest.fixture
    def oauth_service(self):
        return GoogleOAuthService()

    def test_get_authorization_url(self, oauth_service):
        """Test generating authorization URL"""
        url = oauth_service.get_authorization_url()
        assert "https://accounts.google.com/o/oauth2/auth" in url
        assert "client_id=196623045052" in url
        assert "scope=openid+email+profile" in url
        assert "response_type=code" in url

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens(self, oauth_service):
        """Test exchanging authorization code for tokens"""
        mock_response = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
            "token_type": "Bearer"
        }

        mock_response_obj = Mock()
        mock_response_obj.status_code = 200
        mock_response_obj.json.return_value = mock_response

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client_instance = AsyncMock()
            mock_client_instance.post.return_value = mock_response_obj
            mock_client_class.return_value.__aenter__.return_value = mock_client_instance

            result = await oauth_service.exchange_code_for_tokens("test_code")
            assert result == mock_response

    @pytest.mark.asyncio
    async def test_get_user_info(self, oauth_service):
        """Test getting user info from Google"""
        mock_user_info = {
            "id": "123456789",
            "email": "test@example.com",
            "name": "Test User"
        }

        mock_response_obj = Mock()
        mock_response_obj.status_code = 200
        mock_response_obj.json.return_value = mock_user_info

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response_obj
            mock_client_class.return_value.__aenter__.return_value = mock_client_instance

            result = await oauth_service.get_user_info("test_token")
            assert result == mock_user_info


class TestAuthServiceGoogleOAuth:
    """Test AuthService Google OAuth functionality"""

    @pytest.fixture
    def auth_service(self):
        user_repo = Mock()
        password_hasher = Mock()
        return AuthService(user_repo, password_hasher)

    @pytest.mark.asyncio
    async def test_login_with_google_new_user(self, auth_service):
        """Test Google OAuth login for new user"""
        # Mock user repo
        auth_service.user_repo.get_by_google_id = AsyncMock(return_value=None)
        auth_service.user_repo.get_by_email = AsyncMock(return_value=None)
        auth_service.user_repo.create = AsyncMock(return_value=User(
            id=uuid4(),
            email=Email("test@example.com"),
            password_hash="mock_hash",
            full_name="Test User",
            target_job_title="",
            industry="",
            google_user_id="123456789",
            google_access_token="access_token",
            google_refresh_token="refresh_token"
        ))

        result_user, message = await auth_service.login_with_google(
            google_user_id="123456789",
            email="test@example.com",
            full_name="Test User",
            access_token="access_token",
            refresh_token="refresh_token"
        )

        assert result_user.email.value == "test@example.com"
        assert result_user.google_user_id == "123456789"
        assert "created" in message.lower()

    @pytest.mark.asyncio
    async def test_login_with_google_existing_user(self, auth_service):
        """Test Google OAuth login for existing user"""
        existing_user = User(
            id=uuid4(),
            email=Email("test@example.com"),
            password_hash="mock_hash",
            full_name="Test User",
            target_job_title="",
            industry="",
            google_user_id="123456789"
        )

        auth_service.user_repo.get_by_google_id = AsyncMock(return_value=existing_user)
        auth_service.user_repo.update_google_credentials = AsyncMock(return_value=existing_user)

        result_user, message = await auth_service.login_with_google(
            google_user_id="123456789",
            email="test@example.com",
            full_name="Test User",
            access_token="access_token",
            refresh_token="refresh_token"
        )

        assert result_user == existing_user
        assert "successfully" in message.lower()


class TestCredentialEncryption:
    """Test credential encryption service"""

    def test_encrypt_decrypt_indeed_credentials(self):
        """Test encrypting and decrypting Indeed credentials"""
        from application.services.auth.credential_encryption import credential_encryption

        username = "test@example.com"
        password = "test_password"

        # Encrypt
        enc_username, enc_password = credential_encryption.encrypt_indeed_credentials(username, password)

        # Decrypt
        dec_username, dec_password = credential_encryption.decrypt_indeed_credentials(enc_username, enc_password)

        assert dec_username == username
        assert dec_password == password

    def test_encrypt_decrypt_glassdoor_credentials(self):
        """Test encrypting and decrypting Glassdoor credentials"""
        from application.services.auth.credential_encryption import credential_encryption

        username = "test@example.com"
        password = "test_password"

        # Encrypt
        enc_username, enc_password = credential_encryption.encrypt_glassdoor_credentials(username, password)

        # Decrypt
        dec_username, dec_password = credential_encryption.decrypt_glassdoor_credentials(enc_username, enc_password)

        assert dec_username == username
        assert dec_password == password