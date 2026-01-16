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
"""Tests for quest intent normalization in OutcomeParser."""

import pytest
from app.services.outcome_parser import OutcomeParser
from app.models import QuestIntent


@pytest.fixture
def parser():
    """Create a fresh OutcomeParser for each test."""
    return OutcomeParser()


def test_normalize_none_intent_no_policy(parser):
    """Test that None intent with no policy trigger stays None."""
    result = parser.normalize_quest_intent(None, policy_triggered=False)
    assert result is None


def test_normalize_none_intent_with_policy(parser):
    """Test that None intent with policy trigger creates fallback offer."""
    result = parser.normalize_quest_intent(None, policy_triggered=True)
    assert result is not None
    assert result.action == "offer"
    assert result.quest_title == "A New Opportunity"
    assert result.quest_summary == "An opportunity for adventure presents itself."
    assert result.quest_details == {}


def test_normalize_valid_offer_intent(parser):
    """Test that valid offer intent passes through unchanged."""
    intent = QuestIntent(
        action="offer",
        quest_title="Find the Lost Sword",
        quest_summary="A legendary sword is lost in the mountains.",
        quest_details={"difficulty": "medium"}
    )
    result = parser.normalize_quest_intent(intent, policy_triggered=True)
    assert result.action == "offer"
    assert result.quest_title == "Find the Lost Sword"
    assert result.quest_summary == "A legendary sword is lost in the mountains."
    assert result.quest_details == {"difficulty": "medium"}


def test_normalize_offer_missing_title(parser):
    """Test that offer with missing title gets fallback."""
    intent = QuestIntent(
        action="offer",
        quest_title=None,
        quest_summary="A legendary sword is lost.",
        quest_details={}
    )
    result = parser.normalize_quest_intent(intent, policy_triggered=True)
    assert result.action == "offer"
    assert result.quest_title == "A New Opportunity"
    assert result.quest_summary == "A legendary sword is lost."


def test_normalize_offer_empty_title(parser):
    """Test that offer with empty/whitespace title gets fallback."""
    intent = QuestIntent(
        action="offer",
        quest_title="   ",
        quest_summary="A legendary sword is lost.",
        quest_details={}
    )
    result = parser.normalize_quest_intent(intent, policy_triggered=True)
    assert result.action == "offer"
    assert result.quest_title == "A New Opportunity"
    assert result.quest_summary == "A legendary sword is lost."


def test_normalize_offer_missing_summary(parser):
    """Test that offer with missing summary gets fallback."""
    intent = QuestIntent(
        action="offer",
        quest_title="Find the Lost Sword",
        quest_summary=None,
        quest_details={}
    )
    result = parser.normalize_quest_intent(intent, policy_triggered=True)
    assert result.action == "offer"
    assert result.quest_title == "Find the Lost Sword"
    assert result.quest_summary == "An opportunity for adventure presents itself."


def test_normalize_offer_empty_summary(parser):
    """Test that offer with empty/whitespace summary gets fallback."""
    intent = QuestIntent(
        action="offer",
        quest_title="Find the Lost Sword",
        quest_summary="  ",
        quest_details={}
    )
    result = parser.normalize_quest_intent(intent, policy_triggered=True)
    assert result.action == "offer"
    assert result.quest_title == "Find the Lost Sword"
    assert result.quest_summary == "An opportunity for adventure presents itself."


def test_normalize_offer_missing_details(parser):
    """Test that offer with missing details gets empty dict."""
    intent = QuestIntent(
        action="offer",
        quest_title="Find the Lost Sword",
        quest_summary="A legendary sword is lost.",
        quest_details=None
    )
    result = parser.normalize_quest_intent(intent, policy_triggered=True)
    assert result.action == "offer"
    assert result.quest_title == "Find the Lost Sword"
    assert result.quest_summary == "A legendary sword is lost."
    assert result.quest_details == {}


def test_normalize_complete_intent(parser):
    """Test that complete intent passes through unchanged."""
    intent = QuestIntent(
        action="complete",
        quest_title=None,
        quest_summary=None,
        quest_details=None
    )
    result = parser.normalize_quest_intent(intent, policy_triggered=False)
    assert result.action == "complete"
    assert result.quest_title is None
    assert result.quest_summary is None
    assert result.quest_details is None


def test_normalize_abandon_intent(parser):
    """Test that abandon intent passes through unchanged."""
    intent = QuestIntent(
        action="abandon",
        quest_title=None,
        quest_summary=None,
        quest_details=None
    )
    result = parser.normalize_quest_intent(intent, policy_triggered=False)
    assert result.action == "abandon"


def test_normalize_none_action(parser):
    """Test that none action passes through unchanged."""
    intent = QuestIntent(
        action="none",
        quest_title="Ignored",
        quest_summary="Ignored",
        quest_details={}
    )
    result = parser.normalize_quest_intent(intent, policy_triggered=False)
    assert result.action == "none"


def test_normalize_all_missing_fields_with_policy(parser):
    """Test full fallback when all fields are missing but policy triggered."""
    intent = QuestIntent(
        action="offer",
        quest_title=None,
        quest_summary=None,
        quest_details=None
    )
    result = parser.normalize_quest_intent(intent, policy_triggered=True)
    assert result.action == "offer"
    assert result.quest_title == "A New Opportunity"
    assert result.quest_summary == "An opportunity for adventure presents itself."
    assert result.quest_details == {}
