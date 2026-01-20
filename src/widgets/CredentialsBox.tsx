import { Dialog } from '@jupyterlab/apputils';
import { TranslationBundle } from '@jupyterlab/translation';
import { Widget } from '@lumino/widgets';
import { Auth } from '../auth';
import { showAuthDialog } from './AuthDialog';
import { Git } from '../tokens';

/**
 * The UI for the credentials form
 */
export class GitCredentialsForm
  extends Widget
  implements Dialog.IBodyWidget<Git.IAuth>
{
  private _passwordPlaceholder: string;
  private _repoUrl?: string;

  constructor(
    trans: TranslationBundle,
    textContent = trans.__('Enter credentials for remote repository'),
    warningContent = '',
    passwordPlaceholder = trans.__('password / personal access token'),
    repoUrl?: string
  ) {
    super();
    this._trans = trans;
    this._passwordPlaceholder = passwordPlaceholder;
    this._repoUrl = repoUrl;
    this.node.appendChild(this.createBody(textContent, warningContent));
  }

  private createBody(textContent: string, warningContent: string): HTMLElement {
    const node = document.createElement('div');
    const label = document.createElement('label');

    const checkboxLabel = document.createElement('label');
    this._checkboxCacheCredentials = document.createElement('input');
    const checkboxText = document.createElement('span');

    this._user = document.createElement('input');
    this._user.type = 'text';
    this._password = document.createElement('input');
    this._password.type = 'password';

    const text = document.createElement('span');
    const warning = document.createElement('div');

    node.className = 'jp-CredentialsBox';
    warning.className = 'jp-CredentialsBox-warning';
    text.textContent = textContent;
    warning.textContent = warningContent;
    this._user.placeholder = this._trans.__('username');
    this._password.placeholder = this._passwordPlaceholder;

    checkboxLabel.className = 'jp-CredentialsBox-label-checkbox';
    this._checkboxCacheCredentials.type = 'checkbox';
    checkboxText.textContent = this._trans.__('Save my login temporarily');

    label.appendChild(text);
    label.appendChild(this._user);
    label.appendChild(this._password);
    node.appendChild(label);
    node.appendChild(warning);

    checkboxLabel.appendChild(this._checkboxCacheCredentials);
    checkboxLabel.appendChild(checkboxText);
    node.appendChild(checkboxLabel);

    // Add "Sign in with..." section if we can detect the provider
    if (this._repoUrl) {
      const repoInfo = Auth.parseRepoUrl(this._repoUrl);
      if (repoInfo && repoInfo.provider) {
        const separator = document.createElement('div');
        separator.className = 'jp-CredentialsBox-separator';
        separator.textContent = this._trans.__('or');
        node.appendChild(separator);

        const signInButton = document.createElement('button');
        signInButton.className = 'jp-Button jp-mod-styled jp-mod-accept';
        signInButton.textContent = this._trans.__(
          'Sign in with %1',
          Auth.getProviderDisplayName(repoInfo.provider)
        );
        signInButton.onclick = async () => {
          try {
            const result = await showAuthDialog(
              repoInfo.provider!,
              undefined,
              this._trans
            );
            if (result) {
              // Store the result so it can be retrieved
              this._authResult = result;
              // Close the dialog by triggering the OK button
              const okButton = document.querySelector<HTMLButtonElement>(
                '.jp-Dialog-button.jp-mod-accept'
              );
              if (okButton) {
                okButton.click();
              }
            }
          } catch (error) {
            console.error('Failed to sign in:', error);
          }
        };
        node.appendChild(signInButton);

        const hint = document.createElement('div');
        hint.className = 'jp-CredentialsBox-hint';
        hint.textContent = this._trans.__(
          'Sign in once and your credentials will be stored securely'
        );
        node.appendChild(hint);
      }
    }

    return node;
  }

  /**
   * Returns the input value.
   */
  getValue(): Git.IAuth {
    // If we have an auth result from the sign-in flow, use that
    if (this._authResult) {
      return {
        username: this._authResult.username,
        password: '', // Password will be retrieved from token storage
        cache_credentials: false,
        use_stored_token: true,
        provider: this._authResult.provider,
        host: this._authResult.host
      };
    }

    return {
      username: this._user.value,
      password: this._password.value,
      cache_credentials: this._checkboxCacheCredentials.checked
    };
  }

  protected _trans: TranslationBundle;
  // @ts-expect-error initialization is indirect
  private _user: HTMLInputElement;
  // @ts-expect-error initialization is indirect
  private _password: HTMLInputElement;
  // @ts-expect-error initialization is indirect
  private _checkboxCacheCredentials: HTMLInputElement;
  private _authResult?: Auth.IAuthResult;
}
