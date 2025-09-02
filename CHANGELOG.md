IX Design MCP Server – Changelog

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
