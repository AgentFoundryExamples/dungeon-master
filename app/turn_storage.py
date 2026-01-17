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
"""Turn state storage for admin introspection and debugging.

This module provides in-memory storage for turn state data that enables
admin endpoints to inspect specific turns for debugging. Includes:
- Turn detail capture (user_action, context, policy decisions, LLM output)
- TTL-based cleanup to prevent memory growth
- Sensitive data redaction
- Thread-safe access
"""

import re
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from app.logging import StructuredLogger

logger = StructuredLogger(__name__)


class TurnDetail:
    """Detailed turn state for admin introspection.
    
    Captures all relevant state for a turn including inputs, decisions,
    LLM outputs, and journey-log writes. Used by admin endpoints for
    debugging and auditing.
    
    Attributes:
        turn_id: Unique identifier for the turn
        character_id: Character UUID
        timestamp: ISO 8601 timestamp of turn start
        user_action: Player's input action
        context_snapshot: Snapshot of character context (redacted)
        policy_decisions: Policy engine decisions (quest/POI eligibility, rolls)
        llm_narrative: Generated narrative text (truncated if needed)
        llm_intents: Structured intents from LLM
        journey_log_writes: Summary of subsystem writes attempted
        errors: List of errors encountered during processing
        latency_ms: Total turn processing time in milliseconds
    """
    
    def __init__(
        self,
        turn_id: str,
        character_id: str,
        timestamp: str,
        user_action: str,
        context_snapshot: Optional[Dict[str, Any]] = None,
        policy_decisions: Optional[Dict[str, Any]] = None,
        llm_narrative: Optional[str] = None,
        llm_intents: Optional[Dict[str, Any]] = None,
        journey_log_writes: Optional[Dict[str, Any]] = None,
        errors: Optional[List[Dict[str, str]]] = None,
        latency_ms: Optional[float] = None
    ):
        self.turn_id = turn_id
        self.character_id = character_id
        self.timestamp = timestamp
        self.user_action = user_action
        self.context_snapshot = context_snapshot or {}
        self.policy_decisions = policy_decisions or {}
        self.llm_narrative = llm_narrative
        self.llm_intents = llm_intents
        self.journey_log_writes = journey_log_writes or {}
        self.errors = errors or []
        self.latency_ms = latency_ms
    
    def to_dict(self, redact_sensitive: bool = True) -> Dict[str, Any]:
        """Convert turn detail to dictionary for serialization.
        
        Args:
            redact_sensitive: Whether to redact sensitive data
            
        Returns:
            Dictionary representation of turn detail
        """
        # Redact sensitive fields from context snapshot
        context = self.context_snapshot.copy() if self.context_snapshot else {}
        if redact_sensitive and context:
            # Remove or redact potentially sensitive fields
            context.pop('additional_fields', None)  # May contain arbitrary data
            if 'recent_history' in context:
                # Truncate recent history to prevent large payloads
                context['recent_history'] = context['recent_history'][:5]
        
        # Truncate narrative if too long
        narrative = self.llm_narrative
        if narrative and len(narrative) > 2000:
            narrative = narrative[:2000] + "... [truncated]"
        
        return {
            "turn_id": self.turn_id,
            "character_id": self.character_id,
            "timestamp": self.timestamp,
            "user_action": self.user_action,
            "context_snapshot": context,
            "policy_decisions": self.policy_decisions,
            "llm_narrative": narrative,
            "llm_intents": self.llm_intents,
            "journey_log_writes": self.journey_log_writes,
            "errors": self.errors,
            "latency_ms": self.latency_ms,
            "redacted": redact_sensitive
        }


