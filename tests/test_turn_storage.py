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
"""Tests for TurnStorage."""

import time
from datetime import datetime, timezone

from app.turn_storage import TurnStorage, TurnDetail


def test_turn_detail_creation():
    """Test TurnDetail creation with basic fields."""
    turn = TurnDetail(
        turn_id="turn-123",
        character_id="char-456",
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_action="I attack the goblin",
        context_snapshot={"status": "Healthy"},
        policy_decisions={"quest_triggered": False},
        llm_narrative="You swing your sword...",
        llm_intents={"quest_intent": {"action": "none"}},
        journey_log_writes={"quest": {"action": "none"}},
        errors=[],
        latency_ms=1234.5
    )
    
    assert turn.turn_id == "turn-123"
    assert turn.character_id == "char-456"
    assert turn.user_action == "I attack the goblin"


def test_turn_detail_to_dict_with_redaction():
    """Test TurnDetail to_dict with redaction."""
    turn = TurnDetail(
        turn_id="turn-123",
        character_id="char-456",
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_action="Test action",
        context_snapshot={"status": "Healthy", "additional_fields": {"secret": "data"}},
        policy_decisions={},
        llm_narrative="Test narrative",
        llm_intents={},
        journey_log_writes={},
        errors=[],
        latency_ms=100.0
    )
    
    # With redaction
    redacted = turn.to_dict(redact_sensitive=True)
    assert "additional_fields" not in redacted["context_snapshot"]
    assert redacted["redacted"] is True
    
    # Without redaction
    unredacted = turn.to_dict(redact_sensitive=False)
    assert "additional_fields" in unredacted["context_snapshot"]
    assert unredacted["redacted"] is False


def test_turn_detail_narrative_truncation():
    """Test narrative truncation for large narratives."""
    long_narrative = "x" * 3000  # 3000 characters
    
    turn = TurnDetail(
        turn_id="turn-123",
        character_id="char-456",
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_action="Test",
        llm_narrative=long_narrative
    )
    
    turn_dict = turn.to_dict()
    
    # Should be truncated to 2000 chars + "... [truncated]"
    assert len(turn_dict["llm_narrative"]) < len(long_narrative)
    assert "truncated" in turn_dict["llm_narrative"]


def test_turn_storage_store_and_retrieve():
    """Test storing and retrieving a turn."""
    storage = TurnStorage(max_size=100, ttl_seconds=60)
    
    turn = TurnDetail(
        turn_id="turn-123",
        character_id="char-456",
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_action="Test action",
        llm_narrative="Test narrative"
    )
    
    storage.store_turn(turn)
    
    retrieved = storage.get_turn("turn-123")
    assert retrieved is not None
    assert retrieved.turn_id == "turn-123"
    assert retrieved.character_id == "char-456"


def test_turn_storage_ttl_expiration():
    """Test turn expiration based on TTL."""
    storage = TurnStorage(max_size=100, ttl_seconds=1)  # 1 second TTL
    
    turn = TurnDetail(
        turn_id="turn-123",
        character_id="char-456",
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_action="Test action"
    )
    
    storage.store_turn(turn)
    
    # Should be retrievable immediately
    assert storage.get_turn("turn-123") is not None
    
    # Wait for TTL to expire
    time.sleep(1.5)
    
    # Should be expired
    assert storage.get_turn("turn-123") is None


def test_turn_storage_lru_eviction():
    """Test LRU eviction when max size reached."""
    storage = TurnStorage(max_size=3, ttl_seconds=3600)
    
    # Store 3 turns
    for i in range(3):
        turn = TurnDetail(
            turn_id=f"turn-{i}",
            character_id="char-456",
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_action=f"Action {i}"
        )
        storage.store_turn(turn)
    
    # All 3 should be retrievable
    assert storage.get_turn("turn-0") is not None
    assert storage.get_turn("turn-1") is not None
    assert storage.get_turn("turn-2") is not None
    
    # Store 4th turn, should evict oldest (turn-0)
    turn = TurnDetail(
        turn_id="turn-3",
        character_id="char-456",
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_action="Action 3"
    )
    storage.store_turn(turn)
    
    # turn-0 should be evicted
    assert storage.get_turn("turn-0") is None
    # Others should still be present
    assert storage.get_turn("turn-1") is not None
    assert storage.get_turn("turn-2") is not None
    assert storage.get_turn("turn-3") is not None


