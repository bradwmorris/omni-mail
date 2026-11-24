"""Launch Omni Mail on the local Mac."""

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import unquote, urlsplit

from . import gmail
from .inbox import CombinedInbox, Inbox
from .jev import Jev, PROVIDERS
from .profiles import STOCK, load_profile

WEB = Path(__file__).resolve().parents[1] / "web" / "dist"
DEFAULT_DATA = Path.home() / "Library" / "Application Support" / "Omni Mail"


class InboxService:
    def __init__(self, inbox, mailboxes, model=None, profiles=None, worker=None, model_available=None, jev=None):
        self.inbox = inbox
        self.mailboxes = mailboxes
        self.model = model
        self.profiles = profiles
        self.worker = worker
        self.model_available = model_available
        self.jev = jev
        self.lock = Lock()

    def snapshot(self):
        data = self.inbox.overview()
        if self.profiles:
            data["model"] = self.model
            data["models"] = [
                {"id": key, "label": profile.label, "available": self.model_available(profile)}
                for key, profile in self.profiles.items()
            ]
        if self.jev:
            providers = [
                {"id": key, "label": spec[0], "connected": bool(self.jev.key(key))}
                for key, spec in PROVIDERS.items()
            ]
            data["jev"] = providers
            data["models"].extend(
                {"id": "jev-" + provider["id"], "label": "JEV · " + provider["label"], "available": True}
                for provider in providers if provider["connected"]
            )
        return data

    def overview(self):
        with self.lock:
            return self.snapshot()

    def refresh(self):
        with self.lock:
            self.inbox.refresh()
            return self.snapshot()

    def process(self, identifiers):
        with self.lock:
            snapshot = self.snapshot()
            if snapshot["stage"] != "idle":
                return {"error": "Wait for the current inbox pass to finish."}, 409
            if identifiers is not None:
                existing = {row["id"] for row in snapshot["threads"]}
                if not identifiers <= existing:
                    return {"error": "Some selected threads are no longer in the inbox."}, 409
            if self.model and self.model.startswith("jev-"):
                if not self.jev.key(self.model.removeprefix("jev-")):
                    return {"error": "Connect a Jev API key to process mail."}, 422
            elif self.profiles and not self.model_available(self.profiles[self.model]):
                return {"error": "Download the selected model using the setup guide."}, 422
            self.inbox.process(identifiers)
            return self.snapshot(), 202

    def _activate(self, key, version, factory):
        for inbox in self.mailboxes:
            inbox.activate(version, factory)
        self.model = key
        return self.snapshot(), 200

    def choose(self, key):
        with self.lock:
            if key == self.model:
                return self.snapshot(), 200
            if self.inbox.overview()["stage"] != "idle":
                return {"error": "Wait for the current inbox pass to finish."}, 409
            provider = key.removeprefix("jev-")
            if self.jev and key.startswith("jev-") and provider in PROVIDERS:
                if not self.jev.key(provider):
                    return {"error": "Connect an API key for this Jev provider."}, 422
                return self._activate(key, self.jev.version(provider), lambda: self.jev.classifier(provider))
            if not self.profiles or key not in self.profiles:
                return {"error": "Unknown model."}, 404
            profile = self.profiles[key]
            if not self.model_available(profile):
                return {"error": f"Download {profile.label} using the setup guide."}, 422
            return self._activate(key, profile.version, lambda: self.worker.for_profile(profile))

    def connect_jev(self, provider, key):
        with self.lock:
            if not self.jev or not isinstance(provider, str) or provider not in PROVIDERS:
                return {"error": "Choose OpenRouter or TypeSafe."}, 400
            if self.inbox.overview()["stage"] != "idle":
                return {"error": "Wait for the current inbox pass to finish."}, 409
            try:
                self.jev.save_key(provider, key)
            except ValueError as error:
                return {"error": str(error)}, 400
            except OSError:
                return {"error": "Couldn’t save the key in the local application directory."}, 500
            model = "jev-" + provider
            if self.model == model:
                return self._activate(model, self.jev.version(provider), lambda: self.jev.classifier(provider))
            return self.snapshot(), 200


