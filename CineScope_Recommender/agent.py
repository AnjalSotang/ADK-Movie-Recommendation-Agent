# CineScope_Recommender/agent.py

from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file in the same directory
load_dotenv(Path(__file__).parent / ".env")

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioServerParameters


PATH_TO_MCP_SERVER = str((Path(__file__).parent / "mcp_server.py").resolve())

SYSTEM_PROMPT = """
You are an assistant that only answers using data fetched via MCP tools.
If a tool lacks data, say so and offer alternatives.
Always include source names and data timestamps when summarising results.
When recommending films or TV:
- Explain WHY each title fits the user's request (genre, tone, rating, themes).
- Respect user constraints (year, language, genre).
- Prefer a single, best tool call per turn.
"""

DEVELOPER_PROMPT = """
Choose the single best MCP tool call for each user request.
If uncertain about the title/type, ask one clarifying question.
Avoid repeating identical tool calls within 60 seconds for the same arguments.
Use:
- search_title for "who starred in X", "find X"
- get_recommendations for "if I liked X, what next?"
- discover for filter-based queries (year, genre, language, sort_by).
"""

# Combine system + developer behaviour into a single instruction,
# since this ADK version doesn't support `developer_description`.
COMBINED_INSTRUCTION = (SYSTEM_PROMPT.strip() + "\n\n" + DEVELOPER_PROMPT.strip()).strip()

root_agent = LlmAgent(
    model="gemini-2.5-flash",
    # IMPORTANT: must be a valid identifier (no spaces)
    name="CineScope_Recommender",
    description="A helpful assistant for recommending movies and TV shows.",
    instruction=COMBINED_INSTRUCTION,
    tools=[
        McpToolset(
            connection_params=StdioServerParameters(
                command="python3",
                args=[PATH_TO_MCP_SERVER],
            )
        )
    ],
)
