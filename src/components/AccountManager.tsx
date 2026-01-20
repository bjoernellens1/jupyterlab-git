/**
 * Account management component for viewing and managing connected accounts
 */

import { TranslationBundle } from '@jupyterlab/translation';
import * as React from 'react';
import { Auth } from '../auth';
import { showAuthDialog } from '../widgets/AuthDialog';

/**
 * Props for AccountManager component
 */
interface IAccountManagerProps {
  trans: TranslationBundle;
  onAccountChange?: () => void;
}

/**
 * State for AccountManager component
 */
interface IAccountManagerState {
  accounts: Auth.ICredential[];
  loading: boolean;
  error?: string;
}

/**
 * Account management component
 */
export class AccountManager extends React.Component<
  IAccountManagerProps,
  IAccountManagerState
> {
  constructor(props: IAccountManagerProps) {
    super(props);
    this.state = {
      accounts: [],
      loading: true
    };
  }

  componentDidMount(): void {
    this.loadAccounts();
  }

  private async loadAccounts(): Promise<void> {
    try {
      this.setState({ loading: true, error: undefined });
      const accounts = await Auth.listTokens();
      this.setState({ accounts, loading: false });
    } catch (error) {
      this.setState({
        loading: false,
        error: (error as Error).message
      });
    }
  }

  private async handleSignIn(provider: Auth.Provider): Promise<void> {
    try {
      const result = await showAuthDialog(provider, undefined, this.props.trans);
      if (result) {
        await this.loadAccounts();
        if (this.props.onAccountChange) {
          this.props.onAccountChange();
        }
      }
    } catch (error) {
      this.setState({
        error: (error as Error).message
      });
    }
  }

  private async handleSignOut(account: Auth.ICredential): Promise<void> {
    const confirmed = window.confirm(
      this.props.trans.__(
        'Are you sure you want to sign out from %1 (%2)?',
        Auth.getProviderDisplayName(account.provider),
        account.username
      )
    );

    if (!confirmed) {
      return;
    }

    try {
      await Auth.deleteToken(account.provider, account.host);
      await this.loadAccounts();
      if (this.props.onAccountChange) {
        this.props.onAccountChange();
      }
    } catch (error) {
      this.setState({
        error: (error as Error).message
      });
    }
  }

  render(): JSX.Element {
    const { trans } = this.props;
    const { accounts, loading, error } = this.state;

    return (
      <div className="jp-Git-account-manager">
        <h3 className="jp-Git-account-manager-title">
          {trans.__('Connected Accounts')}
        </h3>

        {loading && (
          <div className="jp-Git-account-manager-loading">
            {trans.__('Loading accounts...')}
          </div>
        )}

        {error && (
          <div className="jp-Git-account-manager-error">
            {trans.__('Error: %1', error)}
          </div>
        )}

        {!loading && accounts.length === 0 && (
          <div className="jp-Git-account-manager-empty">
            <p>{trans.__('No accounts connected.')}</p>
            <p className="jp-Git-account-manager-hint">
              {trans.__(
                'Connect an account to enable seamless Git operations without entering credentials.'
              )}
            </p>
          </div>
        )}

        {!loading && accounts.length > 0 && (
          <div className="jp-Git-account-list">
            {accounts.map((account, index) => (
              <div key={index} className="jp-Git-account-item">
                <div className="jp-Git-account-info">
                  <div className="jp-Git-account-provider">
                    {Auth.getProviderDisplayName(account.provider)}
                  </div>
                  <div className="jp-Git-account-username">
                    {account.username}@{account.host}
                  </div>
                  {account.storage && (
                    <div className="jp-Git-account-storage">
                      {trans.__('Storage: %1', account.storage)}
                    </div>
                  )}
                </div>
                <button
                  className="jp-Button jp-mod-styled jp-mod-warn"
                  onClick={() => this.handleSignOut(account)}
                  title={trans.__('Sign out')}
                >
                  {trans.__('Sign Out')}
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="jp-Git-account-manager-actions">
          <h4>{trans.__('Connect New Account')}</h4>
          <div className="jp-Git-account-manager-buttons">
            <button
              className="jp-Button jp-mod-styled"
              onClick={() => this.handleSignIn('github')}
            >
              {trans.__('Sign in with GitHub')}
            </button>
            <button
              className="jp-Button jp-mod-styled"
              onClick={() => this.handleSignIn('gitlab')}
            >
              {trans.__('Sign in with GitLab')}
            </button>
            <button
              className="jp-Button jp-mod-styled"
              onClick={() => this.handleSignIn('gitea')}
            >
              {trans.__('Sign in with Gitea/Forgejo')}
            </button>
          </div>
        </div>
      </div>
    );
  }
}
