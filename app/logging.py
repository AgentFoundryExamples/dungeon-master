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
from contextvars import ContextVar
from typing import Optional, Dict, Any
import json

# Context variables for request correlation
request_id_ctx: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
character_id_ctx: ContextVar[Optional[str]] = ContextVar('character_id', default=None)


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


def clear_context() -> None:
    """Clear all context variables.
    
    Should be called at the end of request processing to avoid leaks.
    """
    request_id_ctx.set(None)
    character_id_ctx.set(None)


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
        Dictionary with request_id and character_id if available
    """
    extras: Dict[str, Any] = {}
    
    request_id = get_request_id()
    if request_id:
        extras['request_id'] = request_id
    
    character_id = get_character_id()
    if character_id:
        extras['character_id'] = character_id
    
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
        extras.update(kwargs)
        
        # Create a formatted message with extras
        if extras:
            extra_str = ' '.join(f'{k}={v}' for k, v in extras.items() if v is not None)
            if extra_str:
                message = f"{message} | {extra_str}"
        
        self.logger.log(level, message, extra=extras)
    
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
            duration_ms=f"{duration_ms:.2f}"
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
            duration_ms=f"{duration_ms:.2f}"
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
            duration_ms=f"{duration_ms:.2f}"
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
            duration_ms=f"{duration_ms:.2f}"
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
    import re
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
