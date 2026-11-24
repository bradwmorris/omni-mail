# Gmail setup

[Back to the Omni Mail walkthrough](../README.md)

## Connect Gmail

Omni Mail uses Google OAuth. The **Desktop app** JSON identifies your app
to Google. When you run `authorize`, Google opens a browser window for
sign-in and consent. Google sends a one-time code back to Omni Mail on your
Mac. Omni Mail exchanges that code for a token and saves it locally in the
mailbox's `gmail-token.json` for future syncs. Your Gmail password stays
with Google. [Google OAuth for desktop apps](https://developers.google.com/identity/protocols/oauth2/native-app)

The token grants `gmail.readonly`. Omni Mail can read mail for inbox sync
and lab exports. Sending replies, archiving, and changing Gmail labels
remain actions you take in Gmail. Keep the downloaded JSON and the saved
token private. [Gmail API permissions](https://developers.google.com/workspace/gmail/api/auth/scopes)

[Build the app and install its Python environment](install.md#build-the-app) first.
Then set up read-only Gmail access:

1. Create or select a Google Cloud project. Enable **Gmail API** in that exact
   project. If two projects have similar names, check the project ID or number
   before enabling it.
2. Set up the OAuth consent screen. If the app is in External Testing, add
   each Gmail account you plan to connect as a test user.
3. Create an OAuth client of type **Desktop app**. Download its JSON file and
   save it in a private folder outside the checkout.
4. Run the authorize command and choose the Gmail account in your browser.
   Check that the consent screen requests read-only Gmail access.
   [Google's Gmail setup guide](https://developers.google.com/workspace/gmail/api/quickstart/python)

For one Gmail account:

```sh
.venv/bin/python -m omni_mail authorize /path/to/your/client_secret.json
.venv/bin/python -m omni_mail serve --mode gmail --model d1-2b
```

To combine two accounts, authorize each into a separate private directory.
Choose a different account at each consent screen.

```sh
omni_data="$HOME/Library/Application Support/Omni Mail"
.venv/bin/python -m omni_mail --data-dir "$omni_data/account-1" authorize /path/to/your/client_secret.json
.venv/bin/python -m omni_mail --data-dir "$omni_data/account-2" authorize /path/to/your/client_secret.json
.venv/bin/python -m omni_mail serve --mode gmail --model d1-2b --mailbox account-1 --mailbox account-2
```

Leave the server running. When you're ready to see your mail, open the
[inbox guide](inbox.md#sync-and-process-mail). Each account has its own
token, mail cache, and decisions. If Google asks you to reconnect, repeat the
authorize command for that account. External Testing can issue refresh tokens
that expire after seven days. [Google's token expiration rules](https://developers.google.com/identity/protocols/oauth2#expiration)
