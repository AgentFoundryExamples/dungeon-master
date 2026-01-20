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
"""Shared test fixtures for Dungeon Master service.

This module provides pytest fixtures for testing the Dungeon Master service:
- test_env: Test environment variables
- client: FastAPI TestClient with mocked dependencies
- mock_journey_log_client: Mocked JourneyLogClient
- mock_llm_client: Mocked LLMClient

Usage:
    Run tests with pytest:
        pytest tests/
        pytest tests/test_turn_integration.py -v
        pytest tests/test_turn_integration.py::test_name -v

    Override fixtures in individual tests as needed:
        def test_custom(client):
            # Use the client fixture
            response = client.post("/turn", json={...})
            assert response.status_code == 200
"""

import asyncio
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import os


@pytest.fixture
def test_env():
    """Fixture providing test environment variables.
    
    Returns a dictionary of environment variables configured for testing:
    - JOURNEY_LOG_BASE_URL: Mock journey-log service URL
    - OPENAI_API_KEY: Test API key (not used in stub mode)
    - OPENAI_STUB_MODE: Enabled to avoid real API calls
    - Other configuration with safe test defaults
    
    Usage:
        def test_example(test_env):
            with patch.dict(os.environ, test_env):
                # Test code that uses environment variables
    """
    return {
        "JOURNEY_LOG_BASE_URL": "http://localhost:8000",
        "OPENAI_API_KEY": "sk-test-key-12345",
        "OPENAI_MODEL": "gpt-5.1",
        "OPENAI_STUB_MODE": "true",  # Use stub mode for tests
        "JOURNEY_LOG_TIMEOUT": "30",
        "OPENAI_TIMEOUT": "60",
        "JOURNEY_LOG_RECENT_N": "20",
        "HEALTH_CHECK_JOURNEY_LOG": "false",
        "SERVICE_NAME": "dungeon-master-test",
        "LOG_LEVEL": "INFO",
        "ENABLE_METRICS": "false"
    }


@pytest.fixture
def client(test_env):
    """Fixture providing FastAPI test client with mocked dependencies.
    
    Creates a TestClient with:
    - Test environment variables
    - Mocked HTTP client for journey-log requests
    - Mocked JourneyLogClient and LLMClient
    - LLM client in stub mode (no real API calls)
    
    The fixture overrides FastAPI dependency injection to provide
    test doubles for all external dependencies. It automatically
    cleans up after the test completes.
    
    Usage:
        def test_turn_endpoint(client):
            response = client.post("/turn", json={
                "character_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_action": "I search the room"
            })
            assert response.status_code == 200
    
    To mock specific responses, patch httpx.AsyncClient methods:
        def test_custom_response(client):
            with patch('httpx.AsyncClient.get') as mock_get:
                mock_get.return_value = mock_response
                response = client.post("/turn", json={...})
    """
    with patch.dict(os.environ, test_env, clear=True):
        # Clear the settings cache
        from app.config import get_settings
        get_settings.cache_clear()
        
        # Import dependencies FIRST before importing app
        from app.api.routes import (
            get_http_client,
            get_journey_log_client,
            get_llm_client,
            get_policy_engine,
            get_turn_orchestrator,
            get_character_rate_limiter,
            get_llm_semaphore
        )
        
        from app.main import app
        from httpx import AsyncClient
        from app.services.journey_log_client import JourneyLogClient
        from app.services.llm_client import LLMClient
        from app.services.policy_engine import PolicyEngine
        from app.services.turn_orchestrator import TurnOrchestrator
        from app.prompting.prompt_builder import PromptBuilder
        from app.resilience import RateLimiter
        
        # Create test HTTP client
        test_http_client = AsyncClient()
        
        try:
            # Create test service clients
            settings = get_settings()
            test_journey_log_client = JourneyLogClient(
                base_url=settings.journey_log_base_url,
                http_client=test_http_client,
                timeout=settings.journey_log_timeout,
                recent_n_default=settings.journey_log_recent_n
            )
            test_llm_client = LLMClient(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                timeout=settings.openai_timeout,
                stub_mode=True  # Always use stub mode in tests
            )
            test_policy_engine = PolicyEngine(
                quest_trigger_prob=settings.quest_trigger_prob,
                quest_cooldown_turns=settings.quest_cooldown_turns,
                poi_trigger_prob=settings.poi_trigger_prob,
                poi_cooldown_turns=settings.poi_cooldown_turns,
                rng_seed=settings.rng_seed
            )
            test_prompt_builder = PromptBuilder()
            test_turn_orchestrator = TurnOrchestrator(
                policy_engine=test_policy_engine,
                llm_client=test_llm_client,
                journey_log_client=test_journey_log_client,
                prompt_builder=test_prompt_builder
            )
            test_rate_limiter = RateLimiter(max_rate=10.0)  # 10 requests per second
            test_llm_semaphore = asyncio.Semaphore(5)  # Allow 5 concurrent LLM calls
            
            # Override dependencies (don't clear - just overwrite the ones from main.py)
            app.dependency_overrides[get_http_client] = lambda: test_http_client
            app.dependency_overrides[get_journey_log_client] = lambda: test_journey_log_client
            app.dependency_overrides[get_llm_client] = lambda: test_llm_client
            app.dependency_overrides[get_policy_engine] = lambda: test_policy_engine
            app.dependency_overrides[get_turn_orchestrator] = lambda: test_turn_orchestrator
            app.dependency_overrides[get_character_rate_limiter] = lambda: test_rate_limiter
            app.dependency_overrides[get_llm_semaphore] = lambda: test_llm_semaphore
            
            with TestClient(app) as client:
                yield client
        finally:
            # Cleanup - close async client and clear overrides
            asyncio.run(test_http_client.aclose())
            app.dependency_overrides.clear()