def test_turn_storage_character_recent_turns():
    """Test retrieving recent turns for a character."""
    storage = TurnStorage(max_size=100, ttl_seconds=3600)
    
    # Store turns for different characters
    for i in range(5):
        turn = TurnDetail(
            turn_id=f"turn-char1-{i}",
            character_id="char-1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_action=f"Action {i}"
        )
        storage.store_turn(turn)
    
    for i in range(3):
        turn = TurnDetail(
            turn_id=f"turn-char2-{i}",
            character_id="char-2",
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_action=f"Action {i}"
        )
        storage.store_turn(turn)
    
    # Get recent turns for char-1
    char1_turns = storage.get_character_recent_turns("char-1", limit=10)
    assert len(char1_turns) == 5
    
    # Get recent turns for char-2
    char2_turns = storage.get_character_recent_turns("char-2", limit=10)
    assert len(char2_turns) == 3
    
    # Get recent turns for non-existent character
    char3_turns = storage.get_character_recent_turns("char-3", limit=10)
    assert len(char3_turns) == 0


def test_turn_storage_character_recent_turns_limit():
    """Test limit parameter for recent turns."""
    storage = TurnStorage(max_size=100, ttl_seconds=3600)
    
    # Store 10 turns
    for i in range(10):
        turn = TurnDetail(
            turn_id=f"turn-{i}",
            character_id="char-1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_action=f"Action {i}"
        )
        storage.store_turn(turn)
    
    # Request only 5
    recent_turns = storage.get_character_recent_turns("char-1", limit=5)
    assert len(recent_turns) == 5
    
    # Should be most recent 5 (in reverse chronological order)
    # Since we store turn-9 last, it should be first in results
    assert recent_turns[0].turn_id == "turn-9"
    assert recent_turns[4].turn_id == "turn-5"


def test_turn_storage_stats():
    """Test storage statistics."""
    storage = TurnStorage(max_size=100, ttl_seconds=3600)
    
    # Initially empty
    stats = storage.get_storage_stats()
    assert stats["total_turns_stored"] == 0
    assert stats["tracked_characters"] == 0
    
    # Store some turns
    for i in range(5):
        turn = TurnDetail(
            turn_id=f"turn-{i}",
            character_id=f"char-{i % 2}",  # 2 different characters
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_action=f"Action {i}"
        )
        storage.store_turn(turn)
    
    stats = storage.get_storage_stats()
    assert stats["total_turns_stored"] == 5
    assert stats["tracked_characters"] == 2
    assert stats["max_size"] == 100
    assert stats["ttl_seconds"] == 3600


def test_turn_storage_cleanup_expired():
    """Test automatic cleanup of expired turns."""
    storage = TurnStorage(max_size=100, ttl_seconds=1)
    
    # Store turns
    for i in range(3):
        turn = TurnDetail(
            turn_id=f"turn-{i}",
            character_id="char-1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_action=f"Action {i}"
        )
        storage.store_turn(turn)
    
    # All should be active
    assert storage.get_storage_stats()["total_turns_stored"] == 3
    
    # Wait for expiration
    time.sleep(1.5)
    
    # Store another turn to trigger cleanup
    turn = TurnDetail(
        turn_id="turn-new",
        character_id="char-1",
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_action="New action"
    )
    storage.store_turn(turn)
    
    # Old turns should be cleaned up, only new one remains
    assert storage.get_turn("turn-0") is None
    assert storage.get_turn("turn-1") is None
    assert storage.get_turn("turn-2") is None
    assert storage.get_turn("turn-new") is not None
