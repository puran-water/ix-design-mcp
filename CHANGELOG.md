IX Design MCP Server – Changelog

2.3.0 – 2025-12-04
- **MCP Protocol Compliance**: Full alignment with MCP best practices
  - Server renamed from "IX Design Server" to "ix_design_mcp" (lowercase with underscores)
  - All tools renamed with `ix_` prefix: `ix_configure_sac`, `ix_configure_wac`, `ix_simulate_watertap`, etc.
  - Added tool annotations (readOnlyHint, destructiveHint, idempotentHint, openWorldHint)
  - Tools now accept direct Pydantic models for automatic JSON schema generation
  - Added `response_format` parameter for JSON or Markdown output selection
  - `ix_list_jobs` now returns full pagination metadata (total, count, offset, limit, has_more, next_offset)
- **Code Architecture Improvements**:
  - SAC simulation now properly inherits from BaseIXSimulation (removed legacy delegation pattern)
  - Eliminated duplicate PHREEQC engine initialization code (~200 lines removed)
  - Created `tools/exceptions.py` with typed exception hierarchy (IXDesignError, PHREEQCError, etc.)
  - Created `tools/mcp_types.py` with ResponseFormat enum and markdown formatters
- **Test Infrastructure**:
  - Added `pytest.ini` with marker support (unit, integration, slow, sac, wac)
  - Added `tests/conftest.py` with shared fixtures for water compositions
  - Added `.coveragerc` for coverage configuration (70% threshold)
  - Created `tests/mocks/mock_phreeqc.py` for unit testing without PHREEQC dependency
- **Development Tooling**:
  - Added `pyproject.toml` with black, isort, flake8, and mypy configuration
  - Added `.pre-commit-config.yaml` for automated code quality checks
  - Updated CI workflow with proper pytest markers and test organization
- **Documentation**: Updated README with new tool names, pagination support, and response format options
- Modified files: `server.py`, `tools/base_ix_simulation.py`, `tools/sac_simulation.py`, `tools/wac_simulation.py`, `utils/job_manager.py`, `.github/workflows/ix-tests.yml`
- New files: `tools/mcp_types.py`, `tools/exceptions.py`, `pytest.ini`, `tests/conftest.py`, `.coveragerc`, `pyproject.toml`, `.pre-commit-config.yaml`, `tests/mocks/`
- Why it matters: Better MCP client compatibility, cleaner codebase, improved testability

2.2.1 – 2025-11-21
- **CRITICAL**: Implemented auto-scaling for Pitzer + SURFACE numerical stability
  - Root cause (validated): Large site inventory (~18,000 mol) overwhelms Newton-Raphson solver with Pitzer database
  - Test evidence: 10% site density (~1,800 mol) succeeded, full density (~17,940 mol) failed
  - Solution: Automatically increase cell count when sites_per_cell > 2,000 mol threshold
  - Added `enable_autoscaling` parameter to `build_wac_surface_template()` (default: True)
  - Auto-scaling activates for Pitzer database + high site density (transparent to user)
- **Improved**: Smart database selection for WAC H-form simulations
  - Calculate ionic strength (I) from water composition for accurate database selection
  - I < 0.5 M: Use phreeqc.dat (better SURFACE convergence, adequate accuracy)
  - I ≥ 0.5 M: Use pitzer.dat (required for high ionic strength)
  - Moderate TDS (10-15 g/L) waters now use phreeqc.dat for improved stability
- **Fixed**: Staged initialization now triggers on TDS/IS, not database choice
  - Changed from database-based to TDS > 10 g/L OR I > 0.2 M threshold
  - Prevents direct H-form initialization failures with high-TDS water
- **Test Results** (Jobs 7d9bb124, ce44fc56, 8e91a22a, f42999a1):
  - ✅ SAC: 181.4 BV, 84.2% utilization, 98.9% hardness removal
  - ✅ WAC Na+: 65.4 BV, 50.6% utilization, clean convergence
  - ❌ WAC H+: Blocked by Donnan layer convergence failure with high-TDS (I=0.25M)
  - Error: "Too many iterations in calc_psi_avg" during staged initialization
- **Known Limitation**: WAC H-form SURFACE model fails convergence for TDS > 10 g/L due to Donnan layer + high ionic strength incompatibility in PHREEQC
- Modified files: `tools/wac_surface_builder.py` (lines 36, 59-103), `tools/wac_simulation.py` (lines 1395-1451)
- Why it matters: SAC and WAC Na+ now work reliably. WAC H+ needs alternative approach for high-TDS waters (EXCHANGE model or Donnan removal)

