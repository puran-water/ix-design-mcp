"""
Generic IX Report Generator

Generates professional HTML reports for any ion exchange simulation type
using modular notebook sections, handcalcs for calculations, and forallpeople
for unit handling.
"""

from __future__ import annotations
import json
import logging
import yaml
import math
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Callable, List, Optional, Union
import asyncio
import sys
import os

import nbformat
from nbconvert import HTMLExporter

try:
    import papermill as pm
except ImportError as e:
    raise ImportError(
        "Required packages not installed. Install with: "
        "pip install papermill nbformat nbconvert handcalcs forallpeople"
    ) from e

logger = logging.getLogger(__name__)

# Molecular weights for equivalent calculations
MOLECULAR_WEIGHTS = {
    'Ca_2+': 40.078,
    'Mg_2+': 24.305,
    'Na_+': 22.990,
    'HCO3_-': 61.017,
    'Cl_-': 35.453,
    'SO4_2-': 96.06
}

# Valences for equivalent weight calculations
VALENCES = {
    'Ca_2+': 2,
    'Mg_2+': 2,
    'Na_+': 1,
    'HCO3_-': 1,
    'Cl_-': 1,
    'SO4_2-': 2
}

# Project structure
PROJECT_ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK_ROOT = PROJECT_ROOT / "notebooks"
MANIFESTS_DIR = NOTEBOOK_ROOT / "manifests"
SECTIONS_DIR = NOTEBOOK_ROOT / "sections"
COMPILED_DIR = NOTEBOOK_ROOT / "compiled"
OUTPUT_DIR = PROJECT_ROOT / "output" / "reports"


def safe_extract(data: Dict[str, Any], path: str, default: Any = None) -> Any:
    """Safely extract nested values from dictionaries.

    Args:
        data: The dictionary to extract from
        path: Dot-separated path to the value (e.g., 'performance.service_hours')
        default: Default value if path not found (None by default)

    Returns:
        The value at the path or default if not found
    """
    keys = path.split('.')
    value = data

    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
            if value is None:
                return default
        else:
            return default

    # Don't return empty dicts/lists, use default instead
    if isinstance(value, (dict, list)) and not value:
        return default

    return value


def mg_to_meq(concentration_mg_l: float, ion: str) -> float:
    """Convert mg/L to meq/L using proper molecular weights.

    Args:
        concentration_mg_l: Concentration in mg/L
        ion: Ion formula (e.g., 'Ca_2+', 'Mg_2+')

    Returns:
        Concentration in meq/L
    """
    if concentration_mg_l is None or math.isnan(concentration_mg_l):
        return None

    mw = MOLECULAR_WEIGHTS.get(ion)
    valence = VALENCES.get(ion)

    if not mw or not valence:
        # Fallback for unknown ions
        logger.warning(f"Unknown ion {ion}, using approximate conversion")
        return concentration_mg_l / 20  # Approximate

    equivalent_weight = mw / valence
    return concentration_mg_l / equivalent_weight


