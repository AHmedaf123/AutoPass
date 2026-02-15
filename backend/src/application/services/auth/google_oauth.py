"""
Google OAuth Service
Handles Google OAuth 2.0 authentication flow
"""
import secrets
from typing import Optional, Dict, Any
from urllib.parse import urlencode
import httpx
from loguru import logger

from core.config import settings


class GoogleOAuthService:
    """Google OAuth 2.0 service for user authentication"""
    
    def __init__(self):
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
        self.redirect_uri = settings.GOOGLE_REDIRECT_URI
        self.oauth_url = settings.GOOGLE_OAUTH_URL
        self.token_url = settings.GOOGLE_TOKEN_URL
        self.userinfo_url = settings.GOOGLE_USERINFO_URL
    
    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """
        Generate Google OAuth authorization URL
        
        Args:
            state: Optional state parameter for CSRF protection
            
        Returns:
            Authorization URL for Google OAuth
        """
        if not state:
            state = secrets.token_urlsafe(32)
        
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'scope': 'openid email profile',
            'response_type': 'code',
            'access_type': 'offline',
            'prompt': 'consent',
            'state': state
        }
        
        return f"{self.oauth_url}?{urlencode(params)}"
    
    async def exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access and refresh tokens
        
        Args:
            code: Authorization code from Google
            
        Returns:
            Token response containing access_token, refresh_token, etc.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'code': code,
                    'grant_type': 'authorization_code',
                    'redirect_uri': self.redirect_uri
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            
            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.text}")
                raise Exception(f"Failed to exchange code for tokens: {response.text}")
            
            return response.json()
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Get user information from Google using access token
        
        Args:
            access_token: Google access token
            
        Returns:
            User information (email, name, etc.)
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.userinfo_url,
                headers={'Authorization': f'Bearer {access_token}'}
            )
            
            if response.status_code != 200:
                logger.error(f"User info fetch failed: {response.text}")
                raise Exception(f"Failed to get user info: {response.text}")
            
            return response.json()
    
    async def verify_google_token(self, id_token: str) -> Dict[str, Any]:
        """
        Verify Google ID token from Android app
        
        This is used when Android app sends the ID token directly to backend.
        The backend verifies the token with Google's tokeninfo endpoint.
        
        Args:
            id_token: Google ID token from Android Google Sign-In
            
        Returns:
            Verified user information (email, sub, name, etc.)
            
        Raises:
            Exception: If token verification fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
            )
            
            if response.status_code != 200:
                logger.error(f"Token verification failed: {response.text}")
                raise Exception(f"Invalid Google token: {response.text}")
            
            token_info = response.json()
            
            # Verify the token is for your app
            if token_info.get('aud') != self.client_id:
                logger.error(f"Token audience mismatch. Expected: {self.client_id}, Got: {token_info.get('aud')}")
                raise Exception("Token was not issued for this application")
            
            # Check if token is expired
            if 'exp' in token_info:
                import time
                if int(token_info['exp']) < int(time.time()):
                    raise Exception("Token has expired")
            
            logger.info(f"Successfully verified Google token for user: {token_info.get('email')}")
            return token_info
    
    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh access token using refresh token
        
        Args:
            refresh_token: Google refresh token
            
        Returns:
            New token response
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'refresh_token': refresh_token,
                    'grant_type': 'refresh_token'
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            
            if response.status_code != 200:
                logger.error(f"Token refresh failed: {response.text}")
                raise Exception(f"Failed to refresh token: {response.text}")
            
            return response.json()


# Global instance
google_oauth = GoogleOAuthService()