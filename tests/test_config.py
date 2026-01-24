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


def test_config_policy_engine_cooldown_accepts_negative():
    """Test that negative cooldown values are accepted (they skip waiting periods)."""
    from app.config import Settings
    
    settings = Settings(
        journey_log_base_url="http://localhost:8000",
        openai_api_key="sk-test",
        quest_cooldown_turns=-5,
        poi_cooldown_turns=-3
    )
    
    assert settings.quest_cooldown_turns == -5
    assert settings.poi_cooldown_turns == -3


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


def test_config_gcp_defaults():
    """Test that GCP config loads with default values."""
    from app.config import Settings, get_settings
    
    get_settings.cache_clear()
    
    test_env = {
        "JOURNEY_LOG_BASE_URL": "http://localhost:8000",
        "OPENAI_API_KEY": "sk-test-key"
    }
    
    with patch.dict(os.environ, test_env, clear=True):
        settings = Settings(_env_file=None)
        
        # Check GCP defaults
        assert settings.gcp_project_id is None
        assert settings.gcp_region == "us-central1"
        assert settings.cloud_run_service == "dungeon-master"
        assert settings.artifact_repo == "dungeon-master"
        assert settings.secret_manager_config == "disabled"


def test_config_gcp_custom_values():
    """Test that GCP config accepts custom values."""
    from app.config import Settings, get_settings
    
    get_settings.cache_clear()
    
    test_env = {
        "JOURNEY_LOG_BASE_URL": "http://localhost:8000",
        "OPENAI_API_KEY": "sk-test-key",
        "GCP_PROJECT_ID": "my-project-123",
        "GCP_REGION": "us-east1",
        "CLOUD_RUN_SERVICE": "dm-service",
        "ARTIFACT_REPO": "my-repo",
        "SECRET_MANAGER_CONFIG": "env_vars"
    }
    
    with patch.dict(os.environ, test_env, clear=True):
        settings = Settings(_env_file=None)
        
        assert settings.gcp_project_id == "my-project-123"
        assert settings.gcp_region == "us-east1"
        assert settings.cloud_run_service == "dm-service"
        assert settings.artifact_repo == "my-repo"
        assert settings.secret_manager_config == "env_vars"


def test_config_gcp_project_id_validation():
    """Test that GCP project ID is validated."""
    from app.config import Settings
    
    # Valid project IDs
    settings = Settings(
        journey_log_base_url="http://localhost:8000",
        openai_api_key="sk-test",
        gcp_project_id="my-project-123"
    )
    assert settings.gcp_project_id == "my-project-123"
    
    # Empty project ID should be None (valid for local dev)
    settings = Settings(
        journey_log_base_url="http://localhost:8000",
        openai_api_key="sk-test",
        gcp_project_id=""
    )
    assert settings.gcp_project_id is None
    
    # Too short
    with pytest.raises(ValidationError, match="6-30 characters"):
        Settings(
            journey_log_base_url="http://localhost:8000",
            openai_api_key="sk-test",
            gcp_project_id="short"
        )
    
    # Too long
    with pytest.raises(ValidationError, match="6-30 characters"):
        Settings(
            journey_log_base_url="http://localhost:8000",
            openai_api_key="sk-test",
            gcp_project_id="a" * 31
        )
    
    # Must start with letter
    with pytest.raises(ValidationError, match="must start with a letter"):
        Settings(
            journey_log_base_url="http://localhost:8000",
            openai_api_key="sk-test",
            gcp_project_id="123-project"
        )
    
    # Invalid characters (uppercase)
    with pytest.raises(ValidationError, match="lowercase letters, digits, and hyphens"):
        Settings(
            journey_log_base_url="http://localhost:8000",
            openai_api_key="sk-test",
            gcp_project_id="My-Project-123"
        )


def test_config_gcp_region_validation():
    """Test that GCP region is validated."""
    from app.config import Settings
    
    # Valid regions
    valid_regions = ["us-central1", "us-east1", "europe-west1", "asia-northeast1"]
    for region in valid_regions:
        settings = Settings(
            journey_log_base_url="http://localhost:8000",
            openai_api_key="sk-test",
            gcp_region=region
        )
        assert settings.gcp_region == region
    
    # Empty region
    with pytest.raises(ValidationError, match="cannot be empty"):
        Settings(
            journey_log_base_url="http://localhost:8000",
            openai_api_key="sk-test",
            gcp_region=""
        )


def test_config_cloud_run_service_validation():
    """Test that Cloud Run service name is validated."""
    from app.config import Settings
    
    # Valid service name
    settings = Settings(
        journey_log_base_url="http://localhost:8000",
        openai_api_key="sk-test",
        cloud_run_service="my-service-123"
    )
    assert settings.cloud_run_service == "my-service-123"
    
    # Empty service name
    with pytest.raises(ValidationError, match="cannot be empty"):
        Settings(
            journey_log_base_url="http://localhost:8000",
            openai_api_key="sk-test",
            cloud_run_service=""
        )
    
    # Too long (> 63 characters)
    with pytest.raises(ValidationError, match="max 63 characters"):
        Settings(
            journey_log_base_url="http://localhost:8000",
            openai_api_key="sk-test",
            cloud_run_service="a" * 64
        )
    
    # Invalid characters (uppercase)
    with pytest.raises(ValidationError, match="lowercase letters, digits, and hyphens"):
        Settings(
            journey_log_base_url="http://localhost:8000",
            openai_api_key="sk-test",
            cloud_run_service="MyService"
        )


def test_config_artifact_repo_validation():
    """Test that Artifact Registry repo name is validated."""
    from app.config import Settings
    
    # Valid repo name
    settings = Settings(
        journey_log_base_url="http://localhost:8000",
        openai_api_key="sk-test",
        artifact_repo="my-repo-123"
    )
    assert settings.artifact_repo == "my-repo-123"
    
    # Empty repo name
    with pytest.raises(ValidationError, match="cannot be empty"):
        Settings(
            journey_log_base_url="http://localhost:8000",
            openai_api_key="sk-test",
            artifact_repo=""
        )
    
    # Invalid characters (uppercase)
    with pytest.raises(ValidationError, match="lowercase letters, digits, and hyphens"):
        Settings(
            journey_log_base_url="http://localhost:8000",
            openai_api_key="sk-test",
            artifact_repo="MyRepo"
        )


def test_config_secret_manager_validation():
    """Test that Secret Manager config mode is validated."""
    from app.config import Settings
    
    # Valid modes
    valid_modes = ["disabled", "env_vars", "volume"]
    for mode in valid_modes:
        settings = Settings(
            journey_log_base_url="http://localhost:8000",
            openai_api_key="sk-test",
            secret_manager_config=mode
        )
        assert settings.secret_manager_config == mode
    
    # Invalid mode
    with pytest.raises(ValidationError, match="must be one of"):
        Settings(
            journey_log_base_url="http://localhost:8000",
            openai_api_key="sk-test",
            secret_manager_config="invalid_mode"
        )
