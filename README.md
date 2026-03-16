# Autonomous SRE Agent

Open-source MVP of a LangGraph-orchestrated Site Reliability Engineering agent. It ingests telemetry (via webhooks), searches expert runbooks (RAG), predicts remediation actions via Reinforcement Learning (RL), and proposes fixes. It exposes a FastAPI backend where SRE teams can review and approve actions asynchronously.

## MVP Scope

This repository is intentionally MVP-oriented for open-source collaboration.

- Includes: end-to-end incident workflow, approval gate, configurable thresholds, optional API key protection, health/readiness endpoints, and containerized runtime.
- Excludes (for now): enterprise IAM integration, durable distributed checkpointing, real cloud/Kubernetes actuators, and full policy engine.
- Safety posture: all infra tools are simulated stubs by default and should be replaced before real production actuation.

## Architecture

```
Telemetry Stream (async)
        │
        ▼
┌──────────────────────────────────────────────────────┐
│                   LangGraph Pipeline                 │
│                                                      │
│  ┌──────────┐    ┌────────────┐    ┌───────────┐     │
│  │ Analyzer │───►│ Researcher │───►│ Predictor │     │
│  └──────────┘    │  (RAG)     │    │  (RL)     │     │
│       │          └────────────┘    └─────┬─────┘     │
│       │ (LOW severity skip)              │           │
│       └──────────────┐                   │           │
│                      ▼                   ▼           │
│               ┌──────────┐               |           │
│               │ Proposer │◄──────────────┘           |
│               └────┬─────┘                           │
│                    ▼                                 │
│          ┌──────────────────┐                        │
│          │ Human-in-the-Loop│◄── (FastAPI Checkpoint)│
│          │   (API Pause)    │                        │
│          └─────────┬────────┘                        │
│                    ▼                                 │
│              ┌────────────┐                          │
│              │ Actuators  │                          │
│              │ (Tools)    │                          │
│              └────────────┘                          │
└──────────────────────────────────────────────────────┘
        │
        ▼
  ServiceControlTool
  (Scale / Restart / Rollback)
```

## Project Structure

| File | Purpose |
|---|---|
| `main.py` | Entry point — boots simulator, runs the graph, displays results |
| `state.py` | Pydantic data models (`TelemetryEvent`, `IncidentState`, `RemediationProposal`, `AgentState`) |
| `graph.py` | LangGraph `StateGraph` with 5 nodes and conditional routing |
| `rag.py` | RAG engine backed by FAISS with synthetic expert guides |
| `learning.py` | RL scaffolding — `LearningEngine`, `ReplayBuffer`, `Experience` |
| `tools.py` | Simulated `ServiceControlTool`├── Pyproject.toml     # Packaging and metadata
├── Dockerfile         # Production container
├── docker-compose.yml 
├── .env.example       # API Keys
├── graph.py           # LangGraph orchestration
├── api.py             # FastAPI backend (Webhooks & HitL)
├── learning.py        # Reinforcement Learning logic
├── state.py           # Pydantic schemas and AgentState
├── rag.py             # FAISS Retrieval-Augmented Generation
├── tools.py           # Idempotent infrastructure actuators
└── telemetry.py       # Metrics Simulator / Payload schemas
```

## Setup & Running

You can run the Agent either natively via Python or via Docker.

### Option 1: Docker (Recommended)
```bash
docker-compose up --build
```

### Option 1b: Docker (Production-like Compose)
```bash
cp .env.example .env
# set API_KEY and OPENAI_API_KEY in .env
docker-compose -f docker-compose.prod.yml up --build
```

### Option 2: Native Python
1. Clone the repository and install dependencies:
```bash
pip install -r requirements.txt
# For contributor workflow (tests + formatting tools):
pip install -e .[dev]
```
2. Start the API Server:
```bash
uvicorn api:app --reload --port 8000
```

### Run Tests
```bash
pytest -q
```

## Simulate Production Locally

Use the included simulator to generate sustained webhook traffic and auto-process approvals.

```bash
# 1) Start API first
uvicorn api:app --reload --port 8000