@pytest.fixture
def mock_journey_log_context():
    """Fixture providing a mock journey-log context response.
    
    Returns a dictionary representing a typical context response from
    the journey-log service. Can be customized in tests as needed.
    
    Usage:
        def test_example(mock_journey_log_context):
            # Customize as needed
            mock_journey_log_context["player_state"]["status"] = "Wounded"
            # Use in test
    """
    return {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "identity": {"name": "Aria", "race": "Elf", "class": "Ranger"},
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "The Nexus"}
        },
        "quest": None,
        "combat": {"active": False, "state": None},
        "narrative": {
            "recent_turns": []
        }
    }


@pytest.fixture
def client_with_failed_quest_roll(test_env):
    """Fixture providing a test client with a policy engine that always fails quest rolls.
    
    This fixture is useful for testing that failed quest rolls block quest propagation
    even if the LLM suggests a quest.
    
    Usage:
        def test_example(client_with_failed_quest_roll):
            response = client_with_failed_quest_roll.post("/turn", json={...})
    """
    with patch.dict(os.environ, test_env, clear=True):
        from app.config import get_settings
        get_settings.cache_clear()
        
        from app.api.routes import (
            get_http_client,
            get_journey_log_client,
            get_llm_client,
            get_policy_engine,
            get_turn_orchestrator,
            get_character_rate_limiter,
            get_llm_semaphore
        )
        from app.main import app
        from httpx import AsyncClient
        from app.services.journey_log_client import JourneyLogClient
        from app.services.llm_client import LLMClient
        from app.services.policy_engine import PolicyEngine
        from app.services.turn_orchestrator import TurnOrchestrator
        from app.prompting.prompt_builder import PromptBuilder
        from app.resilience import RateLimiter
        
        test_http_client = AsyncClient()
        
        try:
            settings = get_settings()
            test_journey_log_client = JourneyLogClient(
                base_url=settings.journey_log_base_url,
                http_client=test_http_client,
                timeout=settings.journey_log_timeout,
                recent_n_default=settings.journey_log_recent_n
            )
            test_llm_client = LLMClient(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                timeout=settings.openai_timeout,
                stub_mode=True
            )
            # Policy engine that always fails quest rolls
            test_policy_engine = PolicyEngine(
                quest_trigger_prob=0.0,  # Always fail quest rolls
                quest_cooldown_turns=0,
                poi_trigger_prob=1.0,
                poi_cooldown_turns=0,
                rng_seed=42
            )
            test_prompt_builder = PromptBuilder()
            test_turn_orchestrator = TurnOrchestrator(
                policy_engine=test_policy_engine,
                llm_client=test_llm_client,
                journey_log_client=test_journey_log_client,
                prompt_builder=test_prompt_builder
            )
            test_rate_limiter = RateLimiter(max_rate=10.0)
            test_llm_semaphore = asyncio.Semaphore(5)
            
            app.dependency_overrides[get_http_client] = lambda: test_http_client
            app.dependency_overrides[get_journey_log_client] = lambda: test_journey_log_client
            app.dependency_overrides[get_llm_client] = lambda: test_llm_client
            app.dependency_overrides[get_policy_engine] = lambda: test_policy_engine
            app.dependency_overrides[get_turn_orchestrator] = lambda: test_turn_orchestrator
            app.dependency_overrides[get_character_rate_limiter] = lambda: test_rate_limiter
            app.dependency_overrides[get_llm_semaphore] = lambda: test_llm_semaphore
            
            with TestClient(app) as client:
                yield client
        finally:
            asyncio.run(test_http_client.aclose())
            app.dependency_overrides.clear()


