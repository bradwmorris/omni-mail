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
from .profiles import STOCK, load_profile

WEB = Path(__file__).resolve().parents[1] / "web" / "dist"
DEFAULT_DATA = Path.home() / "Library" / "Application Support" / "Omni Mail"


class InboxService:
    def __init__(self, inbox, mailboxes, model=None, profiles=None, worker=None, model_available=None):
        self.inbox = inbox
        self.mailboxes = mailboxes
        self.model = model
        self.profiles = profiles
        self.worker = worker
        self.model_available = model_available
        self.lock = Lock()

    def snapshot(self):
        data = self.inbox.overview()
        if self.profiles:
            data["model"] = self.model
            data["models"] = [
                {"id": key, "label": profile.label, "available": self.model_available(profile)}
                for key, profile in self.profiles.items()
            ]
        return data

    def overview(self):
        with self.lock:
            return self.snapshot()

    def refresh(self):
        with self.lock:
            self.inbox.refresh()
            return self.snapshot()

    def choose(self, key):
        with self.lock:
            if not self.profiles or key not in self.profiles:
                return {"error": "Unknown model."}, 404
            if key == self.model:
                return self.snapshot(), 200
            profile = self.profiles[key]
            if not self.model_available(profile):
                return {"error": f"Download {profile.label} using the setup guide."}, 422
            if self.inbox.overview()["stage"] != "idle":
                return {"error": "Wait for the current inbox pass to finish."}, 409
            for inbox in self.mailboxes:
                inbox.activate(profile.version, lambda: self.worker.for_profile(profile))
            self.model = key
            return self.snapshot(), 202


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

        def do_POST(self):
            if not self.local_request() or self.headers.get("Origin") != "http://" + self.headers["Host"]:
                return self.response({"error": "Omni Mail is local only."}, 403)
            if self.path == "/api/refresh":
                return self.response(service.refresh(), 202)
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
    service = InboxService(inbox, mailboxes, args.model, profiles, worker, available)
    with ThreadingHTTPServer(("127.0.0.1", args.port), server_handler(service)) as server:
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
