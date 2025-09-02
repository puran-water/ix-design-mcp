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

5. **Standard Operating Procedure for Testing the Model Directly**: Use the MCP Server tools directly (you are an MCP client that can test the MCP server tools directly).  However, you MUST PAUSE AND REQUEST A MCP SERVER RECONNECTION IF YOU MAKE A MODIFICATION TO THE MCP SERVER CODEBASE AND WOULD LIKE TO TEST THIS MODIFCATION DIRECTLY BY INVOKING A TOOL.
6. **Second Opinion**: You can invoke the Codex MCP server for a second opinion on debugging or testing strategies.  The Codex MCP server is another Coding Agent like yourself that has access to GitHub, DeepWiki, and Sequential Thinking tools. Your prompt to the Codex MCP server should include:
   - The names of the repositories you are working with to allow for proper DeepWiki and GitHub tool calls   

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

### Performance Metrics Fix (v2.0.1) - Critical Equipment Design Issue

#### The Problem
The original metrics calculation was reporting **average removal values** instead of **breakthrough values**. This created a critical equipment design flaw:
- WAC H-form showed 99.996% average alkalinity removal
- WAC H-form showed only ~85% alkalinity removal at breakthrough
- Equipment sized on averages would be **undersized** for end-of-cycle water quality

#### Root Cause
The `_calculate_performance_metrics` method was calculating averages over the first half of the breakthrough curve, not values at the actual breakthrough point.

#### Solution Implemented
1. **Added `_index_at_bv` Helper Method**: Finds array indices at specific bed volumes using `np.searchsorted`
2. **Dual Metrics Structure**: Metrics now include both:
   - `breakthrough_*`: Values at breakthrough point (for equipment design)
   - `avg_*`: Average values over service cycle (for operational estimates)
3. **Breakthrough-Based Design**: Equipment sizing now uses worst-case breakthrough values

#### Technical Implementation
```python
def _index_at_bv(self, data: Dict[str, np.ndarray], breakthrough_bv: float) -> int:
    """Find array index corresponding to breakthrough BV"""
    bvs = data.get('BV', data.get('bv', np.array([])))
    idx = np.searchsorted(bvs, breakthrough_bv, side='left')
    return min(max(0, idx), len(bvs) - 1)

# Use breakthrough index for design metrics
breakthrough_idx = self._index_at_bv(breakthrough_data, breakthrough_bv)
ca_at_breakthrough = ca_eff[breakthrough_idx]
ca_removal = 100 * (1 - ca_at_breakthrough / feed_ca)
```

#### Impact
- **Equipment Design**: Now correctly sized for worst-case (breakthrough) water quality
- **Economic Analysis**: Still provides average values for operational cost estimates  
- **Safety**: Eliminates risk of undersized systems that fail to meet water quality targets

#### Why This Was Critical
In industrial water treatment, equipment must handle **end-of-cycle water quality**, not cycle averages. A resin bed that averages 99% removal but only achieves 85% at breakthrough will fail water quality specifications before regeneration. This fix ensures:
1. Vessels are properly sized for actual breakthrough performance
2. Downstream equipment (RO, etc.) receives acceptable feed quality throughout the cycle
3. Design margins account for real-world performance degradation

### Future Improvements
1. **Kinetic Models**: Add intraparticle diffusion for more accurate MTZ
2. **Fouling Prediction**: ML-based fouling factor from water quality
3. **Multi-Component**: Extend to trace metals and organics
4. **Real-Time Optimization**: Dynamic adjustment based on effluent quality