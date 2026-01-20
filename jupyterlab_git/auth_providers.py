"""
Authentication provider system for GitHub, GitLab, and Gitea/Forgejo.
Implements OAuth device flow similar to VS Code.
"""

import asyncio
import json
import time
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import aiohttp
from tornado.httpclient import AsyncHTTPClient, HTTPRequest

from .log import get_logger


class AuthProvider(ABC):
    """Base class for authentication providers."""

    def __init__(self, name: str, display_name: str):
        self.name = name
        self.display_name = display_name
        self.logger = get_logger()

    @abstractmethod
    async def start_device_flow(self) -> Dict[str, str]:
        """
        Start the device authorization flow.
        
        Returns:
            Dict with 'device_code', 'user_code', 'verification_uri', 'expires_in', 'interval'
        """
        pass

    @abstractmethod
    async def poll_for_token(
        self, device_code: str, interval: int = 5, timeout: int = 300
    ) -> Optional[str]:
        """
        Poll for the access token after user authorization.
        
        Args:
            device_code: Device code from start_device_flow
            interval: Polling interval in seconds
            timeout: Maximum time to wait in seconds
            
        Returns:
            Access token if successful, None otherwise
        """
        pass

    @abstractmethod
    async def validate_token(self, token: str) -> Tuple[bool, Optional[str]]:
        """
        Validate an access token.
        
        Args:
            token: Access token to validate
            
        Returns:
            Tuple of (is_valid, username)
        """
        pass

    @abstractmethod
    def get_git_credential_url(self, repo_url: str) -> str:
        """
        Get the URL pattern this provider handles.
        
        Args:
            repo_url: Repository URL
            
        Returns:
            URL pattern (e.g., 'github.com', 'gitlab.com')
        """
        pass


class GitHubAuthProvider(AuthProvider):
    """GitHub authentication provider using device flow."""

    # GitHub OAuth App credentials for JupyterLab Git extension
    CLIENT_ID = "Iv1.b507a08c87ecfe98"  # This should be configured per deployment
    DEVICE_CODE_URL = "https://github.com/login/device/code"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    API_URL = "https://api.github.com"

    def __init__(self):
        super().__init__("github", "GitHub")

    async def start_device_flow(self) -> Dict[str, str]:
        """Start GitHub device authorization flow."""
        try:
            http_client = AsyncHTTPClient()
            request = HTTPRequest(
                url=self.DEVICE_CODE_URL,
                method="POST",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                body=json.dumps(
                    {
                        "client_id": self.CLIENT_ID,
                        "scope": "repo user",  # Required scopes for git operations
                    }
                ),
            )
            response = await http_client.fetch(request)
            data = json.loads(response.body.decode("utf-8"))
            return {
                "device_code": data["device_code"],
                "user_code": data["user_code"],
                "verification_uri": data["verification_uri"],
                "expires_in": data["expires_in"],
                "interval": data.get("interval", 5),
            }
        except Exception as e:
            self.logger.error(f"Failed to start GitHub device flow: {e}")
            raise

    async def poll_for_token(
        self, device_code: str, interval: int = 5, timeout: int = 300
    ) -> Optional[str]:
        """Poll GitHub for access token."""
        start_time = time.time()
        http_client = AsyncHTTPClient()

        while time.time() - start_time < timeout:
            try:
                request = HTTPRequest(
                    url=self.TOKEN_URL,
                    method="POST",
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    body=json.dumps(
                        {
                            "client_id": self.CLIENT_ID,
                            "device_code": device_code,
                            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        }
                    ),
                )
                response = await http_client.fetch(request, raise_error=False)
                data = json.loads(response.body.decode("utf-8"))

                if "access_token" in data:
                    return data["access_token"]
                elif data.get("error") == "authorization_pending":
                    # User hasn't authorized yet, keep polling
                    await asyncio.sleep(interval)
                elif data.get("error") == "slow_down":
                    # Increase polling interval
                    interval += 5
                    await asyncio.sleep(interval)
                elif data.get("error") in ["expired_token", "access_denied"]:
                    # Flow failed
                    self.logger.warning(f"GitHub auth failed: {data.get('error')}")
                    return None
                else:
                    self.logger.error(f"Unexpected GitHub response: {data}")
                    return None
            except Exception as e:
                self.logger.error(f"Error polling for GitHub token: {e}")
                await asyncio.sleep(interval)

        self.logger.warning("GitHub device flow timed out")
        return None

    async def validate_token(self, token: str) -> Tuple[bool, Optional[str]]:
        """Validate GitHub token and get username."""
        try:
            http_client = AsyncHTTPClient()
            request = HTTPRequest(
                url=f"{self.API_URL}/user",
                method="GET",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"token {token}",
                },
            )
            response = await http_client.fetch(request, raise_error=False)

            if response.code == 200:
                data = json.loads(response.body.decode("utf-8"))
                return True, data.get("login")
            else:
                return False, None
        except Exception as e:
            self.logger.error(f"Failed to validate GitHub token: {e}")
            return False, None

    def get_git_credential_url(self, repo_url: str) -> str:
        """Get the URL pattern for GitHub."""
        parsed = urlparse(repo_url)
        if "github.com" in parsed.netloc:
            return "github.com"
        return ""


