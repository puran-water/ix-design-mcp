# Degasser Implementation Comparison Report

Generated: 2025-07-23 12:11:30

## Summary

                  Implementation        Status HCO3 Removal %  Uses PHREEQC  Tracks pH  Tracks Alkalinity
                 degasser_simple import_failed            N/A         False      False              False
               degasser_tower_0D  build_failed            N/A         False      False              False
        degasser_tower_0D_simple  build_failed            N/A         False      False              False
       degasser_tower_0D_phreeqc  build_failed            N/A         False      False              False
degasser_tower_0D_phreeqc_simple  build_failed            N/A         False      False              False
 degasser_tower_0D_phreeqc_final  build_failed            N/A         False      False              False


## Detailed Results


### degasser_simple
**Description:** Simple degasser without detailed chemistry
**Status:** import_failed

**Errors:**
- Failed to import: No module named 'tools.degasser_simple'

### degasser_tower_0D
**Description:** 0D tower model with detailed chemistry
**Status:** build_failed

**Errors:**
- Failed to build model: Property package missing required species: {'CO3_2-', 'H_+', 'OH_-'}

### degasser_tower_0D_simple
**Description:** 0D tower model simplified version
**Status:** build_failed

**Errors:**
- Failed to build model: 'ScalarPort' object has no attribute 'connect'

### degasser_tower_0D_phreeqc
**Description:** 0D tower with PHREEQC chemistry (original)
**Status:** build_failed

**Errors:**
- Failed to build model: "Index '(0.0, 'Liq', 'H_+')' is not valid for indexed component 'fs.degasser.control_volume.mass_transfer_term'"

### degasser_tower_0D_phreeqc_simple
**Description:** 0D tower with PHREEQC simplified
**Status:** build_failed

**Errors:**
- Failed to build model: 'ScalarPort' object has no attribute 'connect'

### degasser_tower_0D_phreeqc_final
**Description:** 0D tower with PHREEQC (final version)
**Status:** build_failed

**Errors:**
- Failed to build model: 'ScalarPort' object has no attribute 'connect'


## Recommendations for Production Selection
