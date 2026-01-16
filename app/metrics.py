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
- Thread-safe atomic operations without locks
"""

import time
from typing import Dict, Optional
from dataclasses import dataclass
from threading import Lock
from collections import defaultdict


@dataclass
class LatencyStats:
    """Statistics for operation latency."""
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float('inf')
    max_ms: float = 0.0
    
    @property
    def avg_ms(self) -> float:
        """Calculate average latency."""
        return self.total_ms / self.count if self.count > 0 else 0.0
    
    def record(self, duration_ms: float) -> None:
        """Record a new latency sample.
        
        Args:
            duration_ms: Duration in milliseconds
        """
        self.count += 1
        self.total_ms += duration_ms
        self.min_ms = min(self.min_ms, duration_ms)
        self.max_ms = max(self.max_ms, duration_ms)
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for serialization."""
        return {
            "count": self.count,
            "avg_ms": round(self.avg_ms, 2),
            "min_ms": round(self.min_ms, 2) if self.min_ms != float('inf') else 0.0,
            "max_ms": round(self.max_ms, 2)
        }


class MetricsCollector:
    """In-memory metrics collector with thread-safe operations.
    
    Collects:
    - HTTP request counts by status code
    - Operation latencies (turn processing, LLM calls, journey-log calls)
    - Error counts by type
    """
    
    def __init__(self):
        """Initialize metrics collector."""
        self._lock = Lock()
        self._request_counts: Dict[int, int] = defaultdict(int)
        self._error_counts: Dict[str, int] = defaultdict(int)
        self._latencies: Dict[str, LatencyStats] = defaultdict(LatencyStats)
        self._start_time = time.time()
    
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
                    operation: stats.to_dict()
                    for operation, stats in self._latencies.items()
                }
            }
    
    def reset(self) -> None:
        """Reset all metrics. Useful for testing."""
        with self._lock:
            self._request_counts.clear()
            self._error_counts.clear()
            self._latencies.clear()
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