class GitLabAuthProvider(AuthProvider):
    """GitLab authentication provider using device flow."""

    # GitLab.com OAuth App credentials
    CLIENT_ID = "your_gitlab_client_id"  # Should be configured
    DEVICE_CODE_URL = "https://gitlab.com/oauth/authorize_device"
    TOKEN_URL = "https://gitlab.com/oauth/token"
    API_URL = "https://gitlab.com/api/v4"

    def __init__(self, base_url: str = "https://gitlab.com"):
        super().__init__("gitlab", "GitLab")
        self.base_url = base_url.rstrip("/")
        self.DEVICE_CODE_URL = f"{self.base_url}/oauth/authorize_device"
        self.TOKEN_URL = f"{self.base_url}/oauth/token"
        self.API_URL = f"{self.base_url}/api/v4"

    async def start_device_flow(self) -> Dict[str, str]:
        """Start GitLab device authorization flow."""
        try:
            http_client = AsyncHTTPClient()
            request = HTTPRequest(
                url=self.DEVICE_CODE_URL,
                method="POST",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                body=json.dumps(
                    {
                        "client_id": self.CLIENT_ID,
                        "scope": "read_repository write_repository",
                    }
                ),
            )
            response = await http_client.fetch(request)
            data = json.loads(response.body.decode("utf-8"))
            return {
                "device_code": data["device_code"],
                "user_code": data["user_code"],
                "verification_uri": data["verification_uri"],
                "expires_in": data["expires_in"],
                "interval": data.get("interval", 5),
            }
        except Exception as e:
            self.logger.error(f"Failed to start GitLab device flow: {e}")
            raise

    async def poll_for_token(
        self, device_code: str, interval: int = 5, timeout: int = 300
    ) -> Optional[str]:
        """Poll GitLab for access token."""
        start_time = time.time()
        http_client = AsyncHTTPClient()

        while time.time() - start_time < timeout:
            try:
                request = HTTPRequest(
                    url=self.TOKEN_URL,
                    method="POST",
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    body=json.dumps(
                        {
                            "client_id": self.CLIENT_ID,
                            "device_code": device_code,
                            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        }
                    ),
                )
                response = await http_client.fetch(request, raise_error=False)
                data = json.loads(response.body.decode("utf-8"))

                if "access_token" in data:
                    return data["access_token"]
                elif data.get("error") == "authorization_pending":
                    await asyncio.sleep(interval)
                elif data.get("error") in ["expired_token", "access_denied"]:
                    self.logger.warning(f"GitLab auth failed: {data.get('error')}")
                    return None
                else:
                    self.logger.error(f"Unexpected GitLab response: {data}")
                    return None
            except Exception as e:
                self.logger.error(f"Error polling for GitLab token: {e}")
                await asyncio.sleep(interval)

        self.logger.warning("GitLab device flow timed out")
        return None

    async def validate_token(self, token: str) -> Tuple[bool, Optional[str]]:
        """Validate GitLab token and get username."""
        try:
            http_client = AsyncHTTPClient()
            request = HTTPRequest(
                url=f"{self.API_URL}/user",
                method="GET",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            )
            response = await http_client.fetch(request, raise_error=False)

            if response.code == 200:
                data = json.loads(response.body.decode("utf-8"))
                return True, data.get("username")
            else:
                return False, None
        except Exception as e:
            self.logger.error(f"Failed to validate GitLab token: {e}")
            return False, None

    def get_git_credential_url(self, repo_url: str) -> str:
        """Get the URL pattern for GitLab."""
        parsed = urlparse(repo_url)
        if "gitlab.com" in parsed.netloc or self.base_url in repo_url:
            return parsed.netloc
        return ""


class GiteaAuthProvider(AuthProvider):
    """Gitea/Forgejo authentication provider using Personal Access Tokens."""

    def __init__(self, base_url: str = "https://gitea.com"):
        super().__init__("gitea", "Gitea/Forgejo")
        self.base_url = base_url.rstrip("/")
        self.API_URL = f"{self.base_url}/api/v1"

    async def start_device_flow(self) -> Dict[str, str]:
        """
        Gitea doesn't support device flow yet, so we return instructions
        for creating a Personal Access Token.
        """
        return {
            "device_code": "",
            "user_code": "",
            "verification_uri": f"{self.base_url}/user/settings/applications",
            "expires_in": 0,
            "interval": 0,
            "manual_token_required": True,
            "instructions": "Please create a Personal Access Token with 'repo' scope in your Gitea settings.",
        }

    async def poll_for_token(
        self, device_code: str, interval: int = 5, timeout: int = 300
    ) -> Optional[str]:
        """
        Not applicable for Gitea - user must manually provide token.
        """
        return None

    async def validate_token(self, token: str) -> Tuple[bool, Optional[str]]:
        """Validate Gitea token and get username."""
        try:
            http_client = AsyncHTTPClient()
            request = HTTPRequest(
                url=f"{self.API_URL}/user",
                method="GET",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"token {token}",
                },
            )
            response = await http_client.fetch(request, raise_error=False)

            if response.code == 200:
                data = json.loads(response.body.decode("utf-8"))
                return True, data.get("login") or data.get("username")
            else:
                return False, None
        except Exception as e:
            self.logger.error(f"Failed to validate Gitea token: {e}")
            return False, None

    def get_git_credential_url(self, repo_url: str) -> str:
        """Get the URL pattern for Gitea."""
        parsed = urlparse(repo_url)
        if self.base_url in repo_url:
            return parsed.netloc
        return ""


# Provider registry
PROVIDERS = {
    "github": GitHubAuthProvider,
    "gitlab": GitLabAuthProvider,
    "gitea": GiteaAuthProvider,
}


def get_provider(provider_name: str, **kwargs) -> Optional[AuthProvider]:
    """
    Get an authentication provider by name.
    
    Args:
        provider_name: Name of the provider ('github', 'gitlab', 'gitea')
        **kwargs: Provider-specific configuration (e.g., base_url for GitLab/Gitea)
        
    Returns:
        AuthProvider instance or None if not found
    """
    provider_class = PROVIDERS.get(provider_name.lower())
    if provider_class:
        return provider_class(**kwargs)
    return None
