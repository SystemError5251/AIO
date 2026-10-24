import io
import json
import urllib.error
import urllib.request

import pytest

from aio.core import config, registry
from aio.core.main import main


def plugin(pid):
    return {p.id: p for p in registry.discover()}[pid].load()


def index(pid):
    return str([p.id for p in registry.discover()].index(pid) + 1)


# -- site watcher ----------------------------------------------------------- #

PAGE = """<html><head><style>.x{}</style><script>var t = %d;</script></head>
<body><!-- build %d --><h1>Shop</h1><p>Status:&nbsp;%s</p></body></html>"""


class FakeResponse(io.BytesIO):
    status = 200

    class headers:
        @staticmethod
        def get_content_charset():
            return "utf-8"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener_for(body):
    return lambda request, timeout: FakeResponse(body.encode())


def test_visible_text_ignores_scripts_comments_and_tags():
    sw = plugin("site_watch")
    assert sw.visible_text(PAGE % (1, 1, "In stock")) == "Shop Status: In stock"
    assert sw.visible_text(PAGE % (1, 1, "x")) == sw.visible_text(PAGE % (2, 9, "x"))


def test_check_all_detects_change_and_expected_text(monkeypatch):
    sw = plugin("site_watch")
    pages = {"now": PAGE % (1, 1, "Sold out")}

    def fetcher(url, expect=""):
        return sw.fetch(url, expect, opener=opener_for(pages["now"]))

    items = [{"url": "https://shop.example", "expect": "in stock"}]
    (_, result, notes), = sw.check_all(items, fetcher)
    assert result.status == 200 and notes == ["site_watch.first_check", "site_watch.text_missing"]
    pages["now"] = PAGE % (7, 7, "Sold out")  # only script/comment changed
    assert sw.check_all(items, fetcher)[0][2] == ["site_watch.unchanged", "site_watch.text_missing"]
    pages["now"] = PAGE % (7, 7, "In Stock")
    assert sw.check_all(items, fetcher)[0][2] == ["site_watch.changed", "site_watch.text_found"]