2.2.0 – 2025-11-20
- **CRITICAL**: Implemented staged initialization for WAC H-form to fix convergence failures with corrected log_k values
  - Root cause: Direct H-form initialization dumps massive proton load into high-TDS brine → extreme charge imbalance
  - Solution: Pre-equilibrate in Na-form, then gradually convert to H-form via mild HCl additions (pH 3.0 → 2.5)
  - Added `initialization_mode` parameter to `build_wac_surface_template()` ('direct' or 'staged')
  - Automatic detection: Staged mode activated for high-TDS water (>10 g/L) requiring Pitzer database
- **Fixed**: PHREEQC syntax errors in staged initialization template (validated against upstream source)
  - Corrected KNOBS parameters: `-itmax` → `-iterations`, `-damp` → `-step_size`
  - Added custom `Fix_pH` pseudo-phase definition (`H+ = H+, log_k = 0.0`) for pH control
  - Fixed USE statement: replaced range syntax `1-{cells}` with explicit list
  - Validated via Codex CLI research of phreeqc3 source (session 019aa24e-66e2)
- **Fixed**: Staged initialization convergence failure (removed Fix_pH over-constraint)
  - Root cause: Fix_pH at pH 7.8 created impossible charge balance (17,840 mol H+ released vs. 10 mol NaOH available)
  - Solution 1: Removed Fix_pH EQUILIBRIUM_PHASES block - let pH float to thermodynamic equilibrium (~2-4)
  - Solution 2: Added Donnan layer (`-donnan`) to SURFACE definition for proper charge balance
  - Expected behavior: pH drops naturally during first contact (matches commercial WAC H-form operation)
  - Validated via Codex CLI research of PHREEQC documentation (session 019aa2b9-d23b)
- Modified files: `tools/wac_surface_builder.py`, `tools/wac_simulation.py`
- Why it matters: Corrected log_k values (Ca: 1.5, Mg: 1.3) enable realistic pH-dependent hardness leakage, but convergence failures with direct H-form initialization prevented validation until staged approach implemented

2.1.0 – 2025-09-26
- **BREAKING CHANGE**: SAC leakage calculation now requires feed water composition (Ca/Mg/Na)
- **Major**: Replaced flawed dose-based SAC leakage model with USEPA Gaines-Thomas equilibrium solver
  - OLD: Hardcoded leakage tiers from regeneration dose (ignored feed chemistry)
  - NEW: Mass action equilibrium from Ca/Mg/Na composition (Helfferich 1962)
  - Extracted from USEPA Water_Treatment_Models (public domain, peer-reviewed)
  - Validated to ±0.001% on Gaines-Thomas relationship
  - Parameterized with f_active (0.08-0.15) for mass transfer zone effects
- **Major**: Implemented WAC-H pH floor derating model
  - Target alkalinity drives pH floor via carbonate equilibrium
  - Henderson-Hasselbalch capacity calculation for weak acid groups
  - pH-dependent capacity fraction accurately predicts breakthrough
- Added knowledge-based configuration tools (Tier 1: <1 sec)
  - tools/equilibrium_leakage.py - USEPA equilibrium solver (290 lines)
  - tools/breakthrough_calculator.py - Literature-based breakthrough models
  - tools/capacity_derating.py - Regeneration efficiency and selectivity
  - tools/selectivity_coefficients.py - K_Ca_Na, K_Mg_Na from literature
  - tools/knowledge_based_config.py - Unified configurator
- Code quality: Removed 49 development artifacts (32% reduction in tools/ directory)
  - Deleted 35 standalone test/debug/analysis scripts
  - Removed 8 dead code files (superseded WAC exploration)
  - Removed 6 development documentation files
- Testing: Added comprehensive equilibrium physics test suite (9 tests, 100% pass)
- Documentation: Updated README with three-tier architecture and recent improvements
- Why it matters: SAC predictions now physics-based, WAC-H predictions driven by targets

2.0.1 – 2025-09-02
- Critical: Performance metrics now report breakthrough values (design) in addition to averages (operations).
- SAC/WAC simulations use effluent quality at breakthrough for design metrics.
- Added helper for BV-indexing; improved bounds/edge-case handling.
- Why it matters: prevents undersized equipment sized on cycle averages.

2.0.0 – 2025-01-18
- Added WAC support (Na-form and H-form) with proper breakthrough criteria.
- Introduced BaseIXSimulation with shared enhancements (ionic strength, temperature, MTZ, capacity degradation).
- New tools: configure_wac_ix, simulate_wac_ix; updated docs and examples.
- PHREEQC integration improvements and convergence fixes for high TDS waters.

1.1.0 – 2025-07-28
- Startup/import performance improvements; eliminated first-call hangs.
- Smart breakthrough data sampling to reduce response size while preserving critical resolution.
- Logged import timing; improved stability under large responses.
