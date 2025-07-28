#!/usr/bin/env python
"""
Fix mass transfer term issue by unfixing variables
"""

import sys
import os

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project to path
sys.path.insert(0, 'C:\\Users\\hvksh\\mcp-servers\\ix-design-mcp')

from pyomo.environ import ConcreteModel, value, SolverFactory
from idaes.core import FlowsheetBlock
from idaes.core.util.model_statistics import degrees_of_freedom
from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock, MaterialFlowBasis
from watertap_ix_transport import IonExchangeTransport0D, ResinType

def main():
    print("="*60)
    print("FIX MASS TRANSFER TERM ISSUE")
    print("="*60)

    # Create model
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)

    # Create property package
    m.fs.properties = MCASParameterBlock(
        solute_list=['Ca_2+', 'Mg_2+', 'Na_+', 'Cl_-'],
        material_flow_basis=MaterialFlowBasis.mass
    )

    # Create IX unit
    m.fs.ix = IonExchangeTransport0D(
        property_package=m.fs.properties,
        resin_type=ResinType.SAC
    )

    # Set parameters
    m.fs.ix.bed_depth.set_value(1.0)
    m.fs.ix.bed_diameter.set_value(1.0)
    m.fs.ix.service_time.set_value(24)
    m.fs.ix.operating_capacity.set_value(0.8)

    # Set inlet
    inlet = m.fs.ix.control_volume.properties_in[0]
    inlet.temperature.fix(298.15)
    inlet.pressure.fix(101325)
    inlet.flow_mass_phase_comp['Liq', 'H2O'].fix(0.275)
    inlet.flow_mass_phase_comp['Liq', 'Ca_2+'].fix(0.000022)
    inlet.flow_mass_phase_comp['Liq', 'Mg_2+'].fix(0.0000066)
    inlet.flow_mass_phase_comp['Liq', 'Na_+'].fix(0.00023)
    inlet.flow_mass_phase_comp['Liq', 'Cl_-'].fix(0.00039)

    print("\nBefore initialization:")
    print(f"Model DOF: {degrees_of_freedom(m)}")
    
    # Check if mass_transfer_terms are fixed
    print("\nChecking mass_transfer_term fixed status:")
    for idx in m.fs.ix.control_volume.mass_transfer_term:
        var = m.fs.ix.control_volume.mass_transfer_term[idx]
        print(f"  {idx}: fixed={var.fixed}, value={value(var):.6e}")
    
    # Initialize
    print("\n" + "-"*50)
    print("Initializing with standard approach...")
    m.fs.ix.initialize()
    
    # Check values after standard initialization
    print("\nAfter standard initialization:")
    print_results(m)
    
    # Now try to fix the issue
    print("\n" + "="*60)
    print("APPLYING FIX: Unfix mass_transfer_terms and solve")
    print("="*60)
    
    # Unfix all mass_transfer_terms except H2O
    for idx in m.fs.ix.control_volume.mass_transfer_term:
        if idx[2] != 'H2O':  # Don't unfix water
            m.fs.ix.control_volume.mass_transfer_term[idx].unfix()
            print(f"Unfixed mass_transfer_term{idx}")
    
    print(f"\nModel DOF after unfixing: {degrees_of_freedom(m)}")
    
    # Solve the model
    solver = SolverFactory('ipopt')
    solver.options['tol'] = 1e-8
    solver.options['max_iter'] = 100
    
    print("\nSolving model...")
    results = solver.solve(m, tee=False)
    
    print(f"\nSolver status: {results.solver.termination_condition}")
    
    # Check results after fix
    print("\nAfter applying fix:")
    print_results(m)
    
    # Verify constraints are satisfied
    print("\n" + "-"*50)
    print("Constraint satisfaction check:")
    for idx in m.fs.ix.eq_mass_transfer:
        if m.fs.ix.eq_mass_transfer[idx].active:
            constr = m.fs.ix.eq_mass_transfer[idx]
            body_val = value(constr.body)
            upper_val = value(constr.upper)
            error = abs(body_val - upper_val)
            satisfied = error < 1e-6
            
            print(f"\n{idx}:")
            print(f"  ion_removal_rate: {body_val:.6e}")
            print(f"  mass_transfer_term: {upper_val:.6e}")
            print(f"  Error: {error:.6e}")
            print(f"  Satisfied: {satisfied}")
    
    print("\n" + "="*60)


def print_results(m):
    """Print key results"""
    inlet = m.fs.ix.control_volume.properties_in[0]
    outlet = m.fs.ix.control_volume.properties_out[0]
    
    print("\nIon removal rates:")
    for idx in m.fs.ix.ion_removal_rate:
        if idx[1] in ['Ca_2+', 'Mg_2+', 'Na_+']:
            val = value(m.fs.ix.ion_removal_rate[idx])
            print(f"  {idx}: {val:.6e} kg/s")
    
    print("\nMass transfer terms:")
    for idx in m.fs.ix.control_volume.mass_transfer_term:
        if idx[2] in ['Ca_2+', 'Mg_2+', 'Na_+']:
            val = value(m.fs.ix.control_volume.mass_transfer_term[idx])
            print(f"  {idx}: {val:.6e} kg/s")
    
    print("\nConcentrations:")
    for comp in ['Ca_2+', 'Mg_2+', 'Na_+']:
        inlet_conc = value(inlet.conc_mass_phase_comp['Liq', comp]) * 1000
        outlet_conc = value(outlet.conc_mass_phase_comp['Liq', comp]) * 1000
        print(f"  {comp}: {inlet_conc:.1f} → {outlet_conc:.1f} mg/L")
    
    # Calculate hardness
    inlet_hardness = (value(inlet.conc_mass_phase_comp['Liq', 'Ca_2+']) * 2.5 + 
                     value(inlet.conc_mass_phase_comp['Liq', 'Mg_2+']) * 4.1) * 1000
    outlet_hardness = (value(outlet.conc_mass_phase_comp['Liq', 'Ca_2+']) * 2.5 + 
                      value(outlet.conc_mass_phase_comp['Liq', 'Mg_2+']) * 4.1) * 1000
    
    removal = (inlet_hardness - outlet_hardness) / inlet_hardness * 100
    print(f"\nHardness: {inlet_hardness:.0f} → {outlet_hardness:.0f} mg/L as CaCO3")
    print(f"Removal: {removal:.1f}%")


if __name__ == '__main__':
    main()