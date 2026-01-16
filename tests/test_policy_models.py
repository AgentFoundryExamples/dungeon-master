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
"""Tests for PolicyEngine decision models."""

import pytest
from pydantic import ValidationError
from app.models import QuestTriggerDecision, POITriggerDecision


def test_quest_trigger_decision_valid():
    """Test QuestTriggerDecision with valid data."""
    decision = QuestTriggerDecision(
        eligible=True,
        probability=0.5,
        roll_passed=True
    )
    
    assert decision.eligible is True
    assert decision.probability == 0.5
    assert decision.roll_passed is True


def test_quest_trigger_decision_probability_bounds():
    """Test QuestTriggerDecision probability validation."""
    # Probability must be between 0.0 and 1.0
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        QuestTriggerDecision(
            eligible=True,
            probability=1.5,
            roll_passed=True
        )
    
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        QuestTriggerDecision(
            eligible=True,
            probability=-0.5,
            roll_passed=False
        )


def test_quest_trigger_decision_edge_probabilities():
    """Test QuestTriggerDecision with edge case probabilities."""
    # Test probability = 0.0
    decision_zero = QuestTriggerDecision(
        eligible=True,
        probability=0.0,
        roll_passed=False
    )
    assert decision_zero.probability == 0.0
    
    # Test probability = 1.0
    decision_one = QuestTriggerDecision(
        eligible=True,
        probability=1.0,
        roll_passed=True
    )
    assert decision_one.probability == 1.0


def test_quest_trigger_decision_missing_fields():
    """Test QuestTriggerDecision requires all fields."""
    with pytest.raises(ValidationError, match="Field required"):
        QuestTriggerDecision(
            eligible=True,
            probability=0.5
            # Missing roll_passed
        )


def test_poi_trigger_decision_valid():
    """Test POITriggerDecision with valid data."""
    decision = POITriggerDecision(
        eligible=True,
        probability=0.3,
        roll_passed=False
    )
    
    assert decision.eligible is True
    assert decision.probability == 0.3
    assert decision.roll_passed is False


def test_poi_trigger_decision_probability_bounds():
    """Test POITriggerDecision probability validation."""
    # Probability must be between 0.0 and 1.0
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        POITriggerDecision(
            eligible=True,
            probability=2.0,
            roll_passed=True
        )
    
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        POITriggerDecision(
            eligible=False,
            probability=-1.0,
            roll_passed=False
        )


def test_poi_trigger_decision_edge_probabilities():
    """Test POITriggerDecision with edge case probabilities."""
    # Test probability = 0.0
    decision_zero = POITriggerDecision(
        eligible=True,
        probability=0.0,
        roll_passed=False
    )
    assert decision_zero.probability == 0.0
    
    # Test probability = 1.0
    decision_one = POITriggerDecision(
        eligible=True,
        probability=1.0,
        roll_passed=True
    )
    assert decision_one.probability == 1.0


def test_poi_trigger_decision_missing_fields():
    """Test POITriggerDecision requires all fields."""
    with pytest.raises(ValidationError, match="Field required"):
        POITriggerDecision(
            eligible=False
            # Missing probability and roll_passed
        )


def test_quest_trigger_decision_json_serialization():
    """Test QuestTriggerDecision JSON serialization."""
    decision = QuestTriggerDecision(
        eligible=True,
        probability=0.4,
        roll_passed=True
    )
    
    json_data = decision.model_dump()
    
    assert json_data == {
        "eligible": True,
        "probability": 0.4,
        "roll_passed": True
    }


def test_poi_trigger_decision_json_serialization():
    """Test POITriggerDecision JSON serialization."""
    decision = POITriggerDecision(
        eligible=False,
        probability=0.2,
        roll_passed=False
    )
    
    json_data = decision.model_dump()
    
    assert json_data == {
        "eligible": False,
        "probability": 0.2,
        "roll_passed": False
    }


def test_quest_trigger_decision_from_json():
    """Test QuestTriggerDecision deserialization from JSON."""
    json_data = {
        "eligible": True,
        "probability": 0.6,
        "roll_passed": False
    }
    
    decision = QuestTriggerDecision(**json_data)
    
    assert decision.eligible is True
    assert decision.probability == 0.6
    assert decision.roll_passed is False


def test_poi_trigger_decision_from_json():
    """Test POITriggerDecision deserialization from JSON."""
    json_data = {
        "eligible": True,
        "probability": 0.8,
        "roll_passed": True
    }
    
    decision = POITriggerDecision(**json_data)
    
    assert decision.eligible is True
    assert decision.probability == 0.8
    assert decision.roll_passed is True
