"""
Feature Flags for PHREEQC Optimization

Enables gradual rollout and quick rollback of optimization features.
All flags are controlled via environment variables for easy configuration.

Usage:
    from tools.feature_flags import FeatureFlags
    
    if FeatureFlags.should_use_cache():
        # Use optimized engine with caching
    else:
        # Use direct engine
"""

import os
import hashlib
import logging
from typing import Optional, Dict, Any
from functools import lru_cache

logger = logging.getLogger(__name__)


class FeatureFlags:
    """
    Centralized feature flag management for PHREEQC optimizations.
    
    All flags default to False (disabled) for safety.
    Enable via environment variables or configuration.
    """
    
    # Feature enable/disable flags
    ENABLE_PHREEQC_CACHE = os.getenv('IX_ENABLE_PHREEQC_CACHE', 'false').lower() == 'true'
    ENABLE_BATCH_PROCESSING = os.getenv('IX_ENABLE_BATCH_PROCESSING', 'false').lower() == 'true'
    ENABLE_PARALLEL_EXECUTION = os.getenv('IX_ENABLE_PARALLEL_EXECUTION', 'false').lower() == 'true'
    
    # Rollout percentages (0-100)
    CACHE_ROLLOUT_PERCENT = int(os.getenv('IX_CACHE_ROLLOUT_PERCENT', '0'))
    BATCH_ROLLOUT_PERCENT = int(os.getenv('IX_BATCH_ROLLOUT_PERCENT', '0'))
    PARALLEL_ROLLOUT_PERCENT = int(os.getenv('IX_PARALLEL_ROLLOUT_PERCENT', '0'))
    
    # Performance tuning parameters
    CACHE_SIZE = int(os.getenv('IX_CACHE_SIZE', '256'))
    CACHE_TTL_SECONDS = int(os.getenv('IX_CACHE_TTL_SECONDS', '3600'))
    MAX_BATCH_SIZE = int(os.getenv('IX_MAX_BATCH_SIZE', '10'))
    MAX_WORKERS = int(os.getenv('IX_MAX_WORKERS', '4'))
    
    # Safety limits
    MAX_INPUT_SIZE = int(os.getenv('IX_MAX_INPUT_SIZE', '1000000'))  # 1MB
    PROCESS_TIMEOUT = int(os.getenv('IX_PROCESS_TIMEOUT', '300'))  # 5 minutes
    
    # Monitoring and debugging
    ENABLE_PERFORMANCE_METRICS = os.getenv('IX_ENABLE_PERFORMANCE_METRICS', 'true').lower() == 'true'
    LOG_CACHE_OPERATIONS = os.getenv('IX_LOG_CACHE_OPERATIONS', 'false').lower() == 'true'
    
    @staticmethod
    def _hash_identifier(identifier: str) -> int:
        """
        Generate consistent hash for gradual rollout.
        
        Args:
            identifier: User ID, session ID, or other unique identifier
            
        Returns:
            Hash value between 0-99 for percentage comparison
        """
        # Use SHA256 for consistent hashing across restarts
        hash_bytes = hashlib.sha256(identifier.encode()).digest()
        # Take first 4 bytes and convert to int
        hash_int = int.from_bytes(hash_bytes[:4], byteorder='big')
        return hash_int % 100
    
    @classmethod
    def should_use_cache(cls, identifier: Optional[str] = None) -> bool:
        """
        Determine if caching should be used for this request.
        
        Args:
            identifier: Optional unique identifier for gradual rollout
            
        Returns:
            True if caching should be used
        """
        if not cls.ENABLE_PHREEQC_CACHE:
            return False
            
        if cls.CACHE_ROLLOUT_PERCENT >= 100:
            return True
            
        if cls.CACHE_ROLLOUT_PERCENT <= 0:
            return False
            
        if identifier is None:
            # No identifier provided, use global percentage
            return cls.CACHE_ROLLOUT_PERCENT > 50
            
        # Use consistent hashing for gradual rollout
        user_hash = cls._hash_identifier(identifier)
        return user_hash < cls.CACHE_ROLLOUT_PERCENT
    
    @classmethod
    def should_use_batch_processing(cls, identifier: Optional[str] = None) -> bool:
        """Determine if batch processing should be used."""
        if not cls.ENABLE_BATCH_PROCESSING:
            return False
            
        if cls.BATCH_ROLLOUT_PERCENT >= 100:
            return True
            
        if cls.BATCH_ROLLOUT_PERCENT <= 0:
            return False
            
        if identifier is None:
            return cls.BATCH_ROLLOUT_PERCENT > 50
            
        user_hash = cls._hash_identifier(identifier)
        return user_hash < cls.BATCH_ROLLOUT_PERCENT
    
    @classmethod
    def should_use_parallel_execution(cls, identifier: Optional[str] = None) -> bool:
        """Determine if parallel execution should be used."""
        if not cls.ENABLE_PARALLEL_EXECUTION:
            return False
            
        if cls.PARALLEL_ROLLOUT_PERCENT >= 100:
            return True
            
        if cls.PARALLEL_ROLLOUT_PERCENT <= 0:
            return False
            
        if identifier is None:
            return cls.PARALLEL_ROLLOUT_PERCENT > 50
            
        user_hash = cls._hash_identifier(identifier)
        return user_hash < cls.PARALLEL_ROLLOUT_PERCENT
    
    @classmethod
    def get_optimization_config(cls, identifier: Optional[str] = None) -> Dict[str, Any]:
        """
        Get complete optimization configuration for a request.
        
        Args:
            identifier: Optional unique identifier
            
        Returns:
            Dictionary with all applicable settings
        """
        config = {
            'use_cache': cls.should_use_cache(identifier),
            'use_batch': cls.should_use_batch_processing(identifier),
            'use_parallel': cls.should_use_parallel_execution(identifier),
            'cache_size': cls.CACHE_SIZE if cls.should_use_cache(identifier) else 0,
            'cache_ttl': cls.CACHE_TTL_SECONDS,
            'max_batch_size': cls.MAX_BATCH_SIZE,
            'max_workers': cls.MAX_WORKERS if cls.should_use_parallel_execution(identifier) else 1,
            'collect_metrics': cls.ENABLE_PERFORMANCE_METRICS,
            'log_cache_ops': cls.LOG_CACHE_OPERATIONS
        }
        
        if cls.LOG_CACHE_OPERATIONS:
            logger.info(f"Optimization config for {identifier}: {config}")
            
        return config
    
    @classmethod
    def log_configuration(cls) -> None:
        """Log current feature flag configuration."""
        logger.info("Feature Flag Configuration:")
        logger.info(f"  ENABLE_PHREEQC_CACHE: {cls.ENABLE_PHREEQC_CACHE}")
        logger.info(f"  ENABLE_BATCH_PROCESSING: {cls.ENABLE_BATCH_PROCESSING}")
        logger.info(f"  ENABLE_PARALLEL_EXECUTION: {cls.ENABLE_PARALLEL_EXECUTION}")
        logger.info(f"  CACHE_ROLLOUT_PERCENT: {cls.CACHE_ROLLOUT_PERCENT}%")
        logger.info(f"  BATCH_ROLLOUT_PERCENT: {cls.BATCH_ROLLOUT_PERCENT}%")
        logger.info(f"  PARALLEL_ROLLOUT_PERCENT: {cls.PARALLEL_ROLLOUT_PERCENT}%")
        logger.info(f"  CACHE_SIZE: {cls.CACHE_SIZE}")
        logger.info(f"  CACHE_TTL_SECONDS: {cls.CACHE_TTL_SECONDS}")
        logger.info(f"  MAX_BATCH_SIZE: {cls.MAX_BATCH_SIZE}")
        logger.info(f"  MAX_WORKERS: {cls.MAX_WORKERS}")
    
    @classmethod
    @lru_cache(maxsize=1)
    def validate_configuration(cls) -> Dict[str, Any]:
        """
        Validate feature flag configuration and return any warnings.
        
        Returns:
            Dictionary with validation results and warnings
        """
        warnings = []
        errors = []
        
        # Validate rollout percentages
        for name, value in [
            ('CACHE_ROLLOUT_PERCENT', cls.CACHE_ROLLOUT_PERCENT),
            ('BATCH_ROLLOUT_PERCENT', cls.BATCH_ROLLOUT_PERCENT),
            ('PARALLEL_ROLLOUT_PERCENT', cls.PARALLEL_ROLLOUT_PERCENT)
        ]:
            if value < 0 or value > 100:
                errors.append(f"{name} must be between 0-100, got {value}")
        
        # Validate cache settings
        if cls.CACHE_SIZE < 0:
            errors.append(f"CACHE_SIZE must be non-negative, got {cls.CACHE_SIZE}")
        elif cls.CACHE_SIZE > 10000:
            warnings.append(f"CACHE_SIZE is very large ({cls.CACHE_SIZE}), may use excessive memory")
            
        if cls.CACHE_TTL_SECONDS < 0:
            errors.append(f"CACHE_TTL_SECONDS must be non-negative, got {cls.CACHE_TTL_SECONDS}")
        elif cls.CACHE_TTL_SECONDS > 86400:  # 24 hours
            warnings.append(f"CACHE_TTL_SECONDS is very long ({cls.CACHE_TTL_SECONDS}s), may serve stale data")
        
        # Validate batch settings
        if cls.MAX_BATCH_SIZE < 1:
            errors.append(f"MAX_BATCH_SIZE must be at least 1, got {cls.MAX_BATCH_SIZE}")
        elif cls.MAX_BATCH_SIZE > 100:
            warnings.append(f"MAX_BATCH_SIZE is very large ({cls.MAX_BATCH_SIZE}), may cause memory issues")
        
        # Validate worker settings
        cpu_count = os.cpu_count() or 1
        if cls.MAX_WORKERS < 1:
            errors.append(f"MAX_WORKERS must be at least 1, got {cls.MAX_WORKERS}")
        elif cls.MAX_WORKERS > cpu_count * 2:
            warnings.append(f"MAX_WORKERS ({cls.MAX_WORKERS}) exceeds 2x CPU count ({cpu_count})")
        
        # Check for inconsistent settings
        if cls.ENABLE_PHREEQC_CACHE and cls.CACHE_SIZE == 0:
            warnings.append("ENABLE_PHREEQC_CACHE is true but CACHE_SIZE is 0")
            
        if cls.ENABLE_PARALLEL_EXECUTION and cls.MAX_WORKERS == 1:
            warnings.append("ENABLE_PARALLEL_EXECUTION is true but MAX_WORKERS is 1")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }


