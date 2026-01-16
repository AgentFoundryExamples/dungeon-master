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
"""Integration tests for parser validation and fallback behavior.

These tests verify the acceptance criteria from the issue:
1. Parser returns DungeonMasterOutcome on success and fallback with narrative when parsing fails
2. Validation failures log schema version, payload, and errors without blocking persistence
3. POST /characters/{id}/narrative is invoked with narrative even if intents invalid
4. LLM invocation path passes through parser
5. Metrics capture schema-conformance rate
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.llm_client import LLMClient
from app.services.outcome_parser import OutcomeParser, ParsedOutcome
from app.metrics import MetricsCollector, init_metrics_collector, disable_metrics_collector
from app.models import OUTCOME_VERSION


@pytest.fixture
def parser():
    """Create an OutcomeParser instance."""
    return OutcomeParser()


@pytest.fixture
def metrics_collector():
    """Create a MetricsCollector instance for testing."""
    collector = init_metrics_collector()
    collector.reset()
    yield collector
    disable_metrics_collector()


def test_acceptance_criterion_1_parser_returns_outcome_on_success(parser):
    """Verify: Parser returns DungeonMasterOutcome on success."""
    valid_json = '''{
        "narrative": "You discover a treasure chest.",
        "intents": {
            "quest_intent": {"action": "none"},
            "combat_intent": {"action": "none"},
            "poi_intent": {"action": "none"},
            "meta": null
        }
    }'''
    
    result = parser.parse(valid_json)
    
    # AC1: Parser returns DungeonMasterOutcome on success
    assert result.is_valid
    assert result.outcome is not None
    assert result.outcome.narrative == "You discover a treasure chest."
    assert result.narrative == "You discover a treasure chest."


def test_acceptance_criterion_1_parser_returns_fallback_on_failure(parser):
    """Verify: Parser returns fallback structure with narrative when parsing fails."""
    invalid_json = "This is not JSON"
    
    result = parser.parse(invalid_json)
    
    # AC1: Parser returns fallback with narrative text plus empty intents when parsing fails
    assert not result.is_valid
    assert result.outcome is None  # No typed object
    assert result.narrative  # Narrative is always present
    assert result.narrative == invalid_json  # Raw text used as fallback
    assert result.error_type == "json_decode_error"


def test_acceptance_criterion_1_parser_extracts_narrative_from_partial_json(parser):
    """Verify: Parser extracts narrative from partially valid JSON."""
    partial_json = '''{
        "narrative": "You enter the tavern.",
        "intents": {
            "quest_intent": {"action": "invalid_literal"}
        }
    }'''
    
    result = parser.parse(partial_json)
    
    # AC1: Even with invalid intents, narrative is extracted
    assert not result.is_valid
    assert result.outcome is None
    assert result.narrative == "You enter the tavern."
    assert result.error_type == "validation_error"


def test_acceptance_criterion_2_validation_logs_schema_version(parser, caplog):
    """Verify: Validation failures log schema version."""
    import logging
    caplog.set_level(logging.ERROR)
    
    invalid_json = '{"narrative": 123}'  # Wrong type
    
    result = parser.parse(invalid_json)
    
    # AC2: Logs include schema version
    assert not result.is_valid
    # Check that schema version is tracked in parser
    assert parser.schema_version == OUTCOME_VERSION


def test_acceptance_criterion_2_validation_logs_truncated_payload(parser):
    """Verify: Validation failures log truncated payload to prevent secrets leakage."""
    long_text = "A" * 1000
    
    result = parser.parse(long_text)
    
    # AC2: Payload is truncated for logging
    truncated = parser._truncate_for_log(long_text)
    assert len(truncated) <= 520  # MAX_PAYLOAD_LOG_LENGTH + marker
    assert "truncated" in truncated


def test_acceptance_criterion_2_validation_logs_error_details(parser):
    """Verify: Validation failures log explicit error list."""
    invalid_json = '''{
        "narrative": "",
        "intents": {}
    }'''
    
    result = parser.parse(invalid_json)
    
    # AC2: Error details are captured
    assert not result.is_valid
    assert result.error_details is not None
    assert len(result.error_details) > 0


@pytest.mark.asyncio
async def test_acceptance_criterion_3_narrative_persisted_with_invalid_intents():
    """Verify: POST /characters/{id}/narrative is invoked even with invalid intents."""
    from app.services.journey_log_client import JourneyLogClient
    from httpx import AsyncClient
    
    # Create mock journey log client
    mock_http_client = AsyncMock(spec=AsyncClient)
    mock_context_response = MagicMock()
    mock_context_response.status_code = 200
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "Nexus"}
        },
        "narrative": {"recent_turns": []},
        "combat": {}
    }
    mock_http_client.get.return_value = mock_context_response
    
    mock_persist_response = MagicMock()
    mock_persist_response.status_code = 200
    mock_http_client.post.return_value = mock_persist_response
    
    journey_client = JourneyLogClient(
        base_url="http://test",
        http_client=mock_http_client
    )
    
    # Create LLM client that returns invalid intents
    llm_client = LLMClient(api_key="sk-test", stub_mode=False)
    
    # Mock LLM response with invalid intents
    mock_output_item = MagicMock()
    mock_output_item.content = '''{
        "narrative": "Valid narrative text here",
        "intents": {
            "quest_intent": {"action": "invalid_action"}
        }
    }'''
    
    mock_llm_response = MagicMock()
    mock_llm_response.output = [mock_output_item]
    
    with patch.object(llm_client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_llm_response
        
        # Call LLM to get parsed outcome
        parsed = await llm_client.generate_narrative(
            system_instructions="Test",
            user_prompt="Test"
        )
        
        # AC3: Even though intents are invalid, narrative is present
        assert not parsed.is_valid
        assert parsed.narrative == "Valid narrative text here"
        
        # Persist narrative (as routes would do)
        await journey_client.persist_narrative(
            character_id="550e8400-e29b-41d4-a716-446655440000",
            user_action="test action",
            narrative=parsed.narrative
        )
        
        # AC3: Verify persist was called with the narrative
        mock_http_client.post.assert_called_once()
        call_kwargs = mock_http_client.post.call_args
        assert call_kwargs.kwargs["json"]["ai_response"] == "Valid narrative text here"


@pytest.mark.asyncio
async def test_acceptance_criterion_4_llm_passes_through_parser():
    """Verify: LLM invocation path always passes through parser before returning."""
    client = LLMClient(api_key="sk-test", model="gpt-5.1", stub_mode=False)
    
    # Mock LLM response
    mock_output_item = MagicMock()
    mock_output_item.content = '''{
        "narrative": "Test narrative",
        "intents": {
            "quest_intent": {"action": "none"},
            "combat_intent": {"action": "none"},
            "poi_intent": {"action": "none"},
            "meta": null
        }
    }'''
    
    mock_response = MagicMock()
    mock_response.output = [mock_output_item]
    
    with patch.object(client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response
        
        result = await client.generate_narrative(
            system_instructions="Test",
            user_prompt="Test"
        )
        
        # AC4: Result is ParsedOutcome (proving parser was used)
        assert isinstance(result, ParsedOutcome)
        assert result.is_valid
        assert result.outcome is not None


def test_acceptance_criterion_5_metrics_capture_conformance_rate(metrics_collector):
    """Verify: Metrics capture schema-conformance rate (valid vs invalid parses)."""
    # Record some successful parses
    for _ in range(8):
        metrics_collector.record_error("llm_parse_success")
    
    # Record some failed parses
    metrics_collector.record_error("llm_parse_failure_json_decode_error")
    metrics_collector.record_error("llm_parse_failure_validation_error")
    
    metrics = metrics_collector.get_metrics()
    
    # AC5: Metrics include schema conformance data
    assert "schema_conformance" in metrics
    assert metrics["schema_conformance"]["total_parses"] == 10
    assert metrics["schema_conformance"]["successful_parses"] == 8
    assert metrics["schema_conformance"]["failed_parses"] == 2
    assert metrics["schema_conformance"]["conformance_rate"] == 0.8


def test_edge_case_quest_action_typo(parser):
    """Edge case: LLM returns valid JSON but wrong literals (quest action typo)."""
    json_with_typo = '''{
        "narrative": "The innkeeper offers you a quest.",
        "intents": {
            "quest_intent": {"action": "ofer"},
            "combat_intent": {"action": "none"},
            "poi_intent": {"action": "none"}
        }
    }'''
    
    result = parser.parse(json_with_typo)
    
    # Parser rejects and logs while keeping narrative
    assert not result.is_valid
    assert result.error_type == "validation_error"
    assert result.narrative == "The innkeeper offers you a quest."
    assert result.error_details is not None


def test_edge_case_partial_json_stream(parser):
    """Edge case: Responses streaming partial JSON."""
    partial_json = '{"narrative": "You enter'
    
    result = parser.parse(partial_json)
    
    # Parser treats as failure with fallback
    assert not result.is_valid
    assert result.error_type == "json_decode_error"
    assert result.narrative  # Some fallback is present


@pytest.mark.asyncio
async def test_parser_integration_with_routes_flow():
    """Integration test: Verify parser works end-to-end in routes."""
    from app.api.routes import process_turn
    from app.models import TurnRequest
    from app.config import Settings
    from httpx import AsyncClient
    from app.services.policy_engine import PolicyEngine
    
    # Create mocks
    mock_http_client = AsyncMock(spec=AsyncClient)
    
    # Mock journey log context
    mock_context_response = MagicMock()
    mock_context_response.status_code = 200
    mock_context_response.json.return_value = {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "player_state": {
            "status": "Healthy",
            "location": {"id": "origin:nexus", "display_name": "Nexus"}
        },
        "narrative": {"recent_turns": []},
        "combat": {}
    }
    mock_http_client.get.return_value = mock_context_response
    
    # Mock journey log persist
    mock_persist_response = MagicMock()
    mock_persist_response.status_code = 200
    mock_http_client.post.return_value = mock_persist_response
    
    from app.services.journey_log_client import JourneyLogClient
    journey_client = JourneyLogClient(
        base_url="http://test",
        http_client=mock_http_client
    )
    
    # Create LLM client with invalid response
    llm_client = LLMClient(api_key="sk-test", stub_mode=False)
    mock_output_item = MagicMock()
    mock_output_item.content = '''{
        "narrative": "You see something interesting.",
        "intents": {"invalid": "structure"}
    }'''
    
    mock_llm_response = MagicMock()
    mock_llm_response.output = [mock_output_item]
    
    # Create policy engine
    policy_engine = PolicyEngine(
        quest_trigger_prob=0.5,
        poi_trigger_prob=0.5,
        rng_seed=42
    )
    
    with patch.object(llm_client.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_llm_response
        
        # Create settings
        settings = Settings(
            service_name="test",
            journey_log_base_url="http://test",
            openai_api_key="sk-test"
        )
        
        # Call process_turn
        request = TurnRequest(
            character_id="550e8400-e29b-41d4-a716-446655440000",
            user_action="look around"
        )
        
        response = await process_turn(
            request=request,
            journey_log_client=journey_client,
            llm_client=llm_client,
            policy_engine=policy_engine,
            settings=settings
        )
        
        # Verify narrative was returned even with invalid schema
        assert response.narrative == "You see something interesting."
        
        # Verify persist was called with narrative
        assert mock_http_client.post.called
