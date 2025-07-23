# Technical Details - IX Design MCP Server

## Architecture Overview

The IX Design MCP Server follows a modular architecture designed for extensibility and maintainability:

```
┌─────────────────┐     ┌──────────────────┐
│   MCP Client    │────▶│    server.py     │
│  (AI Agent)     │     │  (FastMCP STDIO) │
└─────────────────┘     └────────┬─────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
            ┌───────▼────────┐     ┌─────────▼──────────┐
            │ Configuration  │     │    Simulation      │
            │     Tool       │     │      Tool          │
            └───────┬────────┘     └─────────┬──────────┘
                    │                         │
            ┌───────▼────────┐     ┌─────────▼──────────┐
            │   IX Sizing    │     │  PhreeqPy Engine   │
            │   Economics    │     │  Breakthrough Sim  │
            └────────────────┘     └────────────────────┘
```

## Core Components

### 1. MCP Server (server.py)
- Built on FastMCP framework
- STDIO communication protocol
- Tool registration and dispatch
- Error handling and logging

### 2. Configuration Tool
- Water chemistry analysis
- Flowsheet selection logic
- Hydraulic sizing calculations
- Economic modeling

### 3. Simulation Tool  
- **Papermill notebook execution for process isolation**
- PhreeqPy integration in subprocess
- Breakthrough curve prediction
- Performance metrics calculation
- Water quality progression

### 4. Schemas (Pydantic Models)
- MCAS water composition
- IX configuration structures
- Simulation inputs/outputs
- Data validation

## Water Chemistry Processing

### Hardness Classification
```python
temporary_hardness = min(alkalinity, total_hardness)
permanent_hardness = total_hardness - temporary_hardness
temp_fraction = temporary_hardness / total_hardness

if temp_fraction > 0.9:
    flowsheet = "H-WAC → Degasser → Na-WAC"
elif permanent_hardness > 100:
    flowsheet = "SAC → Na-WAC → Degasser"
else:
    flowsheet = "Na-WAC → Degasser"
```

### Na+ Competition Modeling
```python
# Selectivity coefficients
K_Ca_Na = 5.0  # Ca++ preference over Na+
K_Mg_Na = 3.0  # Mg++ preference over Na+

# Competition factor calculation
na_hardness_ratio = na_conc / (ca_conc + mg_conc)
competition_factor = 1 / (1 + 0.5 * na_hardness_ratio)

# Minimum 30% capacity retention
competition_factor = max(0.3, competition_factor)
```

## Vessel Sizing Algorithm

### Design Parameters
- Service flow rate: 16 BV/hr
- Linear velocity: 25 m/hr
- Bed depth range: 1.0 - 3.0 m
- Maximum diameter: 3.0 m

### Sizing Logic
```python
# Calculate vessel area from linear velocity
area_m2 = flow_m3_hr / linear_velocity_m_hr

# Determine vessel diameter
diameter_m = math.sqrt(4 * area_m2 / math.pi)

# Check diameter constraints
if diameter_m > max_diameter:
    n_vessels = math.ceil(diameter_m / max_diameter)
    diameter_m = math.sqrt(4 * area_m2 / (n_vessels * math.pi))

# Calculate bed volume
bed_volume_m3 = flow_m3_hr / service_bv_hr

# Determine bed depth
bed_depth_m = bed_volume_m3 / (n_vessels * area_per_vessel)
```

## Economic Calculations

### CAPEX Components
```python
capex = {
    "vessels": vessel_count * vessel_unit_cost,
    "resin": resin_volume_m3 * resin_cost_per_m3,
    "degasser": degasser_cost,
    "pumps": pump_cost,
    "instrumentation": 0.15 * equipment_cost,
    "installation": 1.5 * total_equipment_cost
}
```

### OPEX Components
```python
opex = {
    "regenerant": annual_regenerant_kg * chemical_cost,
    "power": pump_kw * 8760 * electricity_cost,
    "labor": operator_hours * labor_rate,
    "waste_disposal": waste_volume * disposal_cost,
    "maintenance": 0.03 * capex_total
}
```

### LCOW Calculation
```python
# 10-year NPV at 8% discount rate
discount_rate = 0.08
project_life = 10

npv_factor = sum(1/(1+discount_rate)**i for i in range(1, project_life+1))
total_cost_npv = capex + opex * npv_factor
total_water_m3 = annual_production * project_life

lcow = total_cost_npv / total_water_m3
```