def create_phreeqc_engine(identifier: Optional[str] = None):
    """
    Factory function to create appropriate PHREEQC engine based on feature flags.
    
    Args:
        identifier: Optional unique identifier for gradual rollout
        
    Returns:
        Either OptimizedPhreeqcEngine or DirectPhreeqcEngine based on flags
    """
    config = FeatureFlags.get_optimization_config(identifier)
    
    if not any([config['use_cache'], config['use_batch'], config['use_parallel']]):
        # No optimizations enabled, use direct engine
        from watertap_ix_transport.transport_core.direct_phreeqc_engine import DirectPhreeqcEngine
        logger.info(f"Using DirectPhreeqcEngine for {identifier}")
        return DirectPhreeqcEngine()
    
    # Use optimized engine with appropriate settings
    from watertap_ix_transport.transport_core.optimized_phreeqc_engine_refactored import OptimizedPhreeqcEngine
    
    engine = OptimizedPhreeqcEngine(
        cache_size=config['cache_size'],
        cache_ttl_seconds=config['cache_ttl'],
        max_workers=config['max_workers'],
        enable_cache=config['use_cache'],
        enable_parallel=config['use_parallel'],
        collect_metrics=config['collect_metrics']
    )
    
    logger.info(f"Using OptimizedPhreeqcEngine for {identifier} with config: {config}")
    return engine


# Validate configuration on module load
validation_result = FeatureFlags.validate_configuration()
if not validation_result['valid']:
    for error in validation_result['errors']:
        logger.error(f"Feature flag configuration error: {error}")
    raise ValueError("Invalid feature flag configuration")

for warning in validation_result['warnings']:
    logger.warning(f"Feature flag configuration warning: {warning}")

# Log configuration if debugging
if logger.isEnabledFor(logging.DEBUG):
    FeatureFlags.log_configuration()