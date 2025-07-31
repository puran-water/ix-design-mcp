"""
Notebook Runner Tool

Executes parameterized Jupyter notebooks for analysis workflows.
Uses papermill for execution and nbconvert for HTML generation.
"""

import json
import logging
import os
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import sys

try:
    import papermill as pm
    import nbformat
    from nbconvert import HTMLExporter
except ImportError as e:
    raise ImportError(
        "Required packages not installed. Install with: "
        "pip install papermill nbformat nbconvert"
    ) from e

# Configure logging with UTF-8 encoding for Windows
logger = logging.getLogger(__name__)

# Set UTF-8 as default encoding if on Windows
if sys.platform == 'win32':
    import locale
    if hasattr(locale, 'getpreferredencoding'):
        # Override the preferred encoding
        def getpreferredencoding(do_setlocale=True):
            return 'utf-8'
        locale.getpreferredencoding = getpreferredencoding


def get_project_root() -> Path:
    """
    Determine project root with multiple fallback strategies.
    
    Returns absolute path to project root directory.
    """
    # Strategy 1: Environment variable (most reliable for MCP clients)
    if 'IX_DESIGN_MCP_ROOT' in os.environ:
        root = Path(os.environ['IX_DESIGN_MCP_ROOT'])
        if root.exists():
            logger.info(f"Using project root from IX_DESIGN_MCP_ROOT: {root}")
            return root
        else:
            logger.warning(f"IX_DESIGN_MCP_ROOT points to non-existent path: {root}")
    
    # Strategy 2: Relative to this file (fallback)
    # Use resolve() to get absolute path first
    root = Path(__file__).resolve().parent.parent
    logger.info(f"Using project root relative to notebook_runner.py: {root}")
    return root


# Get project root once at module level
project_root = get_project_root()


async def run_sac_notebook_analysis_impl(analysis_input: str) -> Dict[str, Any]:
    """
    Execute SAC analysis notebook with parameters and return results.
    
    This function:
    1. Parses input parameters
    2. Executes notebook with papermill
    3. Extracts results from executed notebook
    4. Converts to HTML for viewing
    5. Returns MCP-compliant response
    """
    try:
        # Parse input parameters
        if isinstance(analysis_input, str):
            params = json.loads(analysis_input)
        else:
            params = analysis_input
        
        # Setup paths
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_dir = project_root / "output" / "notebooks"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Notebook paths
        template_notebook = project_root / "notebooks" / "sac_breakthrough_analysis.ipynb"
        output_notebook = output_dir / f"sac_analysis_{timestamp}.ipynb"
        output_html = output_dir / f"sac_analysis_{timestamp}.html"
        
        # Verify template exists
        if not template_notebook.exists():
            return {
                'status': 'error',
                'error': f'Template notebook not found: {template_notebook}',
                'details': 'Please ensure sac_breakthrough_analysis.ipynb exists in notebooks/'
            }
        
        # Add project root to parameters for robust path handling
        params['project_root_str'] = str(project_root)
        
        logger.info(f"Executing notebook with parameters: {list(params.keys())}")
        
        # Execute notebook with papermill
        # Run in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        
        def execute_notebook():
            # Set UTF-8 encoding for Windows to handle Unicode characters
            import sys
            if sys.platform == 'win32':
                os.environ['PYTHONIOENCODING'] = 'utf-8'
            return pm.execute_notebook(
                str(template_notebook),
                str(output_notebook),
                parameters=params,
                kernel_name='python3',
                log_output=False,  # Disable logging to stdout for MCP protocol compliance
                report_mode=True  # Continue execution even if cells fail
            )
        
        try:
            await loop.run_in_executor(None, execute_notebook)
            logger.info(f"Notebook executed successfully: {output_notebook}")
        except Exception as e:
            logger.error(f"Notebook execution failed: {e}")
            # Still try to extract partial results
        
        # Extract results from executed notebook
        notebook_results = await extract_notebook_results(output_notebook)
        
        # Convert to HTML
        html_path = await convert_notebook_to_html(output_notebook, output_html)
        
        # Prepare response
        response = {
            'status': notebook_results.get('status', 'success'),
            'breakthrough_bv': notebook_results.get('breakthrough_bv'),
            'service_time_hours': notebook_results.get('service_time_hours'),
            'total_cycle_time_hours': notebook_results.get('total_cycle_time_hours'),
            'capacity_factor': notebook_results.get('capacity_factor'),
            'final_recovery': notebook_results.get('final_recovery'),
            'regenerant_kg': notebook_results.get('regenerant_kg'),
            'outputs': {
                'notebook_path': str(output_notebook),
                'html_path': str(html_path) if html_path else None
            },
            'warnings': notebook_results.get('warnings', [])
        }
        
        logger.info(f"Analysis complete. Results: BV={response['breakthrough_bv']}, Recovery={response['final_recovery']}")
        
        return response
        
    except Exception as e:
        logger.error(f"Notebook analysis failed: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'details': 'Failed to run SAC notebook analysis'
        }


