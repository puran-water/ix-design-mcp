1. **Use PowerShell with venv312 for testing**: When running Python tests in mcp-servers, use PowerShell with the venv312 environment to avoid dependency issues:
   ```powershell
   powershell.exe -Command "cd C:\Users\hvksh\mcp-servers\ix-design-mcp; C:\Users\hvksh\mcp-servers\venv312\Scripts\python.exe tests\test_script.py"
   ```
   **Important**: Always use `powershell.exe` when running tests or scripts, not cmd.exe or direct Python execution.

2. **Unicode Handling on Windows**: When writing test scripts that output Unicode characters (✓, ✗, ⚠), add UTF-8 encoding setup at the beginning:
   ```python
   # Set UTF-8 encoding for Windows
   if sys.platform == 'win32':
       import codecs
       sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
       sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
   ```
3. **Addressing Error Messages or Failures During Testing**: When addressing error messages or failures during testing, ensure you:
   - Leverage DeepWiki to ask targeted questions regarding the error messages and **use the correct repo** in your questions i.e. WaterTAP (watertap-org/watertap), phreeqc (usgs-coupled/phreeqc3), phreeqpython wrapper (Vitens/phreeqpython).

4. **Using DeepWiki for Intractable Bugs (Standard Operating Procedure)**: When encountering intractable bugs or infeasibility issues that persist after initial debugging attempts:
   - **Query DeepWiki at least twice** with targeted questions about the specific error or infeasibility
   - **Focus on constraint violations**: For example, "pressure_balance[0.0]: -3.33 =/= 0.0" - ask DeepWiki about the specific constraint
   - **Use the correct repository**: 
     - IDAES framework issues: IDAES/idaes-pse
     - WaterTAP unit models: watertap-org/watertap
     - PHREEQC chemistry: usgs-coupled/phreeqc3
     - PyPhreeqc wrapper: Vitens/phreeqpython
   - **Ask about root causes**: For unexpected behavior (e.g., negative removal rates), ask DeepWiki about what could cause this specific issue
   - **Example queries**:
     - "I have a control volume with pressure balance infeasibility showing 'pressure_balance[0.0]: -3.33 =/= 0.0' in an ion exchange model. What could cause this?"
     - "In an ion exchange model, I'm seeing negative Ca removal (-80.2%) during initialization. What could cause negative removal in an IX model?"
   - **Apply insights systematically**: DeepWiki often reveals hidden constraints, improper initialization procedures, or model configuration issues that aren't obvious from error messages alone
   - **Always review working SAC implementation**: When tests fail, compare with the working SAC (Strong Acid Cation) implementation to identify deviations. SAC has been proven to work correctly, so it serves as a reference implementation.

5. **Standard Operating Procedure for Testing the Model Directly**: When testing IX model improvements or debugging issues:
   - **Create a test configuration file** (test_config.json):
     ```json
     {
       "water_analysis": {
         "flow_m3_hr": 100,
         "temperature_celsius": 25,
         "pressure_bar": 1.0,
         "pH": 7.5,
         "ion_concentrations_mg_L": {
           "Ca_2+": 180,
           "Mg_2+": 80,
           "Na_+": 50,
           "Cl_-": 350,
           "HCO3_-": 300
         }
       },
       "configuration": {
         "ix_vessels": {
           "SAC": {
             "resin_type": "SAC",
             "bed_depth_m": 2.0,
             "diameter_m": 1.5,
             "number_service": 1
           }
         }
       }
     }
     ```
   - **Test using ix_cli.py directly**:
     ```powershell
     powershell.exe -Command "cd C:\Users\hvksh\mcp-servers\ix-design-mcp; C:\Users\hvksh\mcp-servers\venv312\Scripts\python.exe ix_cli.py run test_config.json --output test_results.json"
     ```
   - **Create focused test scripts** for specific issues (e.g., test_pressure_drop.py, test_mass_balance.py):
     ```python
     #!/usr/bin/env python3
     import sys
     if sys.platform == 'win32':
         import codecs
         sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
         sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
     
     from pathlib import Path
     project_root = Path(__file__).parent
     if str(project_root) not in sys.path:
         sys.path.insert(0, str(project_root))
     
     from ix_cli import parse_config, build_model, initialize_model, run_simulation
     
     # Test specific functionality
     config = parse_config("test_config.json")
     model, metadata = build_model(config)
     init_results = initialize_model(model, config)
     sim_results = run_simulation(model, config)
     
     # Add assertions or debugging output
     print(f"Ca removal: {sim_results['performance']['ca_removal_percent']:.1f}%")
     ```

