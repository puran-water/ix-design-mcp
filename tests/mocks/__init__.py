"""
Mock modules for unit testing.

This package provides mock implementations of external dependencies
to enable fast, isolated unit tests without requiring actual PHREEQC
or WaterTAP installations.
"""

from .mock_phreeqc import MockPhreeqcEngine, MockBreakthroughData

__all__ = ["MockPhreeqcEngine", "MockBreakthroughData"]
