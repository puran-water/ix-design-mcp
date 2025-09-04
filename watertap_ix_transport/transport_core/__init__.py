"""
Transport Core Module

Reusable PHREEQC-based transport and modeling engines
"""

# Only import modules that actually exist
__all__ = []

# Import PHREEQC engines
try:
    from .direct_phreeqc_engine import DirectPhreeqcEngine
    __all__.append("DirectPhreeqcEngine")
except ImportError:
    pass

try:
    from .optimized_phreeqc_engine import OptimizedPhreeqcEngine
    __all__.append("OptimizedPhreeqcEngine")
except ImportError:
    pass