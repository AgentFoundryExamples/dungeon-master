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
"""Tests for PolicyConfigManager."""

import pytest
import tempfile
import json
from pathlib import Path

from app.policy_config import PolicyConfigManager, PolicyConfigSchema


def test_policy_config_schema_valid():
    """Test PolicyConfigSchema with valid values."""
    config = PolicyConfigSchema(
        quest_trigger_prob=0.5,
        quest_cooldown_turns=10,
        poi_trigger_prob=0.3,
        poi_cooldown_turns=5,
        memory_spark_probability=0.2,
        quest_poi_reference_probability=0.1
    )
    
    assert config.quest_trigger_prob == 0.5
    assert config.quest_cooldown_turns == 10
    assert config.poi_trigger_prob == 0.3
    assert config.poi_cooldown_turns == 5


def test_policy_config_schema_invalid_probability():
    """Test PolicyConfigSchema rejects invalid probabilities."""
    from pydantic import ValidationError
    
    # Test probability > 1.0
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        PolicyConfigSchema(
            quest_trigger_prob=1.5,
            quest_cooldown_turns=5,
            poi_trigger_prob=0.2,
            poi_cooldown_turns=3,
            memory_spark_probability=0.2,
            quest_poi_reference_probability=0.1
        )
    
    # Test negative probability
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        PolicyConfigSchema(
            quest_trigger_prob=0.3,
            quest_cooldown_turns=5,
            poi_trigger_prob=-0.1,
            poi_cooldown_turns=3,
            memory_spark_probability=0.2,
            quest_poi_reference_probability=0.1
        )


def test_policy_config_schema_invalid_cooldown():
    """Test PolicyConfigSchema rejects negative cooldowns."""
    from pydantic import ValidationError
    
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        PolicyConfigSchema(
            quest_trigger_prob=0.3,
            quest_cooldown_turns=-5,
            poi_trigger_prob=0.2,
            poi_cooldown_turns=3,
            memory_spark_probability=0.2,
            quest_poi_reference_probability=0.1
        )


def test_policy_config_manager_init_with_initial_config():
    """Test PolicyConfigManager initialization with initial config."""
    initial_config = PolicyConfigSchema(
        quest_trigger_prob=0.4,
        quest_cooldown_turns=8,
        poi_trigger_prob=0.25,
        poi_cooldown_turns=4,
        memory_spark_probability=0.2,
        quest_poi_reference_probability=0.1
    )
    
    manager = PolicyConfigManager(initial_config=initial_config)
    
    current = manager.get_current_config()
    assert current is not None
    assert current.quest_trigger_prob == 0.4
    assert current.quest_cooldown_turns == 8


def test_policy_config_manager_load_from_dict():
    """Test loading config from dictionary."""
    manager = PolicyConfigManager()
    
    config_dict = {
        "quest_trigger_prob": 0.6,
        "quest_cooldown_turns": 12,
        "poi_trigger_prob": 0.35,
        "poi_cooldown_turns": 6,
        "memory_spark_probability": 0.2,
        "quest_poi_reference_probability": 0.1
    }
    
    success, error = manager.load_config(actor="test", config_dict=config_dict)
    
    assert success is True
    assert error is None
    
    current = manager.get_current_config()
    assert current.quest_trigger_prob == 0.6
    assert current.quest_cooldown_turns == 12


def test_policy_config_manager_load_invalid_config():
    """Test loading invalid config fails with validation error."""
    manager = PolicyConfigManager()
    
    # Invalid probability
    invalid_config = {
        "quest_trigger_prob": 2.0,  # Invalid: > 1.0
        "quest_cooldown_turns": 5,
        "poi_trigger_prob": 0.2,
        "poi_cooldown_turns": 3,
        "memory_spark_probability": 0.2,
        "quest_poi_reference_probability": 0.1
    }
    
    success, error = manager.load_config(actor="test", config_dict=invalid_config)
    
    assert success is False
    assert error is not None
    assert "validation failed" in error.lower()
    
    # Current config should remain unchanged (None in this case)
    assert manager.get_current_config() is None


