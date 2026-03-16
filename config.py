"""
config.py — Centralised settings for the Autonomous SRE Agent.

All configuration is loaded from environment variables (or a .env file)
via pydantic-settings for type-safe, validated access.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application-wide configuration."""

    # ── LLM ──
    openai_api_key: str = Field(default="sk-placeholder", description="OpenAI API key")
    openai_model_name: str = Field(default="gpt-4o", description="Model to use for LLM calls")

    # ── Anomaly Detection ──
    anomaly_cpu_threshold: float = Field(default=85.0, description="CPU % above which an anomaly is flagged")
    anomaly_memory_threshold: float = Field(default=90.0, description="Memory % above which an anomaly is flagged")
    anomaly_error_rate_threshold: float = Field(default=5.0, description="Error-rate % threshold for anomaly detection")

    # ── RL Engine ──
    rl_learning_rate: float = Field(default=0.001, description="Learning rate for the RL policy network")
    rl_discount_factor: float = Field(default=0.99, description="Discount factor (gamma) for future rewards")
    rl_replay_buffer_size: int = Field(default=10_000, description="Max experiences in the replay buffer")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Singleton instance — import this everywhere
settings = Settings()
