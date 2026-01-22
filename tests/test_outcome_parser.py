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
"""Tests for OutcomeParser with validation and fallback behavior."""

import pytest
import json
from app.services.outcome_parser import OutcomeParser
from app.models import OUTCOME_VERSION


@pytest.fixture
def parser():
    """Create an OutcomeParser instance for testing."""
    return OutcomeParser()


@pytest.fixture
def valid_outcome_json():
    """Valid DungeonMasterOutcome JSON."""
    return {
        "narrative": "You discover a hidden treasure chest in the corner.",
        "intents": {
            "quest_intent": {"action": "none"},
            "combat_intent": {"action": "none"},
            "poi_intent": {"action": "none"},
            "meta": None
        }
    }


@pytest.fixture
def valid_outcome_with_intents_json():
    """Valid DungeonMasterOutcome JSON with full intents."""
    return {
        "narrative": "You enter the tavern and meet a grizzled innkeeper.",
        "intents": {
            "quest_intent": {
                "action": "offer",
                "quest_title": "Find My Daughter",
                "quest_summary": "The innkeeper's daughter is missing"
            },
            "combat_intent": {"action": "none"},
            "poi_intent": {
                "action": "create",
                "name": "The Rusty Tankard",
                "description": "A weathered tavern"
            },
            "meta": {
                "player_mood": "curious",
                "pacing_hint": "normal"
            }
        }
    }


def test_parse_valid_outcome(parser, valid_outcome_json):
    """Test parsing a valid outcome succeeds."""
    json_str = json.dumps(valid_outcome_json)
    
    result = parser.parse(json_str)
    
    assert result.is_valid
    assert result.outcome is not None
    assert result.outcome.narrative == "You discover a hidden treasure chest in the corner."
    assert result.narrative == "You discover a hidden treasure chest in the corner."
    assert result.error_type is None
    assert result.error_details is None


def test_parse_valid_outcome_with_full_intents(parser, valid_outcome_with_intents_json):
    """Test parsing a valid outcome with full intents succeeds."""
    json_str = json.dumps(valid_outcome_with_intents_json)
    
    result = parser.parse(json_str)
    
    assert result.is_valid
    assert result.outcome is not None
    assert result.outcome.narrative == "You enter the tavern and meet a grizzled innkeeper."
    assert result.narrative == "You enter the tavern and meet a grizzled innkeeper."
    assert result.outcome.intents.quest_intent is not None
    assert result.outcome.intents.quest_intent.action == "offer"
    assert result.outcome.intents.poi_intent is not None
    assert result.outcome.intents.poi_intent.action == "create"


def test_parse_invalid_json(parser):
    """Test parsing invalid JSON returns fallback narrative."""
    invalid_json = "This is not JSON at all"
    
    result = parser.parse(invalid_json)
    
    assert not result.is_valid
    assert result.outcome is None
    assert result.error_type == "json_decode_error"
    assert result.error_details is not None
    assert len(result.error_details) > 0
    # Should use raw text as fallback
    assert result.narrative == invalid_json


def test_parse_partial_json(parser):
    """Test parsing truncated JSON returns fallback narrative."""
    partial_json = '{"narrative": "You discover'
    
    result = parser.parse(partial_json)
    
    assert not result.is_valid
    assert result.outcome is None
    assert result.error_type == "json_decode_error"
    assert result.error_details is not None


def test_parse_missing_narrative_field(parser):
    """Test parsing JSON without narrative field fails validation."""
    invalid_json = json.dumps({
        "intents": {
            "quest_intent": {"action": "none"},
            "combat_intent": {"action": "none"},
            "poi_intent": {"action": "none"}
        }
    })
    
    result = parser.parse(invalid_json)
    
    assert not result.is_valid
    assert result.outcome is None
    assert result.error_type == "validation_error"
    assert result.error_details is not None
    assert any("narrative" in err for err in result.error_details)
    # Should use fallback narrative
    assert "[Unable to generate narrative" in result.narrative


def test_parse_empty_narrative(parser):
    """Test parsing JSON with empty narrative fails validation."""
    invalid_json = json.dumps({
        "narrative": "",
        "intents": {
            "quest_intent": {"action": "none"},
            "combat_intent": {"action": "none"},
            "poi_intent": {"action": "none"}
        }
    })
    
    result = parser.parse(invalid_json)
    
    assert not result.is_valid
    assert result.outcome is None
    assert result.error_type == "validation_error"


def test_parse_missing_intents_field(parser):
    """Test parsing JSON without intents field fails validation."""
    invalid_json = json.dumps({
        "narrative": "You discover a treasure chest."
    })
    
    result = parser.parse(invalid_json)
    
    assert not result.is_valid
    assert result.outcome is None
    assert result.error_type == "validation_error"
    assert result.error_details is not None
    assert any("intents" in err for err in result.error_details)
    # Should extract narrative from partial JSON
    assert result.narrative == "You discover a treasure chest."


def test_parse_invalid_action_literal(parser):
    """Test parsing JSON with invalid action literal fails validation."""
    invalid_json = json.dumps({
        "narrative": "You see a quest giver.",
        "intents": {
            "quest_intent": {"action": "invalid_action"},  # Invalid literal
            "combat_intent": {"action": "none"},
            "poi_intent": {"action": "none"}
        }
    })
    
    result = parser.parse(invalid_json)
    
    assert not result.is_valid
    assert result.outcome is None
    assert result.error_type == "validation_error"
    assert result.error_details is not None
    # Should extract narrative from partial JSON
    assert result.narrative == "You see a quest giver."


