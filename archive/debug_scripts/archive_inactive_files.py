#!/usr/bin/env python3
"""
Archive all files not actively used by the MCP server workflow.
Preserves GrayBox integration for future use.
"""

import os
import shutil
from pathlib import Path

# Define active files and directories
ACTIVE_FILES = {
    # Entry point
    "server.py",
    
    # Tools
    "tools/__init__.py",
    "tools/ix_configuration.py",
    "tools/ix_simulation.py",
    "tools/schemas.py",
    
    # Notebooks
    "notebooks/ix_simulation_graybox_template.ipynb",
    "notebooks/ix_simulation_cli_wrapper.ipynb",
    
    # CLI
    "ix_cli.py",
    
    # Supporting files
    "requirements.txt",
    "CLAUDE.md",
    "README.md",
    "LICENSE",
    "SETUP.md",
    "PROJECT_STATUS_ONBOARDING.md",
    "ACTIVE_FILES_TRACE.md",
    
    # Test files (keep main test)
    "test_mcp_workflow.py",
    
    # This script
    "archive_inactive_files.py",
}

# Active directories (keep entire directory)
ACTIVE_DIRS = {
    "watertap_ix_transport",  # Imported by ix_cli.py
    "phreeqc_pse",  # GrayBox integration (keep for future)
    "data",  # Resin parameters
    "examples",  # Keep for documentation
    "docs",  # Keep all documentation
    "config",  # Keep config directory
    "results",  # Keep results directory
    ".github",  # Keep GitHub workflows if present
}

# Files to archive (not delete)
TO_ARCHIVE = [
    # Old reports and summaries
    "CLEANUP_SUMMARY.md",
    "ENHANCED_MODEL_DEBUG_REPORT.md", 
    "ENHANCED_MODEL_INVESTIGATION_SUMMARY.md",
    "FILES_FOR_PUBLIC_REPO.md",
    "FINAL_MASS_TRANSFER_FIX_SUMMARY.md",
    "FINAL_STATUS_REPORT.md",
    "FIXES_APPLIED_SUMMARY.md",
    "GRAYBOX_IMPLEMENTATION_SUMMARY.md",
    "GRAYBOX_INTEGRATION_GUIDE.md",
    "MASS_TRANSFER_FIX_RESULTS.md",
    "MCP_CLIENT_GUIDE.md",
    "MCP_CLIENT_TESTING.md",
    "PHREEQC_GRAYBOX_IMPLEMENTATION.md",
    "PROCESS_ISOLATION_IMPLEMENTATION.md",
    "PRODUCTION_READINESS_FINAL.md",
    "SOPHISTICATED_MODELING_IMPLEMENTATION_PLAN.md",
    "TEST_PROTOCOL_FOR_SWE.md",
    "AI_SYSTEM_PROMPT.md",
    
    # Patch files
    "fix_ion_exchange_mass_balance.patch",
    "minimal_patch_fix.py",
    "add_pressure_fix_to_notebook.py",
    
    # Test scripts (not main workflow)
    "test_arc_fix.py",
    "test_clean_dof.py",
    "test_config.json",
    "test_constraint_diagnosis.py",
    "test_constraint_structure.py",
    "test_debug_removal.py",
    "test_dof_complete.py",
    "test_dof_diagnostics.py",
    "test_dof_fix.py",
    "test_dof_fixed.py",
    "test_dof_simple.py",
    "test_feed_dof.py",
    "test_final_dof.py",
    "test_fix_infeasibility.py",
    "test_infeasibility_diagnostic.py",
    "test_ix_constraints.py",
    "test_phreeqc_debug.py",
    "test_phreeqc_long.py",
    "test_phreeqc_raw.py",
    "test_pressure_drop_deactivate.py",
    "test_pressure_drop_fix.py",
    "test_remaining_dof.py",
    "test_results.json",
    "test_results_after_fixes.json",
    "test_results_final.json",
    "test_results_fixed.json",
    "flow_debug.log",
    
    # Old notebooks
    "notebooks/ix_simulation_unified_enhanced_template.ipynb",
    "notebooks/ix_simulation_unified_template.ipynb",
    "notebooks/ix_simulation_cli_based.ipynb",
    "notebooks/ix_simulation_cli_wrapper.txt",
    
    # Tools not used
    "tools/ix_simulation_watertap.py",
    "tools/ix_economics_watertap.py",
]

# Directories to archive entirely
TO_ARCHIVE_DIRS = [
    "test_outputs",  # Old test outputs
    "tests",  # Old tests directory
    "utils",  # Not used
]

def archive_file(file_path, archive_base="archive"):
    """Move a file to archive, preserving directory structure."""
    src = Path(file_path)
    if not src.exists():
        return
        
    # Create archive path preserving structure
    archive_path = Path(archive_base) / src
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Move file
    print(f"Archiving: {src} -> {archive_path}")
    shutil.move(str(src), str(archive_path))

def main():
    """Archive inactive files."""
    archive_count = 0
    
    # Archive individual files
    for file in TO_ARCHIVE:
        if os.path.exists(file):
            archive_file(file)
            archive_count += 1
    
    # Archive directories
    for dir_name in TO_ARCHIVE_DIRS:
        if os.path.exists(dir_name):
            print(f"Archiving directory: {dir_name}")
            archive_path = Path("archive") / dir_name
            if archive_path.exists():
                # Merge with existing
                import tempfile
                temp_name = tempfile.mktemp(dir=str(archive_path.parent))
                shutil.move(dir_name, temp_name)
                # Merge contents
                for item in Path(temp_name).iterdir():
                    dest = archive_path / item.name
                    if dest.exists():
                        if dest.is_dir():
                            shutil.rmtree(dest)
                        else:
                            dest.unlink()
                    shutil.move(str(item), str(dest))
                shutil.rmtree(temp_name)
            else:
                archive_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(dir_name, str(archive_path))
            archive_count += 1
    
    print(f"\nArchived {archive_count} items")
    print("\nActive files preserved:")
    for f in sorted(ACTIVE_FILES):
        if os.path.exists(f):
            print(f"  [OK] {f}")
    
    print("\nActive directories preserved:")
    for d in sorted(ACTIVE_DIRS):
        if os.path.exists(d):
            print(f"  [OK] {d}/")

if __name__ == "__main__":
    main()