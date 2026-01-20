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
"""Optional metrics collection for observability.

This module provides simple in-memory metrics collection:
- Request counters (total, success, error by status code)
- Latency tracking (min, max, avg, count by operation)
- Thread-safe atomic operations using locks
"""

import time
from typing import Dict, Optional
from dataclasses import dataclass
from threading import Lock
from collections import defaultdict


@dataclass
class LatencyStats:
    """Statistics for a generic numeric value (latency, counts, etc.)."""
    count: int = 0
    total: float = 0.0
    min: float = float('inf')
    max: float = 0.0
    
    @property
    def avg(self) -> float:
        """Calculate average value."""
        return self.total / self.count if self.count > 0 else 0.0
    
    # Backward compatibility properties for latency use case
    @property
    def total_ms(self) -> float:
        """Alias for total (backward compatibility)."""
        return self.total
    
    @property
    def min_ms(self) -> float:
        """Alias for min (backward compatibility)."""
        return self.min
    
    @property
    def max_ms(self) -> float:
        """Alias for max (backward compatibility)."""
        return self.max
    
    @property
    def avg_ms(self) -> float:
        """Alias for avg (backward compatibility)."""
        return self.avg
    
    def record(self, value: float) -> None:
        """Record a new sample.
        
        Args:
            value: The value to record (e.g., duration in ms, token count)
        """
        self.count += 1
        self.total += value
        self.min = min(self.min, value)
        self.max = max(self.max, value)
    
    def to_dict(self, unit: str = "ms") -> Dict[str, float]:
        """Convert to dictionary for serialization.
        
        Args:
            unit: Unit suffix for keys (e.g., "ms" for milliseconds, "" for dimensionless)
        
        Returns:
            Dictionary with count, avg, min, max with appropriate unit suffix
        """
        # Suffix keys with unit if provided (e.g., "avg_ms")
        suffix = f"_{unit}" if unit else ""
        avg_key = f"avg{suffix}"
        min_key = f"min{suffix}"
        max_key = f"max{suffix}"
        return {
            "count": self.count,
            avg_key: round(self.avg, 2),
            min_key: round(self.min, 2) if self.min != float('inf') else 0.0,
            max_key: round(self.max, 2)
        }


