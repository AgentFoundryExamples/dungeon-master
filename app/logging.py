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
"""Structured logging utilities for Dungeon Master service.

This module provides:
- Context management for request_id and character_id correlation
- Structured log helpers for major phases
- Secret redaction for API keys and sensitive data
- JSON logging formatter option
"""

import logging
import re
import time
import random
from contextvars import ContextVar
from typing import Optional, Dict, Any
import json

# Context variables for request correlation
request_id_ctx: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
character_id_ctx: ContextVar[Optional[str]] = ContextVar('character_id', default=None)
turn_id_ctx: ContextVar[Optional[str]] = ContextVar('turn_id', default=None)


def set_request_id(request_id: str) -> None:
    """Set the request ID in context for correlation.
    
    Args:
        request_id: Unique identifier for the request
    """
    request_id_ctx.set(request_id)


def get_request_id() -> Optional[str]:
    """Get the current request ID from context.
    
    Returns:
        Current request ID or None if not set
    """
    return request_id_ctx.get()


def set_character_id(character_id: str) -> None:
    """Set the character ID in context for correlation.
    
    Args:
        character_id: Character UUID identifier
    """
    character_id_ctx.set(character_id)


def get_character_id() -> Optional[str]:
    """Get the current character ID from context.
    
    Returns:
        Current character ID or None if not set
    """
    return character_id_ctx.get()


def set_turn_id(turn_id: str) -> None:
    """Set the turn ID in context for correlation.
    
    Args:
        turn_id: Unique identifier for the turn
    """
    turn_id_ctx.set(turn_id)


def get_turn_id() -> Optional[str]:
    """Get the current turn ID from context.
    
    Returns:
        Current turn ID or None if not set
    """
    return turn_id_ctx.get()


def clear_context() -> None:
    """Clear all context variables.
    
    Should be called at the end of request processing to avoid leaks.
    """
    request_id_ctx.set(None)
    character_id_ctx.set(None)
    turn_id_ctx.set(None)


def redact_secrets(text: str) -> str:
    """Redact API keys and secrets from text for safe logging.
    
    Redacts:
    - OpenAI API keys (sk-...)
    - Generic API keys patterns
    - Bearer tokens
    
    Args:
        text: Text that may contain secrets
        
    Returns:
        Text with secrets redacted
    """
    # Redact OpenAI API keys
    text = re.sub(r'sk-[a-zA-Z0-9]{32,}', 'sk-***REDACTED***', text)
    
    # Redact generic API key patterns
    text = re.sub(r'api[_-]?key["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{16,})', 
                  'api_key=***REDACTED***', text, flags=re.IGNORECASE)
    
    # Redact Bearer tokens
    text = re.sub(r'Bearer\s+[a-zA-Z0-9\-._~+/]+', 'Bearer ***REDACTED***', text, flags=re.IGNORECASE)
    
    return text


def get_structured_extras() -> Dict[str, Any]:
    """Get structured logging extras with correlation IDs.
    
    Returns:
        Dictionary with request_id, character_id, and turn_id if available
    """
    extras: Dict[str, Any] = {}
    
    request_id = get_request_id()
    if request_id:
        extras['request_id'] = request_id
    
    character_id = get_character_id()
    if character_id:
        extras['character_id'] = character_id
    
    turn_id = get_turn_id()
    if turn_id:
        extras['turn_id'] = turn_id
    
    return extras


