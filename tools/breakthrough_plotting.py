"""
Breakthrough Curve Plotting Tool

Generates visualizations from ion exchange simulation results.
Separated from simulation logic to avoid heavy imports unless needed.
"""

import logging
from pathlib import Path
from typing import Dict, List, Literal, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BreakthroughPlotInput(BaseModel):
    """Input for breakthrough curve plotting"""
    # Raw breakthrough data from simulation
    breakthrough_data: Dict[str, List[float]] = Field(
        ..., 
        description="Must contain: bed_volumes, ca_pct, mg_pct, na_mg_l, hardness_mg_l"
    )
    
    # Water composition for reference lines
    feed_na_mg_l: float = Field(..., description="Feed sodium concentration for reference")
    
    # Target for breakthrough indication
    target_hardness_mg_l: float = Field(..., description="Target hardness for breakthrough line")
    
    # Output format
    output_format: Literal['png', 'html', 'csv'] = Field('html', description="Output format")
    
    # Optional metadata for plot title
    simulation_date: Optional[str] = None
    vessel_id: Optional[str] = None


class BreakthroughPlotOutput(BaseModel):
    """Output from breakthrough plotting"""
    status: str
    output_path: str
    output_format: str
    file_size_kb: Optional[float] = None
    
    
def generate_png_plot(
    data: Dict[str, List[float]], 
    feed_na: float,
    target_hardness: float,
    output_dir: Path,
    metadata: Dict[str, Any]
) -> str:
    """Generate static PNG breakthrough curves using matplotlib."""
    # Lazy import matplotlib only when PNG is requested
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    
    # Extract data
    bv = data['bed_volumes']
    ca_pct = data['ca_pct']
    mg_pct = data['mg_pct']
    na_mg_l = data['na_mg_l']
    hardness = data['hardness_mg_l']
    
    # Create figure with subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 10))
    
    # Plot 1: Ca and Mg breakthrough curves with hardness
    ax1.plot(bv, ca_pct, 'b-', linewidth=2, label='Ca²⁺')
    ax1.plot(bv, mg_pct, 'g-', linewidth=2, label='Mg²⁺')
    
    # Plot total hardness on secondary y-axis
    ax1_twin = ax1.twinx()
    ax1_twin.plot(bv, hardness, 'k-', linewidth=2, label='Total Hardness')
    ax1_twin.axhline(
        y=target_hardness,
        color='red',
        linestyle='--',
        linewidth=2,
        label=f'Target Hardness ({target_hardness} mg/L CaCO₃)'
    )
    ax1_twin.set_ylabel('Hardness (mg/L as CaCO₃)')
    ax1_twin.legend(loc='upper right')
    
    ax1.axhline(y=100, color='gray', linestyle=':', alpha=0.3)
    ax1.set_xlabel('Bed Volumes (BV)')
    ax1.set_ylabel('Effluent Concentration (% of Feed)')
    ax1.set_title('Hardness Breakthrough Curves')
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper left')
    ax1.set_xlim(0, max(bv))
    
    # Dynamic Y-axis to accommodate Mg spike
    max_conc = max(max(ca_pct), max(mg_pct))
    ax1.set_ylim(0, max(120, max_conc * 1.1))
    
    # Plot 2: Na release curve
    ax2.plot(bv, na_mg_l, 'orange', linewidth=2, label='Na⁺')
    ax2.axhline(y=feed_na, 
                color='r', linestyle='--', alpha=0.5, 
                label=f'Feed Na⁺ ({feed_na:.0f} mg/L)')
    ax2.set_xlabel('Bed Volumes (BV)')
    ax2.set_ylabel('Na⁺ Concentration (mg/L)')
    ax2.set_title('Sodium Release Curve')
    ax2.grid(True, alpha=0.3)
    ax2.legend()
    ax2.set_xlim(0, max(bv))
    
    # Add title with metadata
    title = f"Ion Exchange Breakthrough Curves - {metadata.get('date', datetime.now().strftime('%Y-%m-%d'))}"
    if metadata.get('vessel_id'):
        title += f" - {metadata['vessel_id']}"
    fig.suptitle(title, fontsize=14)
    
    plt.tight_layout()
    
    # Save plot
    filename = f"breakthrough_curves_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    plot_path = output_dir / filename
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    return str(plot_path)


