/**
 * Authentication dialog for permanent sign-in
 */

import { Dialog, showDialog } from '@jupyterlab/apputils';
import { TranslationBundle } from '@jupyterlab/translation';
import { Widget } from '@lumino/widgets';
import * as React from 'react';
import { createRoot, Root } from 'react-dom/client';
import { Auth } from '../auth';

/**
 * Props for AuthDialog component
 */
interface IAuthDialogProps {
  provider: Auth.Provider;
  baseUrl?: string;
  trans: TranslationBundle;
  onSuccess: (result: Auth.IAuthResult) => void;
  onCancel: () => void;
}

/**
 * State for AuthDialog component
 */
interface IAuthDialogState {
  step: 'loading' | 'device_code' | 'polling' | 'manual_token' | 'success' | 'error';
  deviceFlow?: Auth.IDeviceFlow;
  error?: string;
  manualToken?: string;
  manualUsername?: string;
}

/**
 * React component for authentication dialog
 */
class AuthDialogComponent extends React.Component<
  IAuthDialogProps,
  IAuthDialogState
> {
  private _pollInterval?: number;

  constructor(props: IAuthDialogProps) {
    super(props);
    this.state = {
      step: 'loading'
    };
  }

  componentDidMount(): void {
    this.startAuthFlow();
  }

  componentWillUnmount(): void {
    if (this._pollInterval) {
      window.clearInterval(this._pollInterval);
    }
  }

  private async startAuthFlow(): Promise<void> {
    try {
      const deviceFlow = await Auth.startDeviceFlow(
        this.props.provider,
        this.props.baseUrl
      );

      if (deviceFlow.manual_token_required) {
        // Gitea/Forgejo requires manual token
        this.setState({
          step: 'manual_token',
          deviceFlow
        });
      } else {
        // GitHub/GitLab device flow
        this.setState({
          step: 'device_code',
          deviceFlow
        });
      }
    } catch (error) {
      this.setState({
        step: 'error',
        error: (error as Error).message
      });
    }
  }

  private startPolling(): void {
    if (!this.state.deviceFlow) {
      return;
    }

    this.setState({ step: 'polling' });

    const poll = async (): Promise<void> => {
      try {
        const result = await Auth.pollForToken(
          this.props.provider,
          this.state.deviceFlow!.device_code,
          this.state.deviceFlow!.interval,
          this.props.baseUrl
        );

        if (this._pollInterval) {
          window.clearInterval(this._pollInterval);
        }

        this.setState({ step: 'success' });
        this.props.onSuccess(result);
      } catch (error) {
        // Continue polling if not successful yet
        console.log('Polling for token...');
      }
    };

    // Start polling
    poll();
    this._pollInterval = window.setInterval(
      poll,
      (this.state.deviceFlow.interval || 5) * 1000
    );
  }

  private async submitManualToken(): Promise<void> {
    if (!this.state.manualToken || !this.state.manualUsername) {
      this.setState({
        error: 'Please enter both username and token'
      });
      return;
    }

    try {
      this.setState({ step: 'polling' });

      const host = this.props.baseUrl
        ? new URL(this.props.baseUrl).hostname
        : `${this.props.provider}.com`;

      const result = await Auth.storeToken(
        this.props.provider,
        host,
        this.state.manualUsername,
        this.state.manualToken
      );

      this.setState({ step: 'success' });
      this.props.onSuccess(result);
    } catch (error) {
      this.setState({
        step: 'manual_token',
        error: (error as Error).message
      });
    }
  }

  render(): JSX.Element {
    const { provider, trans } = this.props;
    const { step, deviceFlow, error, manualToken, manualUsername } = this.state;

    const providerName = Auth.getProviderDisplayName(provider);

    return (
      <div className="jp-Git-auth-dialog">
        {step === 'loading' && (
          <div className="jp-Git-auth-loading">
            <p>{trans.__('Initializing authentication with %1...', providerName)}</p>
          </div>
        )}

        {step === 'device_code' && deviceFlow && (
          <div className="jp-Git-auth-device-code">
            <h3>{trans.__('Sign in to %1', providerName)}</h3>
            <p>{trans.__('To continue, please authorize this application:')}</p>
            <div className="jp-Git-auth-code-box">
              <div className="jp-Git-auth-code">{deviceFlow.user_code}</div>
            </div>
            <p>
              {trans.__(
                'Open the following URL in your browser and enter the code above:'
              )}
            </p>
            <a
              href={deviceFlow.verification_uri}
              target="_blank"
              rel="noopener noreferrer"
              className="jp-Git-auth-link"
            >
              {deviceFlow.verification_uri}
            </a>
            <button
              className="jp-Button jp-mod-styled jp-mod-accept"
              onClick={() => this.startPolling()}
            >
              {trans.__('I have authorized')}
            </button>
          </div>
        )}

        {step === 'polling' && (
          <div className="jp-Git-auth-polling">
            <div className="jp-Git-auth-spinner" />
            <p>{trans.__('Waiting for authorization...')}</p>
            <p className="jp-Git-auth-hint">
              {trans.__(
                'Please complete the authorization in your browser. This dialog will close automatically.'
              )}
            </p>
          </div>
        )}

        {step === 'manual_token' && deviceFlow && (
          <div className="jp-Git-auth-manual-token">
            <h3>{trans.__('Sign in to %1', providerName)}</h3>
            <p>{deviceFlow.instructions}</p>
            <a
              href={deviceFlow.verification_uri}
              target="_blank"
              rel="noopener noreferrer"
              className="jp-Git-auth-link"
            >
              {trans.__('Open %1 settings', providerName)}
            </a>
            <div className="jp-Git-auth-form">
              <label>
                <span>{trans.__('Username')}</span>
                <input
                  type="text"
                  className="jp-Input"
                  value={manualUsername || ''}
                  onChange={e =>
                    this.setState({ manualUsername: e.target.value })
                  }
                  placeholder={trans.__('Enter your username')}
                />
              </label>
              <label>
                <span>{trans.__('Personal Access Token')}</span>
                <input
                  type="password"
                  className="jp-Input"
                  value={manualToken || ''}
                  onChange={e => this.setState({ manualToken: e.target.value })}
                  placeholder={trans.__('Paste your token here')}
                />
              </label>
              {error && <div className="jp-Git-auth-error">{error}</div>}
              <button
                className="jp-Button jp-mod-styled jp-mod-accept"
                onClick={() => this.submitManualToken()}
              >
                {trans.__('Sign In')}
              </button>
            </div>
          </div>
        )}

        {step === 'success' && (
          <div className="jp-Git-auth-success">
            <div className="jp-Git-auth-success-icon">✓</div>
            <p>{trans.__('Successfully signed in to %1!', providerName)}</p>
          </div>
        )}

        {step === 'error' && (
          <div className="jp-Git-auth-error-container">
            <h3>{trans.__('Authentication Failed')}</h3>
            <p className="jp-Git-auth-error">{error}</p>
            <button
              className="jp-Button jp-mod-styled jp-mod-accept"
              onClick={() => this.startAuthFlow()}
            >
              {trans.__('Try Again')}
            </button>
          </div>
        )}
      </div>
    );
  }
}