def test_fetch_errors():
    sw = plugin("site_watch")

    def down(request, timeout):
        raise urllib.error.URLError("Name or service not known")

    def missing(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    r = sw.fetch("https://nope.invalid", opener=down)
    assert r.status is None and "not known" in r.error
    assert sw.check_all([{"url": "x"}], lambda u, e="": r)[0][2] == ["site_watch.down"]
    r404 = sw.fetch("https://example.org/x", opener=missing)
    assert r404.status == 404
    assert sw.check_all([{"url": "x"}], lambda u, e="": r404)[0][2] == ["site_watch.http_error"]


def test_normalize_url():
    sw = plugin("site_watch")
    assert sw.normalize_url(" example.org ") == "https://example.org"
    assert sw.normalize_url("http://a.b") == "http://a.b"


def test_site_watch_menu(monkeypatch, term):
    monkeypatch.setattr(urllib.request, "urlopen", opener_for(PAGE % (1, 1, "In stock")))
    config.set_value("language", "en")
    t = term([index("site_watch"), "", "n", "example.org", "stock", "r", "1", "b", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "Status 200," in t.text
    assert "First check, changes are detected from now on." in t.text
    assert 'Text found: "stock"' in t.text
    assert "Removed: https://example.org" in t.text
    assert config.load()["site_watch"] == []


# -- wifi share ------------------------------------------------------------- #

@pytest.fixture
def share(tmp_path):
    ws = plugin("wifi_share")
    root = tmp_path / "share"
    (root / "sub").mkdir(parents=True)
    (root / "hello.txt").write_text("hi")
    (root / "sub" / "ü.txt").write_text("umlaut")
    (tmp_path / "secret.txt").write_text("nope")
    (root / "escape").symlink_to(tmp_path / "secret.txt")
    servers = []

    def start(upload):
        server, path, log = ws.start(root, upload, port=0, token="tok")
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}", root, log

    yield start
    for s in servers:
        s.shutdown()
        s.server_close()


def _get(url, method="GET", data=None):
    req = urllib.request.Request(url, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_share_lists_and_serves_files(share):
    base, root, _ = share(False)
    status, body = _get(base + "/tok/")
    assert status == 200 and b"hello.txt" in body and b"sub/" in body and b"<form" not in body
    assert _get(base + "/tok/hello.txt") == (200, b"hi")
    assert _get(base + "/tok/sub/%C3%BC.txt") == (200, "umlaut".encode())


def test_share_refuses_wrong_token_traversal_and_symlinks(share):
    base, _, _ = share(False)
    assert _get(base + "/wrong/hello.txt")[0] == 404
    assert _get(base + "/tok/../secret.txt")[0] == 404
    assert _get(base + "/tok/%2e%2e/secret.txt")[0] == 404
    assert _get(base + "/tok/escape")[0] == 404
    assert _get(base + "/tok/new.txt", "PUT", b"x")[0] == 403


def test_share_upload_never_overwrites(share):
    base, root, log = share(True)
    assert b"<form" in _get(base + "/tok/")[1]
    assert _get(base + "/tok/hello.txt", "PUT", b"new")[0] == 201
    assert (root / "hello.txt").read_text() == "hi"
    assert (root / "hello-2.txt").read_text() == "new"
    assert _get(base + "/tok/sub/x.bin", "PUT", b"\x00\x01")[0] == 201
    assert (root / "sub" / "x.bin").read_bytes() == b"\x00\x01"
    assert "upload hello-2.txt" in log


def test_lan_ip_returns_an_address():
    ip = plugin("wifi_share").lan_ip()
    assert ip.count(".") == 3


# -- secrets vault ---------------------------------------------------------- #

@pytest.fixture
def fast_scrypt(monkeypatch):
    pytest.importorskip("cryptography")
    vault = plugin("secrets_vault")
    monkeypatch.setattr(vault, "SCRYPT", {"n": 2 ** 10, "r": 8, "p": 1})
    return vault


def test_vault_roundtrip_wrong_password_and_tamper(fast_scrypt):
    vault = fast_scrypt
    vault.save({"github": "ghp_123", "wlan": "pässwort"}, "correct horse")
    raw = vault.vault_path().read_text()
    assert "ghp_123" not in raw and "github" not in raw
    assert vault.load("correct horse") == {"github": "ghp_123", "wlan": "pässwort"}
    with pytest.raises(vault.WrongPassword):
        vault.load("wrong password")
    blob = json.loads(raw)
    blob["n"] = 2 ** 11  # header is authenticated
    vault.vault_path().write_text(json.dumps(blob))
    with pytest.raises(vault.WrongPassword):
        vault.load("correct horse")


def test_vault_file_is_private(fast_scrypt):
    fast_scrypt.save({}, "12345678")
    assert fast_scrypt.vault_path().stat().st_mode & 0o077 == 0


def test_copy_to_clipboard(fast_scrypt, monkeypatch):
    calls = []
    monkeypatch.setattr(fast_scrypt.media, "has", lambda name: True)
    monkeypatch.setattr(fast_scrypt.subprocess, "run",
                        lambda cmd, **kw: calls.append((cmd, kw["input"])) or type("R", (), {"returncode": 0}))
    assert fast_scrypt.copy_to_clipboard("s3cr3t")
    assert calls == [(["termux-clipboard-set"], "s3cr3t")]


def test_vault_menu_end_to_end(fast_scrypt, term):
    vault = fast_scrypt
    config.set_value("language", "en")
    t = term([index("secrets_vault"), "",
              "short", "longenough1", "different", "longenough1", "longenough1",   # create
              "n", "api", "s3cr3t",                                             # add
              "c", "1", "s", "1",                                               # copy, show
              "p", "newpassword", "newpassword",                                # change password
              "b", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "Too short" in t.text and "The passwords do not match." in t.text
    assert "Saved: api" in t.text and "   api: s3cr3t" in t.text
    assert "Copying needs Termux:API" in t.text  # no termux-clipboard-set here
    assert "Master password changed." in t.text
    assert vault.load("newpassword") == {"api": "s3cr3t"}
    t = term([index("secrets_vault"), "", "nope", "nope2", "nope3", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert t.text.count("Wrong password.") == 3


def test_vault_without_cryptography(monkeypatch, term):
    vault = plugin("secrets_vault")
    monkeypatch.setattr(vault, "_aesgcm", lambda: None)
    config.set_value("language", "de")
    t = term([index("secrets_vault"), "", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "pkg install python-cryptography" in t.text
