import json

from aio.core import registry


def _make_plugin(base, pid, manifest=None, code="def run(ctx):\n    return 'ran'\n"):
    folder = base / pid
    folder.mkdir(parents=True)
    data = {"id": pid, "version": "1.0", "name_key": f"{pid}.name",
            "desc_key": f"{pid}.desc", "help_key": f"{pid}.help"}
    if manifest is not None:
        data = manifest
    (folder / "manifest.json").write_text(json.dumps(data), "utf-8")
    (folder / "plugin.py").write_text(code, "utf-8")
    return folder


def test_builtin_dummy_plugins_are_found():
    ids = [p.id for p in registry.discover()]
    assert "demo_hello" in ids and "demo_sysinfo" in ids


def test_discover_and_run(tmp_path):
    _make_plugin(tmp_path, "alpha")
    (plugin,) = registry.discover([tmp_path])
    assert plugin.id == "alpha" and plugin.run(None) == "ran"


def test_broken_plugins_are_skipped_with_warning(tmp_path):
    _make_plugin(tmp_path, "good")
    _make_plugin(tmp_path, "bad", manifest={"id": "bad"})
    (tmp_path / "junk").mkdir()
    (tmp_path / "junk" / "manifest.json").write_text("{oops", "utf-8")
    warnings = []
    plugins = registry.discover([tmp_path], warnings=warnings)
    assert [p.id for p in plugins] == ["good"]
    assert len(warnings) == 2


def test_user_plugins_dir_is_searched(aio_home):
    _make_plugin(aio_home / "plugins", "mine")
    assert "mine" in [p.id for p in registry.discover()]


def test_duplicate_ids_keep_first(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _make_plugin(a, "same")
    _make_plugin(b, "same")
    warnings = []
    (plugin,) = registry.discover([a, b], warnings=warnings)
    assert plugin.path.parent == a and warnings
