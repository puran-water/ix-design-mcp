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
    breakthrough_data: Dict[str, Any] = Field(
        ..., 
        description="Must contain: bed_volumes, ca_pct, mg_pct, na_mg_l, hardness_mg_l. For multi-phase, also includes: phases, na_fraction, tds_mg_l"
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
    
    # Multi-phase plotting options
    plot_regeneration: bool = Field(False, description="Plot full cycle with regeneration phases")
    regeneration_config: Optional[Dict[str, Any]] = Field(None, description="Regeneration configuration for phase labels")


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


def generate_multiphase_plot(
    data: Dict[str, Any], 
    feed_na: float,
    target_hardness: float,
    output_dir: Path,
    metadata: Dict[str, Any],
    output_format: str = 'html'
) -> str:
    """Generate multi-phase breakthrough curves with regeneration visualization."""
    if output_format == 'html':
        return _generate_multiphase_html(data, feed_na, target_hardness, output_dir, metadata)
    else:
        return _generate_multiphase_png(data, feed_na, target_hardness, output_dir, metadata)


def _generate_multiphase_html(
    data: Dict[str, Any], 
    feed_na: float,
    target_hardness: float,
    output_dir: Path,
    metadata: Dict[str, Any]
) -> str:
    """Generate interactive HTML multi-phase plot using Plotly."""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        raise ImportError("Plotly not installed. Install with: pip install plotly")
    
    # Create subplots with 3 rows for complete cycle visualization
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=(
            'Ion Exchange: Ca²⁺/Mg²⁺ Breakthrough and Hardness',
            'Na⁺ Release and Resin Recovery',
            'TDS and Phase Indicators'
        ),
        row_heights=[0.4, 0.3, 0.3],
        specs=[[{"secondary_y": True}], [{"secondary_y": True}], [{"secondary_y": False}]]
    )
    
    # Extract data
    bv = data['bed_volumes']
    phases = data.get('phases', ['SERVICE'] * len(bv))
    ca_mg_l = data.get('ca_mg_l', data.get('ca_pct', []))
    mg_mg_l = data.get('mg_mg_l', data.get('mg_pct', []))
    na_mg_l = data['na_mg_l']
    hardness = data['hardness_mg_l']
    na_fraction = data.get('na_fraction', [])
    tds = data.get('tds_mg_l', [])
    
    # Plot 1: Ca/Mg breakthrough with hardness
    fig.add_trace(
        go.Scatter(x=bv, y=ca_mg_l, mode='lines', name='Ca²⁺',
                  line=dict(color='blue', width=2)),
        row=1, col=1, secondary_y=False
    )
    fig.add_trace(
        go.Scatter(x=bv, y=mg_mg_l, mode='lines', name='Mg²⁺',
                  line=dict(color='green', width=2)),
        row=1, col=1, secondary_y=False
    )
    
    # Hardness on secondary y-axis
    fig.add_trace(
        go.Scatter(x=bv, y=hardness, mode='lines', name='Total Hardness',
                  line=dict(color='black', width=2)),
        row=1, col=1, secondary_y=True
    )
    
    # Target hardness line
    fig.add_hline(y=target_hardness, line_dash="dash", line_color="red",
                  annotation_text=f"Target: {target_hardness} mg/L",
                  row=1, col=1, secondary_y=True)
    
    # Plot 2: Na release and resin recovery
    fig.add_trace(
        go.Scatter(x=bv, y=na_mg_l, mode='lines', name='Na⁺',
                  line=dict(color='orange', width=2)),
        row=2, col=1, secondary_y=False
    )
    
    if na_fraction:
        fig.add_trace(
            go.Scatter(x=bv, y=[f*100 for f in na_fraction], mode='lines',
                      name='Na+ Sites (%)', line=dict(color='purple', width=2)),
            row=2, col=1, secondary_y=True
        )
    
    # Plot 3: TDS and phase indicators
    if tds:
        fig.add_trace(
            go.Scatter(x=bv, y=tds, mode='lines', name='TDS',
                      line=dict(color='brown', width=2)),
            row=3, col=1
        )
    
    # Add phase boundaries
    phase_colors = {
        'SERVICE': 'lightblue',
        'BACKWASH': 'lightgray',
        'REGENERATION': 'lightcoral',
        'SLOW_RINSE': 'lightyellow',
        'FAST_RINSE': 'lightgreen'
    }
    
    current_phase = phases[0]
    phase_start = bv[0]
    
    for i in range(1, len(phases)):
        if phases[i] != current_phase:
            # Add vertical shaded region for the phase
            for row in [1, 2, 3]:
                fig.add_vrect(
                    x0=phase_start, x1=bv[i-1],
                    fillcolor=phase_colors.get(current_phase, 'white'),
                    opacity=0.2, layer="below", line_width=0,
                    row=row, col=1
                )
            phase_start = bv[i-1]
            current_phase = phases[i]
    
    # Add last phase
    for row in [1, 2, 3]:
        fig.add_vrect(
            x0=phase_start, x1=bv[-1],
            fillcolor=phase_colors.get(current_phase, 'white'),
            opacity=0.2, layer="below", line_width=0,
            row=row, col=1
        )
    
    # Update layout
    fig.update_xaxes(title_text="Bed Volumes", row=3, col=1)
    fig.update_yaxes(title_text="Concentration (mg/L)", row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="Hardness (mg/L CaCO₃)", row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="Na⁺ (mg/L)", row=2, col=1, secondary_y=False)
    fig.update_yaxes(title_text="Na⁺ Sites (%)", row=2, col=1, secondary_y=True)
    fig.update_yaxes(title_text="TDS (mg/L)", row=3, col=1)
    
    title = "Ion Exchange Full Cycle: Service → Regeneration → Rinse"
    if metadata.get('vessel_id'):
        title += f" - {metadata['vessel_id']}"
    
    fig.update_layout(
        title=title,
        showlegend=True,
        height=1000,
        hovermode='x unified'
    )
    
    # Save HTML
    filename = f"multiphase_breakthrough_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    plot_path = output_dir / filename
    fig.write_html(plot_path, include_plotlyjs='cdn')
    
    return str(plot_path)


