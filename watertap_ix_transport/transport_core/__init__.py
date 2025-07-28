"""
Transport Core Module

Reusable PHREEQC-based transport and modeling engines
"""

from .phreeqc_transport_engine import PhreeqcTransportEngine, TransportParameters

# Only import modules that exist
__all__ = ["PhreeqcTransportEngine", "TransportParameters"]

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

try:
    from .phreeqpy_engine import PhreeqPyEngine, IXColumn
    __all__.extend(["PhreeqPyEngine", "IXColumn"])
except ImportError:
    pass

try:
    from .kinetic_model import KineticModel, KineticParameters
    __all__.extend(["KineticModel", "KineticParameters"])
except ImportError:
    pass

try:
    from .fouling_model import FoulingModel
    __all__.append("FoulingModel")
except ImportError:
    pass

try:
    from .trace_metals_model import TraceMetalsModel
    __all__.append("TraceMetalsModel")
except ImportError:
    pass