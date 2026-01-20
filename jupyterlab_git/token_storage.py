"""
Secure token storage using system keyring.
Provides cross-platform credential storage similar to VS Code.
"""

import json
from typing import Dict, Optional, List

try:
    import keyring
    from keyring.errors import KeyringError, NoKeyringError

    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False
    KeyringError = Exception
    NoKeyringError = Exception

from .log import get_logger

# Service name for keyring
SERVICE_NAME = "jupyterlab-git"
logger = get_logger()


class TokenStorage:
    """Manages secure storage of authentication tokens."""

    def __init__(self):
        self.logger = logger
        self._fallback_storage: Dict[str, Dict[str, str]] = {}

        if not KEYRING_AVAILABLE:
            self.logger.warning(
                "keyring library not available. Tokens will be stored in memory only. "
                "Install keyring package for persistent secure storage: pip install keyring"
            )

    def _get_key_name(self, provider: str, host: str) -> str:
        """Generate a unique key name for the token."""
        return f"{provider}:{host}"

    def store_token(
        self, provider: str, host: str, username: str, token: str
    ) -> bool:
        """
        Store an authentication token securely.

        Args:
            provider: Provider name (github, gitlab, gitea)
            host: Host URL (e.g., github.com, gitlab.com)
            username: Username associated with the token
            token: Access token to store

        Returns:
            True if successful, False otherwise
        """
        key_name = self._get_key_name(provider, host)

        # Create credential object
        credential = {"username": username, "token": token, "provider": provider}

        try:
            if KEYRING_AVAILABLE:
                # Store in system keyring
                keyring.set_password(
                    SERVICE_NAME, key_name, json.dumps(credential)
                )
                self.logger.info(
                    f"Token stored securely for {username}@{host} ({provider})"
                )
                return True
            else:
                # Fallback to in-memory storage
                self._fallback_storage[key_name] = credential
                self.logger.warning(
                    f"Token stored in memory only for {username}@{host} ({provider}). "
                    "Install keyring for persistent storage."
                )
                return True
        except (KeyringError, NoKeyringError) as e:
            self.logger.error(f"Failed to store token in keyring: {e}")
            # Fallback to in-memory storage
            self._fallback_storage[key_name] = credential
            self.logger.warning(
                f"Token stored in memory only for {username}@{host} ({provider})"
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to store token: {e}")
            return False

    def get_token(self, provider: str, host: str) -> Optional[Dict[str, str]]:
        """
        Retrieve an authentication token.

        Args:
            provider: Provider name (github, gitlab, gitea)
            host: Host URL (e.g., github.com, gitlab.com)

        Returns:
            Dict with 'username', 'token', 'provider' or None if not found
        """
        key_name = self._get_key_name(provider, host)

        try:
            if KEYRING_AVAILABLE:
                credential_json = keyring.get_password(SERVICE_NAME, key_name)
                if credential_json:
                    credential = json.loads(credential_json)
                    self.logger.debug(f"Token retrieved for {host} ({provider})")
                    return credential
            
            # Check fallback storage
            if key_name in self._fallback_storage:
                self.logger.debug(f"Token retrieved from memory for {host} ({provider})")
                return self._fallback_storage[key_name]

            return None
        except (KeyringError, NoKeyringError) as e:
            self.logger.error(f"Failed to retrieve token from keyring: {e}")
            # Check fallback storage
            return self._fallback_storage.get(key_name)
        except Exception as e:
            self.logger.error(f"Failed to retrieve token: {e}")
            return None

    def delete_token(self, provider: str, host: str) -> bool:
        """
        Delete an authentication token.

        Args:
            provider: Provider name (github, gitlab, gitea)
            host: Host URL (e.g., github.com, gitlab.com)

        Returns:
            True if successful, False otherwise
        """
        key_name = self._get_key_name(provider, host)

        try:
            if KEYRING_AVAILABLE:
                try:
                    keyring.delete_password(SERVICE_NAME, key_name)
                    self.logger.info(f"Token deleted for {host} ({provider})")
                except KeyringError:
                    # Token might not exist, that's okay
                    pass

            # Also remove from fallback storage
            if key_name in self._fallback_storage:
                del self._fallback_storage[key_name]
                self.logger.info(
                    f"Token deleted from memory for {host} ({provider})"
                )

            return True
        except Exception as e:
            self.logger.error(f"Failed to delete token: {e}")
            return False

    def list_tokens(self) -> List[Dict[str, str]]:
        """
        List all stored tokens.

        Returns:
            List of dicts with 'provider', 'host', 'username'
        """
        tokens = []

        # Keyring doesn't provide a way to list all credentials,
        # so we only return in-memory tokens
        for key_name, credential in self._fallback_storage.items():
            provider, host = key_name.split(":", 1)
            tokens.append(
                {
                    "provider": provider,
                    "host": host,
                    "username": credential.get("username", ""),
                    "storage": "memory",
                }
            )

        return tokens

    def clear_all_tokens(self) -> bool:
        """
        Clear all stored tokens.

        Returns:
            True if successful, False otherwise
        """
        try:
            # Clear fallback storage
            self._fallback_storage.clear()
            self.logger.info("All tokens cleared from memory")
            return True
        except Exception as e:
            self.logger.error(f"Failed to clear tokens: {e}")
            return False


# Global token storage instance
_token_storage = None


def get_token_storage() -> TokenStorage:
    """Get the global token storage instance."""
    global _token_storage
    if _token_storage is None:
        _token_storage = TokenStorage()
    return _token_storage
