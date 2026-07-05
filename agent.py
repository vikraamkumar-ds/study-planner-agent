"""
agent.py
--------
Capstone: "Study Planner" multi-agent system.

Demonstrates 3 required concepts:
  1. Multi-agent system built with ADK   -> planner_agent + reviewer_agent
                                             chained in a SequentialAgent
  2. MCP server integration              -> reviewer_agent calls a live MCP
                                             tool (mcp_server.py) to check the
                                             student's real available hours
  3. Security / guardrail feature        -> a before_model_callback rejects
                                             unrealistic or unsafe requests
                                             (e.g. "study 40 hours a day")
                                             BEFORE any model call is made

Requires a Gemini API key. On Kaggle, add it as a secret named
GOOGLE_API_KEY (Add-ons -> Secrets), or set it as an environment variable
before running.
"""

import os
import sys

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from google.genai import types as genai_types

# ---------------------------------------------------------------------------
# 1) SECURITY GUARDRAIL
#    Runs before every call to the LLM. If the user's request is unsafe or
#    unrealistic, we short-circuit and return a fixed response instead of
#    letting the model (and the agent pipeline) proceed.
# ---------------------------------------------------------------------------
MAX_REASONABLE_DAILY_HOURS = 16  # a human cannot productively study more than this


def study_request_guardrail(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> LlmResponse | None:
    """Blocks requests that ask for unrealistic/unsafe study schedules."""
    # Pull the latest user text out of the request contents
    last_user_text = ""
    for content in reversed(llm_request.contents or []):
        if content.role == "user" and content.parts:
            for part in content.parts:
                if getattr(part, "text", None):
                    last_user_text = part.text
                    break
            if last_user_text:
                break

    lowered = last_user_text.lower()

    # crude but effective checks for obviously unsafe/unrealistic asks
    unsafe_signals = [
        "no sleep", "without sleep", "all nighter every night",
        "24 hours a day", "24/7",
    ]
    if any(s in lowered for s in unsafe_signals):
        return LlmResponse(
            content=genai_types.Content(
                role="model",
                parts=[genai_types.Part(text=(
                    "I can't build a plan that skips sleep or runs 24/7 — "
                    "that's not sustainable or safe. Tell me your goal and "
                    "deadline and I'll build a realistic schedule instead."
                ))],
            )
        )

    # look for an explicit "N hours" pattern and cap it
    import re
    for match in re.finditer(r"(\d{1,3})\s*hours?", lowered):
        hours = int(match.group(1))
        if hours > MAX_REASONABLE_DAILY_HOURS:
            return LlmResponse(
                content=genai_types.Content(
                    role="model",
                    parts=[genai_types.Part(text=(
                        f"{hours} hours in a day isn't realistic (max ~"
                        f"{MAX_REASONABLE_DAILY_HOURS} productive study hours). "
                        "Please give me a more realistic daily limit."
                    ))],
                )
            )

    # request looks fine -> return None so the real model call proceeds
    return None


# ---------------------------------------------------------------------------
# 2) MCP TOOL
#    Launches mcp_server.py as a local subprocess over stdio and exposes its
#    `get_available_hours` tool to the reviewer agent.
# ---------------------------------------------------------------------------
_SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "mcp_server.py")

calendar_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,      # reuse this same python interpreter
            args=[_SERVER_SCRIPT],
        ),
        timeout=10.0,
    ),
    tool_filter=["get_available_hours"],
)

# ---------------------------------------------------------------------------
# 3) MULTI-AGENT SYSTEM
# ---------------------------------------------------------------------------
planner_agent = LlmAgent(
    name="planner_agent",
    model="gemini-2.5-flash",
    instruction=(
        "You are a study planner. The user will give you a learning goal and "
        "a deadline in days. Draft a DAY-BY-DAY study plan (topic + hours per "
        "day) to reach the goal by the deadline. Keep it concise. Do not "
        "worry yet about whether the hours are realistic — a reviewer will "
        "check that next. Output the draft plan clearly labelled by day."
    ),
    before_model_callback=study_request_guardrail,
)

reviewer_agent = LlmAgent(
    name="reviewer_agent",
    model="gemini-2.5-flash",
    instruction=(
        "You receive a draft day-by-day study plan from the previous agent. "
        "Call the get_available_hours tool to check how many hours the "
        "student actually has free on each of those days. Then rewrite the "
        "plan so no day exceeds the available hours — redistribute study "
        "topics/hours to later days if needed. Present the FINAL adjusted "
        "plan as a clear table: Date | Weekday | Available Hours | Planned Hours | Topic."
    ),
    tools=[calendar_toolset],
    before_model_callback=study_request_guardrail,
)

# root_agent: the entry point ADK looks for when running `adk run` / `adk web`
root_agent = SequentialAgent(
    name="study_planner_pipeline",
    sub_agents=[planner_agent, reviewer_agent],
    description=(
        "Multi-agent pipeline: planner_agent drafts a study schedule, then "
        "reviewer_agent checks it against real calendar availability (via "
        "an MCP tool) and produces the final, realistic plan."
    ),
)
