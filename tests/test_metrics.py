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
"""Tests for metrics collection."""

from unittest.mock import patch
import os

from app.metrics import (
    MetricsCollector,
    LatencyStats,
    init_metrics_collector,
    disable_metrics_collector,
    get_metrics_collector,
    MetricsTimer
)


def test_latency_stats():
    """Test LatencyStats calculations."""
    stats = LatencyStats()
    
    # Record some samples
    stats.record(100.0)
    stats.record(200.0)
    stats.record(150.0)
    
    assert stats.count == 3
    assert stats.total_ms == 450.0
    assert stats.min_ms == 100.0
    assert stats.max_ms == 200.0
    assert stats.avg_ms == 150.0
    
    # Test to_dict
    data = stats.to_dict()
    assert data['count'] == 3
    assert data['avg_ms'] == 150.0
    assert data['min_ms'] == 100.0
    assert data['max_ms'] == 200.0


def test_metrics_collector_requests():
    """Test request metrics recording."""
    collector = MetricsCollector()
    
    # Record some requests
    collector.record_request(200)
    collector.record_request(200)
    collector.record_request(404)
    collector.record_request(502)
    
    metrics = collector.get_metrics()
    
    assert metrics['requests']['total'] == 4
    assert metrics['requests']['success'] == 2  # 200s
    assert metrics['requests']['errors'] == 2  # 404 + 502
    assert metrics['requests']['by_status_code'][200] == 2
    assert metrics['requests']['by_status_code'][404] == 1
    assert metrics['requests']['by_status_code'][502] == 1


def test_metrics_collector_errors():
    """Test error metrics recording."""
    collector = MetricsCollector()
    
    # Record some errors
    collector.record_error("character_not_found")
    collector.record_error("llm_timeout")
    collector.record_error("character_not_found")
    
    metrics = collector.get_metrics()
    
    assert metrics['errors']['by_type']['character_not_found'] == 2
    assert metrics['errors']['by_type']['llm_timeout'] == 1


def test_metrics_collector_latencies():
    """Test latency metrics recording."""
    collector = MetricsCollector()
    
    # Record some latencies
    collector.record_latency("turn", 1000.0)
    collector.record_latency("turn", 1200.0)
    collector.record_latency("llm_call", 500.0)
    
    metrics = collector.get_metrics()
    
    assert 'turn' in metrics['latencies']
    assert metrics['latencies']['turn']['count'] == 2
    assert metrics['latencies']['turn']['avg_ms'] == 1100.0
    assert metrics['latencies']['turn']['min_ms'] == 1000.0
    assert metrics['latencies']['turn']['max_ms'] == 1200.0
    
    assert 'llm_call' in metrics['latencies']
    assert metrics['latencies']['llm_call']['count'] == 1
    assert metrics['latencies']['llm_call']['avg_ms'] == 500.0


def test_metrics_collector_reset():
    """Test metrics reset."""
    collector = MetricsCollector()
    
    # Record some data
    collector.record_request(200)
    collector.record_error("test_error")
    collector.record_latency("test_op", 100.0)
    
    # Reset
    collector.reset()
    
    metrics = collector.get_metrics()
    assert metrics['requests']['total'] == 0
    assert len(metrics['errors']['by_type']) == 0
    assert len(metrics['latencies']) == 0


def test_metrics_timer():
    """Test MetricsTimer context manager."""
    collector = MetricsCollector()
    
    # Temporarily set global collector
    from app import metrics
    original_collector = metrics._metrics_collector
    metrics._metrics_collector = collector
    
    try:
        # Use timer
        with MetricsTimer("test_operation"):
            import time
            time.sleep(0.01)  # Sleep for 10ms
        
        # Check metrics were recorded
        collected_metrics = collector.get_metrics()
        assert 'test_operation' in collected_metrics['latencies']
        assert collected_metrics['latencies']['test_operation']['count'] == 1
        # Should be at least 10ms
        assert collected_metrics['latencies']['test_operation']['avg_ms'] >= 10.0
    finally:
        # Restore original collector
        metrics._metrics_collector = original_collector


def test_init_and_disable_metrics_collector():
    """Test initialization and disabling of global metrics collector."""
    # Initialize
    collector = init_metrics_collector()
    assert collector is not None
    assert get_metrics_collector() is not None
    
    # Disable
    disable_metrics_collector()
    assert get_metrics_collector() is None


