# IX Design MCP Server Changelog

All notable changes to the IX Design MCP Server will be documented in this file.

## [2.0.0] - 2025-01-18

### Added

#### WAC (Weak Acid Cation) Support
- Full WAC implementation for both Na-form and H-form resins
- `configure_wac_ix` tool for WAC vessel sizing
- `simulate_wac_ix` tool for WAC cycle simulation  
- pH-dependent capacity modeling for carboxylic acid functional groups
- Two-step regeneration for WAC-Na (acid → caustic)
- Single-step acid regeneration for WAC-H
- Alkalinity tracking and CO₂ generation calculations
- Post-processing to limit H-form to temporary hardness removal

#### Universal Enhancement Framework
- `BaseIXSimulation` abstract class with shared enhancement methods
- Ionic strength corrections using Davies equation
- Temperature corrections using Van't Hoff equation
- Mass Transfer Zone (MTZ) modeling for realistic bed utilization
- Capacity degradation modeling for aged/fouled resins
- H-form leakage calculations for Na⁺/K⁺ breakthrough
- CO₂ generation tracking from alkalinity removal
- Dynamic EXCHANGE_SPECIES generation with all corrections applied

#### Enhanced Configuration System
- Centralized configuration in `core_config.py`
- Enhancement control flags for individual features
- Ion-specific parameters (charges, sizes, enthalpies)
- Frozen dataclass with method-based parameter access
- Support for capacity factors and cycle-based degradation

#### Documentation
- Comprehensive API_REFERENCE.md with all tool specifications
- ENHANCEMENTS.md technical documentation for framework
- Updated README.md with WAC capabilities and examples
- Expanded usage examples for all resin types

### Changed

#### Architecture Improvements
- Refactored to inheritance-based architecture
- Moved common functionality to BaseIXSimulation
- Standardized regeneration across all resin types
- Consistent breakthrough detection logic
- Unified enhancement application across SAC and WAC

#### SAC Enhancements
- Integrated universal enhancement framework
- Added temperature and ionic strength corrections
- Improved Na⁺ competition modeling
- Enhanced regeneration optimization

#### PHREEQC Integration
- Standardized EXCHANGE block generation
- Proper HX species definition for H-form resins
- Improved charge balance handling
- Better convergence for high TDS waters

### Fixed

#### WAC H-form Issues
- Fixed H-form to properly limit hardness removal to temporary hardness
- Resolved immediate breakthrough issues at 0.04 BV
- Fixed negative alkalinity values in output
- Corrected active site calculations using MOL functions
- Proper pH tracking through service cycle

#### Data Structure Issues
- Fixed frozen dataclass with mutable defaults error
- Converted dictionary fields to methods in CONFIG
- Resolved import order dependencies

#### PHREEQC Convergence
- Fixed solution charge balance conflicts
- Improved initial equilibration for exchange sites
- Better handling of high ionic strength waters
- Resolved convergence issues in regeneration

## [1.1.0] - 2025-07-28 - Major Performance and Stability Improvements

### Fixed
1. **Configuration Tool Hanging** (First attempt fix)
   - Removed tool imports from `tools/__init__.py`
   - Prevented matplotlib from loading when importing configuration tool
   
2. **Simulation Tool Hanging** (Second fix)
   - Moved heavy imports to module level in `server.py`
   - Imports now happen at server startup, not during request handling
   - Eliminated 4+ minute delay on first simulation call

3. **BrokenResourceError on Large Responses**
   - Implemented smart breakthrough sampling algorithm
   - Reduces data from ~1000 points to ~114 points (88-93% reduction)
   - Response size reduced from ~50KB to ~3KB
   - Preserves high resolution (every point) in critical ±10 BV zone

### Added
1. **Three-Tool Architecture**
   - Separated plotting into standalone tool
   - Each tool has minimal, focused imports
   - Tools load independently without side effects

2. **Smart Breakthrough Sampling**
   - Intelligent data reduction focused on breakthrough region
   - Critical zone (±10 BV): Every point preserved
   - Transition zone (±10-30 BV): Every 5th point
   - Far zones (>30 BV): Every 20th point
   - Optional `full_data` parameter for complete resolution

3. **Import Timing Logs**
   - Server logs import times at startup
   - Helps diagnose future performance issues

### Performance Improvements
| Metric | Before | After |
|--------|--------|-------|
| Configuration first call | Hanging (~3.5s) | Instant (~0.3s) |
| Simulation first call | Timeout (4+ min) | Normal (~52s) |
| Response size | ~50KB | ~3KB |
| Data points | 1001 | ~114 |

### Technical Details
- Root cause: Synchronous imports blocking async event loop
- Solution: Module-level imports + lazy loading + smart sampling
- Result: Stable, fast MCP server with no hanging or communication errors