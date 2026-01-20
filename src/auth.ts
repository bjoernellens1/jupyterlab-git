/**
 * Authentication service for permanent sign-in with GitHub, GitLab, and Gitea/Forgejo
 */

import { requestAPI } from './git';

export namespace Auth {
  /**
   * Authentication provider type
   */
  export type Provider = 'github' | 'gitlab' | 'gitea';

  /**
   * Device flow data returned by the provider
   */
  export interface IDeviceFlow {
    device_code: string;
    user_code: string;
    verification_uri: string;
    expires_in: number;
    interval: number;
    manual_token_required?: boolean;
    instructions?: string;
  }

  /**
   * Stored credential information
   */
  export interface ICredential {
    provider: Provider;
    host: string;
    username: string;
    has_token?: boolean;
  }

  /**
   * Authentication result
   */
  export interface IAuthResult {
    username: string;
    host: string;
    provider: Provider;
  }

  /**
   * Start device authorization flow
   */
  export async function startDeviceFlow(
    provider: Provider,
    baseUrl?: string
  ): Promise<IDeviceFlow> {
    const body: any = { provider };
    if (baseUrl) {
      body.base_url = baseUrl;
    }

    const response = await requestAPI<{ code: number; data: IDeviceFlow }>(
      'auth/start_flow',
      'POST',
      body
    );

    if (response.code !== 0) {
      throw new Error('Failed to start device flow');
    }

    return response.data;
  }

  /**
   * Poll for access token after user authorization
   */
  export async function pollForToken(
    provider: Provider,
    deviceCode: string,
    interval: number = 5,
    baseUrl?: string
  ): Promise<IAuthResult> {
    const body: any = {
      provider,
      device_code: deviceCode,
      interval
    };
    if (baseUrl) {
      body.base_url = baseUrl;
    }

    const response = await requestAPI<{ code: number; data: IAuthResult }>(
      'auth/poll_token',
      'POST',
      body
    );

    if (response.code !== 0) {
      throw new Error('Failed to get token');
    }

    return response.data;
  }

  /**
   * Manually store a token (for Gitea/Forgejo)
   */
  export async function storeToken(
    provider: Provider,
    host: string,
    username: string,
    token: string
  ): Promise<IAuthResult> {
    const response = await requestAPI<{ code: number; data: IAuthResult }>(
      'auth/store_token',
      'POST',
      {
        provider,
        host,
        username,
        token
      }
    );

    if (response.code !== 0) {
      throw new Error('Failed to store token');
    }

    return response.data;
  }

  /**
   * Get stored token for a provider/host
   */
  export async function getToken(
    provider: Provider,
    host: string
  ): Promise<ICredential | null> {
    try {
      const response = await requestAPI<{ code: number; data: ICredential }>(
        'auth/get_token',
        'POST',
        {
          provider,
          host
        }
      );

      if (response.code === 0) {
        return response.data;
      }
      return null;
    } catch (error) {
      // Token not found
      return null;
    }
  }

  /**
   * Delete stored token (logout)
   */
  export async function deleteToken(
    provider: Provider,
    host: string
  ): Promise<void> {
    const response = await requestAPI<{ code: number }>(
      'auth/delete_token',
      'POST',
      {
        provider,
        host
      }
    );

    if (response.code !== 0) {
      throw new Error('Failed to delete token');
    }
  }

  /**
   * List all stored tokens
   */
  export async function listTokens(): Promise<ICredential[]> {
    const response = await requestAPI<{ code: number; data: ICredential[] }>(
      'auth/list_tokens',
      'GET'
    );

    if (response.code !== 0) {
      throw new Error('Failed to list tokens');
    }

    return response.data;
  }

  /**
   * Extract provider and host from repository URL
   */
  export function parseRepoUrl(
    repoUrl: string
  ): { provider: Provider | null; host: string } | null {
    try {
      const url = new URL(repoUrl);
      const host = url.hostname;

      if (host.includes('github.com')) {
        return { provider: 'github', host: 'github.com' };
      } else if (host.includes('gitlab.com')) {
        return { provider: 'gitlab', host: 'gitlab.com' };
      } else if (host.includes('gitlab')) {
        // Self-hosted GitLab
        return { provider: 'gitlab', host };
      } else if (host.includes('gitea') || host.includes('forgejo')) {
        // Gitea/Forgejo
        return { provider: 'gitea', host };
      }

      return null;
    } catch (error) {
      return null;
    }
  }

  /**
   * Get provider display name
   */
  export function getProviderDisplayName(provider: Provider): string {
    switch (provider) {
      case 'github':
        return 'GitHub';
      case 'gitlab':
        return 'GitLab';
      case 'gitea':
        return 'Gitea/Forgejo';
      default:
        return provider;
    }
  }
}