class StructuredLogger:
    """Structured logger with correlation IDs and phase tracking.
    
    Automatically includes request_id and character_id from context
    in all log messages.
    """
    
    def __init__(self, name: str):
        """Initialize structured logger.
        
        Args:
            name: Logger name (usually __name__)
        """
        self.logger = logging.getLogger(name)
    
    def _log(self, level: int, message: str, **kwargs) -> None:
        """Internal logging method that adds correlation IDs.
        
        Args:
            level: Logging level (e.g., logging.INFO)
            message: Log message
            **kwargs: Additional fields to include in log
        """
        extras = get_structured_extras()
        # Extract reserved logging parameters
        exc_info = kwargs.pop('exc_info', None)
        stack_info = kwargs.pop('stack_info', None)
        stacklevel = kwargs.pop('stacklevel', 1)
        
        extras.update(kwargs)
        
        # Create a formatted message with extras
        if extras:
            extra_str = ' '.join(f'{k}={v}' for k, v in extras.items() if v is not None)
            if extra_str:
                message = f"{message} | {extra_str}"
        
        # Pass reserved parameters separately from extras
        self.logger.log(
            level, 
            message, 
            extra=extras,
            exc_info=exc_info,
            stack_info=stack_info,
            stacklevel=stacklevel
        )
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message with correlation IDs."""
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message with correlation IDs."""
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message with correlation IDs."""
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs) -> None:
        """Log error message with correlation IDs."""
        self._log(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs) -> None:
        """Log critical message with correlation IDs."""
        self._log(logging.CRITICAL, message, **kwargs)


class PhaseTimer:
    """Context manager for timing and logging request phases.
    
    Usage:
        with PhaseTimer("context_fetch", logger):
            # do work
            pass
    """
    
    def __init__(self, phase: str, logger: StructuredLogger):
        """Initialize phase timer.
        
        Args:
            phase: Name of the phase (e.g., "context_fetch", "llm_call")
            logger: Structured logger instance
        """
        self.phase = phase
        self.logger = logger
        self.start_time = 0.0
    
    def __enter__(self):
        """Start the phase timer."""
        self.start_time = time.time()
        self.logger.debug(f"Phase started: {self.phase}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """End the phase timer and log duration."""
        duration_ms = (time.time() - self.start_time) * 1000
        
        if exc_type:
            self.logger.error(
                f"Phase failed: {self.phase}",
                duration_ms=f"{duration_ms:.2f}",
                error_type=exc_type.__name__
            )
        else:
            self.logger.info(
                f"Phase completed: {self.phase}",
                duration_ms=f"{duration_ms:.2f}"
            )


class StreamLifecycleLogger:
    """Logger for tracking streaming turn lifecycle events.
    
    Tracks streaming-specific phases:
    - Stream start
    - Token streaming (with counts)
    - Parse completion
    - Subsystem writes
    - Client disconnect
    - Stream completion
    
    Usage:
        stream_logger = StreamLifecycleLogger(logger, character_id)
        stream_logger.log_stream_start()
        stream_logger.log_token_streamed(token_count=10)
        stream_logger.log_stream_complete(narrative_length=500)
    """
    
    def __init__(self, logger: StructuredLogger, character_id: str):
        """Initialize stream lifecycle logger.
        
        Args:
            logger: Structured logger instance
            character_id: Character UUID for correlation
        """
        self.logger = logger
        self.character_id = character_id
        self.start_time = time.time()
        self.token_count = 0
    
    def log_stream_start(self) -> None:
        """Log the start of a streaming turn."""
        self.start_time = time.time()
        self.token_count = 0
        self.logger.info(
            "Streaming turn started",
            stream_phase="start",
            character_id=self.character_id
        )
    
    def log_token_streamed(self, token_count: int) -> None:
        """Log token streaming progress.
        
        Args:
            token_count: Total number of tokens streamed so far
        """
        self.token_count = token_count
        self.logger.debug(
            "Tokens streamed",
            stream_phase="token_streaming",
            token_count=token_count
        )
    
    def log_parse_complete(self, narrative_length: int, is_valid: bool) -> None:
        """Log completion of narrative parsing.
        
        Args:
            narrative_length: Length of complete narrative in characters
            is_valid: Whether parsing succeeded
        """
        duration_ms = (time.time() - self.start_time) * 1000
        self.logger.info(
            "Narrative parse completed",
            stream_phase="parse_complete",
            narrative_length=narrative_length,
            is_valid=is_valid,
            duration_ms=round(duration_ms, 2)
        )
    
    def log_writes_start(self) -> None:
        """Log start of subsystem writes."""
        self.logger.debug(
            "Subsystem writes starting",
            stream_phase="writes_start"
        )
    
    def log_writes_complete(self, quest_written: bool, combat_written: bool, 
                           poi_written: bool, narrative_written: bool) -> None:
        """Log completion of subsystem writes.
        
        Args:
            quest_written: Whether quest was written
            combat_written: Whether combat was written
            poi_written: Whether POI was written
            narrative_written: Whether narrative was written (same as narrative_persisted)
        """
        self.logger.info(
            "Subsystem writes completed",
            stream_phase="writes_complete",
            quest_written=quest_written,
            combat_written=combat_written,
            poi_written=poi_written,
            narrative_written=narrative_written
        )
    
    def log_client_disconnect(self) -> None:
        """Log client disconnect during streaming."""
        duration_ms = (time.time() - self.start_time) * 1000
        self.logger.info(
            "Client disconnected during streaming",
            stream_phase="client_disconnect",
            token_count=self.token_count,
            duration_ms=round(duration_ms, 2)
        )
    
    def log_stream_complete(self, narrative_length: int, total_tokens: int) -> None:
        """Log successful stream completion.
        
        Args:
            narrative_length: Final narrative length in characters
            total_tokens: Total tokens streamed
        """
        duration_ms = (time.time() - self.start_time) * 1000
        self.logger.info(
            "Streaming turn completed",
            stream_phase="complete",
            narrative_length=narrative_length,
            total_tokens=total_tokens,
            duration_ms=round(duration_ms, 2)
        )
    
    def log_stream_error(self, error_type: str, error_message: str) -> None:
        """Log streaming error.
        
        Args:
            error_type: Type of error
            error_message: Error message (sanitized)
        """
        duration_ms = (time.time() - self.start_time) * 1000
        self.logger.error(
            "Streaming turn failed",
            stream_phase="error",
            error_type=error_type,
            error_message=sanitize_for_log(error_message),
            token_count=self.token_count,
            duration_ms=round(duration_ms, 2)
        )


def sanitize_for_log(text: str, max_length: int = 200) -> str:
    """Sanitize text for safe logging (prevents log injection).
    
    Removes control characters and truncates to prevent log flooding.
    This is different from redact_secrets() which focuses on sensitive data.
    
    Args:
        text: Text to sanitize
        max_length: Maximum length to truncate to
        
    Returns:
        Sanitized text safe for logging
    """
    # Remove control characters (newlines, carriage returns, etc.)
    sanitized = re.sub(r'[\r\n\t\x00-\x1f\x7f-\x9f]', '', str(text))
    # Truncate to max length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."
    return sanitized


class JsonFormatter(logging.Formatter):
    """JSON log formatter for structured logging.
    
    Outputs logs as JSON with consistent fields:
    - timestamp
    - level
    - logger
    - message
    - request_id (if available)
    - character_id (if available)
    - additional fields from extra
    """
    
    # Reserved attributes from Python's logging module that should not be added to log_data
    RESERVED_ATTRS = {
        'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
        'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
        'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
        'processName', 'process', 'message'
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.
        
        Args:
            record: Log record to format
            
        Returns:
            JSON-formatted log string
        """
        log_data = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage()
        }
        
        # Add all other attributes from the record that are not reserved
        for key, value in record.__dict__.items():
            if key not in self.RESERVED_ATTRS and key not in log_data:
                log_data[key] = value
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


