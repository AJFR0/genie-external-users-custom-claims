import base64
import json

import pytest


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        if text is not None:
            self.text = text
        else:
            self.text = json.dumps(payload) if payload is not None else ""

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class FakeHTTP:
    """Records calls and answers them from routes: (METHOD, url substring) -> response | [responses] | callable."""

    def __init__(self):
        self.calls = []
        self._routes = []

    def route(self, method, substring, response):
        self._routes.append([method.upper(), substring, response])
        return self

    def _dispatch(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        for m, sub, resp in self._routes:
            if m == method and sub in url:
                if isinstance(resp, list):
                    item = resp.pop(0) if len(resp) > 1 else resp[0]
                    return item(kwargs) if callable(item) else item
                return resp(kwargs) if callable(resp) else resp
        raise AssertionError(f"unexpected {method} {url}")

    def post(self, url, **kw):
        return self._dispatch("POST", url, **kw)

    def get(self, url, **kw):
        return self._dispatch("GET", url, **kw)

    def delete(self, url, **kw):
        return self._dispatch("DELETE", url, **kw)

    def patch(self, url, **kw):
        return self._dispatch("PATCH", url, **kw)


def _seg(obj):
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def make_jwt(payload, header=None):
    return f"{_seg(header or {'alg': 'RS256', 'typ': 'at+jwt'})}.{_seg(payload)}.c2lnbmF0dXJl"


@pytest.fixture
def fake_http():
    return FakeHTTP()
