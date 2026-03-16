# Autonomous SRE Agent: Deep-Dive Architecture & Implementation Guide

This document provides an in-depth explanation of the algorithms, data structures, and module interactions that power the Autonomous SRE system. It is designed for engineers seeking to debug, maintain, or extend the system.

---

## 1. System Overview & Data Flow

The Autonomous SRE system operates as a **stateful directed graph** using LangGraph. Data flows monotonically from ingestion (Telemetry) through analysis and prediction, culminating in an actionable proposal.

**Core Data Structure**: `AgentState` (defined in `state.py`)
This is the single source of truth passed between nodes. It is a `TypedDict` containing:
- `telemetry_events`: Raw ingestion batch (list of dictionaries).
- `incident`: The current understanding of the anomaly (`IncidentState`).
- `rl_prediction`: The action chosen by the RL policy.
- `proposal`: The final `RemediationProposal`.
- `human_approved`: Boolean flag for the Human-in-the-Loop breakpoint.

By enforcing complete state representation in `AgentState`, the system allows trivially resuming, pausing, or inspecting the pipeline at any node.

---

## 2. Module Breakdown

### 2.1 Telemetry Ingestion (`telemetry.py`)

**Purpose**: Simulates a high-throughput stream of system events.
**Data Structures**:
- Disjoint Union (Pydantic `TelemetryEvent`): `LogEvent | MetricEvent | TraceEvent`.
- Uses a generator-based asynchronous stream (`asyncio.sleep`) to mimic network latency and bursty logging.
**Algorithms**:
- Uses pseudo-random probability distributions (`random.choices` with weights `[0.4, 0.4, 0.2]`) to generate realistic noise vs. signal ratios.

### 2.2 LangGraph Orchestration (`graph.py`)

**Purpose**: defines the control flow of the agent.
**Algorithms & Patterns**:
- **StateGraph**: A state-machine paradigm where nodes are Python functions that receive the current state and return a *partial state update*. LangGraph merges these updates into the master state.
- **Conditional Routing (`_route_after_analyzer`)**: An algorithmic fast-path. If the Analyzer calculates a `Severity.LOW`, the router bypasses the expensive `Researcher` (RAG) node and jumps straight to the `Proposer`.
- **Nodes**:
  1. `analyzer`: Threshold-based anomaly correlation.
  2. `researcher`: Vector-search similarity retrieval.
  3. `predictor`: RL action selection.
  4. `proposer`: Remediation assembly and risk scoring.
  5. `human_in_the_loop`: Breakpoint for execution using LangGraph Checkpointers (`NodeInterrupt`).

## 3. Webhook Pipeline & State Persistence (`api.py`)

**Purpose**: Wraps the LangGraph orchestration in a production FastAPI backend.
**Flow**:
- The `/webhook/alert` asynchronous endpoint receives raw payload alerts from Prometheus/Datadog and maps them to initial `AgentState`.
- It executes `compiled_graph.invoke()` via FastAPI `BackgroundTasks`.
- When the Graph hits `human_in_the_loop`, it throws `NodeInterrupt` and relies on `langgraph.checkpoint.memory.MemorySaver` to persist the state in the database.
- An SRE polls `/api/incidents/pending` via a dashboard, and sends a `POST` request to `/approve` which triggers `update_state(..., {"human_approved": True})` to resume the thread safely.

### 2.3 Knowledge Retrieval / RAG (`rag.py`)

**Purpose**: Contextualises raw metrics using historical expert guides.
**Data Structures**:
- **FAISS (Facebook AI Similarity Search)**: An in-memory vector index optimized for dense vector similarity.
- **Embeddings**: Represents textual debugging guides as high-dimensional float vectors. (Currently stubbed via `FakeEmbeddings`).
**Algorithm**:
- **k-Nearest Neighbors (k-NN) using Cosine Similarity**: When an incident occurs, the `query()` method embeds the `anomaly_summary` and searches the FAISS index for the *k=3* "closest" expert guides in the embedded vector space.

### 2.4 Reinforcement Learning Engine (`learning.py`)