# 2) In another terminal, run a normal traffic simulation
python simulate_prod.py --duration 60 --rps 2

# 3) Run an incident storm (more severe traffic)
python simulate_prod.py --duration 60 --rps 5 --spike-mode
```

If API key auth is enabled, include `--api-key <your-key>` in simulator commands.

For teammate-scoped PR tasks, see `TEAM_PR_MODULES.md`.

## Ollama Setup (for Production-Grade Embeddings)

The system uses **Ollama** for local, self-hosted text embeddings. This is free, requires no API keys, and keeps your data local.

### Install Ollama

1. Download and install [Ollama](https://ollama.ai/) for your OS.

2. Start the Ollama server in a terminal:
```bash
ollama serve
```

3. In another terminal, pull the embedding model (one-time setup):
```bash
ollama pull nomic-embed-text
```

The embedding model will be downloaded (~274MB) and cached locally.

### Alternative: Run Ollama in Docker

Add to your `docker-compose.yml` (already included in dev setup if you want to use it):
```yaml
ollama:
  image: ollama/ollama:latest
  ports:
    - "11434:11434"
  volumes:
    - ollama:/root/.ollama
volumes:
  ollama:
```

Then start both services:
```bash
docker-compose up sre-agent ollama
```

### Configuration

The RAG system will automatically:
- ✅ Detect if Ollama is running and use it for embeddings
- ✅ Fall back to random embeddings (FakeEmbeddings) if Ollama is unavailable (for testing/CI)

To use a different Ollama model, set in `.env`:
```bash
OLLAMA_MODEL=llama2
OLLAMA_BASE_URL=http://localhost:11434
```

Available models: `nomic-embed-text` (faster, recommended), `all-minilm`, `mxbai-embed-large`, etc.


1. **Trigger an Incident:** Submitting a webhook (e.g., from Datadog) starts a background LangGraph thread.
```bash
curl -X POST http://localhost:8000/webhook/alert -H "Content-Type: application/json" -d '{"service":"api-gateway", "alert_name":"HighLatency", "severity":"critical", "metrics":{"latency_ms": 3500}}'
```

If `API_KEY_ENABLED=true`, include the header `x-api-key`:
```bash
curl -X POST http://localhost:8000/webhook/alert \
        -H "Content-Type: application/json" \
        -H "x-api-key: <your-api-key>" \
        -d '{"service":"api-gateway", "alert_name":"HighLatency", "severity":"critical", "metrics":{"latency_ms": 3500}}'
```

2. **Check Pending Approvals:** The graph will pause and wait for human permission.
```bash
curl http://localhost:8000/api/incidents/pending
```

3. **Approve or Reject:** Resume the thread using the `thread_id` returned in the pending list.
```bash
curl -X POST http://localhost:8000/api/incidents/<THREAD_ID>/approve
```

## API Health Endpoints

- `GET /healthz`: liveness probe
- `GET /readyz`: readiness probe with MVP checks

## Environment Configuration

Use `.env.example` as a template. Key fields:

- `ENVIRONMENT`: `dev` or `prod`
- `LOG_LEVEL`: `INFO`, `DEBUG`, etc.
- `API_KEY_ENABLED`: `true` to protect write endpoints
- `API_KEY`: shared secret used when API key auth is enabled
- `ANOMALY_*`, `RL_*`, and `APPROVAL_CONFIDENCE_THRESHOLD`: model and decision tuning knobs

## Tech Stack

- **Python 3.10+** with `asyncio`
- **LangGraph** / **LangChain** for agentic orchestration
- **FAISS** for local vector search (RAG)
- **Ollama** for local, self-hosted text embeddings (production-grade)
- **Pydantic v2** for data validation
- **NumPy** for RL state encoding

## License

MIT
