# Autonomous SRE Agent

An agentic A fully autonomous, LangGraph-orchestrated Site Reliability Engineering agent. It ingests telemetry (via webhooks), searches expert runbooks (RAG), predicts remediation actions via Reinforcement Learning (RL), and proposes fixes. It natively exposes a FastAPI backend allowing SRE teams to review and trigger actions asynchronously via a dashboard.

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

### Option 2: Native Python
1. Clone the repository and install dependencies:
```bash
pip install -r requirements.txt
# Or use pip install -e .
```
2. Start the API Server:
```bash
uvicorn api:app --reload --port 8000
```

## Using the API

1. **Trigger an Incident:** Submitting a webhook (e.g., from Datadog) starts a background LangGraph thread.
```bash
curl -X POST http://localhost:8000/webhook/alert -H "Content-Type: application/json" -d '{"service":"api-gateway", "alert_name":"HighLatency", "severity":"critical", "metrics":{"latency_ms": 3500}}'
```

2. **Check Pending Approvals:** The graph will pause and wait for human permission.
```bash
curl http://localhost:8000/api/incidents/pending
```

3. **Approve or Reject:** Resume the thread using the `thread_id` returned in the pending list.
```bash
curl -X POST http://localhost:8000/api/incidents/<THREAD_ID>/approve
```

## Tech Stack

- **Python 3.10+** with `asyncio`
- **LangGraph** / **LangChain** for agentic orchestration
- **FAISS** for local vector search (RAG)
- **Pydantic v2** for data validation
- **NumPy** for RL state encoding

## License

MIT
