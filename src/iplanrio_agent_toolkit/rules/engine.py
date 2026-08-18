"""Generic priority-ordered rule engine (Chain of Responsibility).

Evaluates a list of :class:`~iplanrio_agent_toolkit.rules.base.Rule` instances
in priority order and returns the result of the first one that applies and
requests evaluation to stop.
"""

from __future__ import annotations

from typing import Generic

from iplanrio_agent_toolkit.rules.base import Rule, RuleResult, TContext


class RuleEngine(Generic[TContext]):
    """Evaluates rules in ascending priority order, stopping at the first match.

    Evaluation flow:

    1. Rules are sorted by ``priority`` (lower number = evaluated first).
    2. Each enabled rule is evaluated in order.
    3. If a rule applies and ``stop_evaluation`` is ``True``, its result is
       returned immediately.
    4. If a rule applies but ``stop_evaluation`` is ``False``, evaluation
       continues to the next rule (useful for rules that only annotate context).
    5. If no rule stops evaluation, a caller-supplied fallback result is
       returned instead of raising — callers should normally include a
       catch-all rule with the lowest priority to make this branch unreachable
       in practice.
    """

    def __init__(self, rules: list[Rule[TContext]]) -> None:
        """Sort and store the rules to evaluate.

        :param rules: Rules to evaluate, in any order (sorted internally by priority).
        """
        self.rules = sorted(rules, key=lambda rule: rule.priority)

    def evaluate(self, context: TContext, fallback: RuleResult | None = None) -> RuleResult:
        """Evaluate all enabled rules against ``context`` in priority order.

        :param context: Application-defined data passed to each rule.
        :param fallback: Result to return if no rule stops evaluation. Defaults
            to a generic "no rule matched" result.
        :returns: The result of the first matching, stop-evaluating rule, or ``fallback``.
        """
        for rule in self.rules:
            if not rule.enabled:
                continue

            result = rule.evaluate(context)
            if result.applies and result.stop_evaluation:
                return result

        return fallback or RuleResult(
            applies=True,
            classification=None,
            stop_evaluation=True,
            reason="No rule matched and no fallback was configured",
            rule_name="NoMatch",
        )
