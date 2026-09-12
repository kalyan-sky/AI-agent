"""Short-term (working) memory.

For this project, working memory *is* `app.agent.state.AgentState` — the
messages, observations, tool_results, and actions accumulated during one
LangGraph run. It lives only in process memory for the duration of a
single `/api/v1/agent/run` call and is never partially persisted mid-run;
`long_term.py` is what survives across separate calls for the same
conversation_id.

This module exists as a named, documented place for that distinction
(per the project's memory architecture) rather than to hold any code of
its own — there's nothing to implement beyond what AgentState already is.
"""
