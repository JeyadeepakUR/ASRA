"""
main.py — Demo runner for the Autonomous SRE Agent.
"""

from __future__ import annotations

import asyncio
import logging
import sys

# Ensure stdout can handle UTF-8/Emoji on Windows cp1252
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from telemetry import TelemetrySimulator
from graph import compiled_graph
from state import AgentState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-15s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)


async def main():
    print("── Initialising Telemetry Simulator ──")
    simulator = TelemetrySimulator()
    batch = await simulator.collect_batch(n=50)

    initial_state: AgentState = {
        "telemetry_events": batch,
        "incident": None,
        "rl_prediction": None,
        "proposal": None,
        "human_approved": False,
        "reward_signal": None,
    }

    print("\n── Running Autonomous SRE Agent ──")
    final_state = compiled_graph.invoke(initial_state)
    
    print(f"\n── Final State ──")
    print(f"Approved: {final_state['human_approved']}")
    
    # Safe float formatting
    reward = final_state.get('reward_signal')
    reward_str = f"{reward:.3f}" if isinstance(reward, float) else "None"
    print(f"Reward:   {reward_str}")
    
    proposal = final_state.get("proposal")
    if proposal:
        print(f"Proposal: {proposal.action}")
        print(f"Confidence: {proposal.confidence_score:.2f}")
        print(f"Rationale: {proposal.risk_rationale}")
        print(f"Rollback Map: {proposal.rollback_action}({proposal.rollback_params})")
    else:
        print("Proposal: None")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)
