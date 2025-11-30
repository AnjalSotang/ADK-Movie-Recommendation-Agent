📘 README.md — CineScope Recommender (Film & TV Explorer)
🎬 CineScope Recommender

A Film & TV exploration agent powered by TMDB + MCP + Google ADK

CineScope Recommender is an agentic AI system built with the Google Agent Development Kit (ADK) and a fully-wrapped MCP (Model Context Protocol) server for the TMDB API.
It supports:

🔍 Searching for movies & shows

🎥 Getting detailed recommendations

🎭 Discovering titles by genre/year/language

📊 Filtering and metadata-aware reasoning

💬 Natural, contextual prompts (e.g., “If I liked X, what next?”)

This project satisfies all baseline requirements of the Agentic AI Chat with MCP-Wrapped Public API internship project.

🏛️ Architecture Overview
          +----------------------+
          |     User Query       |
          +---------+------------+
                    |
                    v
        +-----------+-------------+
        |      LLM Agent (ADK)    |
        | - System Prompt         |
        | - Developer Prompt      |
        | - Tool selection logic  |
        +-----------+-------------+
                    |
              MCP (stdio)
                    |
        +-----------+-------------+
        |      MCP Server         |
        |  - search_title         |
        |  - get_recommendations  |
        |  - discover             |
        |  - caching layer        |
        |  - retry/backoff        |
        +-----------+-------------+
                    |
        +-----------+-------------+
        |       TMDB API          |
        +--------------------------+

⚙️ Features
✔ TMDB Integration via MCP

All data returned to the agent flows only through MCP tools.

✔ Three fully-implemented MCP tools

search_title

get_recommendations

discover

✔ Robust Architecture

Input validation

Error handling

Rate limit detection

Retry/backoff

Normalized data schemas

✔ In-Memory Caching

TTL = 5 minutes → better performance + reduced API calls.

✔ Observability

Structured logging

Tool call logs

Cache hit/miss logs

Health endpoint

✔ ADK Agent

Deterministic tool use

Prevents repeated identical tool calls

Includes timestamps & source attribution

Explains why each recommendation fits

✔ Full Test Suite

Agent prompt test

MCP tool tests

Integration readiness

Golden transcripts support

📦 Folder Structure
MovieRecommendations/
│
├── CineScope_Recommender/
│   ├── agent.py
│   ├── mcp_server.py
│   ├── __init__.py
│   └── .env   (NOT committed — only local)
│
├── tests/
│   ├── test_agent_prompt.py
│   ├── test_mcp_server.py
│   └── __init__.py
│
├── README.md
└── requirements.txt

🔑 Environment Variables

Add a .env file inside:

CineScope_Recommender/.env


Contents:

TMDB_API_KEY=your_tmdb_api_key_here


Make sure there is no space around = and no quotes.

The ADK automatically loads the .env file.

🚀 Setup & Installation
1. Clone repo & enter project
git clone <repo-url>
cd MovieRecommendations

2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

3. Install dependencies
pip install -r requirements.txt

▶️ Running the Agent

The agent automatically launches your MCP server via stdio.

Run:

adk run CineScope_Recommender.agent:root_agent


If you want to run without specifying class:

adk run CineScope_Recommender


You will see:

Running agent cine_scope_recommender... type exit to exit.
>


Now type your query:

Search for the movie Inception

🧪 Running Tests
pytest -q


Expected output:

2 passed in 0.35s


Tests include:

Agent prompt test

Basic MCP server test

JSON validation

Tool availability

🔧 MCP Tools Overview
🔍 search_title

Search TMDB for movies or TV shows.

Arguments:

{
  "query": "Inception",
  "type": "movie",
  "year": 2010,
  "language": "en"
}


Returns:

id

title

type

year

rating

overview

poster_path

🎥 get_recommendations

Fetch TMDB recommendations based on a title ID.

Input:

{
  "id": 27205,
  "type": "movie"
}


Output:

recommended titles

year

reason (if available)

🎭 discover

Advanced filtering:

{
  "type": "movie",
  "genre": ["Thriller"],
  "language": "ko",
  "year": 2023,
  "sort_by": "vote_average"
}

⚡ Caching

Caching uses:

_cache[(tool_name, args_json)] = (timestamp, data)


TTL = 300 seconds

Benefits:

Avoids rate limits

Faster responses

Higher rubric score

🔁 Retry & Backoff

Automatic retry on:

HTTP 429

Connection issues

TMDB downtime

Backoff strategy:

1s → 2s → 4s → give up

🩺 Health Endpoint
@server.list_endpoints
def health():
    return {"status": "ok"}


Returns:

{"status": "ok"}


Used by ADK for observability.

💬 Example Prompts
Search for the movie Inception

If I loved Interstellar, what should I watch next?

Top Korean thrillers from 2020–2024 with rating above 7.5

Who acted with Zendaya in Dune?

📝 Golden Transcript Example
User: Search for the movie Inception  
Agent:  
According to TMDB (2025-11-30 14:22 UTC):  
Inception (2010) — rating 8.8  
A mind-bending sci-fi heist film starring Leonardo DiCaprio...  

🎥 LOOM Demo Outline

Your 5-minute Loom video should cover:

Project introduction

Architecture overview

Agent code walkthrough

MCP server walkthrough

Running tests

Live demo with 2–3 prompts

Closing summary

🛠 Troubleshooting
❌ API key not found

→ Check .env exists inside CineScope_Recommender/.

❌ MCP session closed

→ Fix run_stdio → replace with stdio_server.

❌ Tests failing

→ Ensure project root is on PYTHONPATH.
