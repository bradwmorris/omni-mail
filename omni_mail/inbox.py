"""Local inbox snapshots and one background worker for sync and classification."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from threading import Lock, Thread

from . import gmail
from .sample import sample_threads


class Inbox:
    def __init__(self, mode, directory, classifier_version=None, classifier_factory=None):
        self.mode = mode
        self.directory = directory
        self.classifier_version = classifier_version
        self.classifier_factory = classifier_factory
        self.classifier = None
        self.db = directory / f"{mode}.sqlite3"
        self.lock = Lock()
        self.stage = "idle"
        self.error = None
        self.failed = set()
        with closing(sqlite3.connect(self.db)) as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS snapshot (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    account TEXT, synced TEXT NOT NULL, threads TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decision (
                    message_id TEXT NOT NULL, version TEXT NOT NULL,
                    result TEXT NOT NULL, PRIMARY KEY (message_id, version)
                );
            """)

    def read(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("BEGIN")
            row = connection.execute("SELECT account, synced, threads FROM snapshot").fetchone()
            decisions = dict(connection.execute(
                "SELECT message_id, result FROM decision WHERE version = ?",
                (self.classifier_version,),
            ))
        account, synced, raw = row or (None, None, "[]")
        return account, synced, json.loads(raw), decisions

    def overview(self):
        with self.lock:
            stage, error, failed = self.stage, self.error, self.failed.copy()
        account, synced, threads, decisions = self.read()
        rows = []
        for thread in threads:
            target = thread["target"]
            result = thread["sample_decision"] if self.mode == "sample" else decisions.get(target)
            row = {key: thread[key] for key in ("id", "subject", "sender", "timestamp", "preview")}
            row["decision"] = result or ("unavailable" if target in failed else "pending")
            rows.append(row)
        return {"mode": self.mode, "account": account, "synced": synced, "stage": stage,
                "error": error, "limit": gmail.LIMIT, "threads": rows}

    def thread(self, identifier):
        for thread in self.read()[2]:
            if thread["id"] == identifier:
                return {key: thread[key] for key in ("id", "subject", "messages")}
        return None

    def refresh(self):
        with self.lock:
            if self.stage != "idle":
                return
            self.stage = "syncing"
            self.error = None
            self.failed.clear()
        Thread(target=self._refresh, daemon=True).start()

    def activate(self, version, factory):
        with self.lock:
            if self.stage != "idle":
                raise RuntimeError("Wait for the current inbox pass to finish.")
            self.classifier_version = version
            self.classifier_factory = factory
            self.classifier = None
            self.failed.clear()
            self.error = None
            self.stage = "classifying"
        Thread(target=self._classify_snapshot, daemon=True).start()

    def _classify_snapshot(self):
        try:
            _, _, threads, decisions = self.read()
            self._classify(threads, decisions)
        finally:
            with self.lock:
                self.stage = "idle"

    def _refresh(self):
        try:
            previous_account, _, _, decisions = self.read()

            def require_same_account(account):
                if previous_account and account != previous_account:
                    raise gmail.ReconnectRequired

            if self.mode == "gmail":
                account, threads = gmail.fetch_inbox(self.directory / "gmail-token.json", require_same_account)
            else:
                account, threads = None, sample_threads()

            with closing(sqlite3.connect(self.db)) as connection, connection:
                connection.execute(
                    "INSERT OR REPLACE INTO snapshot VALUES (1, ?, ?, ?)",
                    (account, datetime.now(timezone.utc).isoformat(), json.dumps(threads)),
                )
                latest = [thread["target"] for thread in threads]
                if latest:
                    marks = ",".join("?" for _ in latest)
                    connection.execute(f"DELETE FROM decision WHERE message_id NOT IN ({marks})", latest)
                else:
                    connection.execute("DELETE FROM decision")
            if self.classifier_factory and any(thread["target"] not in decisions for thread in threads):
                with self.lock:
                    self.stage = "classifying"
                self._classify(threads, decisions)
        except gmail.GmailAPIDisabled:
            with self.lock:
                self.error = "The Gmail API is disabled in the OAuth project."
        except gmail.ReconnectRequired:
            with self.lock:
                self.error = "Reconnect the original Gmail account with the authorize command."
        except Exception:
            with self.lock:
                self.error = "Sync failed. Refresh to try again."
        finally:
            with self.lock:
                self.stage = "idle"

    def _classify(self, threads, decisions):
        pending = [thread for thread in threads if thread["target"] not in decisions]
        if not pending:
            return
        if self.classifier is None:
            try:
                self.classifier = self.classifier_factory()
            except Exception:
                with self.lock:
                    self.failed.update(thread["target"] for thread in pending)
                    self.error = "Couldn’t start the local model. Check the notebook environment and model cache."
                return
        for thread in pending:
            target = next(message for message in thread["messages"] if message["id"] == thread["target"])
            try:
                if target["body"] is None:
                    raise ValueError("No readable message body.")
                result = self.classifier(
                    target["from"], target.get("subject", thread["subject"]), target["body"],
                )
                with closing(sqlite3.connect(self.db)) as connection, connection:
                    connection.execute(
                        "INSERT OR REPLACE INTO decision VALUES (?, ?, ?)",
                        (target["id"], self.classifier_version, result),
                    )
            except Exception:
                with self.lock:
                    self.failed.add(target["id"])


class CombinedInbox:
    """Expose one inbox while keeping each Gmail cache and token separate."""

    def __init__(self, mailboxes):
        self.mailboxes = mailboxes

    def overview(self):
        snapshots = [(name, inbox.overview()) for name, inbox in self.mailboxes.items()]
        stages = {box["stage"] for _, box in snapshots}
        stage = next(status for status in ("syncing", "classifying", "idle")
                     if status == "idle" or status in stages)
        rows = [
            {**row, "id": f"{name}/{row['id']}", "account": box["account"] or name}
            for name, box in snapshots for row in box["threads"]
        ]
        rows.sort(key=lambda row: row["timestamp"], reverse=True)
        errors = [f"{box['account'] or name}: {box['error']}"
                  for name, box in snapshots if box["error"]]
        sync_times = [box["synced"] for _, box in snapshots if box["synced"]]
        return {
            "mode": "gmail", "account": f"{len(self.mailboxes)} Gmail accounts",
            "account_count": len(self.mailboxes), "stage": stage,
            "synced": min(sync_times) if len(sync_times) == len(snapshots) else None,
            "revision": "|".join(box["synced"] or "" for _, box in snapshots),
            "error": " ".join(errors) or None, "limit": gmail.LIMIT, "threads": rows,
        }

    def thread(self, identifier):
        name, separator, thread_id = identifier.partition("/")
        if not separator or name not in self.mailboxes:
            return None
        return self.mailboxes[name].thread(thread_id)

    def refresh(self):
        for inbox in self.mailboxes.values():
            inbox.refresh()