def _generate_multiphase_png(
    data: Dict[str, Any], 
    feed_na: float,
    target_hardness: float,
    output_dir: Path,
    metadata: Dict[str, Any]
) -> str:
    """Generate static PNG multi-phase plot using matplotlib."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    
    # Extract data
    bv = data['bed_volumes']
    phases = data.get('phases', ['SERVICE'] * len(bv))
    ca_mg_l = data.get('ca_mg_l', data.get('ca_pct', []))
    mg_mg_l = data.get('mg_mg_l', data.get('mg_pct', []))
    na_mg_l = data['na_mg_l']
    hardness = data['hardness_mg_l']
    na_fraction = data.get('na_fraction', [])
    tds = data.get('tds_mg_l', [])
    
    # Create figure with subplots
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 12))
    
    # Plot 1: Ca/Mg with hardness
    ax1.plot(bv, ca_mg_l, 'b-', linewidth=2, label='Ca²⁺')
    ax1.plot(bv, mg_mg_l, 'g-', linewidth=2, label='Mg²⁺')
    ax1.set_ylabel('Ion Concentration (mg/L)')
    ax1.legend(loc='upper left')
    
    ax1_twin = ax1.twinx()
    ax1_twin.plot(bv, hardness, 'k-', linewidth=2, label='Total Hardness')
    ax1_twin.axhline(y=target_hardness, color='red', linestyle='--',
                     linewidth=2, label=f'Target ({target_hardness} mg/L)')
    ax1_twin.set_ylabel('Hardness (mg/L as CaCO₃)')
    ax1_twin.legend(loc='upper right')
    ax1.set_title('Ion Exchange Full Cycle')
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Na release and recovery
    ax2.plot(bv, na_mg_l, 'orange', linewidth=2, label='Na⁺')
    ax2.set_ylabel('Na⁺ (mg/L)')
    ax2.legend(loc='upper left')
    
    if na_fraction:
        ax2_twin = ax2.twinx()
        ax2_twin.plot(bv, [f*100 for f in na_fraction], 'purple',
                     linewidth=2, label='Na⁺ Sites (%)')
        ax2_twin.set_ylabel('Na⁺ Sites (%)')
        ax2_twin.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: TDS
    if tds:
        ax3.plot(bv, tds, 'brown', linewidth=2, label='TDS')
        ax3.set_ylabel('TDS (mg/L)')
        ax3.legend(loc='upper left')
    ax3.set_xlabel('Bed Volumes (BV)')
    ax3.grid(True, alpha=0.3)
    
    # Add phase shading to all plots
    phase_colors = {
        'SERVICE': 'lightblue',
        'BACKWASH': 'lightgray',
        'REGENERATION': 'lightcoral',
        'SLOW_RINSE': 'lightyellow',
        'FAST_RINSE': 'lightgreen'
    }
    
    for ax in [ax1, ax2, ax3]:
        current_phase = phases[0]
        phase_start = bv[0]
        
        for i in range(1, len(phases)):
            if phases[i] != current_phase:
                ax.axvspan(phase_start, bv[i-1],
                          color=phase_colors.get(current_phase, 'white'),
                          alpha=0.3, label=current_phase)
                phase_start = bv[i-1]
                current_phase = phases[i]
        
        # Add last phase
        ax.axvspan(phase_start, bv[-1],
                  color=phase_colors.get(current_phase, 'white'),
                  alpha=0.3, label=current_phase)
    
    # Add phase legend
    phase_patches = [mpatches.Patch(color=color, alpha=0.3, label=phase)
                    for phase, color in phase_colors.items()]
    ax3.legend(handles=phase_patches, loc='upper center',
              bbox_to_anchor=(0.5, -0.1), ncol=5)
    
    plt.tight_layout()
    
    # Save plot
    filename = f"multiphase_breakthrough_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    plot_path = output_dir / filename
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    return str(plot_path)


def generate_cycle_plots(
    breakthrough_data: Dict[str, Any],
    water_analysis: Any,  # Can be SACWaterComposition or dict
    target_hardness: float
) -> Dict[str, Any]:
    """
    Generate all plots for a cycle, handling unit conversions internally.
    
    This function is designed to work within Jupyter notebooks and returns
    plot objects rather than saving files.
    """
    # Handle both object and dict inputs for water_analysis
    if hasattr(water_analysis, 'ca_mg_l'):
        ca_feed = water_analysis.ca_mg_l
        mg_feed = water_analysis.mg_mg_l  
        na_feed = water_analysis.na_mg_l
    else:
        ca_feed = water_analysis['ca_mg_l']
        mg_feed = water_analysis['mg_mg_l']
        na_feed = water_analysis['na_mg_l']
    
    # Convert mg/L to percentages if needed
    if 'ca_pct' not in breakthrough_data and 'ca_mg_l' in breakthrough_data:
        breakthrough_data['ca_pct'] = [
            (ca / ca_feed * 100) if ca_feed > 0 else 0
            for ca in breakthrough_data['ca_mg_l']
        ]
        breakthrough_data['mg_pct'] = [
            (mg / mg_feed * 100) if mg_feed > 0 else 0
            for mg in breakthrough_data['mg_mg_l']
        ]
        logger.info(f"Converted mg/L to percentages. Ca feed: {ca_feed} mg/L, Mg feed: {mg_feed} mg/L")
    
    plots = {}
    
    # Check if this is a multi-phase dataset
    if 'phases' in breakthrough_data:
        # Generate multi-phase plot using existing function
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
            
            fig = _create_multiphase_plotly_figure(
                breakthrough_data, na_feed, target_hardness
            )
            plots['full_cycle'] = fig
            logger.info("Generated full cycle plot with regeneration phases")
        except ImportError:
            logger.warning("Plotly not available, skipping full cycle plot")
    
    # Also generate service-only plot for the service phase
    try:
        import plotly.graph_objects as go
        
        # Extract service phase data
        service_indices = [
            i for i, phase in enumerate(breakthrough_data.get('phases', ['SERVICE'] * len(breakthrough_data['bed_volumes'])))
            if phase == 'SERVICE'
        ] if 'phases' in breakthrough_data else range(len(breakthrough_data['bed_volumes']))
        
        if service_indices:
            service_data = {
                'bed_volumes': [breakthrough_data['bed_volumes'][i] for i in service_indices],
                'ca_pct': [breakthrough_data['ca_pct'][i] for i in service_indices],
                'mg_pct': [breakthrough_data['mg_pct'][i] for i in service_indices],
                'na_mg_l': [breakthrough_data['na_mg_l'][i] for i in service_indices],
                'hardness_mg_l': [breakthrough_data['hardness_mg_l'][i] for i in service_indices]
            }
            
            fig_service = _create_service_plotly_figure(
                service_data, na_feed, target_hardness
            )
            plots['service_breakthrough'] = fig_service
            logger.info("Generated service breakthrough plot")
    except ImportError:
        logger.warning("Plotly not available for interactive plots")
    
    return plots


def _create_service_plotly_figure(data: Dict[str, List[float]], feed_na: float, target_hardness: float):
    """Create service-only breakthrough plot using Plotly."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    
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
    
    fig.update_layout(
        height=800,
        showlegend=True,
        title_text="SAC Ion Exchange Service Breakthrough",
        hovermode='x unified'
    )
    
    return fig


