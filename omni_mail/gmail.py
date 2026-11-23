"""Read-only, bounded Gmail inbox sync and desktop authorization."""

import base64
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlencode

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me"
LIMIT = 50


class ReconnectRequired(Exception):
    pass


class GmailAPIDisabled(Exception):
    pass


def save_token(path, credentials):
    with NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as staged:
        staged.write(credentials.to_json())
    Path(staged.name).replace(path)


def authorize(client_file, token_file):
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_file), [SCOPE], autogenerate_code_verifier=True,
    )
    credentials = flow.run_local_server(
        host="127.0.0.1", port=0, prompt="select_account consent",
        timeout_seconds=300, authorization_prompt_message="",
    )
    granted = set(credentials.granted_scopes or credentials.scopes or ())
    if granted != {SCOPE}:
        raise SystemExit("Use a dedicated OAuth client authorized only for Gmail read access.")
    save_token(token_file, credentials)


def decode_raw(raw, html_to_text):
    encoded = raw["raw"]
    data = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    mail = BytesParser(policy=policy.default).parsebytes(data)
    part = mail.get_body(preferencelist=("plain", "html"))
    body = None
    if part:
        charset = part.get_content_charset() or "utf-8"
        payload = part.get_payload(decode=True)
        if payload is not None:
            try:
                body = payload.decode(charset, errors="replace")
            except LookupError:
                body = payload.decode("utf-8", errors="replace")
            if part.get_content_type() == "text/html":
                body = html_to_text(body)
    return {"id": raw["id"], "from": str(mail.get("From", "")),
            "timestamp": int(raw["internalDate"]) // 1000, "body": body,
            "inbound_inbox": "INBOX" in raw.get("labelIds", []) and "SENT" not in raw.get("labelIds", []),
            "subject": str(mail.get("Subject", ""))}


def fetch_inbox(token_file, cache_guard, *, limit=LIMIT, date_range=None):
    from bs4 import BeautifulSoup
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.credentials import Credentials

    if not token_file.is_file():
        raise ReconnectRequired
    credentials = Credentials.from_authorized_user_file(str(token_file), scopes=[SCOPE])
    previous_token = credentials.token

    def html_to_text(html):
        soup = BeautifulSoup(html, "html.parser")
        for element in soup(["head", "style", "script", "template"]):
            element.decompose()
        for br in soup.find_all("br"):
            br.replace_with("\n")
        return soup.get_text("\n", strip=True)

    with AuthorizedSession(credentials) as session:
        def read(path, **query):
            url = f"{BASE_URL}/{path}"
            if query:
                url += "?" + urlencode(query)
            try:
                response = session.get(url, timeout=20)
            except RefreshError:
                raise ReconnectRequired from None
            if response.status_code == 401:
                raise ReconnectRequired
            if response.status_code == 403:
                errors = response.json().get("error", {}).get("details", [])
                if any(error.get("reason") == "SERVICE_DISABLED" for error in errors):
                    raise GmailAPIDisabled
            response.raise_for_status()
            return response.json()

        profile = read("profile")
        account = profile["emailAddress"]
        cache_guard(account)
        threads = []
        token = None
        seen = set()
        while len(threads) < limit:
            query = {"labelIds": "INBOX", "maxResults": min(500, limit - len(threads))}
            if date_range:
                first, last = date_range
                query["q"] = f"after:{first - 1} before:{last}"
            if token:
                query["pageToken"] = token
            page = read("threads", **query)
            for item in page.get("threads", []):
                if item["id"] in seen:
                    continue
                seen.add(item["id"])
                # Thread retrieval does not offer RAW. Fetch each message in RAW
                # to let Python's MIME parser handle multipart and encodings.
                meta = read("threads/" + item["id"], format="metadata")
                messages = [
                    decode_raw(read("messages/" + message["id"], format="raw"), html_to_text)
                    for message in meta["messages"] if "DRAFT" not in message.get("labelIds", [])
                ]
                messages.sort(key=lambda message: message["timestamp"])
                inbox = [message for message in messages if message["inbound_inbox"]]
                if date_range:
                    inbox = [message for message in inbox
                             if first <= message["timestamp"] < last and message["body"] is not None]
                if not inbox:
                    continue
                target = inbox[-1]
                name, address = parseaddr(target["from"])
                threads.append({
                    "id": item["id"], "subject": target["subject"] or "(No subject)",
                    "timestamp": messages[-1]["timestamp"], "sender": name or address or "Unknown sender",
                    "preview": " ".join((target["body"] or "").split())[:250], "target": target["id"],
                    "messages": messages,
                })
            token = page.get("nextPageToken")
            if not token:
                break
        if credentials.token != previous_token:
            save_token(token_file, credentials)
    threads.sort(key=lambda thread: thread["timestamp"], reverse=True)
    return account, threads