def format_with_units(value: Union[float, None], unit_str: str, precision: int = 2) -> str:
    """Format a value with units for display.

    Args:
        value: The numeric value
        unit_str: Unit string to append
        precision: Number of decimal places

    Returns:
        Formatted string or '—' for None/NaN values
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"

    return f"{value:.{precision}f} {unit_str}"


@dataclass
class IXReportData:
    """Validated data structure for IX reports."""
    performance: Dict[str, Any]
    mass_balance: Dict[str, Any]
    ion_tracking: Dict[str, Any]
    design: Dict[str, Any]
    economics: Optional[Dict[str, Any]] = None
    breakthrough_data: Optional[Dict[str, Any]] = None

    @classmethod
    def from_simulation(cls, sim_result: Dict[str, Any], design_inputs: Dict[str, Any] = None) -> 'IXReportData':
        """Create from simulation results with validation."""
        # Extract main sections with defaults
        performance = sim_result.get('performance', {})
        mass_balance = sim_result.get('mass_balance', {})
        ion_tracking = sim_result.get('ion_tracking', {})
        economics = sim_result.get('economics')
        breakthrough_data = sim_result.get('breakthrough_data')

        # Use design_inputs if provided, otherwise try to extract from sim_result
        if design_inputs:
            design = design_inputs
        else:
            design = sim_result.get('input', {})

        # Validate required fields
        required_performance = ['service_bv_to_target', 'service_hours']
        missing = [f for f in required_performance if f not in performance]
        if missing:
            logger.warning(f"Missing performance fields: {missing}")

        return cls(
            performance=performance,
            mass_balance=mass_balance,
            ion_tracking=ion_tracking,
            design=design,
            economics=economics,
            breakthrough_data=breakthrough_data
        )

    def validate_critical(self) -> bool:
        """Validate that critical data is present."""
        # Check for minimal required data
        if not self.performance:
            logger.error("No performance data available")
            return False

        if not self.ion_tracking.get('feed_mg_l'):
            logger.error("No feed water composition available")
            return False

        return True


@dataclass
class ReportSpec:
    """Specification for a resin-specific report type"""
    resin_code: str                    # e.g., "SAC", "WAC_Na", "WAC_H"
    display_name: str                  # e.g., "Strong Acid Cation (H-form)"
    manifest_name: str                 # e.g., "sac_report"
    parameter_builder: Callable[[Dict[str, Any]], Dict[str, Any]]
    post_processors: List[Callable] = field(default_factory=list)

    def assemble_notebook(self, run_ctx: Dict[str, Any]) -> Path:
        """Assemble a notebook from manifest sections"""
        manifest_path = MANIFESTS_DIR / f"{self.manifest_name}.yml"

        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")

        with manifest_path.open("r", encoding="utf-8") as fh:
            manifest = yaml.safe_load(fh)

        # Create new notebook with title
        notebook = nbformat.v4.new_notebook()

        # Add metadata
        notebook.metadata.update({
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3"
            },
            "language_info": {
                "name": "python",
                "version": "3.9.0"
            }
        })

        # Add title cell
        title_markdown = f"""# {self.display_name} Ion Exchange Report

**Generated:** {run_ctx['timestamp']}
**Run ID:** {run_ctx['run_id']}
**Resin Type:** {self.resin_code}
"""
        notebook.cells.append(nbformat.v4.new_markdown_cell(title_markdown))

        # Add parameter cell (hidden in final report)
        param_code = """# Parameters injected by papermill
