"""
Dependency Loader - Ensures provider dependencies are loaded

This helper ensures all required modules are loaded when running
outside of a proper package context (e.g., in test harness).

Usage:
    from dependency_loader import ensure_dependencies_loaded
    ensure_dependencies_loaded()
"""

import sys
import importlib.util
from pathlib import Path


def ensure_dependencies_loaded():
    """
    Load all provider dependencies if not already loaded.
    
    This is needed when modules are loaded individually (test harness)
    rather than as a package (AppDaemon).
    """
    # Get providers directory
    providers_dir = Path(__file__).parent
    
    # List of dependencies to load (in order)
    dependencies = [
        ('base_provider', 'base_provider.py'),
        ('time_series_predictor', 'time_series_predictor.py'),
        ('historical_cache', 'historical_cache.py'),
        ('historical_data_cache', 'historical_data_cache.py'),
    ]
    
    for module_name, filename in dependencies:
        if module_name not in sys.modules:
            file_path = providers_dir / filename
            if file_path.exists():
                try:
                    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[module_name] = module
                        spec.loader.exec_module(module)
                except Exception as e:
                    # Silently fail - module will handle missing dependency
                    pass


# Auto-load when this module is imported
ensure_dependencies_loaded()
