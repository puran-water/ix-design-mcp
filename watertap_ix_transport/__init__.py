"""
WaterTAP Ion Exchange Transport Models

This package provides rigorous ion exchange and degasification models
for the WaterTAP water treatment modeling framework.

Models:
- IonExchangeTransport0D: PHREEQC TRANSPORT-based ion exchange model
- DegasserTower0D: PHREEQC-based degasser for CO2 removal

Features:
- Multi-component ion exchange with true thermodynamic modeling
- Kinetic limitations and fouling effects
- Acid dosing and CO2 stripping for degasification
- Full integration with WaterTAP MCAS property packages
"""

from .ion_exchange_transport_0D import (
    IonExchangeTransport0D,
    ResinType,
    RegenerantChem
)
from .ix_flowsheet_builder import (
    build_ix_flowsheet,
    add_costing_to_flowsheet
)
from .ix_initialization import (
    initialize_ix_system
)
from .production_models import (
    ProductionDegasser as DegasserTower0D,
    ProductionPhreeqcEngine,
    DegasserTower0DPhreeqc
)

__all__ = [
    "IonExchangeTransport0D",
    "ResinType",
    "RegenerantChem",
    "build_ix_flowsheet",
    "initialize_ix_system",
    "add_costing_to_flowsheet",
    "DegasserTower0D",
    "DegasserTower0DPhreeqc",
    "ProductionPhreeqcEngine"
]