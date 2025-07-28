# PhreeqPython Ion Exchange Simulation Tool

## Overview

The PhreeqPython simulation tool provides fast, in-memory ion exchange simulations for SAC (Strong Acid Cation) resin systems. It uses the PhreeqPython library to run PHREEQC simulations without file I/O, resulting in 10-100x faster execution compared to file-based approaches.

## Features

- **Fast Execution**: In-memory simulation without file system dependencies
- **Breakthrough Curves**: Generates Ca, Mg breakthrough curves and Na release curves
- **Visual Output**: Automatically creates PNG plots of breakthrough curves
- **Accurate BV Calculations**: Uses industry-standard bed volume definitions
- **Competition Effects**: Models Na+ competition with proper selectivity coefficients

## Usage

1. First, generate a configuration using the `optimize_ix_configuration` tool
2. Pass the configuration JSON to `simulate_ix_phreeqpython`
3. Receive breakthrough data and plot path

### Example

```python
# Step 1: Generate configuration
config = optimize_ix_configuration({
    "water_analysis": {
        "flow_m3_hr": 100,
        "ion_concentrations_mg_L": {
            "Ca_2+": 180,
            "Mg_2+": 80,
            "Na_+": 50,
            "Cl_-": 350,
            "HCO3_-": 300
        },
        "temperature_celsius": 25,
        "pressure_bar": 1.0,
        "pH": 7.5
    }
})

# Step 2: Run PhreeqPython simulation
result = simulate_ix_phreeqpython(json.dumps(config))

# Step 3: Access results
print(f"Ca 50% breakthrough: {result['performance']['ca_50_breakthrough_bv']} BV")
print(f"Service time: {result['performance']['service_time_hours']} hours")
print(f"Plot saved to: {result['performance']['breakthrough_curve_plot']}")
```

## Output

The tool returns:
- **Breakthrough BVs**: 50% and 10% breakthrough points for Ca and Mg
- **Service Time**: Hours of operation before regeneration
- **Capacity Utilization**: Percentage of theoretical capacity achieved
- **Breakthrough Plot**: PNG file showing:
  - Ca and Mg breakthrough curves (% of feed)
  - Na release curve (mg/L)
  - 50% breakthrough reference line

## Technical Details

### PHREEQC Model
- Uses TRANSPORT block for column simulation
- Proper selectivity coefficients: K_Ca/Na = 1.6, K_Mg/Na = 1.3
- Resolution: 20 cells by default
- Maximum simulation: 200 BV

### BV Calculation
```
BV = Volume processed / Total bed volume
```
Where total bed volume includes both resin and void space.

### Limitations
- Currently supports SAC resins only
- Fixed porosity of 0.4
- Fixed resin capacity of 2.0 eq/L

## Performance

Typical execution time: <1 second for 200 BV simulation

## Dependencies

- phreeqpython
- numpy
- matplotlib

## Future Enhancements

- Support for WAC resins
- Multi-stage simulations
- Dynamic porosity and capacity inputs
- Regeneration modeling