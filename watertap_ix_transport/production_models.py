"""
Production models for IX Design MCP

This module provides the selected production implementations after consolidation.
All imports should use these standardized names for consistency.
"""

# Selected PHREEQC Engine (winner from testing)
from .transport_core.phreeqc_transport_engine import PhreeqcTransportEngine
from .transport_core.phreeqc_transport_engine import PhreeqPython

# Selected Degasser Model (winner from testing)
from .degasser_tower_0D_phreeqc_final import DegasserTower0DPhreeqc
from .degasser_tower_0D_phreeqc_final import DegasserTower0DPhreeqcData

# Standardized names for production use
ProductionPhreeqcEngine = PhreeqcTransportEngine
ProductionDegasser = DegasserTower0DPhreeqc

# Export all
__all__ = [
    'PhreeqcTransportEngine',
    'PhreeqPython',
    'DegasserTower0DPhreeqc',
    'DegasserTower0DPhreeqcData',
    'ProductionPhreeqcEngine',
    'ProductionDegasser'
]