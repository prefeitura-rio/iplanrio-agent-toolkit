"""Generic priority-ordered rule engine (Chain of Responsibility pattern)."""

from __future__ import annotations

from iplanrio_agent_toolkit.rules.base import Rule, RuleResult
from iplanrio_agent_toolkit.rules.engine import RuleEngine

__all__ = ["Rule", "RuleEngine", "RuleResult"]
