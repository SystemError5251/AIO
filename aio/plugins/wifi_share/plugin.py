"""WLAN-Dateiteiler: share a folder with devices in the same Wi-Fi via the browser.

Starts a small web server on the phone. The address contains a random token,
so only people who get the link can open it. Visitors can download files and,
if allowed, upload files into the folder (existing files are never replaced).
Paths are confined to the shared folder; symlinks pointing out are refused.
"""

from __future__ import annotations

import html
import secrets
import shutil
import socket
import subprocess
import threading
import urllib.parse
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from aio.core import media

PORT = 8765
CHUNK = 256 * 1024
MAX_UPLOAD = 4 * 1024 ** 3

UPLOAD_FORM = """
<form id="up"><input type="file" id="f" multiple> <button>Upload</button> <span id="s"></span></form>
<script>
document.getElementById('up').onsubmit = async (e) => {
  e.preventDefault();
  const s = document.getElementById('s');
  for (const file of document.getElementById('f').files) {
    s.textContent = file.name + ' …';
    const r = await fetch(location.pathname + encodeURIComponent(file.name), {method: 'PUT', body: file});
    s.textContent = file.name + ': ' + r.status;
  }
  location.reload();
};
</script>"""


def lan_ip() -> str:
    """Address of this device in the local network (no packet is sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def free_name(folder: Path, name: str) -> Path:
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate, n = folder / name, 2
    while candidate.exists():
        candidate = folder / f"{stem}-{n}{suffix}"
        n += 1
    return candidate


class ShareHandler(BaseHTTPRequestHandler):
    server_version = "AIO-share"

    def __init__(self, *args, root: Path, token: str, allow_upload: bool, log: list, **kwargs):
        self.root, self.token, self.allow_upload, self.log_lines = root, token, allow_upload, log
        super().__init__(*args, **kwargs)

    def log_message(self, fmt, *args):  # keep the terminal clean; remember for the summary
        self.log_lines.append(fmt % args)

    def _target(self) -> Path | None:
        """Resolve the request path inside root; None if the token is wrong or it escapes."""
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        prefix = f"/{self.token}/"
        if not (path + "/").startswith(prefix):
            return None
        rel = path[len(prefix):]
        target = (self.root / rel).resolve()
        if target != self.root and self.root not in target.parents:
            return None
        return target

    def _send(self, status: int, body: bytes, ctype: str = "text/plain; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        target = self._target()
        if target is None or not target.exists():
            return self._send(HTTPStatus.NOT_FOUND, b"not found")
        if target.is_dir():
            if not self.path.split("?")[0].endswith("/"):
                self.send_response(HTTPStatus.MOVED_PERMANENTLY)
                self.send_header("Location", self.path + "/")
                return self.end_headers()
            return self._send(HTTPStatus.OK, self._listing(target).encode(), "text/html; charset=utf-8")
        size = target.stat().st_size
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition",
                         "attachment; filename*=UTF-8''" + urllib.parse.quote(target.name))
        self.end_headers()
        if self.command != "HEAD":
            with target.open("rb") as fh:
                shutil.copyfileobj(fh, self.wfile, CHUNK)

    do_HEAD = do_GET

    def do_PUT(self):
        target = self._target()
        if not self.allow_upload or target is None:
            return self._send(HTTPStatus.FORBIDDEN, b"forbidden")
        if not target.parent.is_dir() or not target.name:
            return self._send(HTTPStatus.NOT_FOUND, b"not found")
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._send(HTTPStatus.LENGTH_REQUIRED, b"length required")
        if length > MAX_UPLOAD:
            return self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, b"too large")
        dest = free_name(target.parent, target.name)
        remaining = length
        with dest.open("wb") as fh:
            while remaining:
                chunk = self.rfile.read(min(CHUNK, remaining))
                if not chunk:
                    break
                fh.write(chunk)
                remaining -= len(chunk)
        if remaining:
            dest.unlink(missing_ok=True)
            return self._send(HTTPStatus.BAD_REQUEST, b"incomplete")
        self.log_lines.append(f"upload {dest.name}")
        self._send(HTTPStatus.CREATED, dest.name.encode())

    def _listing(self, folder: Path) -> str:
        rows = []
        if folder != self.root:
            rows.append('<li><a href="../">..</a></li>')
        for entry in sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if entry.name.startswith("."):
                continue
            name = entry.name + ("/" if entry.is_dir() else "")
            size = "" if entry.is_dir() else f" <small>({entry.stat().st_size:,} B)</small>"
            rows.append(f'<li><a href="{urllib.parse.quote(name)}">{html.escape(name)}</a>{size}</li>')
        upload = UPLOAD_FORM if self.allow_upload else ""
        return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                f"<title>AIO</title><h3>{html.escape(folder.name or '/')}</h3><ul>{''.join(rows)}</ul>{upload}")


def start(root: Path, allow_upload: bool, port: int = PORT, token: str | None = None):
    """Start the server in a background thread; returns (server, url_path, log)."""
    token = token or secrets.token_urlsafe(6)
    log: list[str] = []
    handler = partial(ShareHandler, root=root.resolve(), token=token,
                      allow_upload=allow_upload, log=log)
    for candidate in (port, *range(port + 1, port + 20), 0):
        try:
            server = ThreadingHTTPServer(("0.0.0.0", candidate), handler)
            break
        except OSError:
            continue
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"/{token}/", log


def run(ctx):
    root = ctx.ask_file(ctx.t("wifi_share.ask_folder"), allow_dir=True)
    if root is None:
        return
    if not root.is_dir():
        root = root.parent
    allow_upload = ctx.confirm(ctx.t("wifi_share.ask_upload"))
    server, path, log = start(root, allow_upload)
    url = f"http://{lan_ip()}:{server.server_address[1]}{path}"
    ctx.print()
    ctx.print(ctx.t("wifi_share.running", path=str(root)))
    ctx.print("   " + url)
    if media.has("qrencode"):
        subprocess.run(["qrencode", "-t", "ansiutf8", url], check=False)
    ctx.print(ctx.t("wifi_share.hint"))
    try:
        ctx.ask(ctx.t("wifi_share.stop_prompt") + " ")
    finally:
        server.shutdown()
        server.server_close()
    requests = sum(1 for line in log if line.startswith("\"GET "))
    uploads = sum(1 for line in log if line.startswith("upload "))
    ctx.print(ctx.t("wifi_share.stopped", requests=requests, uploads=uploads))
