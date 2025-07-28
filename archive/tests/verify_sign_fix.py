#!/usr/bin/env python3
"""
Verify the sign convention fix works correctly
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Force module reload
for module in list(sys.modules.keys()):
    if module.startswith('watertap_ix_transport'):
        del sys.modules[module]

print("Testing IX model sign convention...")
print("=" * 60)

from pyomo.environ import ConcreteModel, value
from idaes.core import FlowsheetBlock
from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock
from watertap_ix_transport.ion_exchange_transport_0D import (
    IonExchangeTransport0D,
    ResinType,
    RegenerantChem
)
from idaes.core.solvers import get_solver
from idaes.core.util.model_statistics import degrees_of_freedom
import idaes.logger as idaeslog

# Create a simple test model
m = ConcreteModel()
m.fs = FlowsheetBlock(dynamic=False)

# Properties with explicit solute list
m.fs.properties = MCASParameterBlock(
    solute_list=[
        "Ca_2+", "Mg_2+", "Na_+", "H_+", 
        "Cl_-", "SO4_2-", "HCO3_-", "CO3_2-", "OH_-"
    ]
)

# Create IX unit
m.fs.ix = IonExchangeTransport0D(
    property_package=m.fs.properties,
    resin_type=ResinType.SAC,
    regenerant=RegenerantChem.NaCl
)

# Set parameters
m.fs.ix.bed_depth.set_value(2.0)
m.fs.ix.bed_diameter.set_value(1.5)
m.fs.ix.service_time.set_value(24)

# Create feed block
from idaes.models.unit_models import Feed
m.fs.feed = Feed(property_package=m.fs.properties)

# Create product block  
from idaes.models.unit_models import Product
m.fs.product = Product(property_package=m.fs.properties)

# Connect units
from idaes.models.unit_models.mixer import Mixer
from pyomo.network import Arc
m.fs.arc1 = Arc(source=m.fs.feed.outlet, destination=m.fs.ix.inlet)
m.fs.arc2 = Arc(source=m.fs.ix.outlet, destination=m.fs.product.inlet)

# Apply arc equations
from pyomo.environ import TransformationFactory
TransformationFactory("network.expand_arcs").apply_to(m)

# Set feed conditions
feed_state = m.fs.feed.properties[0]
feed_state.temperature.fix(298.15)
feed_state.pressure.fix(101325)

# Fix feed concentrations
flow_rate_m3_s = 100 / 3600  # 100 m³/hr
feed_state.flow_vol_phase['Liq'].fix(flow_rate_m3_s)

# Set concentrations
feed_ca_mg_L = 180
feed_mg_mg_L = 80
feed_state.conc_mass_phase_comp['Liq', 'Ca_2+'].fix(feed_ca_mg_L / 1000)
feed_state.conc_mass_phase_comp['Liq', 'Mg_2+'].fix(feed_mg_mg_L / 1000)
feed_state.conc_mass_phase_comp['Liq', 'Na_+'].fix(50 / 1000)
feed_state.conc_mass_phase_comp['Liq', 'Cl_-'].fix(350 / 1000)
feed_state.conc_mass_phase_comp['Liq', 'SO4_2-'].fix(1e-6)
feed_state.conc_mass_phase_comp['Liq', 'HCO3_-'].fix(300 / 1000)
feed_state.conc_mass_phase_comp['Liq', 'CO3_2-'].fix(1e-6)

# Set pH 7.5
h_conc = 10**(-7.5)  # mol/L
oh_conc = 1e-14 / h_conc
feed_state.conc_mass_phase_comp['Liq', 'H_+'].fix(h_conc * 1.008 / 1000)
feed_state.conc_mass_phase_comp['Liq', 'OH_-'].fix(oh_conc * 17.008 / 1000)

print(f"\nDegrees of freedom before initialization: {degrees_of_freedom(m)}")

# Initialize the flowsheet
print("\nInitializing flowsheet...")
m.fs.feed.initialize(outlvl=idaeslog.NOTSET)

# Propagate state
from idaes.core.util.initialization import propagate_state
propagate_state(m.fs.arc1)

# Initialize IX with 3-step pattern
print("\nStep 1: Initialize IX unit...")
m.fs.ix.initialize(outlvl=idaeslog.NOTSET)

print("\nStep 2: Calculate PHREEQC performance...")
m.fs.ix.calculate_performance()

# Check removal rates before solving
print("\n" + "-"*40)
print("Ion removal rates after calculate_performance:")
for ion in ['Ca_2+', 'Mg_2+', 'Na_+']:
    removal_rate = value(m.fs.ix.ion_removal_rate[0, ion])
    print(f"  {ion}: {removal_rate:.6e} kg/s")

print("\nStep 3: Solve IX unit...")
solver = get_solver()
solver.options['tol'] = 1e-6
results = solver.solve(m.fs.ix, tee=False)

print(f"\nIX unit solve status: {results.solver.termination_condition}")

# Check inlet and outlet concentrations
inlet_ca = value(m.fs.ix.control_volume.properties_in[0].conc_mass_phase_comp['Liq', 'Ca_2+']) * 1000
outlet_ca = value(m.fs.ix.control_volume.properties_out[0].conc_mass_phase_comp['Liq', 'Ca_2+']) * 1000
inlet_mg = value(m.fs.ix.control_volume.properties_in[0].conc_mass_phase_comp['Liq', 'Mg_2+']) * 1000
outlet_mg = value(m.fs.ix.control_volume.properties_out[0].conc_mass_phase_comp['Liq', 'Mg_2+']) * 1000

print("\n" + "-"*40)
print("IX Unit Performance:")
print(f"  Ca: {inlet_ca:.1f} → {outlet_ca:.1f} mg/L")
print(f"  Mg: {inlet_mg:.1f} → {outlet_mg:.1f} mg/L")

# Check mass transfer terms
print("\nMass transfer terms:")
for ion in ['Ca_2+', 'Mg_2+', 'Na_+']:
    mt = value(m.fs.ix.control_volume.mass_transfer_term[0, 'Liq', ion])
    rr = value(m.fs.ix.ion_removal_rate[0, ion])
    print(f"  {ion}: mass_transfer={mt:.6e}, removal_rate={rr:.6e}")

# Calculate removal percentages
ca_removal = (inlet_ca - outlet_ca) / inlet_ca * 100
mg_removal = (inlet_mg - outlet_mg) / inlet_mg * 100

print("\n" + "="*60)
print("RESULTS:")
print(f"  Ca removal: {ca_removal:.1f}%")
print(f"  Mg removal: {mg_removal:.1f}%")

if outlet_ca > inlet_ca:
    print("\n❌ FAILED: Ca concentration increased (negative removal)")
    print("   This indicates the sign convention is still wrong!")
    sys.exit(1)
elif ca_removal < 50:
    print(f"\n❌ FAILED: Ca removal too low ({ca_removal:.1f}% < 50%)")
    sys.exit(1) 
else:
    print(f"\n✅ SUCCESS: Model achieving {ca_removal:.1f}% Ca removal")
    print("   Sign convention is working correctly!")
    sys.exit(0)