# Dependency Research via DeepWiki

## Summary of Key Findings

### 1. PhreeqPython - Python Bindings for PHREEQC

**Key Features:**
- Provides high-level, object-oriented Python API for PHREEQC
- Runs simulations completely in memory without temp files
- Wraps VIPhreeqc module which interfaces with PHREEQC C library
- Supports intuitive operations like `solution1 * 0.5 + solution2 * 0.5`

**Advantages over Direct IPhreeqc:**
- No need to write PHREEQC input scripts manually
- Direct access to properties as attributes (e.g., `solution.pH`)
- Automatic handling of PHREEQC input generation and execution
- More Pythonic interface

**Implementation Example:**
```python
from phreeqpython import PhreeqPython
pp = PhreeqPython()
sol = pp.add_solution_simple({'Ca': 1.0, 'Mg': 0.5})
print(sol.pH)  # Direct property access
```

### 2. IDAES - DOF Analysis and Diagnostics

**DOF Calculation:**
- DOF = (unfixed variables in activated equalities) - (activated equalities)
- Negative DOF indicates over-specification
- Function: `idaes.core.util.model_statistics.degrees_of_freedom(block)`

**Diagnostic Tools:**
- `DiagnosticsToolbox` - Primary tool for structural analysis
- `report_structural_issues()` - Checks for warnings including non-zero DOF
- `display_overconstrained_set()` - Shows variables/constraints in over-constrained sub-problems
- Uses Dulmage-Mendelsohn partitioning to identify structural issues

**Important Limitation:**
- DiagnosticsToolbox does NOT support models with ExternalGreyBoxModel
- This affects our GrayBox migration plans

### 3. WaterTAP - Ion Exchange Models

**Existing Models:**
- `IonExchange0D` - Detailed steady-state model with Langmuir/Freundlich isotherms
- `IonExchangeZO` - Simplified zero-order model
- Both use MCAS property package

**Species Naming Convention:**
- WaterTAP: `Ca_2+`, `Mg_2+` (underscore before charge)
- PHREEQC: `Ca+2`, `Mg+2` (no underscore)
- This mismatch requires mapping in our integration

**Best Practices:**
- Use MCAS property package with proper ion parameters
- Ensure DOF = 0 before solving
- Initialize in sequence: Feed → IX → Product
- Integrate with costing via `cost_ion_exchange`

### 4. PyNumero ExternalGreyBoxModel

**Requirements:**
- Must implement: `input_names()`, `output_names()`, `equality_constraint_names()`
- Main calculation in `evaluate_equality_constraints()`
- Assumes 0-DOF system (outputs are functions of inputs)

**Limitations:**
- IDAES diagnostic tools don't support GrayBox models yet
- Jacobian handling not fully documented
- May complicate model debugging

### 5. MCAS Property Package

**Mole Fraction Handling:**
- Creates `eq_mole_frac_phase_comp` constraints
- Ensures sum of mole fractions = 1
- Can use either molar or mass flow basis

**Material Balance Options:**
- State variables: `flow_mol_phase_comp` or `flow_mass_phase_comp`
- Mole fractions calculated from flow rates
- Optional charge balance constraint for electroneutrality

**Constraint Management:**
- Examples show deactivating pressure equality constraints
- No explicit guidance on deactivating mole fraction constraints
- Over-constraint issues when connecting streams (our DOF = -4 problem)

## Recommendations Based on Research

### 1. Immediate Actions

**Switch to PhreeqPython:**
```python
# Replace DirectPhreeqcEngine with PhreeqPython
from phreeqpython import PhreeqPython

class ImprovedPhreeqcEngine:
    def __init__(self):
        self.pp = PhreeqPython()
    
    def run_ix_simulation(self, feed_composition):
        # Direct in-memory execution
        sol = self.pp.add_solution(feed_composition)
        # No temp files, no parsing needed
        return sol
```

**Use IDAES Diagnostics:**
```python
from idaes.core.util.model_diagnostics import DiagnosticsToolbox
from idaes.core.util.model_statistics import degrees_of_freedom

# After building model
dt = DiagnosticsToolbox(model)
dt.report_structural_issues()
if degrees_of_freedom(model) < 0:
    dt.display_overconstrained_set()
```

### 2. Species Mapping Strategy

Create a bidirectional mapping:
```python
SPECIES_MAP = {
    # WaterTAP to PHREEQC
    'Ca_2+': 'Ca+2',
    'Mg_2+': 'Mg+2',
    'Na_+': 'Na+',
    'Cl_-': 'Cl-',
    'HCO3_-': 'HCO3-',
    # PHREEQC to WaterTAP (reverse)
    'Ca+2': 'Ca_2+',
    'Mg+2': 'Mg_2+',
    # etc.
}
```

### 3. GrayBox Migration Considerations

**Pros:**
- Eliminates manual constraint management
- Automatic Jacobian calculation
- True black-box integration

**Cons:**
- No diagnostic tool support
- More complex debugging
- May need custom Jacobian implementation

**Recommendation:** 
- Fix current approach first using diagnostics
- Consider GrayBox only if performance is critical
- Keep diagnostic capabilities in mind

### 4. Constraint Management

For the DOF = -4 issue:
```python
# After connecting streams with arcs
for arc in model.fs.component_objects(Arc):
    # Check for redundant mole fraction constraints
    src = arc.source
    dest = arc.destination
    
    # If both have eq_mole_frac_phase_comp, deactivate one
    if hasattr(dest, 'eq_mole_frac_phase_comp'):
        dest.eq_mole_frac_phase_comp.deactivate()
```

## Next Steps

1. **Implement PhreeqPython Integration**
   - Replace file-based PHREEQC calls
   - Eliminate parsing overhead
   - Enable true in-memory execution

2. **Add Diagnostic Checks**
   - Use DiagnosticsToolbox in model building
   - Catch over-specification early
   - Document constraint structure

3. **Create Robust Species Mapping**
   - Centralize all name conversions
   - Validate against both systems
   - Add unit tests

4. **Document Integration Patterns**
   - Best practices for PHREEQC-WaterTAP integration
   - Common pitfalls and solutions
   - Performance optimization tips