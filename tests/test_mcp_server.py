# tests/test_mcp_server.py

import asyncio
import json
import os
import pytest

from CineScope_Recommender import mcp_server


@pytest.mark.asyncio
async def test_search_title_validation_error():
    # Missing query should cause validation error
    with pytest.raises(Exception):
        await mcp_server._search_title({})


@pytest.mark.asyncio
async def test_search_title_success(monkeypatch):
    # Fake TMDB response so test doesn't hit network
    async def fake_tmdb_get(path, params):
        return {
            "results": [
                {
                    "id": 123,
                    "title": "Inception",
                    "overview": "Dream heist.",
                    "release_date": "2010-07-16",
                    "vote_average": 8.8,
                    "poster_path": "/poster.jpg",
                }
            ]
        }

    monkeypatch.setattr(mcp_server, "_tmdb_get", fake_tmdb_get)

    res = await mcp_server._search_title({"query": "Inception", "type": "movie"})
    assert "results" in res
    assert res["results"][0]["title"] == "Inception"
    assert res["results"][0]["year"] == 2010
