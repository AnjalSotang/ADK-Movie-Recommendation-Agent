# CineScope_Recommender/mcp_server.py

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime, timezone
# Load environment variables from .env file in the same directory
load_dotenv(Path(__file__).parent / ".env")

import httpx
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool


# -----------------------------------------------------------------------------
# Basic config
# -----------------------------------------------------------------------------

logger = logging.getLogger("tmdb_mcp_server")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
)

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
if not TMDB_API_KEY:
    logger.warning("TMDB_API_KEY not set – server will return an error for all calls.")


TMDB_BASE_URL = "https://api.themoviedb.org/3"
CACHE_TTL_SECONDS = 300  # 5 minutes
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0

server = Server("tmdb-film-tv-explorer")

# Simple in-memory cache: {(tool_name, args_json): (ts, data)}
_cache: Dict[Tuple[str, str], Tuple[float, Any]] = {}


def _cache_get(tool_name: str, args: Dict[str, Any]) -> Optional[Any]:
    key = (tool_name, json.dumps(args, sort_keys=True))
    entry = _cache.get(key)
    if not entry:
        return None
    ts, data = entry
    if time.time() - ts > CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    return data


CACHE_TTL_SECONDS = 300  # 5 minutes

MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0



def _cache_set(tool_name: str, args: Dict[str, Any], data: Any) -> None:
    key = (tool_name, json.dumps(args, sort_keys=True))
    _cache[key] = (time.time(), data)


# -----------------------------------------------------------------------------
# TMDB client helpers
# -----------------------------------------------------------------------------

class TMDBError(Exception):
    def __init__(self, message: str, code: str = "GENERIC_ERROR", status: int = 500):
        super().__init__(message)
        self.code = code
        self.status = status


async def _tmdb_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if not TMDB_API_KEY:
        raise TMDBError("TMDB_API_KEY missing in environment", code="CONFIG_ERROR", status=500)

    url = f"{TMDB_BASE_URL}{path}"
    params = {**params, "api_key": TMDB_API_KEY}
    timeout = httpx.Timeout(10.0, connect=5.0)

    backoff = INITIAL_BACKOFF_SECONDS

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, params=params)
        except httpx.RequestError as e:
            # Network/socket/DNS errors
            logger.warning(
                "Network error calling TMDB (%s %s), attempt %s/%s: %s",
                path,
                params,
                attempt,
                MAX_RETRIES,
                e,
            )
            if attempt == MAX_RETRIES:
                raise TMDBError(
                    "Network error talking to TMDB",
                    code="NETWORK_ERROR",
                    status=500,
                )
            await asyncio.sleep(backoff)
            backoff *= 2
            continue

        # Rate limit (429) – transient
        if resp.status_code == 429:
            logger.warning(
                "TMDB rate limit reached on %s, attempt %s/%s",
                path,
                attempt,
                MAX_RETRIES,
            )
            if attempt == MAX_RETRIES:
                raise TMDBError(
                    "TMDB rate limit reached after retries",
                    code="RATE_LIMIT",
                    status=429,
                )
            await asyncio.sleep(backoff)
            backoff *= 2
            continue

        # 5xx – treat as transient
        if resp.status_code >= 500:
            logger.warning(
                "TMDB upstream error %s on %s, attempt %s/%s",
                resp.status_code,
                path,
                attempt,
                MAX_RETRIES,
            )
            if attempt == MAX_RETRIES:
                raise TMDBError(
                    "TMDB service unavailable",
                    code="UPSTREAM_ERROR",
                    status=resp.status_code,
                )
            await asyncio.sleep(backoff)
            backoff *= 2
            continue

        # Other 4xx – permanent
        if resp.status_code >= 400:
            raise TMDBError(
                f"TMDB returned {resp.status_code}",
                code="BAD_REQUEST",
                status=resp.status_code,
            )

        # Success – parse JSON
        try:
            return resp.json()
        except ValueError as e:
            raise TMDBError(
                f"Failed to parse TMDB JSON: {e}",
                code="JSON_ERROR",
                status=500,
            )

    # Should not reach here, loop either returns or raises
    raise TMDBError("Exhausted TMDB retries", code="UNKNOWN_ERROR", status=500)