@pytest.fixture
def client_with_failed_poi_roll(test_env):
    """Fixture providing a test client with a policy engine that always fails POI rolls.
    
    This fixture is useful for testing that failed POI rolls block POI propagation
    even if the LLM suggests a POI.
    
    Usage:
        def test_example(client_with_failed_poi_roll):
            response = client_with_failed_poi_roll.post("/turn", json={...})
    """
    with patch.dict(os.environ, test_env, clear=True):
        from app.config import get_settings
        get_settings.cache_clear()
        
        from app.api.routes import (
            get_http_client,
            get_journey_log_client,
            get_llm_client,
            get_policy_engine,
            get_turn_orchestrator,
            get_character_rate_limiter,
            get_llm_semaphore
        )
        from app.main import app
        from httpx import AsyncClient
        from app.services.journey_log_client import JourneyLogClient
        from app.services.llm_client import LLMClient
        from app.services.policy_engine import PolicyEngine
        from app.services.turn_orchestrator import TurnOrchestrator
        from app.prompting.prompt_builder import PromptBuilder
        from app.resilience import RateLimiter
        
        test_http_client = AsyncClient()
        
        try:
            settings = get_settings()
            test_journey_log_client = JourneyLogClient(
                base_url=settings.journey_log_base_url,
                http_client=test_http_client,
                timeout=settings.journey_log_timeout,
                recent_n_default=settings.journey_log_recent_n
            )
            test_llm_client = LLMClient(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                timeout=settings.openai_timeout,
                stub_mode=True
            )
            # Policy engine that always fails POI rolls
            test_policy_engine = PolicyEngine(
                quest_trigger_prob=1.0,
                quest_cooldown_turns=0,
                poi_trigger_prob=0.0,  # Always fail POI rolls
                poi_cooldown_turns=0,
                rng_seed=42
            )
            test_prompt_builder = PromptBuilder()
            test_turn_orchestrator = TurnOrchestrator(
                policy_engine=test_policy_engine,
                llm_client=test_llm_client,
                journey_log_client=test_journey_log_client,
                prompt_builder=test_prompt_builder
            )
            test_rate_limiter = RateLimiter(max_rate=10.0)
            test_llm_semaphore = asyncio.Semaphore(5)
            
            app.dependency_overrides[get_http_client] = lambda: test_http_client
            app.dependency_overrides[get_journey_log_client] = lambda: test_journey_log_client
            app.dependency_overrides[get_llm_client] = lambda: test_llm_client
            app.dependency_overrides[get_policy_engine] = lambda: test_policy_engine
            app.dependency_overrides[get_turn_orchestrator] = lambda: test_turn_orchestrator
            app.dependency_overrides[get_character_rate_limiter] = lambda: test_rate_limiter
            app.dependency_overrides[get_llm_semaphore] = lambda: test_llm_semaphore
            
            with TestClient(app) as client:
                yield client
        finally:
            asyncio.run(test_http_client.aclose())
            app.dependency_overrides.clear()


@pytest.fixture
def client_with_deterministic_seed(test_env):
    """Fixture providing a test client with a deterministic policy engine seed.
    
    This fixture is useful for testing that deterministic seeds produce consistent
    policy decision results across multiple requests.
    
    Usage:
        def test_example(client_with_deterministic_seed):
            response = client_with_deterministic_seed.post("/turn", json={...})
    """
    with patch.dict(os.environ, test_env, clear=True):
        from app.config import get_settings
        get_settings.cache_clear()
        
        from app.api.routes import (
            get_http_client,
            get_journey_log_client,
            get_llm_client,
            get_policy_engine,
            get_turn_orchestrator,
            get_character_rate_limiter,
            get_llm_semaphore
        )
        from app.main import app
        from httpx import AsyncClient
        from app.services.journey_log_client import JourneyLogClient
        from app.services.llm_client import LLMClient
        from app.services.policy_engine import PolicyEngine
        from app.services.turn_orchestrator import TurnOrchestrator
        from app.prompting.prompt_builder import PromptBuilder
        from app.resilience import RateLimiter
        
        test_http_client = AsyncClient()
        
        try:
            settings = get_settings()
            test_journey_log_client = JourneyLogClient(
                base_url=settings.journey_log_base_url,
                http_client=test_http_client,
                timeout=settings.journey_log_timeout,
                recent_n_default=settings.journey_log_recent_n
            )
            test_llm_client = LLMClient(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                timeout=settings.openai_timeout,
                stub_mode=True
            )
            # Policy engine with deterministic seed
            test_policy_engine = PolicyEngine(
                quest_trigger_prob=0.5,
                quest_cooldown_turns=0,
                poi_trigger_prob=0.5,
                poi_cooldown_turns=0,
                rng_seed=999  # Deterministic seed
            )
            test_prompt_builder = PromptBuilder()
            test_turn_orchestrator = TurnOrchestrator(
                policy_engine=test_policy_engine,
                llm_client=test_llm_client,
                journey_log_client=test_journey_log_client,
                prompt_builder=test_prompt_builder
            )
            test_rate_limiter = RateLimiter(max_rate=10.0)
            test_llm_semaphore = asyncio.Semaphore(5)
            
            app.dependency_overrides[get_http_client] = lambda: test_http_client
            app.dependency_overrides[get_journey_log_client] = lambda: test_journey_log_client
            app.dependency_overrides[get_llm_client] = lambda: test_llm_client
            app.dependency_overrides[get_policy_engine] = lambda: test_policy_engine
            app.dependency_overrides[get_turn_orchestrator] = lambda: test_turn_orchestrator
            app.dependency_overrides[get_character_rate_limiter] = lambda: test_rate_limiter
            app.dependency_overrides[get_llm_semaphore] = lambda: test_llm_semaphore
            
            with TestClient(app) as client:
                yield client
        finally:
            asyncio.run(test_http_client.aclose())
            app.dependency_overrides.clear()
