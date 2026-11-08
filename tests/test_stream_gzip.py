"""R2: the search stream is gzipped per event (3.6 MB -> ~114 KB for a broad
WA weekend search, measured 2026-11-08). Prod serves it uncompressed:
Cloudflare doesn't compress text/event-stream."""

from __future__ import annotations

import gzip
import zlib

import pytest

from pnw_campsites.routes.search import _gzip_events


async def _events():
    for i in range(3):
        yield f'data: {{"n": {i}, "pad": "{"x" * 500}"}}\n\n'


async def test_each_chunk_decodes_to_its_event_as_it_arrives() -> None:
    d = zlib.decompressobj(31)
    decoded = [d.decompress(chunk).decode() async for chunk in _gzip_events(_events())]
    assert decoded[:3] == [e async for e in _events()]
    assert decoded[3:] == [""]  # gzip trailer


async def test_whole_body_is_valid_gzip() -> None:
    body = b"".join([c async for c in _gzip_events(_events())])
    assert gzip.decompress(body).decode() == "".join([e async for e in _events()])


@pytest.fixture
def stream_engine(monkeypatch):
    from pnw_campsites.routes import search as search_routes

    class Engine:
        async def search_stream(self, query):
            return
            yield

    monkeypatch.setattr(search_routes, "get_engine", lambda: Engine())


DATES = {"start_date": "2027-06-04", "end_date": "2027-06-06"}


def test_stream_is_gzipped_when_the_client_accepts_it(api_client, stream_engine) -> None:
    resp = api_client.get("/api/search/stream", params=DATES, headers={"Accept-Encoding": "gzip"})
    assert resp.headers["content-encoding"] == "gzip"
    assert "data: [DONE]" in resp.text


def test_stream_is_plain_otherwise(api_client, stream_engine) -> None:
    resp = api_client.get("/api/search/stream", params=DATES, headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in resp.headers
    assert "data: [DONE]" in resp.text
