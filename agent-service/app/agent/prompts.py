"""Prompt templates for the ReAct-style agent loop.

The agent does not use any vendor's native tool-calling feature (see
llm_provider.py's docstring for why) — tools are described as plain text
here, and the model must respond with a single JSON object describing
either its next tool call or its final answer. This keeps the same
prompts and parsing logic working identically regardless of which LLM
provider is configured.
"""

import json

from app.tools.base import Tool

SYSTEM_PROMPT_TEMPLATE = """You are an SRE/DevOps incident-investigation agent for an enterprise \
operations platform. You investigate production issues by calling tools \
to gather real evidence. Never guess or fabricate what a service's health, \
logs, deployment status, or tickets say — only state what a tool actually \
returned.

Available tools:
{tool_catalog}

Rules:
- Only call tools from the list above, using exactly the argument names shown.
- Investigate before concluding: prefer checking service health/deployment/logs \
and searching the knowledge base over guessing a root cause.
- A tool marked [HIGH_RISK] or [CRITICAL] will not actually execute even if you \
call it — the system will tell you it requires human approval, or is blocked \
entirely. Don't repeat a blocked/gated call; note it in your final answer instead.
- Stop investigating and answer once you have enough evidence, or once further \
tool calls would not add new information.
- Respond with EXACTLY ONE JSON object per turn, no other text, in one of these \
two shapes:
  {{"thought": "<brief reasoning>", "tool": "<tool_name>", "arguments": {{...}}}}
  {{"thought": "<brief reasoning>", "final_answer": "<grounded answer>", \
"confidence": <0.0-1.0>}}
"""


def build_tool_catalog(tools: list[Tool]) -> str:
    lines = []
    for tool in tools:
        properties = tool.input_schema.model_json_schema().get("properties", {})
        arg_summary = ", ".join(f"{n}: {info.get('type', 'any')}" for n, info in properties.items())
        lines.append(f"- {tool.name}({arg_summary}) [{tool.risk_tier.value}] — {tool.description}")
    return "\n".join(lines)


def build_system_prompt(tools: list[Tool]) -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(tool_catalog=build_tool_catalog(tools))


def parse_agent_json(text: str) -> dict:
    """Extract and parse the model's single JSON response.

    Models occasionally wrap JSON in prose or a code fence despite
    instructions; this tolerates the common cases without silently
    accepting garbage — a genuinely malformed response still raises.
    """
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object found in model output: {text[:200]!r}")
    return json.loads(text[start : end + 1])
