"""
PHREEQC-PSE: Integration of PHREEQC with IDAES Process Systems Engineering
"""

from .core.phreeqc_block import PhreeqcBlock
from .blocks.phreeqc_ix_block import PhreeqcIXBlock
from .core.phreeqc_state import PhreeqcState
from .core.phreeqc_io import PhreeqcInputSpec, PhreeqcOutputSpec, VariableType

__all__ = [
    "PhreeqcBlock",
    "PhreeqcIXBlock", 
    "PhreeqcState",
    "PhreeqcInputSpec",
    "PhreeqcOutputSpec",
    "VariableType"
]

__version__ = "0.1.0"