async def extract_notebook_results(notebook_path: Path) -> Dict[str, Any]:
    """Extract results from executed notebook."""
    try:
        # Read the executed notebook
        with open(notebook_path, 'r', encoding='utf-8') as f:
            nb = nbformat.read(f, as_version=4)
        
        results = {}
        
        # Look for the results cell
        for cell in nb.cells:
            if cell.cell_type == 'code' and 'notebook_results' in cell.source:
                # Check outputs for the results
                for output in cell.get('outputs', []):
                    if output.output_type == 'stream' and 'Results stored' in output.text:
                        # Extract JSON from output
                        text = output.text
                        start = text.find('{')
                        end = text.rfind('}') + 1
                        if start >= 0 and end > start:
                            json_str = text[start:end]
                            try:
                                results = json.loads(json_str)
                                logger.info(f"Extracted results: {list(results.keys())}")
                            except json.JSONDecodeError:
                                logger.warning("Could not parse results JSON")
                
                # Also try to execute the cell source to get results
                if not results and 'notebook_results_json' in cell.source:
                    # Create a namespace for execution
                    namespace = {}
                    try:
                        # Execute just the notebook_results assignment
                        lines = cell.source.split('\n')
                        for line in lines:
                            if 'notebook_results = {' in line:
                                # Find the complete dict definition
                                dict_start = cell.source.find('notebook_results = {')
                                dict_end = cell.source.find('}\n', dict_start) + 1
                                if dict_start >= 0 and dict_end > dict_start:
                                    dict_code = cell.source[dict_start:dict_end]
                                    exec(dict_code, namespace)
                                    results = namespace.get('notebook_results', {})
                                    break
                    except Exception as e:
                        logger.warning(f"Could not execute results extraction: {e}")
        
        # Add any warnings from failed cells
        warnings = []
        for i, cell in enumerate(nb.cells):
            if cell.cell_type == 'code':
                for output in cell.get('outputs', []):
                    if output.output_type == 'error':
                        warnings.append(f"Cell {i}: {output.ename}: {output.evalue}")
        
        if warnings:
            results['warnings'] = warnings
        
        return results
        
    except Exception as e:
        logger.error(f"Failed to extract notebook results: {e}")
        return {'status': 'error', 'error': str(e)}


async def convert_notebook_to_html(notebook_path: Path, html_path: Path) -> Optional[Path]:
    """Convert notebook to HTML for viewing."""
    try:
        # Method 1: Use nbconvert Python API
        with open(notebook_path, 'r', encoding='utf-8') as f:
            nb = nbformat.read(f, as_version=4)
        
        # Create HTML exporter
        html_exporter = HTMLExporter()
        html_exporter.template_name = 'lab'  # Use JupyterLab template
        
        # Convert notebook to HTML
        (body, resources) = html_exporter.from_notebook_node(nb)
        
        # Write HTML file
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(body)
        
        logger.info(f"Converted notebook to HTML: {html_path}")
        return html_path
        
    except Exception as e:
        logger.warning(f"HTML conversion via API failed: {e}")
        
        # Method 2: Try command line nbconvert
        try:
            loop = asyncio.get_event_loop()
            
            def run_nbconvert():
                import subprocess
                result = subprocess.run(
                    ['jupyter', 'nbconvert', '--to', 'html', str(notebook_path), '--output', str(html_path)],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    raise RuntimeError(f"nbconvert failed: {result.stderr}")
            
            await loop.run_in_executor(None, run_nbconvert)
            logger.info(f"Converted notebook to HTML via CLI: {html_path}")
            return html_path
            
        except Exception as e2:
            logger.error(f"HTML conversion via CLI also failed: {e2}")
            return None


def create_notebook_from_template(
    template_name: str,
    parameters: Dict[str, Any],
    output_path: Path
) -> Path:
    """
    Create a new notebook from a template with given parameters.
    
    This is useful for creating custom analysis notebooks on the fly.
    """
    template_path = project_root / "notebooks" / f"{template_name}.ipynb"
    
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    # Execute with papermill
    pm.execute_notebook(
        str(template_path),
        str(output_path),
        parameters=parameters
    )
    
    return output_path