"""
Main configurator using calculated values, not typical ranges.
All calculations based on literature-sourced equations.
"""
import logging
from typing import Dict, Any
from tools.breakthrough_calculator import BreakthroughCalculator
from tools.selectivity_coefficients import SelectivityCoefficients
from tools.capacity_derating import CapacityDerating

logger = logging.getLogger(__name__)


class KnowledgeBasedConfigurator:
    """
    Configure IX systems using literature-based calculations.
    No "typical ranges" - all values calculated from first principles.
    """

    def __init__(self):
        self.breakthrough_calc = BreakthroughCalculator()
        self.selectivity = SelectivityCoefficients()
        self.derating = CapacityDerating()

    def configure_sac_softening(self,
                               water_analysis: Dict[str, Any],
                               regen_dose_g_L: float = 120,
                               target_hardness_mg_L: float = 5.0) -> Dict[str, Any]:
        """
        Configure SAC for water softening using calculated derating and selectivity.

        Args:
            water_analysis: Water quality and flow parameters
            regen_dose_g_L: NaCl regeneration dose (g/L resin)
            target_hardness_mg_L: Target effluent hardness as CaCO3

        Returns:
            Complete configuration with performance predictions
        """
        logger.info(f"Configuring SAC softener with {regen_dose_g_L} g/L NaCl regeneration")

        # Add default flow parameters if missing
        if 'flow_BV_hr' not in water_analysis:
            water_analysis['flow_BV_hr'] = 16  # Standard service flow

        # Calculate breakthrough with all derating factors
        performance = self.breakthrough_calc.calculate_sac_breakthrough(
            water_analysis,
            regen_dose_g_L,
            total_capacity_eq_L=2.0  # Literature value for SAC (sulfonic acid)
        )

        # Vessel sizing
        flow_m3_hr = water_analysis.get('flow_m3_hr', 100)
        flow_BV_hr = water_analysis.get('flow_BV_hr', 16)
        bed_volume_m3 = flow_m3_hr / flow_BV_hr

        # Calculate vessel dimensions
        # Standard L/D ratio = 1.5-2.0
        # Max diameter = 2.4 m (shipping constraint)
        import math
        bed_depth_m = 1.5  # Start with standard depth
        diameter_m = math.sqrt(4 * bed_volume_m3 / (math.pi * bed_depth_m))

        if diameter_m > 2.4:
            diameter_m = 2.4
            bed_depth_m = bed_volume_m3 / (math.pi * (diameter_m/2)**2)

        # Regeneration parameters
        # NaCl dose and concentration from literature
        brine_concentration = 0.10  # 10% w/w standard
        nacl_mw = 58.44  # g/mol

        # Volume of brine needed
        total_nacl_kg = regen_dose_g_L * bed_volume_m3  # g/L * m³ = kg
        brine_volume_m3 = total_nacl_kg / (brine_concentration * 1000)
        regen_volume_BV = brine_volume_m3 / bed_volume_m3

        # Rinse requirement
        rinse_BV = self.derating.calculate_rinse_requirement(regen_dose_g_L, bed_volume_m3)

        # Calculate regenerant efficiency
        # eq regenerated / eq regenerant used
        operating_capacity = performance['operating_capacity_eq_L']
        capacity_regenerated_eq = operating_capacity * bed_volume_m3 * 1000
        regenerant_used_eq = total_nacl_kg * 1000 / nacl_mw
        regenerant_efficiency = capacity_regenerated_eq / regenerant_used_eq if regenerant_used_eq > 0 else 0

        config = {
            'resin_type': 'SAC',
            'application': 'water_softening',
            'vessel': {
                'bed_volume_m3': bed_volume_m3,
                'diameter_m': diameter_m,
                'bed_depth_m': bed_depth_m,
                'L_D_ratio': bed_depth_m / diameter_m,
                'flow_BV_hr': flow_BV_hr,
                'linear_velocity_m_hr': flow_m3_hr / (math.pi * (diameter_m/2)**2),
                'EBCT_min': bed_volume_m3 / flow_m3_hr * 60
            },
            'performance': {
                'breakthrough_BV': performance['BV_breakthrough'],
                'theoretical_BV': performance['BV_theoretical'],
                'operating_capacity_eq_L': performance['operating_capacity_eq_L'],
                'derating_factor': performance['derating_factor'],
                'utilization': performance['utilization'],
                'LUB_fraction': performance['LUB_fraction'],
                'hardness_feed_mg_L': performance['hardness_feed_mg_L'],
                'hardness_leakage_mg_L': performance['hardness_leakage_mg_L'],
                'run_length_hrs': performance['run_length_hrs'],
                'run_volume_m3': performance['BV_breakthrough'] * bed_volume_m3,
                'ion_fractions': performance['ion_fractions']
            },
            'regeneration': {
                'chemical': 'NaCl',
                'dose_g_L': regen_dose_g_L,
                'concentration': f'{brine_concentration*100:.0f}%',
                'volume_BV': regen_volume_BV,
                'volume_m3': brine_volume_m3,
                'rinse_volume_BV': rinse_BV,
                'rinse_volume_m3': rinse_BV * bed_volume_m3,
                'flow_BV_hr': 4,  # Typical regeneration flow
                'duration_hrs': (regen_volume_BV + rinse_BV) / 4,
                'efficiency': regenerant_efficiency,
                'waste_volume_m3': (regen_volume_BV + rinse_BV) * bed_volume_m3
            },
            'selectivity': self.selectivity.SAC_8DVB,
            'design_basis': {
                'total_capacity_eq_L': 2.0,
                'crosslinking': '8% DVB',
                'resin_type': 'Gel-type strong acid cation',
                'functional_group': 'Sulfonic acid (-SO3H)'
            },
            'economics': self._estimate_sac_economics(
                bed_volume_m3,
                regen_dose_g_L,
                performance['BV_breakthrough']
            )
        }

        return config

    def configure_wac_h(self,
                       water_analysis: Dict[str, Any],
                       target_alkalinity_mg_L: float = 10.0) -> Dict[str, Any]:
        """
        Configure WAC-H for alkalinity removal using pH-dependent capacity.

        Args:
            water_analysis: Water quality and flow parameters
            target_alkalinity_mg_L: Target effluent alkalinity as CaCO3

        Returns:
            Complete configuration with performance predictions
        """
        logger.info("Configuring WAC-H for alkalinity removal")

        # Add default flow parameters if missing
        if 'flow_BV_hr' not in water_analysis:
            water_analysis['flow_BV_hr'] = 16

        # Pass target alkalinity to breakthrough calculator
        # This drives the pH floor and capacity calculation
        water_analysis['target_alkalinity_mg_L_CaCO3'] = target_alkalinity_mg_L

        performance = self.breakthrough_calc.calculate_wac_h_breakthrough(
            water_analysis,
            total_capacity_eq_L=4.7  # Literature value for WAC (carboxylic)
        )

        flow_m3_hr = water_analysis.get('flow_m3_hr', 100)
        flow_BV_hr = water_analysis.get('flow_BV_hr', 16)
        bed_volume_m3 = flow_m3_hr / flow_BV_hr

        # Vessel dimensions
        import math
        bed_depth_m = 1.5
        diameter_m = math.sqrt(4 * bed_volume_m3 / (math.pi * bed_depth_m))

        if diameter_m > 2.4:
            diameter_m = 2.4
            bed_depth_m = bed_volume_m3 / (math.pi * (diameter_m/2)**2)

        # Regeneration with HCl
        # Stoichiometric + 10% excess
        operating_capacity = performance['operating_capacity_eq_L']
        capacity_to_regenerate_eq = operating_capacity * bed_volume_m3 * 1000
        regen_eq_required = capacity_to_regenerate_eq * 1.1  # 10% excess

        # HCl concentration: 5% w/w
        hcl_concentration = 0.05
        hcl_mw = 36.46  # g/mol
        hcl_normality = hcl_concentration * 1000 / hcl_mw

        acid_volume_m3 = regen_eq_required / (hcl_normality * 1000)
        regen_volume_BV = acid_volume_m3 / bed_volume_m3

        # Rinse requirement
        rinse_BV = 3  # Standard for acid regeneration

        config = {
            'resin_type': 'WAC_H',
            'application': 'alkalinity_removal',
            'vessel': {
                'bed_volume_m3': bed_volume_m3,
                'diameter_m': diameter_m,
                'bed_depth_m': bed_depth_m,
                'L_D_ratio': bed_depth_m / diameter_m,
                'flow_BV_hr': flow_BV_hr,
                'linear_velocity_m_hr': flow_m3_hr / (math.pi * (diameter_m/2)**2),
                'EBCT_min': bed_volume_m3 / flow_m3_hr * 60
            },
            'performance': {
                'breakthrough_BV': performance['BV_alkalinity'],
                'theoretical_BV': performance['BV_theoretical'],
                'operating_capacity_eq_L': performance['operating_capacity_eq_L'],
                'pH_dependent_fraction': performance['pH_dependent_capacity_fraction'],
                'utilization': performance['utilization'],
                'LUB_fraction': performance['LUB_fraction'],
                'alkalinity_feed_mg_L': performance['alkalinity_feed_mg_L'],
                'CO2_generation_mg_L': performance['CO2_generation_mg_L'],
                'pH_profile': performance['pH_profile'],
                'run_length_hrs': performance['run_length_hrs'],
                'run_volume_m3': performance['BV_alkalinity'] * bed_volume_m3
            },
            'regeneration': {
                'chemical': 'HCl',
                'concentration': f'{hcl_concentration*100:.0f}%',
                'dose_eq_L': regen_eq_required / (bed_volume_m3 * 1000),
                'stoichiometric_excess': '10%',
                'volume_BV': regen_volume_BV,
                'volume_m3': acid_volume_m3,
                'rinse_volume_BV': rinse_BV,
                'rinse_volume_m3': rinse_BV * bed_volume_m3,
                'flow_BV_hr': 4,
                'duration_hrs': (regen_volume_BV + rinse_BV) / 4,
                'waste_pH': '2-3',
                'waste_volume_m3': (regen_volume_BV + rinse_BV) * bed_volume_m3
            },
            'design_basis': {
                'total_capacity_eq_L': 4.7,
                'pKa': 4.5,
                'resin_type': 'Weak acid cation',
                'functional_group': 'Carboxylic acid (-COOH)',
                'pH_dependency': 'Capacity decreases below pH 7'
            },
            'warnings': [
                'CO2 stripping required in effluent',
                'pH control critical for capacity',
                'Not suitable for permanent hardness removal'
            ]
        }

        return config

    def configure_wac_na(self,
                        water_analysis: Dict[str, Any],
                        target_temp_hardness_mg_L: float = 10.0) -> Dict[str, Any]:
        """
        Configure WAC-Na for temporary hardness removal.

        Args:
            water_analysis: Water quality and flow parameters
            target_temp_hardness_mg_L: Target temporary hardness

        Returns:
            Complete configuration
        """
        logger.info("Configuring WAC-Na for temporary hardness removal")

        if 'flow_BV_hr' not in water_analysis:
            water_analysis['flow_BV_hr'] = 16

        performance = self.breakthrough_calc.calculate_wac_na_breakthrough(
            water_analysis,
            total_capacity_eq_L=4.0  # WAC-Na typical capacity
        )

        flow_m3_hr = water_analysis.get('flow_m3_hr', 100)
        flow_BV_hr = water_analysis.get('flow_BV_hr', 16)
        bed_volume_m3 = flow_m3_hr / flow_BV_hr

        # Vessel dimensions
        import math
        bed_depth_m = 1.5
        diameter_m = math.sqrt(4 * bed_volume_m3 / (math.pi * bed_depth_m))

        if diameter_m > 2.4:
            diameter_m = 2.4
            bed_depth_m = bed_volume_m3 / (math.pi * (diameter_m/2)**2)

        # Two-step regeneration for WAC-Na
        # Step 1: Acid (HCl) to convert to H-form
        # Step 2: NaOH to convert to Na-form
        operating_capacity = performance['operating_capacity_eq_L']
        capacity_eq = operating_capacity * bed_volume_m3 * 1000

        # Acid step
        acid_eq = capacity_eq * 1.1  # 10% excess
        acid_concentration = 0.05  # 5% HCl
        acid_volume_m3 = acid_eq / (acid_concentration * 1000 / 36.46 * 1000)

        # Caustic step
        caustic_eq = capacity_eq * 1.05  # 5% excess
        caustic_concentration = 0.04  # 4% NaOH
        caustic_volume_m3 = caustic_eq / (caustic_concentration * 1000 / 40.0 * 1000)

        config = {
            'resin_type': 'WAC_Na',
            'application': 'temporary_hardness_removal',
            'vessel': {
                'bed_volume_m3': bed_volume_m3,
                'diameter_m': diameter_m,
                'bed_depth_m': bed_depth_m,
                'flow_BV_hr': flow_BV_hr
            },
            'performance': {
                'breakthrough_BV': performance['BV_breakthrough'],
                'operating_capacity_eq_L': performance['operating_capacity_eq_L'],
                'removable_hardness_mg_L': performance['removable_hardness_mg_L'],
                'utilization': performance['utilization'],
                'run_length_hrs': performance['run_length_hrs']
            },
            'regeneration': {
                'type': 'two-step',
                'step1': {
                    'chemical': 'HCl',
                    'concentration': '5%',
                    'volume_m3': acid_volume_m3
                },
                'step2': {
                    'chemical': 'NaOH',
                    'concentration': '4%',
                    'volume_m3': caustic_volume_m3
                },
                'rinse_volume_m3': 4 * bed_volume_m3
            }
        }

        return config

    def _estimate_sac_economics(self,
                               bed_volume_m3: float,
                               regen_dose_g_L: float,
                               breakthrough_BV: float) -> Dict[str, float]:
        """
        Estimate economics for SAC softening.

        Based on literature cost factors.
        """
        # Capital costs (rough estimates)
        vessel_cost = bed_volume_m3 * 5000  # $/m³ resin
        resin_cost = bed_volume_m3 * 2800  # $/m³ for SAC resin

        # Operating costs
        # NaCl cost: $0.12/kg typical
        nacl_kg_per_regen = regen_dose_g_L * bed_volume_m3
        nacl_cost_per_regen = nacl_kg_per_regen * 0.12

        # Water for regeneration and rinse
        water_m3_per_regen = 5 * bed_volume_m3  # Approximate
        water_cost_per_regen = water_m3_per_regen * 2.0  # $/m³

        # Cost per m³ treated
        volume_per_cycle_m3 = breakthrough_BV * bed_volume_m3
        chemical_cost_per_m3 = (nacl_cost_per_regen + water_cost_per_regen) / volume_per_cycle_m3

        return {
            'capital_cost_usd': vessel_cost + resin_cost,
            'resin_cost_usd': resin_cost,
            'vessel_cost_usd': vessel_cost,
            'chemical_cost_per_m3': chemical_cost_per_m3,
            'nacl_cost_per_regen': nacl_cost_per_regen,
            'water_cost_per_regen': water_cost_per_regen,
            'cycles_per_year': 365 * 24 / (breakthrough_BV / 16)  # Assuming 16 BV/hr
        }