def server_handler(service):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=WEB, **kwargs)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            super().end_headers()

        def response(self, data, status=200):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def local_request(self):
            port = self.server.server_port
            return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def do_GET(self):
            if not self.local_request():
                return self.response({"error": "Omni Mail is local only."}, 403)
            route = urlsplit(self.path).path
            if route == "/api/inbox":
                return self.response(service.overview())
            if route.startswith("/api/threads/"):
                thread = service.inbox.thread(unquote(route.removeprefix("/api/threads/")))
                return self.response(thread) if thread else self.response({"error": "Thread is no longer in the inbox."}, 404)
            if route == "/" or route.startswith("/assets/"):
                return super().do_GET()
            return self.response({"error": "Page not found."}, 404)

        def read_json(self):
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 32768:
                raise ValueError
            return json.loads(self.rfile.read(length))

        def do_POST(self):
            if not self.local_request() or self.headers.get("Origin") != "http://" + self.headers["Host"]:
                return self.response({"error": "Omni Mail is local only."}, 403)
            if self.path in {"/api/sync", "/api/refresh"}:
                return self.response(service.refresh(), 202)
            if self.path == "/api/process":
                try:
                    thread_ids = self.read_json()["thread_ids"]
                    if thread_ids is not None and (not isinstance(thread_ids, list) or not thread_ids
                                                   or not all(isinstance(key, str) for key in thread_ids)):
                        raise ValueError
                except (ValueError, KeyError, TypeError, UnicodeError):
                    return self.response({"error": "Invalid thread selection."}, 400)
                data, status = service.process(None if thread_ids is None else set(thread_ids))
                return self.response(data, status)
            if self.path == "/api/jev":
                try:
                    payload = self.read_json()
                    provider, key = payload["provider"], payload["key"]
                except (ValueError, KeyError, TypeError, UnicodeError):
                    return self.response({"error": "Invalid Jev settings."}, 400)
                data, status = service.connect_jev(provider, key)
                return self.response(data, status)
            if self.path.startswith("/api/model/"):
                data, status = service.choose(self.path.removeprefix("/api/model/"))
                return self.response(data, status)
            return self.response({"error": "Page not found."}, 404)

        def log_message(self, *_args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    commands = parser.add_subparsers(dest="command", required=True)
    app = commands.add_parser("serve")
    app.add_argument("--mode", choices=("sample", "sample-model", "gmail"), default="sample")
    app.add_argument("--port", type=int, default=8765)
    app.add_argument("--mailbox", action="append", default=[],
                     help="Named Gmail data directory. Repeat to show multiple accounts together.")
    app.add_argument("--model", choices=STOCK, default="omni-600m")
    app.add_argument("--profile", type=Path, action="append", default=[],
                     help="Optional local classifier profile. Repeat to load one per model.")
    oauth = commands.add_parser("authorize")
    oauth.add_argument("client_file", type=Path)
    export = commands.add_parser("export-mail", help="Export private inbox text for labeling.")
    export.add_argument("output", type=Path)
    export.add_argument("--after", required=True, help="First day included, YYYY-MM-DD (UTC)")
    export.add_argument("--before", required=True, help="First day excluded, YYYY-MM-DD (UTC)")
    export.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    args.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.command == "authorize":
        gmail.authorize(args.client_file, args.data_dir / "gmail-token.json")
        print("Gmail read-only access is ready.")
        return

    if args.command == "export-mail":
        try:
            dates = [datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                     for day in (args.after, args.before)]
            first, last = (int(date.timestamp()) for date in dates)
        except ValueError:
            parser.error("Dates must use YYYY-MM-DD.")
        if first >= last or args.limit < 1 or args.output.exists():
            parser.error("Choose increasing dates, a positive limit, and a new output path.")
        if Path(__file__).resolve().parents[1] in args.output.resolve().parents:
            parser.error("Save your email export outside the project checkout.")
        if not args.output.parent.is_dir():
            parser.error("Create the private output directory first.")
        try:
            _, threads = gmail.fetch_inbox(args.data_dir / "gmail-token.json", lambda _: None,
                                          limit=args.limit, date_range=(first, last))
        except gmail.ReconnectRequired:
            parser.error("Authorize the Gmail account before exporting it.")
        except gmail.GmailAPIDisabled:
            parser.error("Enable the Gmail API in the OAuth client's Cloud project.")
        from os import O_CREAT, O_EXCL, O_WRONLY, fdopen, open as open_file

        fd = open_file(args.output, O_CREAT | O_EXCL | O_WRONLY, 0o600)
        with fdopen(fd, "w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(("id", "group_id", "sender", "subject", "body", "label"))
            for thread in threads:
                message = next(row for row in thread["messages"] if row["id"] == thread["target"])
                writer.writerow((message["id"], thread["id"], message["from"],
                                 message["subject"], message["body"], ""))
        print(f"Exported {len(threads)} inbox messages for labeling.")
        return

    if not (WEB / "index.html").is_file():
        parser.error("Build the frontend first with npm --prefix web run build.")
    options = {}
    profiles = worker = available = None
    if args.mode != "sample":
        from .classifier import ModelWorker, checkpoint_path

        profiles = STOCK.copy()
        for path in args.profile:
            try:
                profile = load_profile(path)
            except (ValueError, KeyError, TypeError, OSError) as error:
                parser.error(f"Cannot load profile: {error}")
            profiles[profile.key] = profile
        profile = profiles[args.model]
        worker = ModelWorker()

        def available(candidate):
            return (checkpoint_path(candidate) / "model.safetensors").is_file()

        options = {
            "classifier_version": profile.version,
            "classifier_factory": lambda: worker.for_profile(profile),
        }
    elif args.profile:
        parser.error("--profile requires sample-model or gmail mode.")

    if args.mailbox:
        if args.mode != "gmail":
            parser.error("--mailbox requires Gmail mode.")
        if len(set(args.mailbox)) != len(args.mailbox) or any(
            not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", name) for name in args.mailbox
        ):
            parser.error("Use distinct mailbox names with letters, digits, underscores, or hyphens.")
        boxes = {}
        for name in args.mailbox:
            directory = args.data_dir / name
            directory.mkdir(mode=0o700, exist_ok=True)
            boxes[name] = Inbox("gmail", directory, **options)
        inbox = CombinedInbox(boxes)
        mailboxes = list(boxes.values())
    else:
        inbox = Inbox(args.mode, args.data_dir, **options)
        mailboxes = [inbox]
    jev = Jev(args.data_dir) if profiles else None
    service = InboxService(inbox, mailboxes, args.model, profiles, worker, available, jev)
    with ThreadingHTTPServer(("127.0.0.1", args.port), server_handler(service)) as server:
        if args.mode != "gmail":
            inbox.refresh()
        print(f"Omni Mail: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            if worker:
                worker.close()


if __name__ == "__main__":
    main()