# This cell will be tagged for hiding in HTML export"""
        param_cell = nbformat.v4.new_code_cell(param_code)
        param_cell.metadata["tags"] = ["parameters", "hide-cell", "hide-input"]
        notebook.cells.append(param_cell)

        # Assemble sections from manifest
        for section_id in manifest["sections"]:
            section_path = SECTIONS_DIR / f"{section_id}.ipynb"
            if not section_path.exists():
                logger.warning(f"Section not found, skipping: {section_path}")
                continue

            try:
                section_nb = nbformat.read(section_path, as_version=4)
                # Add section header
                notebook.cells.append(nbformat.v4.new_markdown_cell(
                    f"## {section_id.replace('_', ' ').title()}"
                ))

                # Auto-tag code cells to hide input
                for cell in section_nb.cells:
                    if cell.cell_type == 'code':
                        if 'tags' not in cell.metadata:
                            cell.metadata['tags'] = []
                        # Add hide-input tag if not already present
                        if 'hide-input' not in cell.metadata['tags']:
                            cell.metadata['tags'].append('hide-input')

                notebook.cells.extend(section_nb.cells)
            except Exception as e:
                logger.error(f"Failed to read section {section_id}: {e}")

        # Save compiled notebook
        COMPILED_DIR.mkdir(parents=True, exist_ok=True)
        output_path = COMPILED_DIR / f"{run_ctx['run_id']}_{self.resin_code}.ipynb"
        nbformat.write(notebook, output_path)

        logger.info(f"Assembled notebook: {output_path}")
        return output_path

    def build_parameters(self,
                        simulation_result: Dict[str, Any],
                        design_inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Build papermill parameters from simulation results"""
        # Base parameters available to all reports
        base_params = {
            "simulation": simulation_result,
            "design_inputs": design_inputs,
            "resin_metadata": {
                "code": self.resin_code,
                "display_name": self.display_name,
            },
            "project_root": str(PROJECT_ROOT),
            "artifact_dir": simulation_result.get("artifact_dir", ""),
            "run_id": simulation_result.get("run_id", ""),
        }

        # Add resin-specific parameters
        custom_params = self.parameter_builder(base_params)
        base_params.update(custom_params)

        return base_params


# Global registry for report specifications
REPORT_REGISTRY: Dict[str, ReportSpec] = {}


def register_report(spec: ReportSpec) -> None:
    """Register a report specification"""
    REPORT_REGISTRY[spec.resin_code] = spec
    logger.info(f"Registered report spec for {spec.resin_code}")


def get_report_spec(resin_code: str) -> ReportSpec:
    """Get report specification for a resin type"""
    try:
        return REPORT_REGISTRY[resin_code]
    except KeyError as exc:
        available = list(REPORT_REGISTRY.keys())
        raise ValueError(
            f"No report spec registered for resin '{resin_code}'. "
            f"Available: {available}"
        ) from exc


# ============= SAC Report Specification =============

def _sac_parameters(base_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract SAC-specific parameters"""
    sim = base_payload["simulation"]

    # Check for breakthrough data file
    artifact_dir = Path(base_payload.get("artifact_dir", ""))
    breakthrough_csv = artifact_dir / "breakthrough_curve.csv" if artifact_dir else None

    return {
        # Performance metrics
        "service_volume_bv": safe_extract(sim, "performance.service_bv_to_target", None),
        "service_hours": safe_extract(sim, "performance.service_hours", None),
        "effluent_hardness": safe_extract(sim, "performance.effluent_hardness_mg_l_caco3", None),
        "capacity_utilization": safe_extract(sim, "performance.capacity_utilization_percent", None),

        # Mass balance
        "regenerant_kg_cycle": safe_extract(sim, "mass_balance.regenerant_kg_cycle", None),
        "waste_volume_m3": safe_extract(sim, "mass_balance.waste_m3_cycle", None),
        "hardness_removed_kg": safe_extract(sim, "mass_balance.hardness_removed_kg_caco3", None),

        # Economics (if available)
        "capital_cost_usd": safe_extract(sim, "economics.capital_cost_usd", None),
        "opex_usd_year": safe_extract(sim, "economics.operating_cost_usd_year", None),
        "lcow_usd_m3": safe_extract(sim, "economics.lcow_usd_m3", None),

        # Data paths
        "breakthrough_curve_path": str(breakthrough_csv) if breakthrough_csv and breakthrough_csv.exists() else None,
    }


register_report(ReportSpec(
    resin_code="SAC",
    display_name="Strong Acid Cation (H-form)",
    manifest_name="sac_report",
    parameter_builder=_sac_parameters,
))


# ============= WAC-Na Report Specification =============

def _wac_na_parameters(base_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract WAC-Na specific parameters"""
    sim = base_payload["simulation"]

    # Check for breakthrough data file
    artifact_dir = Path(base_payload.get("artifact_dir", ""))
    breakthrough_csv = artifact_dir / "breakthrough_curve.csv" if artifact_dir else None

    return {
        # Performance metrics
        "service_volume_bv": safe_extract(sim, "performance.service_bv_to_target", None),
        "service_hours": safe_extract(sim, "performance.service_hours", None),
        "effluent_hardness": safe_extract(sim, "performance.effluent_hardness_mg_l_caco3", None),
        "effluent_alkalinity": safe_extract(sim, "performance.effluent_alkalinity_mg_l_caco3", None),
        "capacity_utilization": safe_extract(sim, "performance.capacity_utilization_percent", None),

        # Mass balance
        "regenerant_kg_cycle": safe_extract(sim, "mass_balance.regenerant_kg_cycle", None),
        "waste_volume_m3": safe_extract(sim, "mass_balance.waste_m3_cycle", None),
        "hardness_removed_kg": safe_extract(sim, "mass_balance.hardness_removed_kg_caco3", None),

        # Economics (if available)
        "capital_cost_usd": safe_extract(sim, "economics.capital_cost_usd", None),
        "opex_usd_year": safe_extract(sim, "economics.operating_cost_usd_year", None),
        "lcow_usd_m3": safe_extract(sim, "economics.lcow_usd_m3", None),

        # WAC-specific
        "two_step_regeneration": True,  # WAC-Na uses two-step
        "bed_expansion_percent": 50,    # Na-form expansion

        # Data paths
        "breakthrough_curve_path": str(breakthrough_csv) if breakthrough_csv and breakthrough_csv.exists() else None,
    }


register_report(ReportSpec(
    resin_code="WAC_Na",
    display_name="Weak Acid Cation (Na-form)",
    manifest_name="wac_na_report",
    parameter_builder=_wac_na_parameters,
))


# ============= WAC-H Report Specification =============

def _wac_h_parameters(base_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract WAC-H specific parameters"""
    sim = base_payload["simulation"]

    # Check for breakthrough data file
    artifact_dir = Path(base_payload.get("artifact_dir", ""))
    breakthrough_csv = artifact_dir / "breakthrough_curve.csv" if artifact_dir else None

    return {
        # Performance metrics
        "service_volume_bv": safe_extract(sim, "performance.service_bv_to_target", None),
        "service_hours": safe_extract(sim, "performance.service_hours", None),
        "effluent_hardness": safe_extract(sim, "performance.effluent_hardness_mg_l_caco3", None),
        "effluent_alkalinity": safe_extract(sim, "performance.effluent_alkalinity_mg_l_caco3", None),
        "capacity_utilization": safe_extract(sim, "performance.capacity_utilization_percent", None),

        # Mass balance
        "regenerant_kg_cycle": safe_extract(sim, "mass_balance.regenerant_kg_cycle", None),
        "waste_volume_m3": safe_extract(sim, "mass_balance.waste_m3_cycle", None),
        "hardness_removed_kg": safe_extract(sim, "mass_balance.hardness_removed_kg_caco3", None),

        # Economics (if available)
        "capital_cost_usd": safe_extract(sim, "economics.capital_cost_usd", None),
        "opex_usd_year": safe_extract(sim, "economics.operating_cost_usd_year", None),
        "lcow_usd_m3": safe_extract(sim, "economics.lcow_usd_m3", None),

        # WAC-specific
        "co2_generation": True,         # H-form generates CO2
        "bed_expansion_percent": 100,   # H-form expansion
        "requires_degasser": True,      # Need CO2 removal

        # Data paths
        "breakthrough_curve_path": str(breakthrough_csv) if breakthrough_csv and breakthrough_csv.exists() else None,
    }


register_report(ReportSpec(
    resin_code="WAC_H",
    display_name="Weak Acid Cation (H-form)",
    manifest_name="wac_h_report",
    parameter_builder=_wac_h_parameters,
))


# ============= Report Generation Functions =============

async def generate_ix_report(
    simulation_result: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    design_inputs: Optional[Dict[str, Any]] = None,
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate an IX report from simulation results or artifacts

    Args:
        simulation_result: IXSimulationResult as dict (optional if run_id provided)
        run_id: Run ID to load artifacts from disk (optional if simulation_result provided)
        design_inputs: Original design configuration
        options: Report generation options

    Returns:
        Dict with status and output paths
    """
    try:
        # Load simulation results from artifacts if run_id provided
        if run_id and not simulation_result:
            artifacts_dir = PROJECT_ROOT / "results"
            results_file = artifacts_dir / f"ix_results_{run_id}.json"
            input_file = artifacts_dir / f"ix_input_{run_id}.json"

            if not results_file.exists():
                return {
                    "status": "error",
                    "error": f"Results file not found: {results_file}"
                }

            # Load the simulation results
            with open(results_file, 'r') as f:
                simulation_result = json.load(f)

            # Load design inputs if not provided
            if not design_inputs and input_file.exists():
                with open(input_file, 'r') as f:
                    design_inputs = json.load(f)

        elif not simulation_result:
            return {
                "status": "error",
                "error": "Either simulation_result or run_id must be provided"
            }

        # Extract resin type from simulation or design inputs
        resin_type = simulation_result.get("resin_type")

        if not resin_type and design_inputs:
            # Check design inputs (from ix_input file)
            resin_type = design_inputs.get("resin_type")

        if not resin_type:
            # Try to infer from input if present
            if "input" in simulation_result:
                resin_type = simulation_result["input"].get("resin_type")

        if not resin_type:
            # Default to SAC for backward compatibility
            logger.warning("No resin_type found, defaulting to SAC")
            resin_type = "SAC"

        # Get the appropriate report spec
        spec = get_report_spec(resin_type)

        # Create run context
        run_id = simulation_result.get("run_id", datetime.now().strftime("%Y%m%d_%H%M%S"))
        timestamp = datetime.now().isoformat()

        run_ctx = {
            "run_id": run_id,
            "timestamp": timestamp,
            "resin_type": resin_type,
        }

        # Assemble the notebook
        assembled_nb_path = spec.assemble_notebook(run_ctx)

        # Build parameters
        design_inputs = design_inputs or {}
        parameters = spec.build_parameters(simulation_result, design_inputs)

        # Setup output paths
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_notebook = OUTPUT_DIR / f"{run_id}_{resin_type}_report.ipynb"
        output_html = OUTPUT_DIR / f"{run_id}_{resin_type}_report.html"

        # Execute notebook with papermill
        logger.info(f"Executing notebook with {len(parameters)} parameters")

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()

        def execute_notebook():
            return pm.execute_notebook(
                str(assembled_nb_path),
                str(output_notebook),
                parameters=parameters,
                kernel_name='python3',
                log_output=False,
                report_mode=True  # Continue on cell errors
            )

        await loop.run_in_executor(None, execute_notebook)
        logger.info(f"Notebook executed: {output_notebook}")

        # Convert to HTML
        html_path = await convert_to_html(output_notebook, output_html)

        return {
            "status": "success",
            "resin_type": resin_type,
            "report_type": spec.display_name,
            "outputs": {
                "notebook": str(output_notebook),
                "html": str(html_path) if html_path else None,
                "assembled_template": str(assembled_nb_path),
            },
            "run_id": run_id,
            "timestamp": timestamp,
        }

    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "details": "Failed to generate IX report"
        }


async def convert_to_html(notebook_path: Path, html_path: Path) -> Optional[Path]:
    """Convert notebook to HTML with proper formatting"""
    try:
        with open(notebook_path, 'r', encoding='utf-8') as f:
            nb = nbformat.read(f, as_version=4)

        # Configure HTML exporter with proper settings to hide code
        html_exporter = HTMLExporter(
            exclude_input=True,  # Hide all code inputs
            exclude_input_prompt=True,
            exclude_output_prompt=True,
            template_name='lab'  # Modern template
        )

        # Configure preprocessors to remove tagged cells
        from nbconvert.preprocessors import TagRemovePreprocessor
        tag_remover = TagRemovePreprocessor(
            remove_input_tags={'hide-input', 'hide-cell', 'parameters'},
            remove_all_outputs_tags={'hide-output'},
            remove_cell_tags={'hide-cell', 'parameters'}
        )

        # Process notebook to remove tagged cells/inputs
        nb, _ = tag_remover.preprocess(nb, {})

        # Convert to HTML
        (body, resources) = html_exporter.from_notebook_node(nb)

        # Add custom CSS for professional styling and left-aligned equations
        custom_css = """
<style>
    .jp-RenderedHTMLCommon table {
        border-collapse: collapse;
        margin: 20px 0;
    }
    .jp-RenderedHTMLCommon th, .jp-RenderedHTMLCommon td {
        border: 1px solid #ddd;
        padding: 8px;
        text-align: left;
    }
    .jp-RenderedHTMLCommon th {
        background-color: #f2f2f2;
    }
    /* Left-align all math displays */
    .MathJax_Display {
        text-align: left !important;
        margin: 1em 0 !important;
    }
    /* Override any centered math */
    .jp-OutputArea-output .MathJax_Display {
        text-align: left !important;
    }
    /* Ensure consistent left alignment */
    mjx-container[jax="CHTML"][display="true"] {
        text-align: left !important;
    }
    /* For KaTeX if used */
    .katex-display {
        text-align: left !important;
    }
</style>
"""
        body = body.replace('</head>', custom_css + '</head>')

        # Write HTML file
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(body)

        logger.info(f"Converted to HTML: {html_path}")
        return html_path

    except Exception as e:
        logger.error(f"HTML conversion failed: {e}")
        return None


# ============= Utility Functions =============

def list_available_reports() -> List[str]:
    """List all registered report types"""
    return list(REPORT_REGISTRY.keys())


def validate_manifest(manifest_name: str) -> bool:
    """Validate that a manifest file exists and is valid"""
    manifest_path = MANIFESTS_DIR / f"{manifest_name}.yml"
    if not manifest_path.exists():
        return False

    try:
        with manifest_path.open("r") as f:
            manifest = yaml.safe_load(f)
        return "sections" in manifest and isinstance(manifest["sections"], list)
    except Exception:
        return False