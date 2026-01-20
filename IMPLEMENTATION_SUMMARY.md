# Implementation Summary: Permanent Sign-In Support

## Overview

This implementation adds permanent sign-in support for GitHub, GitLab, and Gitea/Forgejo to the JupyterLab Git extension, following the same user experience as VS Code's authentication system.

## What Was Implemented

### 1. Backend Infrastructure (Python)

#### Authentication Providers (`jupyterlab_git/auth_providers.py`)
- **GitHubAuthProvider**: OAuth device flow implementation
  - Starts device authorization flow
  - Polls for access token
  - Validates tokens via GitHub API
  - Detects github.com URLs
  
- **GitLabAuthProvider**: OAuth device flow for GitLab
  - Supports both gitlab.com and self-hosted instances
  - Custom base URL configuration
  - Similar flow to GitHub
  
- **GiteaAuthProvider**: Personal Access Token flow
  - Manual token entry (device flow not yet supported by Gitea)
  - Works with any Gitea/Forgejo instance
  - Token validation via Gitea API

#### Token Storage (`jupyterlab_git/token_storage.py`)
- **Secure Storage**: Uses system keyring via Python `keyring` library
  - macOS: Keychain
  - Windows: Credential Manager
  - Linux: Secret Service (gnome-keyring/kwallet)
- **Fallback Storage**: In-memory storage when keyring unavailable
- **Operations**: Store, retrieve, delete, list tokens
- **Key Format**: `provider:host` (e.g., `github:github.com`)

#### REST API Endpoints (`jupyterlab_git/handlers.py`)
- `POST /git/auth/start_flow`: Start OAuth device flow
- `POST /git/auth/poll_token`: Poll for access token
- `POST /git/auth/store_token`: Manually store token (for Gitea)
- `POST /git/auth/get_token`: Retrieve stored token
- `POST /git/auth/delete_token`: Delete token (logout)
- `GET /git/auth/list_tokens`: List all stored tokens

#### Git Operations Integration (`jupyterlab_git/git.py`)
- **Auto-detection**: Parses remote URLs to identify provider
- **Token Retrieval**: Checks for stored tokens before prompting user
- **Helper Methods**:
  - `_get_stored_credentials()`: Retrieve credentials from storage
  - `_get_remote_url()`: Get remote URL for a repository
  - `_parse_repo_info()`: Parse URL to extract provider and host
- **Enhanced Operations**: 
  - `push()`: Uses stored tokens automatically
  - `pull()`: Uses stored tokens automatically
  - Graceful fallback to manual credentials

### 2. Frontend Components (TypeScript/React)

#### Authentication Service (`src/auth.ts`)
- Type-safe TypeScript interfaces
- API calls to backend endpoints
- URL parsing utilities
- Provider display name helpers

#### Sign-In Dialog (`src/widgets/AuthDialog.tsx`)
- **Multi-step flow**:
  1. Loading state
  2. Device code display (GitHub/GitLab)
  3. Manual token entry (Gitea)
  4. Polling state with spinner
  5. Success confirmation
  6. Error handling
- **React Component**: Full state management
- **Widget Wrapper**: JupyterLab Dialog integration

#### Account Manager (`src/components/AccountManager.tsx`)
- **List View**: Shows all connected accounts
- **Sign In Buttons**: Quick access to all three providers
- **Sign Out**: Remove accounts with confirmation
- **Empty State**: Helpful message when no accounts connected

#### Enhanced Credentials Dialog (`src/widgets/CredentialsBox.tsx`)
- **Original Functionality**: Username/password entry preserved
- **New Feature**: "Sign in with..." button when provider detected
- **Smart Detection**: Automatically shows provider button based on repo URL
- **Seamless Integration**: Clicking sign-in closes dialog and proceeds with operation

#### Menu Integration (`src/commandsAndMenu.tsx`)
- New command: `git:manage-accounts`
- Menu item: "Manage Accounts" in Git menu
- Lazy loading of AccountManager component

### 3. Styling (`style/auth.css`)

