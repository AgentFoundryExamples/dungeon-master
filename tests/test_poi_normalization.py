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
"""Tests for POIIntent normalization in OutcomeParser.

This module verifies that the OutcomeParser.normalize_poi_intent() method
provides deterministic fallbacks when the policy engine triggers a POI
opportunity but the LLM intent is missing or incomplete.
"""

import pytest
from app.services.outcome_parser import OutcomeParser
from app.models import POIIntent


def test_normalize_poi_intent_none_no_policy():
    """When poi_intent is None and policy didn't trigger, return None."""
    parser = OutcomeParser()
    result = parser.normalize_poi_intent(
        poi_intent=None,
        policy_triggered=False
    )
    assert result is None


def test_normalize_poi_intent_none_with_policy():
    """When poi_intent is None but policy triggered, create minimal create intent."""
    parser = OutcomeParser()
    result = parser.normalize_poi_intent(
        poi_intent=None,
        policy_triggered=True
    )
    assert result is not None
    assert result.action == "create"
    assert result.name == "A Notable Location"
    assert result.description == "An interesting location worth remembering."
    assert result.reference_tags == []


def test_normalize_poi_intent_none_with_policy_uses_location():
    """When poi_intent is None but policy triggered, use location_name if provided."""
    parser = OutcomeParser()
    result = parser.normalize_poi_intent(
        poi_intent=None,
        policy_triggered=True,
        location_name="The Ancient Temple"
    )
    assert result is not None
    assert result.action == "create"
    assert result.name == "The Ancient Temple"
    assert result.description == "An interesting location worth remembering."


def test_normalize_poi_intent_action_none():
    """When action is 'none', return intent as-is."""
    parser = OutcomeParser()
    intent = POIIntent(action="none")
    result = parser.normalize_poi_intent(
        poi_intent=intent,
        policy_triggered=True
    )
    assert result == intent


def test_normalize_poi_intent_create_missing_name():
    """When create action has no name, use fallback."""
    parser = OutcomeParser()
    intent = POIIntent(
        action="create",
        name=None,
        description="A mysterious place"
    )
    result = parser.normalize_poi_intent(
        poi_intent=intent,
        policy_triggered=True
    )
    assert result.action == "create"
    assert result.name == "A Notable Location"
    assert result.description == "A mysterious place"


def test_normalize_poi_intent_create_missing_name_uses_location():
    """When create action has no name, use location_name if provided."""
    parser = OutcomeParser()
    intent = POIIntent(
        action="create",
        name="",
        description="A mysterious place"
    )
    result = parser.normalize_poi_intent(
        poi_intent=intent,
        policy_triggered=True,
        location_name="Shadowfen Swamp"
    )
    assert result.action == "create"
    assert result.name == "Shadowfen Swamp"
    assert result.description == "A mysterious place"


def test_normalize_poi_intent_create_missing_description():
    """When create action has no description, use fallback."""
    parser = OutcomeParser()
    intent = POIIntent(
        action="create",
        name="The Old Mill",
        description=None
    )
    result = parser.normalize_poi_intent(
        poi_intent=intent,
        policy_triggered=True
    )
    assert result.action == "create"
    assert result.name == "The Old Mill"
    assert result.description == "An interesting location worth remembering."


def test_normalize_poi_intent_create_empty_description():
    """When create action has empty description, use fallback."""
    parser = OutcomeParser()
    intent = POIIntent(
        action="create",
        name="The Old Mill",
        description="   "
    )
    result = parser.normalize_poi_intent(
        poi_intent=intent,
        policy_triggered=True
    )
    assert result.action == "create"
    assert result.name == "The Old Mill"
    assert result.description == "An interesting location worth remembering."


def test_normalize_poi_intent_create_trims_long_name():
    """When create action has name > 200 chars, trim to 200."""
    parser = OutcomeParser()
    long_name = "A" * 250
    intent = POIIntent(
        action="create",
        name=long_name,
        description="A place"
    )
    result = parser.normalize_poi_intent(
        poi_intent=intent,
        policy_triggered=True
    )
    assert result.action == "create"
    assert len(result.name) == 200
    assert result.name == long_name[:200]


