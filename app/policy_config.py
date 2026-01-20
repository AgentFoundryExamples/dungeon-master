# Copyright 2025 John Brosnihan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Policy configuration management with runtime reload and validation.

This module provides a configuration management layer for policy parameters
that can be reloaded at runtime without service restarts. It includes:
- Schema validation for policy parameters
- Atomic config reload with rollback on errors
- Audit logging for config changes
- Thread-safe updates with serialization
- File-based or endpoint-driven reload
"""

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator

from app.logging import StructuredLogger

logger = StructuredLogger(__name__)


class PolicyConfigSchema(BaseModel):
    """Schema for policy configuration parameters.
    
    This schema defines the validated structure for policy parameters that
    control quest and POI trigger behavior. All parameters must pass validation
    before being applied to the PolicyEngine.
    
    Attributes:
        quest_trigger_prob: Probability of quest trigger (0.0-1.0)
        quest_cooldown_turns: Number of turns between quest triggers (>= 0)
        poi_trigger_prob: Probability of POI trigger (0.0-1.0)
        poi_cooldown_turns: Number of turns between POI triggers (>= 0)
        memory_spark_probability: Probability of memory spark trigger (0.0-1.0)
        quest_poi_reference_probability: Probability that a quest references a POI (0.0-1.0)
    """
    quest_trigger_prob: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Probability of quest trigger (0.0-1.0)"
    )
    quest_cooldown_turns: int = Field(
        ...,
        ge=0,
        description="Number of turns between quest triggers (must be >= 0)"
    )
    poi_trigger_prob: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Probability of POI trigger (0.0-1.0)"
    )
    poi_cooldown_turns: int = Field(
        ...,
        ge=0,
        description="Number of turns between POI triggers (must be >= 0)"
    )
    memory_spark_probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Probability of memory spark trigger (0.0-1.0)"
    )
    quest_poi_reference_probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Probability that a quest references a POI (0.0-1.0)"
    )

    @field_validator('quest_trigger_prob', 'poi_trigger_prob', 'memory_spark_probability', 'quest_poi_reference_probability')
    @classmethod
    def validate_probability(cls, v: float) -> float:
        """Validate probability is in valid range."""
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"Probability must be between 0.0 and 1.0, got: {v}")
        return v

    @field_validator('quest_cooldown_turns', 'poi_cooldown_turns')
    @classmethod
    def validate_cooldown(cls, v: int) -> int:
        """Validate cooldown is non-negative."""
        if v < 0:
            raise ValueError(f"Cooldown turns must be >= 0, got: {v}")
        return v


class ConfigAuditLog(BaseModel):
    """Audit log entry for configuration changes.
    
    Captures metadata about config mutations including timestamp, actor,
    before/after values, and success/error status.
    
    Attributes:
        timestamp: ISO 8601 timestamp of config change
        actor: Identity of actor making change (IAM caller, admin user, etc.)
        delta_summary: Human-readable summary of changes
        before_config: Previous config values (redacted sensitive fields)
        after_config: New config values (redacted sensitive fields)
        success: Whether config change was successful
        error: Error message if config change failed
    """
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp of config change"
    )
    actor: Optional[str] = Field(
        None,
        description="Identity of actor making change (IAM caller, admin user, file watcher)"
    )
    delta_summary: str = Field(
        ...,
        description="Human-readable summary of changes made"
    )
    before_config: Optional[Dict[str, Any]] = Field(
        None,
        description="Previous config values"
    )
    after_config: Optional[Dict[str, Any]] = Field(
        None,
        description="New config values"
    )
    success: bool = Field(
        ...,
        description="Whether config change was successful"
    )
    error: Optional[str] = Field(
        None,
        description="Error message if config change failed"
    )


class PolicyConfigManager:
    """Manager for policy configuration with runtime reload and validation.
    
    This class provides thread-safe management of policy configuration with
    atomic reload, validation, and rollback on errors. It supports both
    file-based and programmatic configuration updates.
    
    Key Features:
    - Atomic config reload (all-or-nothing updates)
    - Schema validation with actionable error messages
    - Rollback to last-known-good config on validation errors
    - Audit logging for all config mutations
    - Thread-safe updates with serialization
    - Optional file watching for automatic reload
    
    Example:
        >>> manager = PolicyConfigManager(config_file_path="policy_config.json")
        >>> manager.load_config(actor="file_watcher")
        >>> config = manager.get_current_config()
        >>> config.quest_trigger_prob
        0.3
    """
    
    def __init__(
        self,
        config_file_path: Optional[str] = None,
        initial_config: Optional[PolicyConfigSchema] = None
    ):
        """Initialize the policy config manager.
        
        Args:
            config_file_path: Optional path to JSON config file for file-based loading
            initial_config: Optional initial config to use (overrides file if provided)
        """
        self.config_file_path = Path(config_file_path) if config_file_path else None
        self._current_config: Optional[PolicyConfigSchema] = initial_config
        self._last_known_good: Optional[PolicyConfigSchema] = initial_config
        self._lock = threading.Lock()
        self._audit_logs: list[ConfigAuditLog] = []
        
        logger.info(
            "Initialized PolicyConfigManager",
            has_config_file=self.config_file_path is not None,
            has_initial_config=initial_config is not None
        )
    
    def get_current_config(self) -> Optional[PolicyConfigSchema]:
        """Get the current validated policy config.
        
        Returns:
            Current policy config or None if not loaded
        """
        with self._lock:
            return self._current_config
    
    def load_config(
        self,
        actor: str = "system",
        config_dict: Optional[Dict[str, Any]] = None
    ) -> tuple[bool, Optional[str]]:
        """Load and validate policy config from file or dict.
        
        This method performs atomic config reload with validation and rollback.
        If validation fails, the previous config remains active and an audit
        log is created with the error details.
        
        Args:
            actor: Identity of actor making change (for audit log)
            config_dict: Optional config dict to load (overrides file)
            
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        with self._lock:
            try:
                # Load config from dict or file
                if config_dict is not None:
                    config_data = config_dict
                elif self.config_file_path and self.config_file_path.exists():
                    with open(self.config_file_path, 'r') as f:
                        config_data = json.load(f)
                else:
                    error_msg = "No config dict provided and config file does not exist"
                    logger.error("Config load failed", error=error_msg)
                    self._audit_config_change(
                        actor=actor,
                        delta_summary="Config load failed - no source",
                        before_config=self._config_to_dict(self._current_config),
                        after_config=None,
                        success=False,
                        error=error_msg
                    )
                    return False, error_msg
                
                # Validate schema
                new_config = PolicyConfigSchema(**config_data)
                
                # Build delta summary
                delta_summary = self._build_delta_summary(self._current_config, new_config)
                
                # Store previous config for rollback
                previous_config = self._current_config
                
                # Apply new config
                self._current_config = new_config
                self._last_known_good = new_config
                
                # Audit successful change
                self._audit_config_change(
                    actor=actor,
                    delta_summary=delta_summary,
                    before_config=self._config_to_dict(previous_config),
                    after_config=self._config_to_dict(new_config),
                    success=True,
                    error=None
                )
                
                logger.info(
                    "Policy config loaded successfully",
                    actor=actor,
                    delta=delta_summary
                )
                
                return True, None
                
            except Exception as e:
                error_msg = f"Config validation failed: {str(e)}"
                logger.error(
                    "Config load failed",
                    error=error_msg,
                    actor=actor
                )
                
                # Audit failed change (keep previous config)
                self._audit_config_change(
                    actor=actor,
                    delta_summary="Config validation failed",
                    before_config=self._config_to_dict(self._current_config),
                    after_config=config_data if 'config_data' in locals() else None,
                    success=False,
                    error=error_msg
                )
                
                # Rollback to last known good (already in _current_config)
                return False, error_msg
    
    def reload_from_file(self, actor: str = "file_watcher") -> tuple[bool, Optional[str]]:
        """Reload config from file path.
        
        Convenience method for file-based reloading.
        
        Args:
            actor: Identity of actor triggering reload
            
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        return self.load_config(actor=actor, config_dict=None)
    
    def get_audit_logs(self, limit: int = 100) -> list[ConfigAuditLog]:
        """Get recent audit logs for config changes.
        
        Args:
            limit: Maximum number of logs to return (default: 100)
            
        Returns:
            List of recent audit logs in reverse chronological order
        """
        with self._lock:
            return list(reversed(self._audit_logs[-limit:]))
    
    def _config_to_dict(self, config: Optional[PolicyConfigSchema]) -> Optional[Dict[str, Any]]:
        """Convert config to dict for audit logging."""
        if config is None:
            return None
        return config.model_dump()
    
    def _build_delta_summary(
        self,
        before: Optional[PolicyConfigSchema],
        after: PolicyConfigSchema
    ) -> str:
        """Build human-readable delta summary."""
        if before is None:
            return "Initial config load"
        
        changes = []
        if before.quest_trigger_prob != after.quest_trigger_prob:
            changes.append(f"quest_prob: {before.quest_trigger_prob} -> {after.quest_trigger_prob}")
        if before.quest_cooldown_turns != after.quest_cooldown_turns:
            changes.append(f"quest_cooldown: {before.quest_cooldown_turns} -> {after.quest_cooldown_turns}")
        if before.poi_trigger_prob != after.poi_trigger_prob:
            changes.append(f"poi_prob: {before.poi_trigger_prob} -> {after.poi_trigger_prob}")
        if before.poi_cooldown_turns != after.poi_cooldown_turns:
            changes.append(f"poi_cooldown: {before.poi_cooldown_turns} -> {after.poi_cooldown_turns}")
        
        if not changes:
            return "No changes detected"
        
        return ", ".join(changes)
    
    def _audit_config_change(
        self,
        actor: Optional[str],
        delta_summary: str,
        before_config: Optional[Dict[str, Any]],
        after_config: Optional[Dict[str, Any]],
        success: bool,
        error: Optional[str]
    ) -> None:
        """Record audit log for config change."""
        audit_entry = ConfigAuditLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=actor,
            delta_summary=delta_summary,
            before_config=before_config,
            after_config=after_config,
            success=success,
            error=error
        )
        
        self._audit_logs.append(audit_entry)
        
        # Emit structured log for external systems
        logger.info(
            "Config change audit",
            timestamp=audit_entry.timestamp,
            actor=actor,
            delta=delta_summary,
            success=success,
            error=error
        )
