from __future__ import annotations

from dataclasses import dataclass

from iplanrio_agent_toolkit.rules.base import Rule, RuleResult
from iplanrio_agent_toolkit.rules.engine import RuleEngine


@dataclass
class DummyContext:
    value: int


class AlwaysMatchesRule(Rule[DummyContext]):
    def __init__(self, priority: int, classification: str) -> None:
        super().__init__(priority=priority)
        self._classification = classification

    def get_name(self) -> str:
        return f"AlwaysMatches({self._classification})"

    def evaluate(self, context: DummyContext) -> RuleResult:
        return RuleResult(applies=True, classification=self._classification, stop_evaluation=True)


class NeverMatchesRule(Rule[DummyContext]):
    def get_name(self) -> str:
        return "NeverMatches"

    def evaluate(self, context: DummyContext) -> RuleResult:
        return RuleResult(applies=False)


class ConditionalRule(Rule[DummyContext]):
    def get_name(self) -> str:
        return "Conditional"

    def evaluate(self, context: DummyContext) -> RuleResult:
        if context.value > 10:
            return RuleResult(applies=True, classification="HIGH", stop_evaluation=True)
        return RuleResult(applies=False)


def test_evaluates_rules_in_priority_order() -> None:
    engine = RuleEngine(
        [
            AlwaysMatchesRule(priority=100, classification="FALLBACK"),
            AlwaysMatchesRule(priority=10, classification="HIGH_PRIORITY"),
        ]
    )

    result = engine.evaluate(DummyContext(value=1))

    assert result.classification == "HIGH_PRIORITY"


def test_disabled_rules_are_skipped() -> None:
    high_priority = AlwaysMatchesRule(priority=10, classification="HIGH_PRIORITY")
    high_priority.enabled = False

    engine = RuleEngine([high_priority, AlwaysMatchesRule(priority=100, classification="FALLBACK")])
    result = engine.evaluate(DummyContext(value=1))

    assert result.classification == "FALLBACK"


def test_non_applying_rules_are_passed_over() -> None:
    engine = RuleEngine(
        [
            NeverMatchesRule(priority=1),
            ConditionalRule(priority=2),
            AlwaysMatchesRule(priority=100, classification="DEFAULT"),
        ]
    )

    assert engine.evaluate(DummyContext(value=1)).classification == "DEFAULT"
    assert engine.evaluate(DummyContext(value=20)).classification == "HIGH"


def test_no_match_uses_provided_fallback() -> None:
    engine = RuleEngine([NeverMatchesRule(priority=1)])

    fallback = RuleResult(applies=True, classification="CUSTOM_FALLBACK", stop_evaluation=True)
    result = engine.evaluate(DummyContext(value=1), fallback=fallback)

    assert result.classification == "CUSTOM_FALLBACK"


def test_no_match_uses_default_fallback_when_none_provided() -> None:
    engine = RuleEngine([NeverMatchesRule(priority=1)])
    result = engine.evaluate(DummyContext(value=1))

    assert result.rule_name == "NoMatch"
    assert result.classification is None
