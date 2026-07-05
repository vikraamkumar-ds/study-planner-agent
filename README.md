# 🎓 Study Planner — Multi-Agent Capstone Project

**Track:** Concierge Agents
**Course:** 5-Day AI Agents: Intensive Vibe Coding Course With Google

## Problem
Students set study goals ("learn SQL before my interview") but rarely check
whether their calendar actually has enough free time to hit the goal. Plans
built on wishful thinking fall apart within a day or two.

## Solution
A two-agent pipeline that drafts a study schedule, then **corrects it against
the student's real calendar availability** before handing back a final plan —
plus a safety guardrail that refuses unrealistic or unsafe requests (e.g.
"study 24/7 with no sleep") before any model call is made.

## Architecture

```
User request
     │
     ▼
[ before_model_callback: safety guardrail ]  <- blocks unsafe/unrealistic asks
     │ (if safe, proceeds)
     ▼
┌─────────────────┐        ┌──────────────────┐
│  planner_agent   │──────▶│  reviewer_agent   │
│  (ADK LlmAgent)  │        │  (ADK LlmAgent)   │
│  drafts schedule │        │  calls MCP tool,  │
│                  │        │  fixes conflicts  │
└─────────────────┘        └────────┬─────────┘
                                     │
                                     ▼
                        ┌────────────────────────┐
                        │   MCP Server            │
                        │   get_available_hours() │
                        │   (mock calendar tool)  │
                        └────────────────────────┘
```

Both agents are chained with ADK's `SequentialAgent`, so `planner_agent`
always runs first and hands its output to `reviewer_agent`.

## Course concepts demonstrated (3 of 3 minimum required)

| Concept | Implementation |
|---|---|
| Multi-agent system (ADK) | `SequentialAgent` chaining `planner_agent` → `reviewer_agent` in `agent.py` |
| MCP Server | `mcp_server.py` — a standalone MCP server exposing `get_available_hours`, launched as a subprocess and called live via `McpToolset` |
| Security features | `study_request_guardrail`, a `before_agent_callback` on the pipeline that inspects the request once, before either agent runs, and — if unsafe/unrealistic — skips the entire pipeline (no model call, no tool call, from either agent) |

## Repo contents
- `mcp_server.py` — MCP server with the `get_available_hours` tool (mock calendar data)
- `agent.py` — the multi-agent pipeline + guardrail
- `main.py` — CLI entry point to run it locally
- `study_planner_capstone.ipynb` — Kaggle-ready notebook version (same logic, walkthrough format)

## Setup & running it

### 1. Get a free Gemini API key
https://aistudio.google.com/apikey

### 2. Install dependencies
```bash
pip install google-adk mcp
```

### 3. Set your API key (never commit this)
```bash
export GOOGLE_API_KEY="your-key-here"
```

### 4. Run
```bash
python main.py "Learn enough SQL for a job interview" 5
```

### Running the notebook on Kaggle instead
1. Upload `study_planner_capstone.ipynb` as a new Kaggle notebook
2. Add-ons → Secrets → add secret `GOOGLE_API_KEY`
3. Turn on Internet in notebook settings
4. Uncomment the `kaggle_secrets` lines in the "Run it" cell
5. Run all cells

## Safety notes
- No API keys are hardcoded anywhere in this repo.
- The guardrail runs **once, before the whole pipeline** — unsafe requests never reach either agent's model call or the MCP tool. (Verified live: an earlier per-agent version let a blocked request "leak" into the second agent; the fix moves the check to a single `before_agent_callback` on the pipeline itself.)
- The MCP server only exposes one read-only tool (`get_available_hours`) — no write access, no ability to modify a real calendar.

## Possible extensions
- Replace the mock calendar with a real Google Calendar MCP server
- Add a third agent for daily motivational check-ins
- Persist schedules across sessions so the plan updates as days pass
