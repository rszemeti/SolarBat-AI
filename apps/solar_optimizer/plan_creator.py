"""
Compatibility Shim - PlanCreator

DEPRECATED: Use planners.RuleBasedPlanner instead.

This file maintains backward compatibility with existing code
that imports PlanCreator directly.

Old:
    from apps.solar_optimizer.plan_creator import PlanCreator
    
New:
    from apps.solar_optimizer.planners import RuleBasedPlanner
"""

import warnings
from planners.rule_based_planner import RuleBasedPlanner

# Create alias for backward compatibility
PlanCreator = RuleBasedPlanner

# Warn about deprecated import
warnings.warn(
    "PlanCreator is deprecated. Use 'from apps.solar_optimizer.planners import RuleBasedPlanner' instead.",
    DeprecationWarning,
    stacklevel=2
)

__all__ = ['PlanCreator']
