import json

import pytest

from aio.core import config, review
from aio.core.i18n import Translator
from aio.core.main import main
from aio.tools import merge_review


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def locales(tmp_path):
    d = tmp_path / "locales"
    write(d / "en.json", {"a.hello": "Hello {name}", "a.bye": "Bye",
                          "a.files": {"one": "{count} file", "other": "{count} files"},
                          "a.new": "New"})
    write(d / "fr.json", {"a.hello": "Salut {name}", "a.bye": "Ciao",
                          "a.files": {"one": "{count} fichier", "other": "{count} fichiers"},
                          "_auto": ["a.hello", "a.files"]})
    return d


def test_pending_lists_auto_then_missing(locales):
    items = review.pending([locales], "fr")
    assert [(i.key, i.status) for i in items] == [
        ("a.hello", "auto"), ("a.files", "auto"), ("a.new", "missing")]
    assert items[0].source == "Hello {name}" and items[0].current == "Salut {name}"
    assert items[2].current is None  # a.bye is hand-checked: not listed


def test_accept_and_correct_go_to_the_overlay_only(locales):
    items = review.pending([locales], "fr")
    review.accept("fr", "a.hello")
    review.correct("fr", items[2], "Nouveau")
    assert [i.key for i in review.pending([locales], "fr")] == ["a.files"]
    overlay = json.loads(review.overlay_path("fr").read_text(encoding="utf-8"))
    assert overlay == {"_reviewed": ["a.hello", "a.new"], "a.new": "Nouveau"}
    assert "_auto" in json.loads((locales / "fr.json").read_text(encoding="utf-8"))


def test_overlay_wins_in_translator(locales):
    review.correct("fr", review.pending([locales], "fr")[0], "Bonjour {name}")
    tr = Translator("fr", locales_dir=locales)
    assert tr.t("a.hello", name="Ana") == "Salut Ana"
    tr.set_override_dir(review.user_locales_dir())
    assert tr.t("a.hello", name="Ana") == "Bonjour Ana"


@pytest.mark.parametrize("value,ok", [
    ("Bonjour {name}", True),
    ("Bonjour", False),               # dropped placeholder in a plain text
    ("Bonjour {nom}", False),         # invented placeholder
    ("   ", False),
    ({"one": "x"}, False),            # plural given for a plain text
])
def test_check_plain(value, ok):
    assert review.check("Hello {name}", value) is ok


def test_check_plural_may_drop_but_not_invent():
    source = {"one": "{count} file", "other": "{count} files"}
    assert review.check(source, {"one": "un fichier", "other": "{count} fichiers"})
    assert not review.check(source, {"one": "{n} fichier", "other": "{count} fichiers"})
    assert not review.check(source, "{count} fichiers")


def test_correct_rejects_bad_placeholders(locales):
    item = review.pending([locales], "fr")[0]
    with pytest.raises(ValueError):
        review.correct("fr", item, "Salut {nom}")
    assert not review.overlay_path("fr").exists()


def test_merge_overlay_writes_files_and_clears_auto(locales):
    overlay = {"_reviewed": ["a.hello", "a.files", "a.new"],
               "a.files": {"one": "{count} fichier", "other": "{count} fichiers !"},
               "a.new": "Nouveau", "a.bye": "Au revoir {oops}"}
    changed, rejected = review.merge_overlay([locales], "fr", overlay)
    data = json.loads((locales / "fr.json").read_text(encoding="utf-8"))
    assert changed == 3 and rejected == ["a.bye"]
    assert "_auto" not in data
    assert data["a.new"] == "Nouveau" and data["a.files"]["other"] == "{count} fichiers !"
    assert data["a.bye"] == "Ciao"


def test_merge_review_cli(locales, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(merge_review, "locale_dirs", lambda: [locales])
    shared = tmp_path / "fr.json"
    write(shared, {"_reviewed": ["a.hello"]})
    assert merge_review.main([str(shared)]) == 0
    assert "1 texts checked" in capsys.readouterr().out
    data = json.loads((locales / "fr.json").read_text(encoding="utf-8"))
    assert data["_auto"] == ["a.files"]
    assert merge_review.main([str(tmp_path / "xx.json")]) == 1


def test_review_in_app(term):
    config.set_value("language", "fr")
    # settings, review, accept #1, edit #2, quit review, back, quit
    t = term(["s", "5", "", "e", "À plus !", "q", "b", "q"])
    assert main([], input_fn=t.input, print_fn=t.print, interactive=True) == 0
    assert "Vérifier les traductions" in t.text
    assert "traduction automatique" in t.text
    assert "2 textes vérifiés" in t.text
    overlay = json.loads(review.overlay_path("fr").read_text(encoding="utf-8"))
    assert overlay["_reviewed"] == ["app.title", "app.goodbye"]
    assert overlay["app.goodbye"] == "À plus !"
    assert t.lines[-1] == "À plus !"  # the correction is used right away


def test_review_rejects_then_accepts_edit(term):
    config.set_value("language", "fr")
    # skip title, skip goodbye, edit menu.tools plural: bad form, then good forms
    t = term(["s", "5", "s", "s", "e", "{n} outil", "", "", "{count} outils !", "q", "b", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "Non enregistré" in t.text
    overlay = json.loads(review.overlay_path("fr").read_text(encoding="utf-8"))
    assert overlay["menu.tools"] == {"one": "{count} outil disponible :",
                                     "other": "{count} outils !"}


def test_source_language_is_not_reviewed(term):
    config.set_value("language", "de")
    t = term([])
    assert main(["--review"], input_fn=t.input, print_fn=t.print, interactive=True) == 0
    assert "Ausgangssprache" in t.text
    assert not review.overlay_path("de").exists()
