"""
api.py — FastAPI production backend for the Autonomous SRE Agent.

Exposes REST endpoints to:
1. Receive telemetry alerts (simulating Datadog/Prometheus webhooks)
2. Retrieve pending incidents (paused at the Human-in-the-Loop node)
3. Approve or Reject proposals, which resumes the LangGraph thread.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header, status
from pydantic import BaseModel, Field
from langgraph.errors import NodeInterrupt

from graph import compiled_graph
from state import AgentState, Severity
from config import settings
from incident_store import incident_store

# Setup logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(name)-15s | %(levelname)-7s | %(message)s"
)
logger = logging.getLogger("sre_api")

app = FastAPI(
    title="Autonomous SRE Agent API",
    description="Webhook ingestion and Human-in-the-Loop approval endpoints.",
    version="3.0.0"
)

# Backward-compatible aliases for tests and external integrations.
pending_incidents = incident_store._items
pending_incidents_lock = incident_store._lock


def require_api_key(x_api_key: str | None = Header(default=None, alias="x-api-key")) -> None:
    """Optional API key protection for write endpoints.

    This keeps OSS onboarding easy in dev while allowing minimal protection
    for shared/staging deployments.
    """
    if not settings.api_key_enabled:
        return

    if not settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key auth enabled but API_KEY is not configured."
        )

    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key."
        )


class WebhookPayload(BaseModel):
    """Schema for incoming alerts (e.g., from Prometheus Alertmanager)."""
    service: str = Field(min_length=1, max_length=128)
    alert_name: str = Field(min_length=1, max_length=128)
    severity: Severity
    metrics: dict[str, float] = Field(default_factory=dict)


@app.get("/healthz")
def healthcheck():
    """Liveness endpoint for container orchestration."""
    return {"status": "ok", "service": "autonomous-sre-api", "environment": settings.environment}


@app.get("/readyz")
def readiness():
    """Readiness endpoint (MVP baseline checks only)."""
    pending_count = incident_store.count()

    return {
        "status": "ready",
        "api_key_enabled": settings.api_key_enabled,
        "pending_incident_count": pending_count,
    }


@app.post("/webhook/alert")
async def receive_alert(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_api_key),
):
    """Ingest an external alert and start a LangGraph SRE thread."""
    thread_id = str(uuid.uuid4())
    logger.info(f"Received webhook for {payload.service}. Starting thread {thread_id}")
    
    # Map the incoming alert to a simulated telemetry batch for our agent
    event = {
        "event_type": "metric",
        "service": payload.service,
        "cpu_pct": payload.metrics.get("cpu_pct", 50.0),
        "mem_pct": payload.metrics.get("mem_pct", 50.0),
        "latency_ms": payload.metrics.get("latency_ms", 50.0),
        "source_alert": payload.alert_name,
        "severity": payload.severity.value,
    }
    
    initial_state: AgentState = {
        "telemetry_events": [event],
        "incident": None,
        "rl_prediction": None,
        "proposal": None,
        "human_approved": None,  # None means decision pending
        "reward_signal": None,
    }
    
    # Run the graph in the background so we don't block the webhook response
    background_tasks.add_task(run_graph_thread, thread_id, initial_state)
    
    return {"status": "accepted", "thread_id": thread_id, "message": "SRE Agent investigating in background."}


def run_graph_thread(thread_id: str, state: AgentState | None = None, resume: bool = False):
    """Execute or resume the LangGraph thread."""
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        if not resume:
            logger.info(f"Thread {thread_id} | Invoking graph from start...")
            compiled_graph.invoke(state, config=config)
        else:
            logger.info(f"Thread {thread_id} | Resuming graph from interrupt...")
            compiled_graph.invoke(None, config=config)
            
        # If it reached END without raising NodeInterrupt
        logger.info(f"Thread {thread_id} | Completed incident resolution.")
        # Clean up pending store if it was there
        incident_store.remove(thread_id)
        
    except NodeInterrupt:
        logger.info(f"Thread {thread_id} | Graph Paused: Requires Human Approval.")
        # Fetch the current state using the checkpointer
        current_state = compiled_graph.get_state(config).values
        proposal = current_state.get("proposal")

        if proposal:
            incident_store.upsert(
                thread_id,
                {
                    "service": proposal.action_params.get("service"),
                    "action": proposal.action,
                    "confidence": proposal.confidence_score,
                    "rationale": proposal.risk_rationale,
                    "rollback": f"{proposal.rollback_action}({proposal.rollback_params})",
                },
            )
    except Exception as exc:
        logger.error(f"Thread {thread_id} | Unexpected error: {exc}", exc_info=True)


@app.get("/api/incidents/pending")
def list_pending_incidents():
    """Dashboard endpoint to view all incidents awaiting approval."""
    incidents = incident_store.list_all()
    return {"pending_count": len(incidents), "incidents": incidents}


@app.post("/api/incidents/{thread_id}/approve")
def approve_incident(
    thread_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_api_key),
):
    """SRE clicks 'Approve' on the dashboard."""
    if not incident_store.contains(thread_id):
        raise HTTPException(status_code=404, detail="Incident not found or already processed.")
        
    config = {"configurable": {"thread_id": thread_id}}
    logger.info(f"API | Human approved thread {thread_id}.")
    
    # Update the graph state to inject the human's decision
    compiled_graph.update_state(config, {"human_approved": True})
    
    # Resume graph execution in background
    background_tasks.add_task(run_graph_thread, thread_id, resume=True)
    
    return {"status": "approved", "message": "Executing action and updating RL policy."}


@app.post("/api/incidents/{thread_id}/reject")
def reject_incident(
    thread_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_api_key),
):
    """SRE clicks 'Reject' on the dashboard."""
    if not incident_store.contains(thread_id):
        raise HTTPException(status_code=404, detail="Incident not found or already processed.")
        
    config = {"configurable": {"thread_id": thread_id}}
    logger.info(f"API | Human rejected thread {thread_id}.")
    
    # Update the graph state
    compiled_graph.update_state(config, {"human_approved": False})
    
    # Resume graph execution in background (will escalate and penalise RL)
    background_tasks.add_task(run_graph_thread, thread_id, resume=True)
    
    return {"status": "rejected", "message": "Action aborted. RL policy penalised."}
