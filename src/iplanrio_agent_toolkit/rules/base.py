"""Base types for a generic, priority-ordered rule engine (Chain of Responsibility).

Contains no notion of what is being classified, or what the possible
classification labels are — that vocabulary belongs entirely to the
consuming application.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

TContext = TypeVar("TContext")


@dataclass
class RuleResult:
    """Outcome of evaluating a single rule."""

    applies: bool
    classification: str | None = None
    stop_evaluation: bool = False
    reason: str | None = None
    rule_name: str | None = None


class Rule(ABC, Generic[TContext]):
    """A single priority-ordered rule in a :class:`~iplanrio_agent_toolkit.rules.engine.RuleEngine`.

    Each rule evaluates a condition against an application-defined context
    object and, if it applies, may terminate evaluation with a classification.
    """

    def __init__(self, priority: int, enabled: bool = True) -> None:
        """Set this rule's evaluation order and enabled state.

        :param priority: Lower numbers are evaluated first.
        :param enabled: Disabled rules are skipped entirely by the engine.
        """
        self.priority = priority
        self.enabled = enabled

    @abstractmethod
    def get_name(self) -> str:
        """Return a human-readable name for this rule."""

    @abstractmethod
    def evaluate(self, context: TContext) -> RuleResult:
        """Evaluate this rule's condition against ``context``.

        :param context: Application-defined data the rule reasons about.
        :returns: A :class:`RuleResult` describing whether the rule applies.
        """

    def __repr__(self) -> str:
        """Return a debug representation including priority and enabled state."""
        return f"{self.__class__.__name__}(priority={self.priority}, enabled={self.enabled})"