def _create_multiphase_plotly_figure(data: Dict[str, Any], feed_na: float, target_hardness: float):
    """Create multi-phase plot using Plotly - reuse existing logic."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    
    # Create subplots with 3 rows for complete cycle visualization
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=(
            'Ion Exchange: Ca²⁺/Mg²⁺ Breakthrough and Hardness',
            'Na⁺ Release and Resin Recovery',
            'TDS and Phase Indicators'
        ),
        row_heights=[0.4, 0.3, 0.3],
        specs=[[{"secondary_y": True}], [{"secondary_y": True}], [{"secondary_y": False}]]
    )
    
    # Extract data - handle both percentage and mg/L formats
    bv = data['bed_volumes']
    phases = data.get('phases', ['SERVICE'] * len(bv))
    
    # Use percentages if available, otherwise use mg/L directly
    ca_data = data.get('ca_pct', data.get('ca_mg_l', []))
    mg_data = data.get('mg_pct', data.get('mg_mg_l', []))
    ca_label = 'Ca²⁺ (%)' if 'ca_pct' in data else 'Ca²⁺ (mg/L)'
    mg_label = 'Mg²⁺ (%)' if 'mg_pct' in data else 'Mg²⁺ (mg/L)'
    
    na_mg_l = data['na_mg_l']
    hardness = data['hardness_mg_l']
    na_fraction = data.get('na_fraction', [])
    tds = data.get('tds_mg_l', [])
    
    # Plot 1: Ca/Mg breakthrough with hardness
    fig.add_trace(
        go.Scatter(x=bv, y=ca_data, mode='lines', name=ca_label,
                  line=dict(color='blue', width=2)),
        row=1, col=1, secondary_y=False
    )
    fig.add_trace(
        go.Scatter(x=bv, y=mg_data, mode='lines', name=mg_label,
                  line=dict(color='green', width=2)),
        row=1, col=1, secondary_y=False
    )
    
    # Hardness on secondary y-axis
    fig.add_trace(
        go.Scatter(x=bv, y=hardness, mode='lines', name='Total Hardness',
                  line=dict(color='black', width=2)),
        row=1, col=1, secondary_y=True
    )
    
    # Target hardness line
    fig.add_hline(y=target_hardness, line_dash="dash", line_color="red",
                  annotation_text=f"Target: {target_hardness} mg/L",
                  row=1, col=1, secondary_y=True)
    
    # Plot 2: Na release and resin recovery
    fig.add_trace(
        go.Scatter(x=bv, y=na_mg_l, mode='lines', name='Na⁺',
                  line=dict(color='orange', width=2)),
        row=2, col=1, secondary_y=False
    )
    
    if na_fraction:
        fig.add_trace(
            go.Scatter(x=bv, y=[f*100 for f in na_fraction], mode='lines',
                      name='Na+ Sites (%)', line=dict(color='purple', width=2)),
            row=2, col=1, secondary_y=True
        )
    
    # Plot 3: TDS and phase indicators
    if tds:
        fig.add_trace(
            go.Scatter(x=bv, y=tds, mode='lines', name='TDS',
                      line=dict(color='brown', width=2)),
            row=3, col=1
        )
    
    # Add phase boundaries
    phase_colors = {
        'SERVICE': 'lightblue',
        'BACKWASH': 'lightgray',
        'REGENERATION': 'lightcoral',
        'SLOW_RINSE': 'lightyellow',
        'FAST_RINSE': 'lightgreen'
    }
    
    current_phase = phases[0]
    phase_start = bv[0]
    
    for i in range(1, len(phases)):
        if phases[i] != current_phase or i == len(phases) - 1:
            # Add vertical shaded region for the phase
            phase_end = bv[i-1] if phases[i] != current_phase else bv[i]
            for row in [1, 2, 3]:
                fig.add_vrect(
                    x0=phase_start, x1=phase_end,
                    fillcolor=phase_colors.get(current_phase, 'white'),
                    opacity=0.2, layer="below", line_width=0,
                    row=row, col=1
                )
            
            if phases[i] != current_phase:
                phase_start = bv[i]
                current_phase = phases[i]
    
    # Update layout
    fig.update_xaxes(title_text="Bed Volumes", row=3, col=1)
    fig.update_yaxes(title_text="Concentration", row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="Hardness (mg/L CaCO₃)", row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="Na⁺ (mg/L)", row=2, col=1, secondary_y=False)
    fig.update_yaxes(title_text="Na⁺ Sites (%)", row=2, col=1, secondary_y=True)
    fig.update_yaxes(title_text="TDS (mg/L)", row=3, col=1)
    
    title = "Ion Exchange Full Cycle: Service → Regeneration → Rinse"
    
    fig.update_layout(
        title=title,
        showlegend=True,
        height=1000,
        hovermode='x unified'
    )
    
    return fig


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
        # Check if this is a multi-phase plot
        if input_data.plot_regeneration and 'phases' in input_data.breakthrough_data:
            logger.info("Generating multi-phase breakthrough curves with regeneration")
            output_path = generate_multiphase_plot(
                input_data.breakthrough_data,
                input_data.feed_na_mg_l,
                input_data.target_hardness_mg_l,
                output_dir,
                metadata,
                output_format=input_data.output_format
            )
        
        # Generate plot based on requested format
        elif input_data.output_format == 'png':
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