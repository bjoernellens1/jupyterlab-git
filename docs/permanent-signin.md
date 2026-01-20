# Permanent Sign-In for Git Authentication

This feature allows you to permanently sign in to GitHub, GitLab, and Gitea/Forgejo, providing a seamless experience similar to VS Code's authentication system.

## Features

- **Permanent Authentication**: Sign in once and your credentials are stored securely
- **Multiple Providers**: Support for GitHub, GitLab, and Gitea/Forgejo
- **Automatic Token Usage**: Push, pull, and fetch operations automatically use stored credentials
- **Secure Storage**: Tokens are stored using your system's keyring (or in-memory as fallback)
- **Easy Management**: View and manage all connected accounts from a single interface

## How to Use

### Signing In

There are two ways to sign in:

#### Method 1: Through the Git Menu

1. Open JupyterLab
2. Click on the **Git** menu in the top menu bar
3. Select **Manage Accounts**
4. Click on one of the "Sign in with..." buttons (GitHub, GitLab, or Gitea/Forgejo)
5. Follow the authentication flow:
   - **For GitHub/GitLab**: A device code will be displayed. Open the verification URL in your browser and enter the code
   - **For Gitea/Forgejo**: You'll need to manually create a Personal Access Token and paste it

#### Method 2: During Git Operations

When performing a Git operation (push, pull, clone) that requires authentication:

1. The credentials dialog will appear
2. Look for the "or" separator and the "Sign in with [Provider]" button
3. Click the button to start the authentication flow
4. Once complete, the operation will continue automatically

### Managing Accounts

To view or remove connected accounts:

1. Open the **Git** menu
2. Select **Manage Accounts**
3. You'll see a list of all connected accounts with:
   - Provider name (GitHub, GitLab, Gitea/Forgejo)
   - Username and host
   - Storage location (system keyring or memory)
4. To sign out from an account, click the **Sign Out** button

### How It Works

1. **Automatic Detection**: When you perform a Git operation, the extension automatically detects the remote repository's provider
2. **Token Retrieval**: If you have a stored token for that provider and host, it's used automatically
3. **Fallback**: If no stored token is found, you'll be prompted for credentials as before
4. **Security**: Tokens are stored securely using your system's keyring (Keychain on macOS, Credential Manager on Windows, Secret Service on Linux)

## Supported Providers

### GitHub

- Uses OAuth device flow for authentication
- Automatically requests appropriate scopes (`repo` and `user`)
- Works with both github.com and GitHub Enterprise servers

### GitLab

- Uses OAuth device flow for authentication
- Supports both gitlab.com and self-hosted GitLab instances
- Requires `read_repository` and `write_repository` scopes

### Gitea/Forgejo

- Uses Personal Access Token authentication (device flow not yet supported)
- Works with any Gitea or Forgejo instance
- You must manually create a token with `repo` scope from your instance's settings

## Security Considerations

### Token Storage

- **Preferred Method**: System keyring (most secure)
  - macOS: Keychain
  - Windows: Credential Manager
  - Linux: Secret Service (requires D-Bus and a keyring daemon like gnome-keyring or kwallet)
  
- **Fallback Method**: In-memory storage
  - Used when system keyring is not available
  - Tokens are lost when JupyterLab server is restarted
  - A warning is shown when this fallback is used

### Token Permissions

Tokens are requested with minimal required scopes:
- **GitHub**: `repo` (repository access), `user` (user information)
- **GitLab**: `read_repository`, `write_repository`
- **Gitea/Forgejo**: You control the scopes when creating the token

### Revoking Access

To completely revoke access:

1. **In JupyterLab**: Use "Manage Accounts" to sign out (removes token from local storage)
2. **On the Provider**: Go to your account settings and revoke the application's access:
   - GitHub: Settings → Applications → Authorized OAuth Apps
   - GitLab: Preferences → Applications
   - Gitea/Forgejo: Settings → Applications

## Troubleshooting

### "keyring library not available" Warning

If you see this warning, the system keyring is not available. To fix:

1. Install the keyring package: `pip install keyring`
2. On Linux, ensure you have a keyring daemon running (gnome-keyring or kwallet)
3. Restart the JupyterLab server

### Authentication Fails

If authentication fails:

1. Check your internet connection
2. Verify the provider's service is available
3. For self-hosted instances, ensure the URL is correct
4. Try signing out and signing in again
5. Check JupyterLab server logs for detailed error messages

### Stored Token Not Used

If operations still ask for credentials despite having a stored token:

1. Verify the token is stored: Go to "Manage Accounts" and check if your account is listed
2. Ensure the remote URL matches the stored provider (e.g., github.com vs github.example.com)
3. The token may have expired - try signing in again
4. Check if the token has been revoked on the provider's website

### Token Expires or Becomes Invalid

- GitHub tokens don't expire unless explicitly revoked
- GitLab tokens may have expiration dates - you'll need to sign in again
- Gitea/Forgejo token expiration depends on instance configuration

## Configuration

### Server Configuration

You can configure the extension's behavior in `jupyter_notebook_config.py`:

```python
# Credential cache timeout (default: 3600 seconds = 1 hour)
c.JupyterLabGit.credential_helper = 'cache --timeout=3600'

# Git command timeout (default: 20 seconds)
c.JupyterLabGit.git_command_timeout = 20.0
```

### Client Configuration

Advanced settings can be configured in JupyterLab's Settings Editor:

1. Go to Settings → Advanced Settings Editor
2. Select "Git" from the list
3. Modify settings as needed

## Privacy

- Tokens are never sent to any third party except the provider itself
- The JupyterLab Git extension runs entirely on your local machine or your JupyterLab server
- No analytics or usage data is collected

## Requirements

- JupyterLab >= 4.0
- Python >= 3.8
- `keyring` package (optional but recommended): `pip install keyring`
- Git >= 2.0

## Limitations

- Gitea/Forgejo does not yet support OAuth device flow, so manual token entry is required
- SSH key authentication is not affected by this feature - continue using SSH keys as before
- Some Git operations (like submodule operations) may still require separate authentication

## Comparison with Other Methods

| Method | Permanent Sign-In | SSH Keys | HTTPS with Git Credential Helper |
|--------|-------------------|----------|----------------------------------|
| Setup | Easy (one-time sign-in) | Moderate (key generation + upload) | Moderate (credential helper config) |
| Security | High (token-based) | High (key-based) | Moderate (depends on helper) |
| Cross-platform | Yes | Yes | Varies |
| Revocation | Easy (UI or provider) | Moderate (remove from provider) | Varies |
| Multiple accounts | Yes | Yes (multiple keys) | Limited |

## Future Enhancements

Planned improvements:
- Automatic token refresh for providers that support it
- Support for more Git hosting providers
- Integration with JupyterLab's native authentication system
- Multi-factor authentication support
- Token expiration warnings
