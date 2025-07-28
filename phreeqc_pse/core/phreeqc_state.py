"""
PHREEQC State Configuration
Manages system state and configuration for PHREEQC equilibrium calculations
"""

from typing import List, Dict, Optional, Set
from pyomo.environ import Var, Param, Constraint, Set as PyomoSet
from pyomo.environ import units as pyunits
import logging

logger = logging.getLogger(__name__)


class PhreeqcState:
    """
    State object managing PHREEQC system configuration
    
    This class tracks:
    - Active phases (aqueous, gas, mineral)
    - Components/species
    - Thermodynamic database
    - Temperature/pressure conditions
    - Activity models
    """
    
    def __init__(self, 
                 database: str = "phreeqc.dat",
                 phases: List[str] = None,
                 components: List[str] = None,
                 temperature: float = 298.15,
                 pressure: float = 101325.0):
        """
        Initialize PHREEQC state
        
        Args:
            database: PHREEQC database file
            phases: List of phases to consider (default: ['Aqueous'])
            components: List of components to track
            temperature: System temperature (K)
            pressure: System pressure (Pa)
        """
        self.database = database
        self.phases = phases or ['Aqueous']
        self.components = components or []
        self.temperature = temperature
        self.pressure = pressure
        
        # Activity models
        self.activity_model = 'Davies'  # Davies, Debye-Huckel, Pitzer
        
        # Ion exchange specific
        self.has_ion_exchange = False
        self.exchange_sites = {}  # {site_name: capacity}
        self.exchanger_species = []
        
        # Minerals
        self.minerals = []
        self.mineral_constraints = {}  # {mineral: saturation_index}
        
        # Gas phase
        self.gas_components = []
        self.gas_fugacity_model = 'ideal'
        
        # Kinetic reactions
        self.kinetic_reactions = []
        
        logger.info(f"PhreeqcState initialized with {len(self.components)} components, {len(self.phases)} phases")
    
    def add_ion_exchange(self, 
                        site_name: str = 'X',
                        capacity: float = 1.0,
                        exchanger_species: List[str] = None):
        """
        Add ion exchange to the system
        
        Args:
            site_name: Exchange site identifier
            capacity: Exchange capacity (eq/L)
            exchanger_species: List of exchangeable species
        """
        self.has_ion_exchange = True
        self.exchange_sites[site_name] = capacity
        
        if exchanger_species:
            self.exchanger_species.extend(exchanger_species)
        else:
            # Default exchangeable species
            self.exchanger_species = ['CaX2', 'MgX2', 'NaX', 'KX', 'HX']
        
        logger.info(f"Added ion exchange site {site_name} with capacity {capacity} eq/L")
    
    def add_mineral(self, mineral: str, saturation_index: float = 0.0):
        """
        Add mineral equilibrium constraint
        
        Args:
            mineral: Mineral name from database
            saturation_index: Target SI (0 = equilibrium)
        """
        self.minerals.append(mineral)
        self.mineral_constraints[mineral] = saturation_index
        
        logger.info(f"Added mineral {mineral} with SI = {saturation_index}")
    
    def add_gas_component(self, component: str, fugacity: Optional[float] = None):
        """
        Add gas phase component
        
        Args:
            component: Gas species (e.g., 'CO2(g)', 'O2(g)')
            fugacity: Fixed fugacity (bar) if specified
        """
        if 'Gas' not in self.phases:
            self.phases.append('Gas')
        
        self.gas_components.append({
            'component': component,
            'fugacity': fugacity
        })
        
        logger.info(f"Added gas component {component}")
    
    def build_pyomo_sets(self, block):
        """
        Build Pyomo sets on a block
        
        Args:
            block: Pyomo block to add sets to
        """
        # Component set
        if self.components:
            block.component_list = PyomoSet(initialize=self.components)
        
        # Phase set
        block.phase_list = PyomoSet(initialize=self.phases)
        
        # Ion exchange
        if self.has_ion_exchange:
            block.exchange_sites = PyomoSet(initialize=list(self.exchange_sites.keys()))
            block.exchanger_species = PyomoSet(initialize=self.exchanger_species)
            
            # Exchange capacity parameters
            block.exchange_capacity = Param(
                block.exchange_sites,
                initialize=self.exchange_sites,
                units=pyunits.mol/pyunits.L,
                doc="Ion exchange capacity"
            )
        
        # Minerals
        if self.minerals:
            block.mineral_list = PyomoSet(initialize=self.minerals)
            block.mineral_si_target = Param(
                block.mineral_list,
                initialize=self.mineral_constraints,
                doc="Target saturation index"
            )
        
        # Gas components
        if self.gas_components:
            gas_comp_names = [g['component'] for g in self.gas_components]
            block.gas_component_list = PyomoSet(initialize=gas_comp_names)
    
    def get_phreeqc_input_template(self) -> str:
        """
        Generate PHREEQC input template based on state
        
        Returns:
            PHREEQC input file template string
        """
        lines = []
        
        # Database
        lines.append(f"DATABASE {self.database}")
        lines.append("")
        
        # Solution definition
        lines.append("SOLUTION 1")
        lines.append(f"    temp      {self.temperature - 273.15}")  # °C
        lines.append(f"    pressure  {self.pressure / 101325}")  # atm
        lines.append("    pH        7.0")
        lines.append("    pe        4.0")
        
        # Add components as placeholders
        for comp in self.components:
            if comp not in ['H2O', 'H+', 'OH-']:
                lines.append(f"    {comp}    1.0e-6  # placeholder")
        
        # Ion exchange
        if self.has_ion_exchange:
            lines.append("")
            lines.append("EXCHANGE 1")
            for site, capacity in self.exchange_sites.items():
                lines.append(f"    {site}    {capacity}")
            lines.append("    -equilibrate 1")
        
        # Minerals
        if self.minerals:
            lines.append("")
            lines.append("EQUILIBRIUM_PHASES 1")
            for mineral, si in self.mineral_constraints.items():
                lines.append(f"    {mineral}    {si}    10.0")
        
        # Gas phase
        if self.gas_components:
            lines.append("")
            lines.append("GAS_PHASE 1")
            lines.append("    -fixed_pressure")
            lines.append(f"    -pressure {self.pressure / 101325}")
            lines.append(f"    -temperature {self.temperature - 273.15}")
            for gas in self.gas_components:
                if gas['fugacity'] is not None:
                    lines.append(f"    {gas['component']}    {gas['fugacity']}")
                else:
                    lines.append(f"    {gas['component']}    0.0")
        
        lines.append("")
        lines.append("END")
        
        return "\n".join(lines)
    
    def validate(self) -> bool:
        """
        Validate state configuration
        
        Returns:
            True if valid, False otherwise
        """
        # Check components
        if not self.components:
            logger.warning("No components defined")
            return False
        
        # Check for required components
        if 'H2O' not in self.components:
            logger.warning("H2O not in component list")
            return False
        
        # Check temperature/pressure
        if self.temperature < 273.15 or self.temperature > 373.15:
            logger.warning(f"Temperature {self.temperature}K outside normal range")
        
        if self.pressure < 0:
            logger.error("Negative pressure")
            return False
        
        # Check ion exchange
        if self.has_ion_exchange:
            if not self.exchange_sites:
                logger.error("Ion exchange enabled but no sites defined")
                return False
            
            for site, capacity in self.exchange_sites.items():
                if capacity <= 0:
                    logger.error(f"Invalid capacity for site {site}: {capacity}")
                    return False
        
        return True
    
    def to_dict(self) -> Dict:
        """
        Convert state to dictionary for serialization
        
        Returns:
            Dictionary representation
        """
        return {
            'database': self.database,
            'phases': self.phases,
            'components': self.components,
            'temperature': self.temperature,
            'pressure': self.pressure,
            'activity_model': self.activity_model,
            'has_ion_exchange': self.has_ion_exchange,
            'exchange_sites': self.exchange_sites,
            'exchanger_species': self.exchanger_species,
            'minerals': self.minerals,
            'mineral_constraints': self.mineral_constraints,
            'gas_components': self.gas_components,
            'gas_fugacity_model': self.gas_fugacity_model,
            'kinetic_reactions': self.kinetic_reactions
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PhreeqcState':
        """
        Create PhreeqcState from dictionary
        
        Args:
            data: Dictionary representation
            
        Returns:
            PhreeqcState instance
        """
        state = cls(
            database=data.get('database', 'phreeqc.dat'),
            phases=data.get('phases', ['Aqueous']),
            components=data.get('components', []),
            temperature=data.get('temperature', 298.15),
            pressure=data.get('pressure', 101325.0)
        )
        
        # Set additional properties
        state.activity_model = data.get('activity_model', 'Davies')
        state.has_ion_exchange = data.get('has_ion_exchange', False)
        state.exchange_sites = data.get('exchange_sites', {})
        state.exchanger_species = data.get('exchanger_species', [])
        state.minerals = data.get('minerals', [])
        state.mineral_constraints = data.get('mineral_constraints', {})
        state.gas_components = data.get('gas_components', [])
        state.gas_fugacity_model = data.get('gas_fugacity_model', 'ideal')
        state.kinetic_reactions = data.get('kinetic_reactions', [])
        
        return state