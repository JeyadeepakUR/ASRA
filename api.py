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

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

from graph import compiled_graph
from state import AgentState

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)-15s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("sre_api")

app = FastAPI(
    title="Autonomous SRE Agent API",
    description="Webhook ingestion and Human-in-the-Loop approval endpoints.",
    version="3.0.0"
)

# In-memory store of active threads for the dashboard
pending_incidents: dict[str, dict[str, Any]] = {}


class WebhookPayload(BaseModel):
    """Schema for incoming alerts (e.g., from Prometheus Alertmanager)."""
    service: str
    alert_name: str
    severity: str
    metrics: dict[str, float]


@app.post("/webhook/alert")
async def receive_alert(payload: WebhookPayload, background_tasks: BackgroundTasks):
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
            final_state = compiled_graph.invoke(state, config=config)
        else:
            logger.info(f"Thread {thread_id} | Resuming graph from interrupt...")
            final_state = compiled_graph.invoke(None, config=config)
            
        # If it reached END without raising NodeInterrupt
        logger.info(f"Thread {thread_id} | Completed incident resolution.")
        # Clean up pending store if it was there
        pending_incidents.pop(thread_id, None)
        
    except Exception as e:
        # LangGraph raises NodeInterrupt when hitting our manual checkpoint
        if type(e).__name__ == "NodeInterrupt":
            logger.info(f"Thread {thread_id} | Graph Paused: Requires Human Approval.")
            # Fetch the current state using the checkpointer
            current_state = compiled_graph.get_state(config).values
            proposal = current_state.get("proposal")
            
            if proposal:
                # Store it so the dashboard can render it
                pending_incidents[thread_id] = {
                    "service": proposal.action_params.get("service"),
                    "action": proposal.action,
                    "confidence": proposal.confidence_score,
                    "rationale": proposal.risk_rationale,
                    "rollback": f"{proposal.rollback_action}({proposal.rollback_params})"
                }
        else:
            logger.error(f"Thread {thread_id} | Unexpected error: {e}", exc_info=True)


@app.get("/api/incidents/pending")
def list_pending_incidents():
    """Dashboard endpoint to view all incidents awaiting approval."""
    return {"pending_count": len(pending_incidents), "incidents": pending_incidents}


@app.post("/api/incidents/{thread_id}/approve")
def approve_incident(thread_id: str, background_tasks: BackgroundTasks):
    """SRE clicks 'Approve' on the dashboard."""
    if thread_id not in pending_incidents:
        raise HTTPException(status_code=404, detail="Incident not found or already processed.")
        
    config = {"configurable": {"thread_id": thread_id}}
    logger.info(f"API | Human approved thread {thread_id}.")
    
    # Update the graph state to inject the human's decision
    compiled_graph.update_state(config, {"human_approved": True})
    
    # Resume graph execution in background
    background_tasks.add_task(run_graph_thread, thread_id, resume=True)
    
    return {"status": "approved", "message": "Executing action and updating RL policy."}


@app.post("/api/incidents/{thread_id}/reject")
def reject_incident(thread_id: str, background_tasks: BackgroundTasks):
    """SRE clicks 'Reject' on the dashboard."""
    if thread_id not in pending_incidents:
        raise HTTPException(status_code=404, detail="Incident not found or already processed.")
        
    config = {"configurable": {"thread_id": thread_id}}
    logger.info(f"API | Human rejected thread {thread_id}.")
    
    # Update the graph state
    compiled_graph.update_state(config, {"human_approved": False})
    
    # Resume graph execution in background (will escalate and penalise RL)
    background_tasks.add_task(run_graph_thread, thread_id, resume=True)
    
    return {"status": "rejected", "message": "Action aborted. RL policy penalised."}