def test_normalize_poi_intent_create_trims_long_description():
    """When create action has description > 2000 chars, trim to 2000."""
    parser = OutcomeParser()
    long_desc = "B" * 2500
    intent = POIIntent(
        action="create",
        name="The Place",
        description=long_desc
    )
    result = parser.normalize_poi_intent(
        poi_intent=intent,
        policy_triggered=True
    )
    assert result.action == "create"
    assert len(result.description) == 2000
    assert result.description == long_desc[:2000]


def test_normalize_poi_intent_create_none_tags():
    """When create action has None tags, use empty list."""
    parser = OutcomeParser()
    intent = POIIntent(
        action="create",
        name="The Place",
        description="A place",
        reference_tags=None
    )
    result = parser.normalize_poi_intent(
        poi_intent=intent,
        policy_triggered=True
    )
    assert result.action == "create"
    assert result.reference_tags == []


def test_normalize_poi_intent_create_valid():
    """When create action has all valid fields, return normalized."""
    parser = OutcomeParser()
    intent = POIIntent(
        action="create",
        name="The Rusty Tankard Inn",
        description="A weathered tavern at the edge of town",
        reference_tags=["inn", "town", "quest_hub"]
    )
    result = parser.normalize_poi_intent(
        poi_intent=intent,
        policy_triggered=True
    )
    assert result.action == "create"
    assert result.name == "The Rusty Tankard Inn"
    assert result.description == "A weathered tavern at the edge of town"
    assert result.reference_tags == ["inn", "town", "quest_hub"]


def test_normalize_poi_intent_reference_missing_name():
    """When reference action has no name, use fallback."""
    parser = OutcomeParser()
    intent = POIIntent(
        action="reference",
        name=None,
        reference_tags=["location"]
    )
    result = parser.normalize_poi_intent(
        poi_intent=intent,
        policy_triggered=False
    )
    assert result.action == "reference"
    assert result.name == "Unknown Location"


def test_normalize_poi_intent_reference_missing_name_uses_location():
    """When reference action has no name, use location_name if provided."""
    parser = OutcomeParser()
    intent = POIIntent(
        action="reference",
        name="",
        reference_tags=["location"]
    )
    result = parser.normalize_poi_intent(
        poi_intent=intent,
        policy_triggered=False,
        location_name="The Nexus"
    )
    assert result.action == "reference"
    assert result.name == "The Nexus"


def test_normalize_poi_intent_reference_trims_long_name():
    """When reference action has name > 200 chars, trim to 200."""
    parser = OutcomeParser()
    long_name = "C" * 250
    intent = POIIntent(
        action="reference",
        name=long_name,
        reference_tags=[]
    )
    result = parser.normalize_poi_intent(
        poi_intent=intent,
        policy_triggered=False
    )
    assert result.action == "reference"
    assert len(result.name) == 200
    assert result.name == long_name[:200]


def test_normalize_poi_intent_reference_valid():
    """When reference action has valid name, return normalized."""
    parser = OutcomeParser()
    intent = POIIntent(
        action="reference",
        name="The Rusty Tankard Inn",
        reference_tags=["inn"]
    )
    result = parser.normalize_poi_intent(
        poi_intent=intent,
        policy_triggered=False
    )
    assert result.action == "reference"
    assert result.name == "The Rusty Tankard Inn"
    assert result.reference_tags == ["inn"]


def test_normalize_poi_intent_policy_triggered_with_valid_intent():
    """When policy triggers and intent is valid, return normalized intent."""
    parser = OutcomeParser()
    intent = POIIntent(
        action="create",
        name="The Dark Cave",
        description="A mysterious cave entrance"
    )
    result = parser.normalize_poi_intent(
        poi_intent=intent,
        policy_triggered=True
    )
    assert result.action == "create"
    assert result.name == "The Dark Cave"
    assert result.description == "A mysterious cave entrance"
