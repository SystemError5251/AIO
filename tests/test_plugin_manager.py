import json
import subprocess
import zipfile

import pytest

from aio.core import config, plugin_manager, registry
from aio.core.main import main
from aio.tools import new_plugin


@pytest.fixture
def scaffold(tmp_path):
    return new_plugin.create("my_tool", tmp_path / "src")


def test_new_plugin_scaffold_is_a_valid_plugin(scaffold):
    (plugin,) = registry.discover([scaffold.parent])
    assert plugin.id == "my_tool" and plugin.manifest["api"] == registry.API_VERSION
    de = json.loads((scaffold / "locales" / "de.json").read_text("utf-8"))
    assert de["my_tool.name"] == "My Tool" and de["my_tool.done"] == "Fertig: {path}"


def test_new_plugin_rejects_bad_id_and_existing(tmp_path, capsys):
    assert new_plugin.main(["Bad-Id", "--dir", str(tmp_path)]) == 1
    assert new_plugin.main(["ok_tool", "--dir", str(tmp_path)]) == 0
    assert new_plugin.main(["ok_tool", "--dir", str(tmp_path)]) == 1


def test_install_from_folder_and_remove(scaffold):
    plugin = plugin_manager.install(str(scaffold))
    target = config.user_plugins_dir() / "my_tool"
    assert plugin.path == target and (target / "plugin.py").is_file()
    assert "my_tool" in [p.id for p in registry.discover()]
    assert not plugin.builtin
    plugin_manager.remove("my_tool")
    assert not target.exists()
    with pytest.raises(plugin_manager.PluginError) as err:
        plugin_manager.remove("my_tool")
    assert err.value.key == "plugins.error_not_installed"


def test_install_from_zip_with_subfolder(scaffold, tmp_path):
    archive = tmp_path / "tool.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for f in scaffold.rglob("*"):
            zf.write(f, "aio-my-tool-main/" + f.relative_to(scaffold).as_posix())
    assert plugin_manager.install(str(archive)).id == "my_tool"


def test_zip_slip_is_refused(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../evil.py", "x")
    with pytest.raises(plugin_manager.PluginError) as err:
        plugin_manager.install(str(archive))
    assert err.value.key == "plugins.error_unsafe_zip"


def test_install_from_git(scaffold, tmp_path, monkeypatch):
    for cmd in (["init", "-q"], ["add", "."],
                ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=scaffold, check=True)
    monkeypatch.setattr(plugin_manager, "is_git_url", lambda s: s.startswith("file://"))
    plugin = plugin_manager.install(f"file://{scaffold}")
    assert plugin.id == "my_tool" and not (plugin.path / ".git").exists()


@pytest.mark.parametrize("change,key", [
    (lambda d: (d / "locales" / "en.json").unlink(), "plugins.error_locales"),
    (lambda d: _manifest(d, id="demo_hello"), "plugins.error_builtin"),
    (lambda d: _manifest(d, id="Bad"), "plugins.error_id"),
    (lambda d: _manifest(d, api=registry.API_VERSION + 1), "plugins.error_manifest"),
    (lambda d: (d / "manifest.json").unlink(), "plugins.error_no_manifest"),
])
def test_install_refuses_invalid_plugins(scaffold, change, key):
    change(scaffold)
    with pytest.raises(plugin_manager.PluginError) as err:
        plugin_manager.install(str(scaffold))
    assert err.value.key == key
    assert not (config.user_plugins_dir() / "my_tool").exists()


def _manifest(folder, **changes):
    path = folder / "manifest.json"
    data = json.loads(path.read_text("utf-8"))
    data.update(changes)
    path.write_text(json.dumps(data), "utf-8")


def test_newer_api_is_skipped_by_discover(scaffold):
    _manifest(scaffold, api=99)
    warnings = []
    assert registry.discover([scaffold.parent], warnings=warnings) == []
    assert "plugin API 99" in warnings[0]


def test_is_git_url():
    assert plugin_manager.is_git_url("https://github.com/a/b")
    assert plugin_manager.is_git_url("https://example.org/x.git")
    assert not plugin_manager.is_git_url("/sdcard/tool.zip")


def test_cli_install_and_remove(scaffold, term):
    config.set_value("language", "en")
    t = term([])
    assert main(["--install-plugin", str(scaffold)], input_fn=t.input, print_fn=t.print,
                interactive=False) == 0
    assert "Installed: My Tool (v0.1.0)." in t.text
    assert main(["--remove-plugin", "my_tool"], input_fn=t.input, print_fn=t.print,
                interactive=False) == 0
    assert main(["--remove-plugin", "my_tool"], input_fn=t.input, print_fn=t.print,
                interactive=False) == 1


def test_settings_install_then_remove(scaffold, term):
    config.set_value("language", "de")
    t = term(["s", "6", "i", str(scaffold), "j", "b", "b", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "Achtung: Ein Plugin ist Programmcode" in t.text
    assert "Installiert: My Tool (v0.1.0)." in t.text
    assert "My Tool v0.1.0 (installiert)" in t.text
    count = len(registry.discover())  # built-ins + the new one
    assert f"{count} Tools verfügbar:" in t.text  # main menu sees the new tool at once
    t = term(["s", "6", "r", "1", "j", "b", "b", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "Entfernt: my_tool." in t.text
    assert not (config.user_plugins_dir() / "my_tool").exists()