def generate_html_plot(
    data: Dict[str, List[float]], 
    feed_na: float,
    target_hardness: float,
    output_dir: Path,
    metadata: Dict[str, Any]
) -> str:
    """Generate interactive HTML breakthrough curves using Plotly."""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        raise ImportError("Plotly not installed. Install with: pip install plotly")
    
    # Create subplots
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=('Hardness Breakthrough Curves', 'Sodium Release Curve'),
        row_heights=[0.6, 0.4],
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]]
    )
    
    # Extract data
    bv = data['bed_volumes']
    ca_pct = data['ca_pct']
    mg_pct = data['mg_pct']
    na_mg_l = data['na_mg_l']
    hardness = data['hardness_mg_l']
    
    # Plot 1: Ca and Mg breakthrough curves
    fig.add_trace(
        go.Scatter(x=bv, y=ca_pct, mode='lines', 
                  name='Ca²⁺', line=dict(color='blue', width=2)),
        row=1, col=1, secondary_y=False
    )
    fig.add_trace(
        go.Scatter(x=bv, y=mg_pct, mode='lines',
                  name='Mg²⁺', line=dict(color='green', width=2)),
        row=1, col=1, secondary_y=False
    )
    
    # Add total hardness on secondary y-axis
    fig.add_trace(
        go.Scatter(x=bv, y=hardness, mode='lines',
                  name='Total Hardness', line=dict(color='black', width=2)),
        row=1, col=1, secondary_y=True
    )
    
    # Add target hardness line
    fig.add_hline(y=target_hardness, line_dash="dash", line_color="red",
                 annotation_text=f"Target Hardness ({target_hardness} mg/L CaCO₃)",
                 row=1, col=1, secondary_y=True)
    
    # Plot 2: Na release curve
    fig.add_trace(
        go.Scatter(x=bv, y=na_mg_l, mode='lines',
                  name='Na⁺', line=dict(color='orange', width=2)),
        row=2, col=1
    )
    fig.add_hline(y=feed_na, line_dash="dash", line_color="red",
                 annotation_text=f"Feed Na⁺ ({feed_na:.0f} mg/L)",
                 row=2, col=1)
    
    # Update layout
    fig.update_xaxes(title_text="Bed Volumes (BV)", row=2, col=1)
    fig.update_yaxes(title_text="Effluent Concentration (% of Feed)", row=1, col=1)
    fig.update_yaxes(title_text="Hardness (mg/L as CaCO₃)", row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="Na⁺ Concentration (mg/L)", row=2, col=1)
    
    # Add title with metadata
    title = f"Ion Exchange Breakthrough Curves - {metadata.get('date', datetime.now().strftime('%Y-%m-%d %H:%M'))}"
    if metadata.get('vessel_id'):
        title += f" - {metadata['vessel_id']}"
    
    fig.update_layout(
        height=800,
        showlegend=True,
        title_text=title,
        hovermode='x unified'
    )
    
    # Save HTML
    filename = f"breakthrough_curves_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    plot_path = output_dir / filename
    fig.write_html(plot_path, include_plotlyjs='cdn')  # Use CDN for smaller file size
    
    return str(plot_path)


def export_csv(
    data: Dict[str, List[float]], 
    feed_na: float,
    target_hardness: float,
    output_dir: Path,
    metadata: Dict[str, Any]
) -> str:
    """Export breakthrough data to CSV for external analysis."""
    try:
        import pandas as pd
        
        # Create dataframe with all data
        df = pd.DataFrame(data)
        
        # Add metadata columns
        df['target_hardness'] = target_hardness
        df['feed_na_mg_l'] = feed_na
        
        # Save to CSV
        filename = f"breakthrough_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        csv_path = output_dir / filename
        df.to_csv(csv_path, index=False)
        
    except ImportError:
        # Fallback to manual CSV writing
        filename = f"breakthrough_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        csv_path = output_dir / filename
        
        with open(csv_path, 'w') as f:
            # Header
            f.write("bed_volumes,ca_pct,mg_pct,na_mg_l,hardness_mg_l,target_hardness,feed_na_mg_l\n")
            
            # Data rows
            for i in range(len(data['bed_volumes'])):
                f.write(f"{data['bed_volumes'][i]:.3f},"
                       f"{data['ca_pct'][i]:.3f},"
                       f"{data['mg_pct'][i]:.3f},"
                       f"{data['na_mg_l'][i]:.3f},"
                       f"{data['hardness_mg_l'][i]:.3f},"
                       f"{target_hardness},"
                       f"{feed_na}\n")
    
    return str(csv_path)


def plot_breakthrough_curves(input_data: BreakthroughPlotInput) -> BreakthroughPlotOutput:
    """
    Generate breakthrough curve visualizations from simulation data.
    
    This is the main entry point for the plotting tool.
    """
    # Set up output directory
    output_dir = Path("output") / "plots"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Prepare metadata
    metadata = {
        'date': input_data.simulation_date or datetime.now().strftime('%Y-%m-%d %H:%M'),
        'vessel_id': input_data.vessel_id
    }
    
    try:
        # Generate plot based on requested format
        if input_data.output_format == 'png':
            logger.info("Generating PNG breakthrough curves")
            output_path = generate_png_plot(
                input_data.breakthrough_data,
                input_data.feed_na_mg_l,
                input_data.target_hardness_mg_l,
                output_dir,
                metadata
            )
        
        elif input_data.output_format == 'html':
            logger.info("Generating interactive HTML breakthrough curves")
            output_path = generate_html_plot(
                input_data.breakthrough_data,
                input_data.feed_na_mg_l,
                input_data.target_hardness_mg_l,
                output_dir,
                metadata
            )
        
        elif input_data.output_format == 'csv':
            logger.info("Exporting breakthrough data to CSV")
            output_path = export_csv(
                input_data.breakthrough_data,
                input_data.feed_na_mg_l,
                input_data.target_hardness_mg_l,
                output_dir,
                metadata
            )
        
        else:
            raise ValueError(f"Unknown output format: {input_data.output_format}")
        
        # Get file size
        file_size_kb = Path(output_path).stat().st_size / 1024
        
        logger.info(f"Successfully generated {input_data.output_format} at {output_path}")
        
        return BreakthroughPlotOutput(
            status="success",
            output_path=output_path,
            output_format=input_data.output_format,
            file_size_kb=round(file_size_kb, 2)
        )
        
    except Exception as e:
        logger.error(f"Failed to generate plot: {e}")
        return BreakthroughPlotOutput(
            status="error",
            output_path="",
            output_format=input_data.output_format,
            file_size_kb=None
        )