def test_metrics_endpoint_disabled():
    """Test that metrics endpoint returns 404 when disabled."""
    from fastapi.testclient import TestClient
    
    with patch.dict(os.environ, {
        "JOURNEY_LOG_BASE_URL": "http://localhost:8000",
        "OPENAI_API_KEY": "sk-test-key",
        "ENABLE_METRICS": "false"
    }, clear=True):
        from app.config import get_settings
        get_settings.cache_clear()
        
        from app.main import app
        client = TestClient(app)
        
        response = client.get("/metrics")
        assert response.status_code == 404
        assert "disabled" in response.json()["detail"].lower()


def test_metrics_endpoint_enabled():
    """Test that metrics endpoint returns data when enabled."""
    from fastapi.testclient import TestClient
    
    with patch.dict(os.environ, {
        "JOURNEY_LOG_BASE_URL": "http://localhost:8000",
        "OPENAI_API_KEY": "sk-test-key",
        "ENABLE_METRICS": "true"
    }, clear=True):
        from app.config import get_settings
        get_settings.cache_clear()
        
        # Manually initialize metrics collector for test
        from app.metrics import init_metrics_collector
        init_metrics_collector()
        
        # Import after clearing cache to get new settings
        from app.main import app
        client = TestClient(app)
        
        response = client.get("/metrics")
        assert response.status_code == 200
        
        data = response.json()
        assert 'uptime_seconds' in data
        assert 'requests' in data
        assert 'errors' in data
        assert 'latencies' in data


def test_metrics_collector_streaming():
    """Test streaming metrics recording."""
    collector = MetricsCollector()
    
    # Record stream start
    collector.record_stream_start()
    
    # Record successful stream
    collector.record_stream_complete(token_count=50, duration_ms=1500.0)
    
    # Record client disconnect
    collector.record_stream_client_disconnect()
    
    # Record parse failure
    collector.record_stream_parse_failure()
    
    # Record another successful stream
    collector.record_stream_start()
    collector.record_stream_complete(token_count=75, duration_ms=2000.0)
    
    metrics = collector.get_metrics()
    
    # Verify streaming metrics
    assert 'streaming' in metrics
    streaming = metrics['streaming']
    
    assert streaming['total_streams'] == 2
    assert streaming['completed_streams'] == 2
    assert streaming['client_disconnects'] == 1
    assert streaming['parse_failures'] == 1
    
    # Verify token stats
    assert 'tokens_per_stream' in streaming
    token_stats = streaming['tokens_per_stream']
    assert token_stats['count'] == 2
    assert token_stats['avg_ms'] == 62.5  # (50 + 75) / 2
    assert token_stats['min_ms'] == 50.0
    assert token_stats['max_ms'] == 75.0
    
    # Verify duration stats
    assert 'stream_duration' in streaming
    duration_stats = streaming['stream_duration']
    assert duration_stats['count'] == 2
    assert duration_stats['avg_ms'] == 1750.0  # (1500 + 2000) / 2
    assert duration_stats['min_ms'] == 1500.0
    assert duration_stats['max_ms'] == 2000.0


def test_stream_lifecycle_logger():
    """Test StreamLifecycleLogger functionality."""
    from app.logging import StreamLifecycleLogger, StructuredLogger
    import logging
    
    # Create a logger instance
    logger = StructuredLogger("test_stream")
    
    # Create stream lifecycle logger
    character_id = "test-char-123"
    stream_logger = StreamLifecycleLogger(logger, character_id)
    
    # Test log methods (should not raise exceptions)
    stream_logger.log_stream_start()
    stream_logger.log_token_streamed(10)
    stream_logger.log_token_streamed(25)
    stream_logger.log_parse_complete(narrative_length=500, is_valid=True)
    stream_logger.log_writes_start()
    stream_logger.log_writes_complete(
        quest_written=True,
        combat_written=False,
        poi_written=True,
        narrative_written=True
    )
    stream_logger.log_stream_complete(narrative_length=500, total_tokens=25)
    
    # Test error logging
    stream_logger.log_stream_error("test_error", "Test error message")
    
    # Test disconnect logging
    stream_logger.log_client_disconnect()
