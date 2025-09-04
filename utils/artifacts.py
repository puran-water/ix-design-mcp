"""
Artifact Management System

Handles writing and reading of simulation artifacts (JSON results, logs, plots).
Minimal implementation matching RO pattern, with placeholders for future expansion.
"""

import json
import hashlib
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ArtifactManager:
    """Manages simulation artifacts with standardized naming and structure."""
    
    def __init__(self, base_dir: Optional[Path] = None):
        """
        Initialize artifact manager.
        
        Args:
            base_dir: Base directory for artifacts. Defaults to project_root/results
        """
        if base_dir is None:
            # Allow override via environment (useful to avoid slow /mnt/c writes on WSL)
            env_base = os.environ.get("IX_RESULTS_DIR")
            if env_base:
                base_dir = Path(env_base)
            else:
                # Get project root
                project_root = Path(__file__).parent.parent
                base_dir = project_root / "results"
        
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_run_id(self, input_data: Dict[str, Any]) -> str:
        """
        Generate deterministic run ID from input data.
        
        Args:
            input_data: Simulation input parameters
            
        Returns:
            Run ID in format: YYYYMMDD_HHMMSS_hash8
        """
        # Create deterministic hash from sorted input
        input_str = json.dumps(input_data, sort_keys=True, default=str)
        input_hash = hashlib.md5(input_str.encode()).hexdigest()[:8]
        
        # Add timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        return f"{timestamp}_{input_hash}"
    
    def get_artifact_path(
        self,
        run_id: str,
        artifact_type: str,
        extension: str = "json"
    ) -> Path:
        """
        Get standardized artifact path.
        
        Args:
            run_id: Unique run identifier
            artifact_type: Type of artifact (results, input, log, plot, etc.)
            extension: File extension
            
        Returns:
            Path to artifact file
        """
        filename = f"ix_{artifact_type}_{run_id}.{extension}"
        return self.base_dir / filename
    
    def write_json_artifact(
        self,
        data: Dict[str, Any],
        run_id: str,
        artifact_type: str = "results"
    ) -> str:
        """
        Write JSON artifact with proper formatting.
        
        Args:
            data: Data to write
            run_id: Unique run identifier
            artifact_type: Type of artifact
            
        Returns:
            Path to written artifact
        """
        filepath = self.get_artifact_path(run_id, artifact_type, "json")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)
            f.write('\n')  # Newline at EOF
        
        logger.info(f"Wrote {artifact_type} artifact to {filepath}")
        return str(filepath)
    
    def write_text_artifact(
        self,
        content: str,
        run_id: str,
        artifact_type: str,
        extension: str = "txt"
    ) -> str:
        """
        Write text artifact (logs, CSV, etc.).
        
        Args:
            content: Text content to write
            run_id: Unique run identifier
            artifact_type: Type of artifact
            extension: File extension
            
        Returns:
            Path to written artifact
        """
        filepath = self.get_artifact_path(run_id, artifact_type, extension)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
            if not content.endswith('\n'):
                f.write('\n')
        
        logger.info(f"Wrote {artifact_type} artifact to {filepath}")
        return str(filepath)
    
    def read_artifact(
        self,
        run_id: str,
        artifact_type: str,
        extension: str = "json"
    ) -> Any:
        """
        Read artifact from disk.
        
        Args:
            run_id: Unique run identifier
            artifact_type: Type of artifact
            extension: File extension
            
        Returns:
            Artifact contents (parsed JSON or raw text)
        """
        filepath = self.get_artifact_path(run_id, artifact_type, extension)
        
        if not filepath.exists():
            raise FileNotFoundError(f"Artifact not found: {filepath}")
        
        if extension == "json":
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
    
    def create_manifest(
        self,
        run_id: str,
        artifacts: List[str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create manifest file listing all artifacts for a run.
        
        This is a placeholder for future checksum/integrity features.
        
        Args:
            run_id: Unique run identifier
            artifacts: List of artifact paths
            metadata: Optional metadata to include
            
        Returns:
            Path to manifest file
        """
        manifest = {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "artifacts": [],
            "metadata": metadata or {}
        }
        
        # Add artifact entries with placeholders for checksums
        for artifact_path in artifacts:
            if os.path.exists(artifact_path):
                size = os.path.getsize(artifact_path)
                manifest["artifacts"].append({
                    "path": artifact_path,
                    "size_bytes": size,
                    "checksum": None,  # Placeholder for future implementation
                    "type": self._determine_artifact_type(artifact_path)
                })
        
        # Write manifest
        manifest_path = self.write_json_artifact(manifest, run_id, "manifest")
        return manifest_path
    
    def _determine_artifact_type(self, filepath: str) -> str:
        """
        Determine artifact type from filename.
        
        Args:
            filepath: Path to artifact
            
        Returns:
            Artifact type string
        """
        path = Path(filepath)
        name = path.stem.lower()
        
        if "results" in name:
            return "results"
        elif "input" in name:
            return "input"
        elif "log" in name:
            return "log"
        elif "plot" in name or "chart" in name:
            return "plot"
        elif "manifest" in name:
            return "manifest"
        else:
            return "other"
    
    def list_artifacts(self, run_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List available artifacts.
        
        Args:
            run_id: Optional run ID to filter by
            
        Returns:
            List of artifact metadata
        """
        artifacts = []
        pattern = f"ix_*_{run_id}.*" if run_id else "ix_*"
        
        for filepath in self.base_dir.glob(pattern):
            artifacts.append({
                "filename": filepath.name,
                "path": str(filepath),
                "size_bytes": filepath.stat().st_size,
                "modified": datetime.fromtimestamp(filepath.stat().st_mtime).isoformat(),
                "type": self._determine_artifact_type(str(filepath))
            })
        
        return sorted(artifacts, key=lambda x: x["modified"], reverse=True)
    
    def cleanup_old_artifacts(self, days: int = 30) -> int:
        """
        Remove artifacts older than specified days.
        
        Args:
            days: Age threshold in days
            
        Returns:
            Number of artifacts removed
        """
        removed = 0
        cutoff = datetime.now().timestamp() - (days * 86400)
        
        for filepath in self.base_dir.glob("ix_*"):
            if filepath.stat().st_mtime < cutoff:
                try:
                    filepath.unlink()
                    removed += 1
                    logger.info(f"Removed old artifact: {filepath.name}")
                except Exception as e:
                    logger.error(f"Failed to remove {filepath}: {e}")
        
        return removed


# Global artifact manager instance
_artifact_manager = None


def get_artifact_manager(base_dir: Optional[Path] = None) -> ArtifactManager:
    """
    Get or create global artifact manager instance.
    
    Args:
        base_dir: Optional base directory for artifacts
        
    Returns:
        ArtifactManager instance
    """
    global _artifact_manager
    if _artifact_manager is None:
        _artifact_manager = ArtifactManager(base_dir)
    return _artifact_manager