def _map_search_item(item: Dict[str, Any], item_type: str) -> Dict[str, Any]:
    """Normalise TMDB search/discover results to the spec."""
    title = item.get("title") or item.get("name") or ""
    year = None
    date_field = item.get("release_date") or item.get("first_air_date")
    if date_field:
        year = int(date_field.split("-")[0])
    rating = float(item.get("vote_average") or 0.0)

    return {
        "id": int(item["id"]),
        "title": title,
        "type": item_type,
        "year": year,
        "rating": rating,
        "overview": item.get("overview", ""),
        "poster_path": item.get("poster_path"),
    }


async def _search_title(args: Dict[str, Any]) -> Any:
    query = args.get("query", "").strip()
    if not query:
        raise TMDBError("query is required", code="VALIDATION_ERROR", status=400)

    item_type = args.get("type") or "movie"
    if item_type not in ("movie", "tv"):
        raise TMDBError("type must be 'movie' or 'tv'", code="VALIDATION_ERROR", status=400)

    year = args.get("year")
    language = args.get("language") or "en-US"

    params: Dict[str, Any] = {"query": query, "language": language, "include_adult": False}
    if year is not None:
        if not isinstance(year, int):
            raise TMDBError("year must be an integer", code="VALIDATION_ERROR", status=400)
        if item_type == "movie":
            params["primary_release_year"] = year
        else:
            params["first_air_date_year"] = year

    path = "/search/movie" if item_type == "movie" else "/search/tv"
    data = await _tmdb_get(path, params)

    results = data.get("results", [])
    if not results:
        raise TMDBError(f"No results for query '{query}'", code="TITLE_NOT_FOUND", status=404)

    mapped = [_map_search_item(item, item_type) for item in results]
    return {
        "results": mapped,
        "source": "TMDB",
        "fetched_at": time.time(),
    }


async def _get_recommendations(args: Dict[str, Any]) -> Any:
    try:
        media_id = int(args.get("id"))
    except (TypeError, ValueError):
        raise TMDBError("id must be an integer", code="VALIDATION_ERROR", status=400)

    item_type = args.get("type")
    if item_type not in ("movie", "tv"):
        raise TMDBError("type must be 'movie' or 'tv'", code="VALIDATION_ERROR", status=400)

    path = f"/movie/{media_id}/recommendations" if item_type == "movie" else f"/tv/{media_id}/recommendations"
    params = {"language": "en-US"}
    data = await _tmdb_get(path, params)

    results = data.get("results", [])
    recs: List[Dict[str, Any]] = []

    for item in results:
        base = _map_search_item(item, item_type)
        reason = []
        if item.get("vote_average"):
            reason.append(f"high user rating {item['vote_average']:.1f}")
        if item.get("popularity"):
            reason.append("popular among similar viewers")
        recs.append(
            {
                "id": base["id"],
                "title": base["title"],
                "year": base["year"],
                "reason": "; ".join(reason) if reason else None,
            }
        )

    return {
        "results": recs,
        "source": "TMDB",
        "fetched_at": time.time(),
    }