/**
 * Widget wrapper for AuthDialog
 */
export class AuthDialogWidget
  extends Widget
  implements Dialog.IBodyWidget<Auth.IAuthResult | null>
{
  private _root: Root;
  private _result: Auth.IAuthResult | null = null;
  private _resolver?: (value: Auth.IAuthResult | null) => void;

  constructor(
    provider: Auth.Provider,
    baseUrl: string | undefined,
    trans: TranslationBundle
  ) {
    super();
    this.addClass('jp-Git-auth-dialog-widget');

    this._root = createRoot(this.node);
    this._root.render(
      <AuthDialogComponent
        provider={provider}
        baseUrl={baseUrl}
        trans={trans}
        onSuccess={result => {
          this._result = result;
          if (this._resolver) {
            this._resolver(result);
          }
        }}
        onCancel={() => {
          this._result = null;
          if (this._resolver) {
            this._resolver(null);
          }
        }}
      />
    );
  }

  /**
   * Get the dialog result
   */
  getValue(): Auth.IAuthResult | null {
    return this._result;
  }

  /**
   * Dispose of the widget
   */
  dispose(): void {
    this._root.unmount();
    super.dispose();
  }
}

/**
 * Show authentication dialog
 */
export async function showAuthDialog(
  provider: Auth.Provider,
  baseUrl: string | undefined,
  trans: TranslationBundle
): Promise<Auth.IAuthResult | null> {
  const body = new AuthDialogWidget(provider, baseUrl, trans);
  const providerName = Auth.getProviderDisplayName(provider);

  const result = await showDialog({
    title: trans.__('Sign in to %1', providerName),
    body,
    buttons: [Dialog.cancelButton({ label: trans.__('Cancel') })]
  });

  if (result.button.accept) {
    return body.getValue();
  }

  return null;
}
