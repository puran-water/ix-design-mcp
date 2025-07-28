"""
Ion Exchange MCP Server Tools

This module contains the MCP tool implementations for ion exchange system design.
"""

# Import only shared utilities - NO tool imports to prevent coupling!
# Tools should be imported directly where needed to maintain independence
from .core_config import CONFIG
from .unit_conversions import (
    mg_to_meq,
    meq_to_mg,
    calculate_hardness_as_caco3,
    calculate_alkalinity_as_caco3,
    ConcentrationUnit,
    FlowUnit,
    VolumeUnit
)

__all__ = [
    # Utilities only - tools are imported directly in server.py
    'CONFIG',
    'mg_to_meq',
    'meq_to_mg',
    'calculate_hardness_as_caco3',
    'calculate_alkalinity_as_caco3',
    'ConcentrationUnit',
    'FlowUnit',
    'VolumeUnit'
]