# IX Design MCP Server - Client Integration Guide

This guide helps MCP client developers properly integrate with the IX Design MCP Server tools.

## Common Integration Issues

The most common error when calling the `optimize_ix_configuration_wrapped` tool is incorrect input structure. The tool requires a specific nested structure that must be followed exactly.

## Tool Input Structure

### optimize_ix_configuration_wrapped

**CORRECT Structure:**
```json
{
  "input_data": {
    "water_analysis": {
      "flow_m3_hr": 100,
      "ion_concentrations_mg_L": {
        "Na_+": 838.9,
        "Ca_2+": 80.06,
        "Mg_2+": 24.29,
        "Cl_-": 1435.0,
        "HCO3_-": 121.95
      },
      "temperature_celsius": 25.0,
      "pressure_bar": 4.0,
      "pH": 7.0
    },
    "treatment_goals": ["remove_hardness", "remove_alkalinity"],
    "max_vessels_per_train": 3,
    "regenerant_type": "HCl",
    "max_vessel_diameter_m": 2.4
  }
}
```

**COMMON MISTAKES:**

❌ **Mistake 1: Missing water_analysis wrapper**
```json
{
  "input_data": {
    "flow_m3h": 100,
    "feed_composition": {...},  // Wrong field name
    "treatment_goals": [...]
  }
}
```

❌ **Mistake 2: Incorrect nesting of flow and ions**
```json
{
  "input_data": {
    "flow_m3h": 100,  // Should be inside water_analysis
    "water_analysis": {
      "Na_+": 838.9,  // Should be inside ion_concentrations_mg_L
      "Ca_2+": 80.06
    }
  }
}
```

## Required Fields

### water_analysis (REQUIRED)
- **flow_m3_hr**: Flow rate in m³/hr (number > 0)
- **ion_concentrations_mg_L**: Dictionary of ion concentrations in mg/L

### Optional Fields with Defaults
- **temperature_celsius**: 25.0
- **pressure_bar**: 4.0
- **pH**: 7.0
- **treatment_goals**: ["remove_hardness", "remove_alkalinity"]
- **max_vessels_per_train**: 3
- **regenerant_type**: "HCl" (options: "HCl" or "H2SO4")
- **max_vessel_diameter_m**: 2.4

## Ion Notation (MCAS Format)

All ions must use MCAS notation with underscores:

**Cations:**
- Na_+ (sodium)
- Ca_2+ (calcium)
- Mg_2+ (magnesium)
- K_+ (potassium)
- H_+ (hydrogen)
- NH4_+ (ammonium)
- Fe_2+ (ferrous iron)
- Fe_3+ (ferric iron)

**Anions:**
- Cl_- (chloride)
- SO4_2- (sulfate)
- HCO3_- (bicarbonate)
- CO3_2- (carbonate)
- NO3_- (nitrate)
- PO4_3- (phosphate)
- F_- (fluoride)
- OH_- (hydroxide)

**Neutrals:**
- CO2 (carbon dioxide)
- SiO2 (silica)
- B(OH)3 (boric acid)

## Error Handling

When validation errors occur, the server will return helpful error messages:

```json
{
  "error": "Invalid input structure",
  "details": "Field required: water_analysis.flow_m3_hr",
  "hint": "The 'water_analysis' field must contain 'flow_m3_hr' and 'ion_concentrations_mg_L' as nested fields.",
  "example_structure": {
    "water_analysis": {
      "flow_m3_hr": 100,
      "ion_concentrations_mg_L": {
        "Na_+": 500,
        "Ca_2+": 120,
        "Cl_-": 800
      }
    }
  }
}
```

## Integration Testing

To test your MCP client integration:

1. Start with minimal required fields:
```json
{
  "input_data": {
    "water_analysis": {
      "flow_m3_hr": 100,
      "ion_concentrations_mg_L": {
        "Na_+": 500,
        "Ca_2+": 100,
        "Cl_-": 800
      }
    }
  }
}
```

2. Verify you receive a successful response with three flowsheet configurations

3. Add optional parameters as needed

## Output Structure

The tool returns configurations for three flowsheet alternatives:
- H-WAC → Degasser → Na-WAC
- SAC → Na-WAC → Degasser  
- Na-WAC → Degasser

Each configuration includes:
- Vessel dimensions and quantities
- Resin volumes
- Degasser specifications
- Hydraulic parameters
- Water chemistry analysis
- Recommended flowsheet based on water quality

## Best Practices

1. **Always validate** the water_analysis structure before sending
2. **Use try-catch** blocks to handle validation errors gracefully
3. **Check ion notation** - must use MCAS format (e.g., Ca_2+ not Ca2+ or Ca++)
4. **Start simple** - use minimal required fields first, then add options
5. **Log errors** - the error messages contain helpful debugging information

## Example Client Code (Python)

```python
# Example using MCP SDK
async def call_ix_optimization(client):
    try:
        result = await client.call_tool(
            "optimize_ix_configuration_wrapped",
            arguments={
                "input_data": {
                    "water_analysis": {
                        "flow_m3_hr": 100,
                        "ion_concentrations_mg_L": {
                            "Na_+": 838.9,
                            "Ca_2+": 80.06,
                            "Mg_2+": 24.29,
                            "Cl_-": 1435.0,
                            "HCO3_-": 121.95
                        }
                    },
                    "treatment_goals": ["remove_hardness", "remove_alkalinity"],
                    "regenerant_type": "HCl"
                }
            }
        )
        return result
    except Exception as e:
        print(f"Error: {e}")
        # Check if it's a validation error and handle accordingly
```

## Need Help?

If you encounter issues not covered in this guide:
1. Check the tool description in the MCP server output
2. Review the error messages - they contain specific guidance
3. Ensure you're using the latest version of the IX Design MCP Server
4. File an issue with your input structure and error message