async def _discover(args: Dict[str, Any]) -> Any:
    item_type = args.get("type")
    if item_type not in ("movie", "tv"):
        raise TMDBError("type must be 'movie' or 'tv'", code="VALIDATION_ERROR", status=400)

    genre_names = args.get("genre") or []
    year = args.get("year")
    language = args.get("language") or "en-US"
    sort_by = args.get("sort_by") or "popularity"

    if sort_by not in ("popularity", "vote_average"):
        raise TMDBError("sort_by must be 'popularity' or 'vote_average'", code="VALIDATION_ERROR", status=400)

    # For simplicity, we let TMDB handle genres via comma-separated ids.
    # Here we just pass names as a filter phrase using 'with_keywords' style.
    # In a full implementation, you'd map genre names to ids via /genre/movie/list.
    params: Dict[str, Any] = {
        "language": language,
        "include_adult": False,
        "sort_by": f"{sort_by}.desc",
    }

    if year is not None:
        if not isinstance(year, int):
            raise TMDBError("year must be an integer", code="VALIDATION_ERROR", status=400)
        if item_type == "movie":
            params["primary_release_year"] = year
        else:
            params["first_air_date_year"] = year

    path = "/discover/movie" if item_type == "movie" else "/discover/tv"
    data = await _tmdb_get(path, params)

    results = data.get("results", [])
    mapped = [_map_search_item(item, item_type) for item in results]

    return {
        "results": mapped,
        "source": "TMDB",
        "fetched_at": time.time(),
    }


# -----------------------------------------------------------------------------
# MCP tool wiring
# -----------------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> List[Tool]:
    """Advertise the three tools + their JSON schemas to the agent."""
    return [
        Tool(
            name="search_title",
            description="Search for a movie or TV show by title.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "type": {"type": "string", "enum": ["movie", "tv"]},
                    "year": {"type": "integer"},
                    "language": {"type": "string"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_recommendations",
            description="Get TMDB recommendations given a title id and type.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "type": {"type": "string", "enum": ["movie", "tv"]},
                },
                "required": ["id", "type"],
            },
        ),
        Tool(
            name="discover",
            description="Discover movies or TV shows by filters like genre/year/language.",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["movie", "tv"]},
                    "genre": {"type": "array", "items": {"type": "string"}},
                    "year": {"type": "integer"},
                    "language": {"type": "string"},
                    "sort_by": {"type": "string", "enum": ["popularity", "vote_average"]},
                },
                "required": ["type"],
            },
        ),
        Tool(
            name="health",
            description="Checks if the MCP server is running and TMDB key is configured.",
            inputSchema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    """Dispatch tool calls, with logging, caching and error handling."""
    logger.info("Tool call: %s(%s)", name, arguments)
    
    # 🩺 Health check
    if name == "health":
        payload = {
            "status": "ok",
            "tmdb_api_key_configured": bool(TMDB_API_KEY),
            "cache_entries": len(_cache),
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        }
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(payload))],
            isError=False,
        )


    start = time.time()

    try:
        cached = _cache_get(name, arguments)
        if cached is not None:
            logger.info("Cache hit for %s", name)
            payload = cached
        else:
            if name == "search_title":
                payload = await _search_title(arguments)
            elif name == "get_recommendations":
                payload = await _get_recommendations(arguments)
            elif name == "discover":
                payload = await _discover(arguments)
            else:
                raise TMDBError(f"Unknown tool: {name}", code="UNKNOWN_TOOL", status=400)

            _cache_set(name, arguments, payload)

        logger.info("Tool %s completed in %.2fs", name, time.time() - start)

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(payload))]
        )
    except TMDBError as e:
        logger.error("TMDBError in %s: %s", name, e)
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": e.code,
                            "message": str(e),
                            "source": "TMDB",
                        }
                    ),
                )
            ],
            isError=True,
        )

    except Exception as e:
        logger.exception("Unexpected error in %s", name)
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": "INTERNAL_ERROR",
                            "message": str(e),
                        }
                    ),
                )
            ],
            isError=True,
        )



# -----------------------------------------------------------------------------
# Entry point (stdio mode)
# -----------------------------------------------------------------------------

async def main() -> None:
    # Run the MCP server over stdio for ADK
    async with stdio_server() as (read, write):
        await server.run(
            read,
            write,
            InitializationOptions(
                server_name="tmdb-film-tv-explorer",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
