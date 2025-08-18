"""
Regeneration Strategies for Ion Exchange Resins

Implements different regeneration strategies for SAC and WAC resins.
Handles multi-step regeneration sequences with proper chemical dosing
and flow direction control.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from abc import ABC, abstractmethod
import numpy as np
from pathlib import Path
import sys
import json

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tools.core_config import CONFIG

logger = logging.getLogger(__name__)


class RegenerationStep:
    """Represents a single regeneration step"""
    
    def __init__(
        self,
        name: str,
        chemical: str,
        concentration_percent: float,
        normality: float,
        bv: float,
        flow_rate_bv_hr: float,
        flow_direction: str = "back",
        temperature_c: float = 25.0
    ):
        self.name = name
        self.chemical = chemical
        self.concentration_percent = concentration_percent
        self.normality = normality
        self.bv = bv
        self.flow_rate_bv_hr = flow_rate_bv_hr
        self.flow_direction = flow_direction
        self.temperature_c = temperature_c
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "chemical": self.chemical,
            "concentration_percent": self.concentration_percent,
            "normality": self.normality,
            "bv": self.bv,
            "flow_rate_bv_hr": self.flow_rate_bv_hr,
            "flow_direction": self.flow_direction,
            "temperature_c": self.temperature_c
        }
    
    def calculate_chemical_mass(self, bed_volume_L: float) -> float:
        """Calculate mass of chemical needed (kg)"""
        volume_L = self.bv * bed_volume_L
        
        if self.chemical == "NaCl":
            # Concentration in g/L = concentration_percent * 10
            concentration_g_L = self.concentration_percent * 10
            mass_kg = volume_L * concentration_g_L / 1000
        elif self.chemical == "HCl":
            # HCl: normality * MW * volume
            mass_kg = self.normality * 36.46 * volume_L / 1000
        elif self.chemical == "NaOH":
            # NaOH: normality * MW * volume
            mass_kg = self.normality * 40.0 * volume_L / 1000
        elif self.chemical == "H2SO4":
            # H2SO4: normality * MW/2 * volume (diprotic)
            mass_kg = self.normality * 49.04 * volume_L / 1000
        else:
            mass_kg = 0
        
        return mass_kg
    
    def calculate_duration(self, bed_volume_L: float) -> float:
        """Calculate step duration (hours)"""
        return self.bv / self.flow_rate_bv_hr


class BaseRegenerationStrategy(ABC):
    """Base class for regeneration strategies"""
    
    def __init__(self, resin_parameters: Dict[str, Any]):
        self.resin_parameters = resin_parameters
        self.steps: List[RegenerationStep] = []
        self._build_steps()
    
    @abstractmethod
    def _build_steps(self):
        """Build the regeneration steps"""
        pass
    
    def get_steps(self) -> List[RegenerationStep]:
        """Get regeneration steps"""
        return self.steps
    
    def calculate_total_duration(self, bed_volume_L: float) -> float:
        """Calculate total regeneration duration (hours)"""
        return sum(step.calculate_duration(bed_volume_L) for step in self.steps)
    
    def calculate_chemical_usage(self, bed_volume_L: float) -> Dict[str, float]:
        """Calculate total chemical usage (kg)"""
        usage = {}
        for step in self.steps:
            if step.chemical != "water":
                if step.chemical not in usage:
                    usage[step.chemical] = 0
                usage[step.chemical] += step.calculate_chemical_mass(bed_volume_L)
        return usage
    
    def calculate_waste_volume(self, bed_volume_L: float) -> float:
        """Calculate total waste volume (L)"""
        return sum(step.bv * bed_volume_L for step in self.steps)
    
    def get_summary(self, bed_volume_L: float) -> Dict[str, Any]:
        """Get regeneration summary"""
        return {
            "steps": [step.to_dict() for step in self.steps],
            "total_duration_hours": self.calculate_total_duration(bed_volume_L),
            "chemical_usage_kg": self.calculate_chemical_usage(bed_volume_L),
            "waste_volume_L": self.calculate_waste_volume(bed_volume_L),
            "flow_direction": self.steps[0].flow_direction if self.steps else "back"
        }


class SACRegenerationStrategy(BaseRegenerationStrategy):
    """Standard SAC regeneration with NaCl"""
    
    def _build_steps(self):
        """Build SAC regeneration steps"""
        regen_params = self.resin_parameters.get("regeneration", {})
        
        # Backwash (optional)
        if regen_params.get("backwash_enabled", True):
            self.steps.append(RegenerationStep(
                name="backwash",
                chemical="water",
                concentration_percent=0,
                normality=0,
                bv=3.0,
                flow_rate_bv_hr=10.0,
                flow_direction="back"
            ))
        
        # Brine injection
        dose_kg_m3 = regen_params.get("dose_kg_m3", CONFIG.REGENERANT_DOSE_KG_M3)
        concentration_percent = regen_params.get("concentration_percent", CONFIG.REGENERANT_CONCENTRATION_PERCENT)
        
        # Calculate BV from dose and concentration
        # dose (kg/m3) = concentration (%) * 10 * BV
        bv = dose_kg_m3 / (concentration_percent * 10)
        
        self.steps.append(RegenerationStep(
            name="brine",
            chemical="NaCl",
            concentration_percent=concentration_percent,
            normality=concentration_percent * 10 / 58.44,  # g/L to mol/L
            bv=bv,
            flow_rate_bv_hr=regen_params.get("flow_rate_bv_hr", CONFIG.REGENERANT_FLOW_BV_HR),
            flow_direction="back"
        ))
        
        # Slow rinse
        self.steps.append(RegenerationStep(
            name="slow_rinse",
            chemical="water",
            concentration_percent=0,
            normality=0,
            bv=1.0,
            flow_rate_bv_hr=regen_params.get("flow_rate_bv_hr", CONFIG.REGENERANT_FLOW_BV_HR),
            flow_direction="back"
        ))
        
        # Fast rinse
        self.steps.append(RegenerationStep(
            name="fast_rinse",
            chemical="water",
            concentration_percent=0,
            normality=0,
            bv=regen_params.get("rinse_volume_BV", CONFIG.RINSE_VOLUME_BV) - 1.0,
            flow_rate_bv_hr=10.0,
            flow_direction="forward"
        ))


class TwoStepWacNaRegen(BaseRegenerationStrategy):
    """Two-step regeneration for WAC Na-form"""
    
    def _build_steps(self):
        """Build WAC Na-form regeneration steps"""
        # Get steps from resin parameters
        regen_config = self.resin_parameters.get("regeneration", {})
        steps_config = regen_config.get("steps", [])
        
        if not steps_config:
            # Use defaults if not provided
            self._build_default_steps()
        else:
            # Build from configuration
            for step_config in steps_config:
                self.steps.append(RegenerationStep(
                    name=step_config["name"],
                    chemical=step_config["chemical"],
                    concentration_percent=step_config.get("concentration_percent", 0),
                    normality=step_config.get("normality", 0),
                    bv=step_config["bv"],
                    flow_rate_bv_hr=step_config.get("flow_rate_bv_hr", 2.0),
                    flow_direction=step_config.get("flow_direction", "back")
                ))
    
    def _build_default_steps(self):
        """Build default WAC Na-form regeneration steps"""
        # Step 1: Acid (HCl)
        self.steps.append(RegenerationStep(
            name="acid",
            chemical="HCl",
            concentration_percent=5,
            normality=1.5,
            bv=2.0,
            flow_rate_bv_hr=2.0,
            flow_direction="back"
        ))
        
        # Step 2: Water rinse
        self.steps.append(RegenerationStep(
            name="rinse1",
            chemical="water",
            concentration_percent=0,
            normality=0,
            bv=2.0,
            flow_rate_bv_hr=4.0,
            flow_direction="back"
        ))
        
        # Step 3: Caustic (NaOH)
        self.steps.append(RegenerationStep(
            name="caustic",
            chemical="NaOH",
            concentration_percent=4,
            normality=1.0,
            bv=2.0,
            flow_rate_bv_hr=2.0,
            flow_direction="back"
        ))
        
        # Step 4: Final rinse
        self.steps.append(RegenerationStep(
            name="rinse2",
            chemical="water",
            concentration_percent=0,
            normality=0,
            bv=3.0,
            flow_rate_bv_hr=4.0,
            flow_direction="back"
        ))
    
    def calculate_efficiency(self, hardness_removed_eq: float, bed_volume_L: float) -> Dict[str, float]:
        """Calculate regeneration efficiency"""
        # Acid efficiency
        acid_usage = sum(step.calculate_chemical_mass(bed_volume_L) 
                        for step in self.steps if step.chemical == "HCl")
        acid_eq = acid_usage / 0.03646  # kg to eq for HCl
        acid_efficiency = (hardness_removed_eq / acid_eq * 100) if acid_eq > 0 else 0
        
        # Caustic efficiency (for conversion to Na form)
        caustic_usage = sum(step.calculate_chemical_mass(bed_volume_L)
                           for step in self.steps if step.chemical == "NaOH")
        caustic_eq = caustic_usage / 0.040  # kg to eq for NaOH
        
        # Total capacity to convert
        total_capacity = CONFIG.WAC_NA_TOTAL_CAPACITY * bed_volume_L
        caustic_efficiency = (total_capacity / caustic_eq * 100) if caustic_eq > 0 else 0
        
        return {
            "acid_efficiency_percent": min(acid_efficiency, 95),  # Cap at theoretical max
            "caustic_efficiency_percent": min(caustic_efficiency, 90)
        }


class SingleStepWacHRegen(BaseRegenerationStrategy):
    """Single-step regeneration for WAC H-form"""
    
    def _build_steps(self):
        """Build WAC H-form regeneration steps"""
        # Get steps from resin parameters
        regen_config = self.resin_parameters.get("regeneration", {})
        steps_config = regen_config.get("steps", [])
        
        if not steps_config:
            # Use defaults if not provided
            self._build_default_steps()
        else:
            # Build from configuration
            for step_config in steps_config:
                self.steps.append(RegenerationStep(
                    name=step_config["name"],
                    chemical=step_config["chemical"],
                    concentration_percent=step_config.get("concentration_percent", 0),
                    normality=step_config.get("normality", 0),
                    bv=step_config["bv"],
                    flow_rate_bv_hr=step_config.get("flow_rate_bv_hr", 2.0),
                    flow_direction=step_config.get("flow_direction", "back")
                ))
    
    def _build_default_steps(self):
        """Build default WAC H-form regeneration steps"""
        # Step 1: Acid (HCl)
        self.steps.append(RegenerationStep(
            name="acid",
            chemical="HCl",
            concentration_percent=5,
            normality=1.5,
            bv=2.0,
            flow_rate_bv_hr=2.0,
            flow_direction="back"
        ))
        
        # Step 2: Rinse
        self.steps.append(RegenerationStep(
            name="rinse",
            chemical="water",
            concentration_percent=0,
            normality=0,
            bv=3.0,
            flow_rate_bv_hr=4.0,
            flow_direction="back"
        ))
    
    def calculate_efficiency(self, alkalinity_removed_eq: float, bed_volume_L: float) -> Dict[str, float]:
        """Calculate regeneration efficiency"""
        # Acid efficiency
        acid_usage = sum(step.calculate_chemical_mass(bed_volume_L)
                        for step in self.steps if step.chemical == "HCl")
        acid_eq = acid_usage / 0.03646  # kg to eq for HCl
        acid_efficiency = (alkalinity_removed_eq / acid_eq * 100) if acid_eq > 0 else 0
        
        return {
            "acid_efficiency_percent": min(acid_efficiency, 98)  # H-form has very high efficiency
        }


def get_regeneration_strategy(
    resin_type: str,
    resin_parameters: Dict[str, Any]
) -> BaseRegenerationStrategy:
    """Factory function to get appropriate regeneration strategy"""
    
    if resin_type == "SAC":
        return SACRegenerationStrategy(resin_parameters)
    elif resin_type == "WAC_Na":
        return TwoStepWacNaRegen(resin_parameters)
    elif resin_type == "WAC_H":
        return SingleStepWacHRegen(resin_parameters)
    else:
        raise ValueError(f"Unknown resin type: {resin_type}")


def load_resin_parameters(resin_type: str) -> Dict[str, Any]:
    """Load resin parameters from database"""
    db_path = project_root / "databases" / "resin_parameters.json"
    
    if not db_path.exists():
        raise FileNotFoundError(f"Resin parameters database not found: {db_path}")
    
    with open(db_path, 'r') as f:
        all_parameters = json.load(f)
    
    if resin_type not in all_parameters:
        raise ValueError(f"Resin type {resin_type} not found in database")
    
    return all_parameters[resin_type]