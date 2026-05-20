"""Shared helpers for webtools tests."""


class _FakeResponse:
    def __init__(self, text: str, content_type: str = "text/html"):
        self._text = text
        self.headers = {"content-type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self):
        if isinstance(self._text, bytes):
            return self._text
        return self._text.encode()
