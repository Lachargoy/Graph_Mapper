# Quickstart

This guide is meant to validate that the project runs locally and to point you to its most useful entry points.

## 1. Clone the Repository

```bash
git clone https://github.com/Lachargoy/Graph_Mapper.git
cd Graph_Mapper
```

## 2. Create a Dedicated Environment

The simplest setup for this repository is a dedicated local environment such as `mapper-venv`:

```bash
python -m venv mapper-venv
source mapper-venv/bin/activate
pip install -r requirements.txt
playwright install
```

`venv` is the recommended default here. A separate Conda environment is possible, but it does not add much value for the current dependency set unless you already manage your machine that way.

## 3. Choose and Edit a Config Profile

The project currently ships with three canonical profiles under `graph_mapper_agent/bootstrap/configs/`:

- `config_qwen.json`
- `config_lm_studio.json`
- `config_ollama.json`

If you want to use the OpenRouter profile, edit:

- `graph_mapper_agent/bootstrap/configs/config_qwen.json`

and replace each `PUT_YOUR_OPENROUTER_API_KEY_HERE` placeholder with your real API key.

Default profile notes:

- `entry_url` starts at `https://html.duckduckgo.com/html/`
- `goal` is `"."` by default as a placeholder
- for real runs, you will usually want to replace `goal`
- change `entry_url` only if you want a different starting point than the DuckDuckGo HTML flow

The LM Studio and Ollama profiles do not need an OpenRouter key.

## 4. Sanity Check

Compile the package to catch obvious syntax or import issues:

```bash
python -m compileall graph_mapper_agent
python -c "import graph_mapper_agent.bootstrap.runner_menu as rm; print(rm.__file__)"
```

## 5. Interactive Configuration Runner

The local configuration menu lives in `graph_mapper_agent/bootstrap/runner_menu.py`.

```bash
python -m graph_mapper_agent.bootstrap.runner_menu
```

This lets you:

- choose a JSON profile from `graph_mapper_agent/bootstrap/configs/`
- use one of the three canonical profiles:
  `config_qwen.json`, `config_lm_studio.json`, or `config_ollama.json`
- review or revise the proposed goal when that flow is enabled
- run a full agent execution locally

## 6. Local HTTP Interface

To launch the local UI:

```bash
python -m graph_mapper_agent.interfaces.http.server
```

Default address:

- `127.0.0.1:8791`

The current HTTP surface includes:

- `GET /`
- `GET /api/config-profiles`
- `POST /api/jobs`
- `GET /api/jobs/<job_id>`
- `GET /api/sessions/<session_id>`
- `GET /api/runs/<run_id>`
- `GET /api/evidence`

The HTTP interface also loads its config profiles from:

- `graph_mapper_agent/bootstrap/configs/`

Typical first run:

```bash
python -m graph_mapper_agent.interfaces.http.server
```

Then open `http://127.0.0.1:8791`, choose a profile, and launch a run from the UI.

## 7. MCP and Chat

The higher-level interfaces live in:

- `graph_mapper_agent/interfaces/chat/service.py`
- `graph_mapper_agent/interfaces/mcp/service.py`

The most direct entry point for research chat is `process_chat_turn(...)`. Internally it:

- creates or reuses a `session_id`
- records messages in the ledger
- executes `chat_with_research(...)`
- returns an answer, summary, and findings

## 8. Research Modes

The project currently supports three useful modes:

- `read_only`: no artifact downloads
- `collect_artifacts`: downloads and persists validated artifacts
- `mixed`: leaves more room for future persistence policy decisions

## 9. Important Runtime Dependencies

The current `requirements.txt` covers the Python package layer. Two runtime dependencies matter especially in practice:

- Playwright for web navigation
- PyMuPDF for opening or inspecting PDFs

If they are missing, the runtime raises explicit errors when those capabilities are invoked.

## 10. What to Validate Before Publishing

- at least one config profile in `graph_mapper_agent/bootstrap/configs/` runs end-to-end
- the ledger is created under `graph_mapper_agent/data/ledger/`
- the HTTP UI starts and returns jobs and sessions correctly
- the SQLite ledger can be queried after the first run
- the README and `docs/` reflect the real port, endpoints, and entry points
