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
"""Tests for configuration validation including PolicyEngine parameters."""

import pytest
from unittest.mock import patch
import os
from pydantic import ValidationError


def test_config_policy_engine_defaults():
    """Test that PolicyEngine config loads with default values."""
    from app.config import Settings, get_settings
    
    get_settings.cache_clear()
    
    test_env = {
        "JOURNEY_LOG_BASE_URL": "http://localhost:8000",
        "OPENAI_API_KEY": "sk-test-key"
    }
    
    with patch.dict(os.environ, test_env, clear=True):
        settings = Settings(_env_file=None)
        
        # Check PolicyEngine defaults
        assert settings.quest_trigger_prob == 0.3
        assert settings.quest_cooldown_turns == 5
        assert settings.poi_trigger_prob == 0.2
        assert settings.poi_cooldown_turns == 3
        assert settings.rng_seed is None


def test_config_policy_engine_custom_values():
    """Test that PolicyEngine config accepts custom values."""
    from app.config import Settings, get_settings
    
    get_settings.cache_clear()
    
    test_env = {
        "JOURNEY_LOG_BASE_URL": "http://localhost:8000",
        "OPENAI_API_KEY": "sk-test-key",
        "QUEST_TRIGGER_PROB": "0.5",
        "QUEST_COOLDOWN_TURNS": "10",
        "POI_TRIGGER_PROB": "0.4",
        "POI_COOLDOWN_TURNS": "7",
        "RNG_SEED": "42"
    }
    
    with patch.dict(os.environ, test_env, clear=True):
        settings = Settings(_env_file=None)
        
        assert settings.quest_trigger_prob == 0.5
        assert settings.quest_cooldown_turns == 10
        assert settings.poi_trigger_prob == 0.4
        assert settings.poi_cooldown_turns == 7
        assert settings.rng_seed == 42


def test_config_policy_engine_probability_validation():
    """Test that probability values are validated to [0, 1] range."""
    from app.config import Settings
    
    # Test probability > 1.0
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        Settings(
            journey_log_base_url="http://localhost:8000",
            openai_api_key="sk-test",
            quest_trigger_prob=1.5
        )
    
    # Test probability < 0.0
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Settings(
            journey_log_base_url="http://localhost:8000",
            openai_api_key="sk-test",
            poi_trigger_prob=-0.5
        )


def test_config_policy_engine_probability_edge_cases():
    """Test that probability edge values (0.0, 1.0) are accepted."""
    from app.config import Settings
    
    settings = Settings(
        journey_log_base_url="http://localhost:8000",
        openai_api_key="sk-test",
        quest_trigger_prob=0.0,
        poi_trigger_prob=1.0
    )
    
    assert settings.quest_trigger_prob == 0.0
    assert settings.poi_trigger_prob == 1.0


def test_config_policy_engine_cooldown_validation():
    """Test that cooldown values are validated."""
    from app.config import Settings
    
    # Test negative cooldown (should be rejected)
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Settings(
            journey_log_base_url="http://localhost:8000",
            openai_api_key="sk-test",
            quest_cooldown_turns=-5
        )


def test_config_policy_engine_zero_cooldown():
    """Test that zero cooldown is accepted."""
    from app.config import Settings
    
    settings = Settings(
        journey_log_base_url="http://localhost:8000",
        openai_api_key="sk-test",
        quest_cooldown_turns=0,
        poi_cooldown_turns=0
    )
    
    assert settings.quest_cooldown_turns == 0
    assert settings.poi_cooldown_turns == 0


def test_config_policy_engine_rng_seed_optional():
    """Test that RNG seed is optional."""
    from app.config import Settings
    
    # Without seed
    settings1 = Settings(
        journey_log_base_url="http://localhost:8000",
        openai_api_key="sk-test"
    )
    assert settings1.rng_seed is None
    
    # With seed
    settings2 = Settings(
        journey_log_base_url="http://localhost:8000",
        openai_api_key="sk-test",
        rng_seed=12345
    )
    assert settings2.rng_seed == 12345


def test_config_integration_with_policy_engine():
    """Test that config can be used to initialize PolicyEngine."""
    from app.config import Settings
    from app.services.policy_engine import PolicyEngine
    
    settings = Settings(
        journey_log_base_url="http://localhost:8000",
        openai_api_key="sk-test",
        quest_trigger_prob=0.4,
        quest_cooldown_turns=8,
        poi_trigger_prob=0.3,
        poi_cooldown_turns=6,
        rng_seed=999
    )
    
    # Initialize PolicyEngine with config
    engine = PolicyEngine(
        quest_trigger_prob=settings.quest_trigger_prob,
        quest_cooldown_turns=settings.quest_cooldown_turns,
        poi_trigger_prob=settings.poi_trigger_prob,
        poi_cooldown_turns=settings.poi_cooldown_turns,
        rng_seed=settings.rng_seed
    )
    
    assert engine.quest_trigger_prob == 0.4
    assert engine.quest_cooldown_turns == 8
    assert engine.poi_trigger_prob == 0.3
    assert engine.poi_cooldown_turns == 6
    assert engine.rng_seed == 999