class MetricsCollector:
    """In-memory metrics collector with thread-safe operations.
    
    Collects:
    - HTTP request counts by status code
    - Operation latencies (turn processing, LLM calls, journey-log calls)
    - Error counts by type
    - Streaming metrics (token counts, stream durations, client disconnects)
    - Turn-level metrics (processed, policy triggers, subsystem deltas)
    - Journey-log endpoint latencies
    - Schema parse success/failure rates
    """
    
    def __init__(self):
        """Initialize metrics collector."""
        self._lock = Lock()
        self._request_counts: Dict[int, int] = defaultdict(int)
        self._error_counts: Dict[str, int] = defaultdict(int)
        self._latencies: Dict[str, LatencyStats] = defaultdict(LatencyStats)
        self._start_time = time.time()
        
        # Streaming-specific metrics
        self._stream_counts = {
            "total": 0,
            "completed": 0,
            "client_disconnects": 0,
            "parse_failures": 0
        }
        self._stream_token_stats = LatencyStats()  # Track tokens per stream
        self._stream_duration_stats = LatencyStats()  # Track stream duration
        
        # Turn-level metrics with labels
        # Format: {(label_key, label_value): count}
        self._turn_counts: Dict[tuple, int] = defaultdict(int)
        
        # Policy trigger metrics
        # Format: {(policy_type, decision): count}
        self._policy_triggers: Dict[tuple, int] = defaultdict(int)
        
        # Subsystem delta metrics per turn
        # Format: {subsystem: count}
        self._subsystem_deltas: Dict[str, int] = defaultdict(int)
        
        # Journey-log endpoint latencies
        # Format: {endpoint_type: LatencyStats}
        self._journey_log_latencies: Dict[str, LatencyStats] = defaultdict(LatencyStats)
    
    def record_request(self, status_code: int) -> None:
        """Record an HTTP request.
        
        Args:
            status_code: HTTP status code
        """
        with self._lock:
            self._request_counts[status_code] += 1
    
    def record_error(self, error_type: str) -> None:
        """Record an error by type.
        
        Args:
            error_type: Error type/category
        """
        with self._lock:
            self._error_counts[error_type] += 1
    
    def record_latency(self, operation: str, duration_ms: float) -> None:
        """Record operation latency.
        
        Args:
            operation: Operation name (e.g., "turn", "llm_call", "journey_log_fetch")
            duration_ms: Duration in milliseconds
        """
        with self._lock:
            self._latencies[operation].record(duration_ms)
    
    def record_turn_processed(
        self, 
        environment: str = "unknown",
        character_id: Optional[str] = None,
        outcome: str = "success"
    ) -> None:
        """Record a processed turn with labels.
        
        Args:
            environment: Environment label (e.g., "production", "staging")
            character_id: Character ID (hashed for safety, optional)
            outcome: Outcome label ("success", "error", "partial")
        """
        with self._lock:
            # Use first 8 chars of character_id as label if provided (for bounded cardinality)
            char_label = character_id[:8] if character_id else "unknown"
            self._turn_counts[("environment", environment)] += 1
            self._turn_counts[("character_prefix", char_label)] += 1
            self._turn_counts[("outcome", outcome)] += 1
    
    def record_policy_trigger(self, policy_type: str, decision: str) -> None:
        """Record a policy trigger decision.
        
        Args:
            policy_type: Type of policy ("quest", "poi")
            decision: Decision outcome ("triggered", "skipped", "ineligible")
        """
        with self._lock:
            self._policy_triggers[(policy_type, decision)] += 1
    
    def record_subsystem_delta(self, subsystem: str, action: str) -> None:
        """Record a subsystem change per turn.
        
        Args:
            subsystem: Subsystem name ("quest", "combat", "poi", "narrative")
            action: Action taken ("offered", "completed", "started", "ended", "created", "persisted")
        """
        with self._lock:
            self._subsystem_deltas[f"{subsystem}_{action}"] += 1
    
    def record_journey_log_latency(self, endpoint_type: str, duration_ms: float) -> None:
        """Record journey-log endpoint latency.
        
        Args:
            endpoint_type: Endpoint type (e.g., "get_context", "put_quest", "post_poi", "persist_narrative")
            duration_ms: Duration in milliseconds
        """
        with self._lock:
            self._journey_log_latencies[endpoint_type].record(duration_ms)
    
    def get_metrics(self) -> Dict:
        """Get all collected metrics.
        
        Returns:
            Dictionary with all metrics
        """
        with self._lock:
            total_requests = sum(self._request_counts.values())
            success_requests = sum(
                count for status, count in self._request_counts.items()
                if 200 <= status < 400
            )
            error_requests = total_requests - success_requests
            
            uptime_seconds = time.time() - self._start_time
            
            # Calculate schema conformance rate
            llm_parse_success = self._error_counts.get("llm_parse_success", 0)
            llm_parse_failures = sum(
                count for error_type, count in self._error_counts.items()
                if error_type.startswith("llm_parse_failure_")
            )
            total_llm_parses = llm_parse_success + llm_parse_failures
            conformance_rate = (
                llm_parse_success / total_llm_parses if total_llm_parses > 0 else 0.0
            )
            
            return {
                "uptime_seconds": round(uptime_seconds, 2),
                "requests": {
                    "total": total_requests,
                    "success": success_requests,
                    "errors": error_requests,
                    "by_status_code": dict(self._request_counts)
                },
                "errors": {
                    "by_type": dict(self._error_counts)
                },
                "latencies": {
                    operation: stats.to_dict(unit="ms")
                    for operation, stats in self._latencies.items()
                },
                "schema_conformance": {
                    "total_parses": total_llm_parses,
                    "successful_parses": llm_parse_success,
                    "failed_parses": llm_parse_failures,
                    "conformance_rate": round(conformance_rate, 4)
                },
                "turns": {
                    "by_label": {
                        f"{label_key}:{label_value}": count
                        for (label_key, label_value), count in self._turn_counts.items()
                    }
                },
                "policy_triggers": {
                    f"{policy_type}:{decision}": count
                    for (policy_type, decision), count in self._policy_triggers.items()
                },
                "subsystem_deltas": dict(self._subsystem_deltas),
                "journey_log_latencies": {
                    endpoint: stats.to_dict(unit="ms")
                    for endpoint, stats in self._journey_log_latencies.items()
                },
            }
    
    def reset(self) -> None:
        """Reset all metrics. Useful for testing."""
        with self._lock:
            self._request_counts.clear()
            self._error_counts.clear()
            self._latencies.clear()
            self._turn_counts.clear()
            self._policy_triggers.clear()
            self._subsystem_deltas.clear()
            self._journey_log_latencies.clear()
            self._start_time = time.time()


# Global metrics collector instance (singleton)
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> Optional[MetricsCollector]:
    """Get the global metrics collector instance.
    
    Returns:
        MetricsCollector instance if metrics are enabled, None otherwise
    """
    return _metrics_collector


def init_metrics_collector() -> MetricsCollector:
    """Initialize the global metrics collector.
    
    Returns:
        Initialized MetricsCollector instance
    """
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def disable_metrics_collector() -> None:
    """Disable metrics collection by clearing the global instance."""
    global _metrics_collector
    _metrics_collector = None


class MetricsTimer:
    """Context manager for timing operations and recording metrics.
    
    Usage:
        with MetricsTimer("turn"):
            # do work
            pass
    """
    
    def __init__(self, operation: str):
        """Initialize metrics timer.
        
        Args:
            operation: Operation name for metrics
        """
        self.operation = operation
        self.start_time = 0.0
        self.collector = get_metrics_collector()
    
    def __enter__(self):
        """Start the timer."""
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """End the timer and record metrics."""
        if self.collector:
            duration_ms = (time.time() - self.start_time) * 1000
            self.collector.record_latency(self.operation, duration_ms)