def configure_logging(
    level: str = "INFO",
    json_format: bool = False,
    service_name: str = "dungeon-master"
) -> None:
    """Configure application logging.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: If True, use JSON formatter; otherwise use standard formatter
        service_name: Service name to include in logs
    """
    # Convert level string to logging constant
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    
    # Set formatter based on json_format flag
    if json_format:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Log configuration
    root_logger.info(
        f"Logging configured: level={level}, json_format={json_format}, service={service_name}"
    )


class TurnLogger:
    """Structured logger for emitting per-turn JSON logs.
    
    Emits comprehensive structured JSON logs for each turn including:
    - turn_id: Unique identifier for the turn
    - character_id: Character UUID (or placeholder if missing)
    - subsystem_actions: Quest/combat/POI changes
    - policy_decisions: Policy trigger outcomes
    - intent_summary: Key intent fields (without raw narrative)
    - latencies: Timing measurements for each phase
    - errors: Error annotations if any occurred
    
    Sensitive fields (raw narrative, PII) are redacted by default.
    Supports configurable sampling to control log volume.
    """
    
    def __init__(
        self,
        logger: StructuredLogger,
        sampling_rate: float = 1.0,
        redact_narrative: bool = True
    ):
        """Initialize turn logger.
        
        Args:
            logger: Structured logger instance
            sampling_rate: Fraction of turns to log (0.0-1.0), default 1.0 (all turns)
            redact_narrative: If True, redact raw narrative text from logs
        """
        self.logger = logger
        self.sampling_rate = max(0.0, min(1.0, sampling_rate))
        self.redact_narrative = redact_narrative
    
    def should_log_turn(self) -> bool:
        """Determine if this turn should be logged based on sampling rate.
        
        Returns:
            True if turn should be logged, False otherwise
        """
        if self.sampling_rate >= 1.0:
            return True
        if self.sampling_rate <= 0.0:
            return False
        return random.random() < self.sampling_rate
    
    def log_turn(
        self,
        turn_id: str,
        character_id: Optional[str],
        subsystem_actions: dict,
        policy_decisions: dict,
        intent_summary: Optional[dict],
        latencies: dict,
        errors: Optional[list] = None,
        outcome: str = "success"
    ) -> None:
        """Log a complete turn with structured data.
        
        Args:
            turn_id: Unique turn identifier
            character_id: Character UUID (or None for placeholder)
            subsystem_actions: Dict with quest/combat/poi/narrative changes
            policy_decisions: Dict with quest/poi trigger decisions
            intent_summary: Optional dict with key intent fields (no raw narrative)
            latencies: Dict with timing measurements (context_fetch_ms, llm_call_ms, etc.)
            errors: Optional list of error messages/annotations
            outcome: Overall turn outcome ("success", "error", "partial")
        """
        if not self.should_log_turn():
            return
        
        # Use placeholder if character_id is missing
        safe_character_id = character_id if character_id else "unknown"
        
        # Build turn log payload
        turn_log = {
            "log_type": "turn",
            "turn_id": turn_id,
            "character_id": safe_character_id,
            "outcome": outcome,
            "subsystem_actions": subsystem_actions,
            "policy_decisions": policy_decisions,
            "latencies_ms": latencies
        }
        
        # Add intent summary if available (without raw narrative)
        if intent_summary:
            turn_log["intent_summary"] = intent_summary
        
        # Add errors if any
        if errors:
            turn_log["errors"] = errors
        
        # Log as structured JSON
        self.logger.info(
            f"Turn completed: {turn_id}",
            **turn_log
        )
    
    def create_intent_summary(self, intents: Optional[Any]) -> Optional[dict]:
        """Create a redacted intent summary from IntentsBlock.
        
        Extracts key fields without including raw narrative text.
        
        Args:
            intents: IntentsBlock or None
            
        Returns:
            Dict with intent summary or None if intents is None
        """
        if not intents:
            return None
        
        summary = {}
        
        # Quest intent summary
        if hasattr(intents, 'quest_intent') and intents.quest_intent:
            quest = intents.quest_intent
            summary['quest'] = {
                'action': quest.action if hasattr(quest, 'action') else 'none',
                'has_title': bool(quest.quest_title) if hasattr(quest, 'quest_title') else False,
                'has_summary': bool(quest.quest_summary) if hasattr(quest, 'quest_summary') else False
            }
        
        # Combat intent summary
        if hasattr(intents, 'combat_intent') and intents.combat_intent:
            combat = intents.combat_intent
            summary['combat'] = {
                'action': combat.action if hasattr(combat, 'action') else 'none',
                'enemy_count': len(combat.enemies) if hasattr(combat, 'enemies') and combat.enemies else 0
            }
        
        # POI intent summary
        if hasattr(intents, 'poi_intent') and intents.poi_intent:
            poi = intents.poi_intent
            summary['poi'] = {
                'action': poi.action if hasattr(poi, 'action') else 'none',
                'has_name': bool(poi.name) if hasattr(poi, 'name') else False,
                'tag_count': len(poi.reference_tags) if hasattr(poi, 'reference_tags') and poi.reference_tags else 0
            }
        
        return summary if summary else None
