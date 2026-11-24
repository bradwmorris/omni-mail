"""Hosted Jev providers and their local credentials."""

import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from .profiles import D1_INSTRUCTIONS

PROVIDERS = {
    "openrouter": ("OpenRouter", "https://openrouter.ai/api/alpha/decisions", "typesafe/jev-1.14", "OPENROUTER_API_KEY"),
    "typesafe": ("TypeSafe", "https://api.typesafe.ai/v1/systemone", "jev-1.14.0", "TYPESAFE_API_KEY"),
}
BODY_LIMIT = 12000
CUTOFF = 0.5


class JevError(Exception):
    """A provider error suitable to display without request or response details."""


class Jev:
    def __init__(self, directory):
        self.directory = directory

    def key(self, provider):
        path = self.directory / f"jev-{provider}.key"
        try:
            return path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return os.environ.get(PROVIDERS[provider][3], "").strip()

    def save_key(self, provider, key):
        if (not isinstance(key, str) or not 12 <= len(key) <= 512
                or not key.isascii() or any(char.isspace() or ord(char) < 33 for char in key)):
            raise ValueError("Enter a valid API key.")
        with NamedTemporaryFile(mode="w", dir=self.directory, delete=False, encoding="utf-8") as staged:
            staged.write(key + "\n")
        Path(staged.name).replace(self.directory / f"jev-{provider}.key")

    def version(self, provider):
        state = (provider, PROVIDERS[provider][2], D1_INSTRUCTIONS, BODY_LIMIT, CUTOFF, "jev-mail-v1")
        return hashlib.sha256(json.dumps(state).encode()).hexdigest()

    def classifier(self, provider):
        return JevClassifier(provider, self.key(provider))


class JevClassifier:
    def __init__(self, provider, key):
        self.name, self.url, self.model, _ = PROVIDERS[provider]
        self.key = key
        if not key:
            raise JevError(f"Connect a {self.name} API key in Jev settings.")

    def __call__(self, sender, subject, body):
        import requests

        payload = {
            "model": self.model,
            "state": {"sender": sender[:512], "subject": subject[:512], "body": body[:BODY_LIMIT]},
            "questions": {"needs_action": {"type": "noul", "instructions": D1_INSTRUCTIONS}},
        }
        try:
            response = requests.post(
                self.url, headers={"Authorization": f"Bearer {self.key}"}, json=payload,
                timeout=(5, 25), allow_redirects=False,
            )
        except requests.RequestException:
            raise JevError(f"Couldn’t reach Jev via {self.name}. Try processing again.") from None
        if response.status_code in (401, 403):
            raise JevError(f"{self.name} rejected the Jev request. Check the key and account access.")
        if response.status_code == 402:
            raise JevError(f"{self.name} needs credits to process with Jev.")
        if response.status_code == 429:
            raise JevError(f"{self.name} rate limited Jev. Wait before trying the remaining mail.")
        if not 200 <= response.status_code < 300:
            raise JevError(f"Jev via {self.name} returned an error. Try processing again.")
        try:
            score = response.json()["answers"]["needs_action"]["noul"]
            if type(score) not in (float, int) or not 0 <= score <= 1:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise JevError(f"Jev via {self.name} returned an invalid decision.") from None
        return "yes" if score >= CUTOFF else "no"
