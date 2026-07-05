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
import re
import sys

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from google.genai import types as genai_types

# ---------------------------------------------------------------------------
# 1) SECURITY GUARDRAIL
#    IMPORTANT DESIGN NOTE: this is a `before_agent_callback` attached to the
#    ROOT pipeline (the SequentialAgent), not to each individual sub-agent.
#    It runs exactly ONCE, before planner_agent or reviewer_agent ever run.
#    If it returns a Content object, ADK skips the ENTIRE pipeline and uses
#    that Content as the final answer -- so an unsafe/unrealistic request
#    never reaches ANY agent or ANY model call, and can't "leak through" to
#    a downstream agent (which is exactly what happened in our first version
#    of this guardrail, when it was attached per-agent instead).
# ---------------------------------------------------------------------------
MAX_REASONABLE_DAILY_HOURS = 16  # a human cannot productively study more than this

UNSAFE_SIGNALS = [
    "no sleep", "without sleep", "all nighter every night",
    "24 hours a day", "24/7",
]


def _extract_user_text(callback_context: CallbackContext) -> str:
    """Gets the raw text of the original user request for this invocation."""
    invocation_ctx = callback_context._invocation_context
    user_content = getattr(invocation_ctx, "user_content", None)
    if not user_content or not user_content.parts:
        return ""
    for part in user_content.parts:
        if getattr(part, "text", None):
            return part.text
    return ""


def study_request_guardrail(
    callback_context: CallbackContext,
) -> genai_types.Content | None:
    """Blocks the whole pipeline if the request is unsafe/unrealistic.

    Returns a Content object to short-circuit (skip planner + reviewer
    entirely), or None to let the pipeline run normally.
    """
    lowered = _extract_user_text(callback_context).lower()

    if any(s in lowered for s in UNSAFE_SIGNALS):
        return genai_types.Content(
            role="model",
            parts=[genai_types.Part(text=(
                "I can't build a plan that skips sleep or runs 24/7 — "
                "that's not sustainable or safe. Tell me your goal and "
                "deadline and I'll build a realistic schedule instead."
            ))],
        )

    for match in re.finditer(r"(\d{1,3})\s*hours?", lowered):
        hours = int(match.group(1))
        if hours > MAX_REASONABLE_DAILY_HOURS:
            return genai_types.Content(
                role="model",
                parts=[genai_types.Part(text=(
                    f"{hours} hours in a day isn't realistic (max ~"
                    f"{MAX_REASONABLE_DAILY_HOURS} productive study hours). "
                    "Please give me a more realistic daily limit."
                ))],
            )

    # request looks fine -> return None so the pipeline proceeds
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
)

# root_agent: the entry point ADK looks for when running `adk run` / `adk web`
# The guardrail is attached HERE (before_agent_callback), so it runs once,
# before the pipeline starts, and can block both sub-agents at once.
root_agent = SequentialAgent(
    name="study_planner_pipeline",
    sub_agents=[planner_agent, reviewer_agent],
    before_agent_callback=study_request_guardrail,
    description=(
        "Multi-agent pipeline: planner_agent drafts a study schedule, then "
        "reviewer_agent checks it against real calendar availability (via "
        "an MCP tool) and produces the final, realistic plan."
    ),
)