Complete CSS styling for:
- Authentication dialog (all states)
- Device code display
- Loading spinners
- Account list
- Sign-in buttons
- Success/error states
- Responsive layout

### 4. Type Definitions (`src/tokens.ts`)

Extended `Git.IAuth` interface:
```typescript
interface IAuth {
  username: string;
  password: string;
  cache_credentials?: boolean;
  use_stored_token?: boolean;  // New
  provider?: string;            // New
  host?: string;                // New
}
```

### 5. Documentation

#### User Documentation (`docs/permanent-signin.md`)
- Feature overview
- Step-by-step usage guide
- Provider-specific instructions
- Security considerations
- Troubleshooting
- Configuration options
- Privacy information

#### README Updates (`README.md`)
- Feature announcement
- Quick start guide
- Link to detailed documentation

## How It Works

### User Flow

1. **First Time Sign-In**:
   - User opens "Manage Accounts" from Git menu
   - Clicks "Sign in with GitHub" (or GitLab/Gitea)
   - For GitHub/GitLab: Completes OAuth device flow in browser
   - For Gitea: Manually creates and enters token
   - Token stored securely in system keyring

2. **Automatic Authentication**:
   - User performs git push/pull/fetch
   - Extension detects remote repository URL
   - Checks for stored token matching provider and host
   - If found, uses token automatically
   - If not found, shows traditional credentials dialog

3. **Sign-In During Operation**:
   - Credentials dialog appears
   - User sees "Sign in with [Provider]" button
   - Clicks button, completes auth flow
   - Token stored and operation continues automatically

### Security Flow

```
User Action → Frontend Request → Backend Handler
                                      ↓
                            Start OAuth/Token Flow
                                      ↓
                              User Authorizes
                                      ↓
                            Receive Access Token
                                      ↓
                              Validate Token
                                      ↓
                     Store in System Keyring
                                      ↓
                    Token Available for Git Operations
```

### Token Usage Flow

```
Git Operation (push/pull) → Check for Remote URL
                                    ↓
                            Parse Provider/Host
                                    ↓
                        Query Token Storage
                                    ↓
                    ┌───────────────┴───────────────┐
                    ↓                               ↓
              Token Found                     Token Not Found
                    ↓                               ↓
          Use Token Automatically           Show Credentials Dialog
                    ↓                               ↓
              Execute Git Command           User Enters Credentials
```

## Technical Decisions

### Why OAuth Device Flow?
- **User-friendly**: Simple code entry in browser
- **Secure**: No password handling, token-based
- **Scoped**: Can request specific permissions
- **Revocable**: Easy to revoke from provider settings

### Why System Keyring?
- **Security**: OS-level encryption
- **Persistence**: Survives JupyterLab restarts
- **Standard**: Industry best practice
- **Fallback**: Graceful degradation to in-memory

### Why Separate Auth Providers?
- **Extensibility**: Easy to add new providers
- **Maintainability**: Clear separation of concerns
- **Flexibility**: Provider-specific customization
- **Testing**: Individual provider testing

### Why React Components?
- **Consistency**: Matches existing extension UI
- **State Management**: Complex auth flows need state
- **Reusability**: Components can be reused
- **Developer Experience**: Better than vanilla JS

## Files Added/Modified

### New Files (Backend)
- `jupyterlab_git/auth_providers.py` - Authentication providers
- `jupyterlab_git/token_storage.py` - Secure token storage

### New Files (Frontend)
- `src/auth.ts` - Authentication service
- `src/widgets/AuthDialog.tsx` - Sign-in dialog
- `src/components/AccountManager.tsx` - Account management UI

### New Files (Styling)
- `style/auth.css` - Authentication UI styles

### New Files (Documentation)
- `docs/permanent-signin.md` - User guide

### Modified Files
- `jupyterlab_git/handlers.py` - Added auth endpoints
- `jupyterlab_git/git.py` - Integrated token usage
- `src/commandsAndMenu.tsx` - Added menu item
- `src/tokens.ts` - Extended IAuth interface
- `src/widgets/CredentialsBox.tsx` - Enhanced with sign-in
- `style/credentials-box.css` - Added separator styles
- `style/index.css` - Imported auth.css
- `pyproject.toml` - Added keyring dependency
- `README.md` - Added feature documentation
- `src/components/FileList.tsx` - Fixed TypeScript errors

