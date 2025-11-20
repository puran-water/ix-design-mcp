IX Design MCP Server – Changelog

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