def test_parse_wrong_field_types(parser):
    """Test parsing JSON with wrong field types fails validation."""
    invalid_json = json.dumps({
        "narrative": 123,  # Should be string
        "intents": {
            "quest_intent": {"action": "none"}
        }
    })
    
    result = parser.parse(invalid_json)
    
    assert not result.is_valid
    assert result.outcome is None
    assert result.error_type == "validation_error"
    # Should use fallback since narrative is not a string
    assert "[Unable to generate narrative" in result.narrative


def test_parse_additional_properties_accepted(parser):
    """Test that additional properties don't cause validation failure.
    
    Note: The schema may allow additional properties depending on
    strict mode configuration. This test documents the behavior.
    """
    json_with_extra = json.dumps({
        "narrative": "You discover a chest.",
        "intents": {
            "quest_intent": {"action": "none"},
            "combat_intent": {"action": "none"},
            "poi_intent": {"action": "none"}
        },
        "extra_field": "this should not break parsing"
    })
    
    result = parser.parse(json_with_extra)
    
    # Depending on strict mode, this may pass or fail
    # The parser should handle either case gracefully
    if result.is_valid:
        assert result.narrative == "You discover a chest."
    else:
        # If strict mode rejects additional properties, fallback should work
        assert result.narrative == "You discover a chest."





def test_truncate_for_log(parser):
    """Test that long payloads are truncated for logging."""
    long_text = "A" * 1000
    
    truncated = parser._truncate_for_log(long_text)
    
    assert len(truncated) <= 520  # MAX_PAYLOAD_LOG_LENGTH + truncation marker
    assert "truncated" in truncated


def test_extract_validation_errors(parser):
    """Test extraction of validation error details."""
    from pydantic import ValidationError, BaseModel, Field
    
    class TestModel(BaseModel):
        required_field: str = Field(..., min_length=1)
    
    try:
        TestModel.model_validate({"required_field": ""})
    except ValidationError as e:
        errors = parser._extract_validation_errors(e)
        
        assert len(errors) > 0
        assert "required_field" in errors[0]


def test_extract_narrative_from_partial_json(parser):
    """Test extracting narrative from partially valid JSON."""
    partial_json = {
        "narrative": "This is the narrative text.",
        "invalid_field": "extra"
    }
    raw_text = json.dumps(partial_json)
    
    narrative = parser._extract_narrative_from_json(partial_json, raw_text)
    
    assert narrative == "This is the narrative text."


def test_extract_fallback_narrative_from_raw_text(parser):
    """Test fallback narrative extraction from raw text."""
    # Text with narrative field embedded
    raw_text = 'Some text before {"narrative": "The extracted narrative"} some text after'
    
    narrative = parser._extract_fallback_narrative(raw_text)
    
    assert narrative == "The extracted narrative"


def test_extract_fallback_narrative_plain_text(parser):
    """Test fallback narrative extraction from plain text."""
    plain_text = "This is just plain narrative text without JSON."
    
    narrative = parser._extract_fallback_narrative(plain_text)
    
    assert narrative == plain_text


def test_extract_fallback_narrative_too_short(parser):
    """Test fallback narrative for very short text."""
    short_text = "Error"
    
    narrative = parser._extract_fallback_narrative(short_text)
    
    assert "[Unable to generate narrative" in narrative


def test_extract_fallback_narrative_truncates_long_text(parser):
    """Test that very long raw text is truncated."""
    long_text = "A" * 10000
    
    narrative = parser._extract_fallback_narrative(long_text)
    
    assert len(narrative) <= 5003  # 5000 + "..."
    assert narrative.endswith("...")


def test_parser_uses_outcome_version(parser):
    """Test that parser tracks schema version."""
    assert parser.schema_version == OUTCOME_VERSION


def test_parse_with_nested_validation_error(parser):
    """Test parsing with nested validation errors in intents."""
    invalid_json = json.dumps({
        "narrative": "You encounter enemies.",
        "intents": {
            "quest_intent": {"action": "none"},
            "combat_intent": {
                "action": "start",
                "enemies": [
                    {"name": "Goblin", "threat": "invalid_threat_level"}  # Invalid field
                ]
            },
            "poi_intent": {"action": "none"}
        }
    })
    
    result = parser.parse(invalid_json)
    
    # Should still extract narrative even with nested errors
    assert result.narrative == "You encounter enemies."
    if not result.is_valid:
        assert result.error_details is not None


def test_parse_empty_string(parser):
    """Test parsing empty string."""
    result = parser.parse("")
    
    assert not result.is_valid
    assert result.error_type == "json_decode_error"
    assert "[Unable to generate narrative" in result.narrative


def test_parse_whitespace_only(parser):
    """Test parsing whitespace-only string."""
    result = parser.parse("   \n\t  ")
    
    assert not result.is_valid
    assert result.error_type == "json_decode_error"
    assert "[Unable to generate narrative" in result.narrative


def test_parse_preserves_narrative_whitespace(parser, valid_outcome_json):
    """Test that narrative whitespace is preserved correctly."""
    valid_outcome_json["narrative"] = "  Leading and trailing spaces  "
    json_str = json.dumps(valid_outcome_json)
    
    result = parser.parse(json_str)
    
    assert result.is_valid
    # Pydantic should preserve the spaces in the narrative field
    assert result.narrative == "  Leading and trailing spaces  "
