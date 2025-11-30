# tests/test_agent_prompt.py

from CineScope_Recommender.agent import SYSTEM_PROMPT, DEVELOPER_PROMPT


def test_prompts_non_empty():
    assert "only answers using data fetched via MCP tools" in SYSTEM_PROMPT
    assert "search_title" in DEVELOPER_PROMPT
    assert "get_recommendations" in DEVELOPER_PROMPT
    assert "discover" in DEVELOPER_PROMPT
