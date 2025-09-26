IX Design MCP Server – Changelog

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
