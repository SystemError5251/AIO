import pytest


@pytest.fixture(autouse=True)
def aio_home(tmp_path, monkeypatch):
    """Every test gets its own empty ~/.aio."""
    home = tmp_path / "aio_home"
    monkeypatch.setenv("AIO_HOME", str(home))
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        monkeypatch.delenv(var, raising=False)
    from aio.core.i18n import get_translator
    get_translator().language = "en"
    return home


class FakeTerminal:
    """Feeds scripted answers to input() and records everything printed."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.lines = []

    def input(self, prompt=""):
        self.lines.append(prompt)
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)

    def print(self, *args, file=None, **kwargs):
        self.lines.append(" ".join(str(a) for a in args))

    @property
    def text(self):
        return "\n".join(self.lines)


@pytest.fixture
def term():
    return FakeTerminal