**Purpose**: Moves the system from static rule-based alerting to adaptive, programmatic remediation.

#### Data Structures

1. **Experience Replay Buffer**
   - Implemented as a `collections.deque` with a fixed `maxlen`.
   - **Why?** In RL, sequential agent experiences are highly correlated. Training a neural network on sequential data catastrophicly forgets older data. The Replay Buffer stores `(State, Action, Reward, NextState)` tuples. The engine samples uniformly from this buffer (mini-batches) to break correlation and stabilise training (Off-Policy Learning).

2. **State Encoding Vector (`np.ndarray`)**
   - **Crucial Concept**: Neural networks cannot natively ingest arbitrary textual logs. The `encode_state` function compresses the current system health into a fixed-length float32 array (e.g., shape `(8,)`).
   - Normalisation: Every feature (CPU, memory, deploy age) is squashed into a roughly `[0.0, 1.0]` range. This prevents features with large magnitudes (like latency in ms) from dominating the gradient updates.

#### Algorithms

1. **ε-greedy Action Selection**
   - Balances exploration vs. exploitation. With probability `ε` (e.g., 10%), the agent picks a random action to explore new solutions. Otherwise, it picks `argmax(Q(s, a))` — the action with the highest predicted reward.

2. **Q-Learning (Temporal Difference Update)**
   - The engine uses a simplistic linear approximation placeholder: $Q(s, a) = w^T s$.
   - **Bellman Equation**: It updates its internal weights to minimize the Temporal Difference (TD) Error:
     `TD_Error = (Reward + γ * max(Q(next_state))) - Q(current_state, action)`
   - **Reward Shaping (`calculate_reward`)**: Uses a weighted sum of objective success (did it fix the incident?) and subjective feedback (did the human reviewer like the fix?).

### 2.5 Infrastructure Tooling (`tools.py`)

**Purpose**: The actuating "hands" of the agent.
**Design Pattern**:
- **Deterministic Adapters**: In a live system, this layer wraps external SDKs (Kubernetes Python Client, AWS Boto3).
- **Idempotency**: Tools must be designed to be idempotent (e.g., safely scaling to 3 replicas repeatedly) to prevent catastrophic failure loops if the agent misbehaves.

---

## 3. How to Improvise / Extend the System

If you are picking up this codebase, here is how to extend its capabilities:

### 3.1 Swapping the RL Engine for a Deep Neural Net
Currently, `LearningEngine` uses a linear weight matrix `_policy_weights = np.ndarray`.
- **To Upgrade**: Import `torch` (PyTorch). Replace `_policy_weights` with an `nn.Sequential` multi-layer perceptron.
- Update `update_policy()` to use `torch.optim.Adam` and invoke `loss.backward()`.

### 3.2 Upgrading the RAG Implementation
Currently, `rag.py` uses `FakeEmbeddings` and local `FAISS`.
- **To Upgrade**:
  1. Add `langchain-chroma` or `pinecone-client` to `requirements.txt`.
  2. Swap `FakeEmbeddings` with `OpenAIEmbeddings(api_key=...)`.
  3. Replace the local `_SEED_GUIDES` array with a document loader that scrapes your company's Confluence / Notion / Jira tickets.

### 3.3 Adding LLM "Reasoning" to the Proposer
Currently, `proposer_node` uses hard-coded logic to map the RL prediction to strings.
- **To Upgrade**: Construct a LangChain `ChatPromptTemplate` in `graph.py:proposer_node`. Pass the RAG context, the RL recommendation, and the `anomaly_summary` to GPT-4. Ask the LLM to write the `description` and `risk_rationale` paragraphs naturally based on the data.

### 3.4 Handling Real Telemetry
Currently, `telmetry.py` generates fake data.
- **To Upgrade**: Replace `TelemetrySimulator` with a Kafka consumer (using `aiokafka`) or a FastAPI webhook endpoint that receives JSON payloads from Prometheus/Datadog, parses them into `LogEvent`/`MetricEvent` Pydantic models, and pushes them to a processing queue consumed by the LangGraph runner.