def test_policy_config_manager_load_from_file():
    """Test loading config from JSON file."""
    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "quest_trigger_prob": 0.7,
            "quest_cooldown_turns": 15,
            "poi_trigger_prob": 0.4,
            "poi_cooldown_turns": 8,
            "memory_spark_probability": 0.2,
            "quest_poi_reference_probability": 0.1
        }
        json.dump(config_data, f)
        temp_file = f.name
    
    try:
        manager = PolicyConfigManager(config_file_path=temp_file)
        
        success, error = manager.load_config(actor="file_test")
        
        assert success is True
        assert error is None
        
        current = manager.get_current_config()
        assert current.quest_trigger_prob == 0.7
        assert current.quest_cooldown_turns == 15
    finally:
        Path(temp_file).unlink()


def test_policy_config_manager_audit_logs():
    """Test audit logs are created for config changes."""
    manager = PolicyConfigManager()
    
    config_dict = {
        "quest_trigger_prob": 0.5,
        "quest_cooldown_turns": 10,
        "poi_trigger_prob": 0.3,
        "poi_cooldown_turns": 5,
        "memory_spark_probability": 0.2,
        "quest_poi_reference_probability": 0.1
    }
    
    success, error = manager.load_config(actor="admin_user", config_dict=config_dict)
    assert success is True
    
    # Check audit logs
    audit_logs = manager.get_audit_logs(limit=10)
    assert len(audit_logs) >= 1
    
    latest_log = audit_logs[0]
    assert latest_log.actor == "admin_user"
    assert latest_log.success is True
    assert latest_log.error is None


def test_policy_config_manager_rollback_on_error():
    """Test config rollback when validation fails."""
    # Set initial valid config
    initial_config = PolicyConfigSchema(
        quest_trigger_prob=0.3,
        quest_cooldown_turns=5,
        poi_trigger_prob=0.2,
        poi_cooldown_turns=3,
        memory_spark_probability=0.2,
        quest_poi_reference_probability=0.1
    )
    
    manager = PolicyConfigManager(initial_config=initial_config)
    
    # Try to load invalid config
    invalid_config = {
        "quest_trigger_prob": -0.5,  # Invalid
        "quest_cooldown_turns": 5,
        "poi_trigger_prob": 0.2,
        "poi_cooldown_turns": 3,
        "memory_spark_probability": 0.2,
        "quest_poi_reference_probability": 0.1
    }
    
    success, error = manager.load_config(actor="test", config_dict=invalid_config)
    
    assert success is False
    assert error is not None
    
    # Config should still be the initial valid config
    current = manager.get_current_config()
    assert current.quest_trigger_prob == 0.3
    assert current.quest_cooldown_turns == 5


def test_policy_config_manager_delta_summary():
    """Test delta summary is generated correctly."""
    initial_config = PolicyConfigSchema(
        quest_trigger_prob=0.3,
        quest_cooldown_turns=5,
        poi_trigger_prob=0.2,
        poi_cooldown_turns=3,
        memory_spark_probability=0.2,
        quest_poi_reference_probability=0.1
    )
    
    manager = PolicyConfigManager(initial_config=initial_config)
    
    # Load new config with changes
    new_config = {
        "quest_trigger_prob": 0.5,  # Changed
        "quest_cooldown_turns": 5,  # Unchanged
        "poi_trigger_prob": 0.2,    # Unchanged
        "poi_cooldown_turns": 7,    # Changed
        "memory_spark_probability": 0.2,
        "quest_poi_reference_probability": 0.1
    }
    
    success, error = manager.load_config(actor="admin", config_dict=new_config)
    assert success is True
    
    # Check audit log has delta summary
    audit_logs = manager.get_audit_logs(limit=1)
    latest_log = audit_logs[0]
    
    assert "quest_prob" in latest_log.delta_summary
    assert "poi_cooldown" in latest_log.delta_summary
    assert "0.3" in latest_log.delta_summary  # Old quest_prob
    assert "0.5" in latest_log.delta_summary  # New quest_prob