## PhreeqPy Integration

### Solution Definition
```python
solution_lines = ["SOLUTION 1"]
for ion, conc in ion_concentrations.items():
    solution_lines.append(f"    {ion} {conc} mg/L")
solution_lines.append(f"    pH {pH}")
solution_lines.append(f"    temp {temperature}")

# Charge balance on predominant ion
if na_conc > cl_conc:
    solution_lines.append("    charge Na")
else:
    solution_lines.append("    charge Cl")
```

### Ion Exchange Definition
```python
exchange_block = f"""
EXCHANGE 1
    -equil 1
    -formula {resin_type}{capacity_eq}
EXCHANGE_SPECIES
    {resin_type} + Na+ = Na{resin_type}; log_k 0.0
    2{resin_type} + Ca+2 = Ca{resin_type}2; log_k {log_K_Ca}
    2{resin_type} + Mg+2 = Mg{resin_type}2; log_k {log_K_Mg}
"""
```

### Breakthrough Simulation
```python
# Calculate bed volumes
for bv in range(0, max_bed_volumes, step):
    # Add solution volume
    volume_L = resin_volume_L * bv
    
    # Run PHREEQC
    phreeqc_input = solution + exchange + f"SAVE solution 2"
    pp.run_string(phreeqc_input)
    
    # Extract effluent composition
    effluent = pp.get_solution_composition()
    
    # Check breakthrough
    if effluent['Ca'] + effluent['Mg'] > breakthrough_limit:
        breakthrough_bv = bv
        break
```

## Process Isolation

### Why Notebook Execution is Required
WaterTAP and PhreeqPy can conflict with the MCP server process due to:
- Global state modifications
- Memory management conflicts
- Thread safety issues
- Resource locking

### Papermill Solution
- Executes notebooks in separate subprocess
- Isolated Python kernel for each simulation
- Parameters passed via JSON serialization
- Results extracted from notebook outputs
- Complete process isolation from MCP server

This approach matches the RO Design MCP Server architecture and ensures stability.

## Performance Optimizations

### 1. Caching
- PHREEQC database loaded once per notebook
- Resin properties cached
- Economic factors stored

### 2. Parallel Processing
- Multiple configurations generated concurrently
- Independent vessel stages sized in parallel

### 3. Early Termination
- Breakthrough detection stops simulation
- Invalid configurations rejected early

## Error Handling

### Input Validation
- MCAS ion format checking
- Charge balance verification
- Flow rate and pH ranges

### Calculation Safeguards
- Division by zero prevention
- Negative value checks
- Convergence monitoring

### User Feedback
- Clear error messages
- Warnings for unusual conditions
- Suggestions for corrections

## Testing Strategy

### Unit Tests
- Individual component testing
- Mocked dependencies
- Edge case coverage

### Integration Tests
- End-to-end workflows
- Real PHREEQC calculations
- Performance benchmarks

### Validation Tests
- Known water compositions
- Literature case studies
- Field data comparison

## Future Architecture

### Planned Enhancements
1. **Microservices**: Separate sizing and simulation services
2. **Caching Layer**: Redis for result storage
3. **Queue System**: Async job processing
4. **Web API**: REST endpoints alongside MCP
5. **Monitoring**: Prometheus metrics

### Extension Points
- Custom resin types
- Alternative sizing methods
- Advanced economics
- Multi-objective optimization

## Dependencies

### Core Libraries
- `fastmcp`: MCP server framework
- `phreeqpython`: PHREEQC wrapper
- `pydantic`: Data validation
- `numpy`: Numerical operations

### Optional Libraries
- `papermill`: Notebook execution
- `pandas`: Data analysis
- `matplotlib`: Visualization

## Performance Metrics

### Typical Response Times
- Configuration: 100-500 ms
- Simulation: 1-5 seconds
- Full workflow: 2-10 seconds

### Resource Usage
- Memory: 200-500 MB
- CPU: Single core sufficient
- Disk: <100 MB (excluding notebooks)

## Security Considerations

### Input Sanitization
- SQL injection prevention
- Path traversal protection
- Command injection safeguards

### Resource Limits
- Maximum array sizes
- Timeout enforcement
- Memory usage caps

### Data Privacy
- No persistent storage
- Session isolation
- Secure communication