## Testing Recommendations

### Manual Testing Checklist

#### GitHub Authentication
- [ ] Start sign-in flow from Manage Accounts
- [ ] Device code displayed correctly
- [ ] Browser authorization works
- [ ] Token stored successfully
- [ ] Token appears in account list
- [ ] Push/pull uses token automatically
- [ ] Sign out removes token
- [ ] Sign-in from credentials dialog works

#### GitLab Authentication
- [ ] Same tests as GitHub
- [ ] Test with gitlab.com
- [ ] Test with self-hosted instance (if available)

#### Gitea Authentication
- [ ] Manual token creation instructions shown
- [ ] Token validation works
- [ ] Token stored successfully
- [ ] Operations use token
- [ ] Sign out works

#### Integration Testing
- [ ] Multiple accounts (different providers)
- [ ] Multiple accounts (same provider, different hosts)
- [ ] Fallback to manual credentials when no token
- [ ] Token priority over temporary cache
- [ ] Sign-in button only shows for detected providers

#### Error Handling
- [ ] Invalid token shows error
- [ ] Network errors handled gracefully
- [ ] Expired authorization flow handled
- [ ] Keyring unavailable warning shown
- [ ] In-memory fallback works

#### Cross-Platform
- [ ] Test on macOS (Keychain)
- [ ] Test on Windows (Credential Manager)
- [ ] Test on Linux (Secret Service)

### Automated Testing

Consider adding:
- Unit tests for auth providers
- Unit tests for token storage
- Integration tests for API endpoints
- Frontend component tests
- E2E tests for auth flows

## Known Limitations

1. **Gitea/Forgejo**: No OAuth device flow support yet (manual token required)
2. **Token Refresh**: No automatic refresh (user must re-authenticate)
3. **Submodules**: May require separate authentication
4. **SSH**: Not affected by this feature (continue using SSH keys)

## Future Enhancements

1. **Token Refresh**: Implement automatic token refresh
2. **Multi-Factor**: Support MFA flows
3. **More Providers**: Bitbucket, Azure DevOps, etc.
4. **Token Expiry**: Warn before tokens expire
5. **Advanced Scopes**: Let users choose scopes
6. **Audit Log**: Track token usage
7. **Token Encryption**: Additional encryption layer
8. **Gitea OAuth**: When Gitea adds device flow support

## Dependencies

### Python
- `keyring>=23.0.0` - Secure token storage
- Existing dependencies unchanged

### JavaScript
- No new dependencies (React already included)
- `@mui/*` packages already used

## Performance Impact

- **Minimal**: Token lookup is O(1)
- **Network**: Only during sign-in
- **Storage**: Negligible (<1KB per token)
- **UI**: Lazy-loaded components

## Security Audit Points

1. ✅ Tokens stored encrypted (via system keyring)
2. ✅ No plaintext token storage
3. ✅ Secure HTTPS communication
4. ✅ Token validation before use
5. ✅ Minimal scope requests
6. ✅ Easy revocation path
7. ✅ No third-party token sharing
8. ✅ In-memory fallback clearly warned

## Rollout Strategy

### Phase 1: Beta (Current)
- Feature available but opt-in
- Documentation clearly marked as new
- Gather user feedback

### Phase 2: Stable
- After user testing
- Address any issues
- Consider making it default suggestion

### Phase 3: Future
- Potentially deprecate temporary cache
- Make permanent sign-in the primary method

## Success Metrics

Track:
- Number of users signing in
- Number of tokens stored
- Reduction in credential prompts
- User feedback
- Support tickets related to auth

## Support

For issues or questions:
1. Check the troubleshooting section in docs
2. Review JupyterLab server logs
3. Open an issue on GitHub
4. Provide: OS, JupyterLab version, error logs

## License

This feature maintains the existing BSD-3-Clause license of the jupyterlab-git extension.