6. **Standard Operating Procedure for Testing the Full Workflow (MCP Server Integration)**: Test the complete workflow as the MCP server would use it:
   - **Create MCP test script** (test_mcp_workflow.py):
     ```python
     #!/usr/bin/env python3
     import sys
     import json
     import subprocess
     
     if sys.platform == 'win32':
         import codecs
         sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
         sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
     
     # Test the tools as MCP server would call them
     from tools.ix_configuration import IXConfigurationTool
     from tools.ix_simulation import IXSimulationTool
     
     print("Testing IX Configuration Tool...")
     config_tool = IXConfigurationTool()
     config_result = config_tool.run(
         flow_m3_hr=100,
         ca_mg_l=180,
         mg_mg_l=80,
         na_mg_l=50,
         cl_mg_l=350,
         hco3_mg_l=300,
         vessels=["SAC"]
     )
     print(f"✓ Configuration created: {len(config_result['configuration']['ix_vessels'])} vessels")
     
     print("\nTesting IX Simulation Tool...")
     sim_tool = IXSimulationTool()
     sim_result = sim_tool.run(json.dumps(config_result))
     print(f"✓ Simulation status: {sim_result['status']}")
     print(f"  Ca removal: {sim_result['performance']['ca_removal_percent']:.1f}%")
     print(f"  Service time: {sim_result['configuration']['ix_vessels']['SAC']['service_time_hours']:.1f} hours")
     ```
   - **Test via subprocess (process isolation)**:
     ```python
     # Test process isolation as used in notebooks
     result = subprocess.run(
         ["python", "ix_cli.py", "run", "test_config.json", "--output", "test_results.json"],
         capture_output=True,
         text=True,
         cwd=str(project_root)
     )
     assert result.returncode == 0, f"Process failed: {result.stderr}"
     ```
   - **Key test assertions**:
     - Model solves successfully (status == 'success')
     - Ca removal is positive and reasonable (0-100%)
     - Mass balance error < 1%
     - Service time is positive
     - No PHREEQC errors in logs
     - Water mole fraction > 0.95
   - **Run complete test suite**:
     ```powershell
     powershell.exe -Command "cd C:\Users\hvksh\mcp-servers\ix-design-mcp; C:\Users\hvksh\mcp-servers\venv312\Scripts\python.exe test_mcp_workflow.py"
     ```

7. **PowerShell Activation and Test Script Execution**:
   - Use PowerShell to activate venv312 and run test scripts:
     ```powershell
     powershell.exe -Command "& 'C:\Users\hvksh\mcp-servers\venv312\Scripts\Activate.ps1'; cd C:\Users\hvksh\mcp-servers\ix-design-mcp; python tests\test_script.py"
     ```
   - Always ensure you're in the correct directory and using the venv312 Python interpreter
   - Use the full path to Activate.ps1 to guarantee virtual environment activation

## Development History and Key Decisions (v2.0.0)

### WAC Implementation Journey

#### Initial Challenge: WAC H-form Removing 100% Hardness
The WAC H-form was incorrectly removing all hardness instead of being limited to temporary hardness (alkalinity-associated). This violated the fundamental chemistry of weak acid resins.

**Attempted Solutions:**
1. **SURFACE Blocks**: Tried modeling pH-dependent carboxylic acid sites using PHREEQC SURFACE blocks with Wac_sOH species. While theoretically correct, this approach had convergence issues and unit conversion problems.
2. **Modified EXCHANGE Blocks**: Attempted to use HX exchange species with complex equilibria. This led to charge balance issues and PHREEQC errors.
3. **Post-Processing (SELECTED)**: Implemented hardness limitation in post-processing, calculating temporary hardness from alkalinity and capping removal accordingly. This pragmatic approach works reliably.

#### Universal Enhancement Framework
Created `BaseIXSimulation` abstract class to implement enhancements once and share across all resin types:
- Ionic strength corrections (Davies equation)
- Temperature corrections (Van't Hoff equation) 
- Mass Transfer Zone modeling
- Capacity degradation
- H-form leakage calculations
- CO₂ generation tracking

#### Key Technical Decisions
1. **Frozen Dataclass Fix**: Converted mutable dictionary defaults to methods in CONFIG to avoid Python dataclass errors
2. **Post-Processing Over SURFACE**: Chose reliability over theoretical purity for WAC H-form limitations
3. **Inheritance Architecture**: Refactored from composition to inheritance for better code reuse
4. **Dynamic EXCHANGE_SPECIES**: Generate PHREEQC blocks dynamically with all corrections applied

### Testing Strategy

#### Critical Test Cases
1. **WAC H-form Temporary Hardness**: Verify removal limited to alkalinity equivalents
2. **Enhancement Stacking**: Test cumulative effects of multiple enhancements
3. **High TDS Waters**: Validate ionic strength corrections above 3000 mg/L
4. **Temperature Extremes**: Test Van't Hoff corrections at 5°C and 40°C
5. **Aged Resins**: Verify capacity degradation with factor < 1.0

#### Known Issues and Workarounds
1. **PHREEQC Convergence**: High ionic strength can cause convergence failures. Solution: Reduce cells or increase tolerance.
2. **MTZ at Low Flows**: MTZ calculation may exceed bed depth at very low flows. Solution: Cap MTZ at 50% of bed depth.
3. **H-form Active Sites**: MOL("HX") can return negative values. Solution: Use post-processing validation.

### Future Improvements
1. **Kinetic Models**: Add intraparticle diffusion for more accurate MTZ
2. **Fouling Prediction**: ML-based fouling factor from water quality
3. **Multi-Component**: Extend to trace metals and organics
4. **Real-Time Optimization**: Dynamic adjustment based on effluent quality