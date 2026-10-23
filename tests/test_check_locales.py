from aio.tools import check_locales


def test_repository_locales_are_complete():
    assert check_locales.main() == 0
