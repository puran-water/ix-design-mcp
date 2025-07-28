# IX Design MCP Server Changelog

## [2025-07-28] - Major Performance and Stability Improvements

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