class TurnStorage:
    """In-memory storage for turn details with TTL-based cleanup.
    
    Provides thread-safe storage and retrieval of turn state for admin
    introspection. Uses LRU eviction and TTL-based cleanup to prevent
    unbounded memory growth.
    
    Features:
    - Thread-safe access with locks
    - TTL-based expiration (default: 1 hour)
    - LRU eviction when max size reached
    - Per-character turn history tracking
    - Automatic cleanup of expired entries
    
    Example:
        >>> storage = TurnStorage(max_size=1000, ttl_seconds=3600)
        >>> storage.store_turn(turn_detail)
        >>> detail = storage.get_turn("turn-id-123")
        >>> recent = storage.get_character_recent_turns("char-id-456", limit=10)
    """
    
    # Maximum turns to track per character before trimming
    MAX_TURNS_PER_CHARACTER = 100
    
    def __init__(self, max_size: int = 10000, ttl_seconds: int = 3600):
        """Initialize turn storage.
        
        Args:
            max_size: Maximum number of turns to store (LRU eviction)
            ttl_seconds: Time-to-live for turns in seconds (default: 1 hour)
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._turns: OrderedDict[str, tuple[TurnDetail, float]] = OrderedDict()
        self._character_turns: Dict[str, List[str]] = {}  # character_id -> list of turn_ids
        self._lock = threading.Lock()
        
        logger.info(
            "Initialized TurnStorage",
            max_size=max_size,
            ttl_seconds=ttl_seconds
        )
    
    def store_turn(self, turn_detail: TurnDetail) -> None:
        """Store turn detail with current timestamp for TTL.
        
        Args:
            turn_detail: Turn detail to store
        """
        with self._lock:
            current_time = time.time()
            
            # Remove expired entries before storing
            self._cleanup_expired(current_time)
            
            # LRU eviction if at max size
            if len(self._turns) >= self.max_size:
                # Remove oldest entry
                oldest_turn_id, _ = self._turns.popitem(last=False)
                logger.debug(
                    "Evicted oldest turn due to size limit",
                    turn_id=oldest_turn_id,
                    max_size=self.max_size
                )
            
            # Store turn with expiration time
            self._turns[turn_detail.turn_id] = (turn_detail, current_time)
            
            # Track turn by character
            if turn_detail.character_id not in self._character_turns:
                self._character_turns[turn_detail.character_id] = []
            self._character_turns[turn_detail.character_id].append(turn_detail.turn_id)
            
            # Keep only recent turns per character (limit to MAX_TURNS_PER_CHARACTER)
            if len(self._character_turns[turn_detail.character_id]) > self.MAX_TURNS_PER_CHARACTER:
                # Remove oldest turn references
                removed_turn_ids = self._character_turns[turn_detail.character_id][:-self.MAX_TURNS_PER_CHARACTER]
                self._character_turns[turn_detail.character_id] = \
                    self._character_turns[turn_detail.character_id][-self.MAX_TURNS_PER_CHARACTER:]
                
                logger.debug(
                    "Trimmed character turn history",
                    character_id=turn_detail.character_id,
                    removed_count=len(removed_turn_ids)
                )
            
            logger.debug(
                "Stored turn detail",
                turn_id=turn_detail.turn_id,
                character_id=turn_detail.character_id,
                storage_size=len(self._turns)
            )
    
    def get_turn(self, turn_id: str) -> Optional[TurnDetail]:
        """Retrieve turn detail by turn_id.
        
        Args:
            turn_id: Unique turn identifier
            
        Returns:
            TurnDetail if found and not expired, None otherwise
        """
        with self._lock:
            current_time = time.time()
            
            if turn_id not in self._turns:
                return None
            
            turn_detail, stored_time = self._turns[turn_id]
            
            # Check TTL expiration
            if current_time - stored_time > self.ttl_seconds:
                # Expired - remove it
                del self._turns[turn_id]
                logger.debug(
                    "Turn detail expired",
                    turn_id=turn_id,
                    age_seconds=current_time - stored_time
                )
                return None
            
            # Move to end for LRU (most recently accessed)
            self._turns.move_to_end(turn_id)
            
            return turn_detail
    
    def get_character_recent_turns(
        self,
        character_id: str,
        limit: int = 20
    ) -> List[TurnDetail]:
        """Get recent turns for a character.
        
        Args:
            character_id: Character UUID
            limit: Maximum number of turns to return (default: 20)
            
        Returns:
            List of recent TurnDetail objects in reverse chronological order
        """
        with self._lock:
            current_time = time.time()
            
            if character_id not in self._character_turns:
                return []
            
            # Get turn IDs for character (most recent first)
            turn_ids = list(reversed(self._character_turns[character_id]))
            
            # Retrieve turn details (filter expired)
            recent_turns = []
            for turn_id in turn_ids:
                if turn_id not in self._turns:
                    continue
                
                turn_detail, stored_time = self._turns[turn_id]
                
                # Check TTL
                if current_time - stored_time > self.ttl_seconds:
                    continue
                
                recent_turns.append(turn_detail)
                
                if len(recent_turns) >= limit:
                    break
            
            return recent_turns
    
    def _cleanup_expired(self, current_time: float) -> None:
        """Remove expired entries based on TTL.
        
        Args:
            current_time: Current timestamp for comparison
        """
        expired_turn_ids = []
        
        for turn_id, (turn_detail, stored_time) in self._turns.items():
            if current_time - stored_time > self.ttl_seconds:
                expired_turn_ids.append(turn_id)
        
        for turn_id in expired_turn_ids:
            del self._turns[turn_id]
        
        if expired_turn_ids:
            logger.debug(
                "Cleaned up expired turns",
                count=len(expired_turn_ids)
            )
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics for monitoring.
        
        Returns:
            Dictionary with storage metrics
        """
        with self._lock:
            current_time = time.time()
            
            # Count non-expired turns
            active_turns = sum(
                1 for _, (_, stored_time) in self._turns.items()
                if current_time - stored_time <= self.ttl_seconds
            )
            
            return {
                "total_turns_stored": len(self._turns),
                "active_turns": active_turns,
                "tracked_characters": len(self._character_turns),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds
            }
