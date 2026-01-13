"""
Planners Module

All battery optimization planners implement the BasePlanner interface.

Available planners:
- RuleBasedPlanner: Heuristic rule-based optimization (default)
- MLPlanner: Machine learning guided optimization
- LinearProgrammingPlanner: LP-based mathematical optimization

Usage:
    from apps.solar_optimizer.planners import RuleBasedPlanner, MLPlanner, LinearProgrammingPlanner
    
    # Use any planner with same interface
    planner = RuleBasedPlanner()
    plan = planner.create_plan(...)
"""

from .base_planner import BasePlanner
from .rule_based_planner import RuleBasedPlanner

# Optional planners (may require dependencies)
try:
    from .ml_planner import MLPlanner
except ImportError:
    MLPlanner = None

try:
    from .lp_planner import LinearProgrammingPlanner
except ImportError:
    LinearProgrammingPlanner = None

__all__ = [
    'BasePlanner',
    'RuleBasedPlanner',
    'MLPlanner',
    'LinearProgrammingPlanner'
]
