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





def test_metrics_collector_turn_counters():
    """Test turn-level metrics recording with labels."""
    collector = MetricsCollector()
    
    # Record some turns with labels
    collector.record_turn_processed(environment="production", character_id="char-12345678", outcome="success")
    collector.record_turn_processed(environment="production", character_id="char-87654321", outcome="success")
    collector.record_turn_processed(environment="staging", character_id="char-12345678", outcome="error")
    
    metrics = collector.get_metrics()
    
    # Verify turn metrics
    assert 'turns' in metrics
    assert 'by_label' in metrics['turns']
    
    # Check environment labels
    assert 'environment:production' in metrics['turns']['by_label']
    assert metrics['turns']['by_label']['environment:production'] == 2
    assert 'environment:staging' in metrics['turns']['by_label']
    assert metrics['turns']['by_label']['environment:staging'] == 1
    
    # Check outcome labels
    assert 'outcome:success' in metrics['turns']['by_label']
    assert metrics['turns']['by_label']['outcome:success'] == 2
    assert 'outcome:error' in metrics['turns']['by_label']
    assert metrics['turns']['by_label']['outcome:error'] == 1
    
    # Check character prefix labels (first 8 chars)
    assert 'character_prefix:char-123' in metrics['turns']['by_label']
    assert 'character_prefix:char-876' in metrics['turns']['by_label']


def test_metrics_collector_policy_triggers():
    """Test policy trigger metrics recording."""
    collector = MetricsCollector()
    
    # Record policy triggers
    collector.record_policy_trigger("quest", "triggered")
    collector.record_policy_trigger("quest", "triggered")
    collector.record_policy_trigger("quest", "skipped")
    collector.record_policy_trigger("quest", "ineligible")
    collector.record_policy_trigger("poi", "triggered")
    collector.record_policy_trigger("poi", "skipped")
    
    metrics = collector.get_metrics()
    
    # Verify policy trigger metrics
    assert 'policy_triggers' in metrics
    assert 'quest:triggered' in metrics['policy_triggers']
    assert metrics['policy_triggers']['quest:triggered'] == 2
    assert 'quest:skipped' in metrics['policy_triggers']
    assert metrics['policy_triggers']['quest:skipped'] == 1
    assert 'quest:ineligible' in metrics['policy_triggers']
    assert metrics['policy_triggers']['quest:ineligible'] == 1
    assert 'poi:triggered' in metrics['policy_triggers']
    assert metrics['policy_triggers']['poi:triggered'] == 1
    assert 'poi:skipped' in metrics['policy_triggers']
    assert metrics['policy_triggers']['poi:skipped'] == 1


def test_metrics_collector_subsystem_deltas():
    """Test subsystem delta metrics recording."""
    collector = MetricsCollector()
    
    # Record subsystem changes
    collector.record_subsystem_delta("quest", "offered")
    collector.record_subsystem_delta("quest", "completed")
    collector.record_subsystem_delta("combat", "started")
    collector.record_subsystem_delta("combat", "ended")
    collector.record_subsystem_delta("poi", "created")
    collector.record_subsystem_delta("poi", "created")
    collector.record_subsystem_delta("narrative", "persisted")
    collector.record_subsystem_delta("narrative", "persisted")
    collector.record_subsystem_delta("narrative", "persisted")
    
    metrics = collector.get_metrics()
    
    # Verify subsystem delta metrics
    assert 'subsystem_deltas' in metrics
    assert metrics['subsystem_deltas']['quest_offered'] == 1
    assert metrics['subsystem_deltas']['quest_completed'] == 1
    assert metrics['subsystem_deltas']['combat_started'] == 1
    assert metrics['subsystem_deltas']['combat_ended'] == 1
    assert metrics['subsystem_deltas']['poi_created'] == 2
    assert metrics['subsystem_deltas']['narrative_persisted'] == 3


def test_metrics_collector_journey_log_latencies():
    """Test journey-log endpoint latency metrics."""
    collector = MetricsCollector()
    
    # Record latencies for different endpoints
    collector.record_journey_log_latency("get_context", 150.0)
    collector.record_journey_log_latency("get_context", 200.0)
    collector.record_journey_log_latency("put_quest", 75.0)
    collector.record_journey_log_latency("post_poi", 100.0)
    collector.record_journey_log_latency("persist_narrative", 50.0)
    collector.record_journey_log_latency("persist_narrative", 60.0)
    
    metrics = collector.get_metrics()
    
    # Verify journey-log latency metrics
    assert 'journey_log_latencies' in metrics
    
    assert 'get_context' in metrics['journey_log_latencies']
    assert metrics['journey_log_latencies']['get_context']['count'] == 2
    assert metrics['journey_log_latencies']['get_context']['avg_ms'] == 175.0
    
    assert 'put_quest' in metrics['journey_log_latencies']
    assert metrics['journey_log_latencies']['put_quest']['count'] == 1
    assert metrics['journey_log_latencies']['put_quest']['avg_ms'] == 75.0
    
    assert 'post_poi' in metrics['journey_log_latencies']
    assert metrics['journey_log_latencies']['post_poi']['count'] == 1
    
    assert 'persist_narrative' in metrics['journey_log_latencies']
    assert metrics['journey_log_latencies']['persist_narrative']['count'] == 2
    assert metrics['journey_log_latencies']['persist_narrative']['avg_ms'] == 55.0


def test_turn_logger_sampling():
    """Test TurnLogger sampling rate."""
    from app.logging import TurnLogger, StructuredLogger
    
    logger = StructuredLogger("test_turn_logger")
    
    # Test with 100% sampling
    turn_logger_all = TurnLogger(logger, sampling_rate=1.0)
    assert turn_logger_all.should_log_turn() == True
    
    # Test with 0% sampling
    turn_logger_none = TurnLogger(logger, sampling_rate=0.0)
    assert turn_logger_none.should_log_turn() == False
    
    # Test with 50% sampling (probabilistic, test multiple times)
    turn_logger_half = TurnLogger(logger, sampling_rate=0.5)
    results = [turn_logger_half.should_log_turn() for _ in range(100)]
    # Should have roughly 50% True and 50% False (allow 20% variance)
    true_count = sum(results)
    assert 30 <= true_count <= 70


def test_turn_logger_intent_summary():
    """Test TurnLogger intent summary creation."""
    from app.logging import TurnLogger, StructuredLogger
    from app.models import IntentsBlock, QuestIntent, CombatIntent, POIIntent, EnemyDescriptor
    
    logger = StructuredLogger("test_turn_logger")
    turn_logger = TurnLogger(logger)
    
    # Create test intents
    quest_intent = QuestIntent(
        action="offer",
        quest_title="Test Quest",
        quest_summary="A test quest summary",
        quest_details={}
    )
    
    combat_intent = CombatIntent(
        action="start",
        enemies=[
            EnemyDescriptor(name="Goblin", threat="low"),
            EnemyDescriptor(name="Orc", threat="medium")
        ],
        combat_notes=None
    )
    
    poi_intent = POIIntent(
        action="create",
        name="Ancient Temple",
        description="A mysterious temple",
        reference_tags=["temple", "ancient"]
    )
    
    intents = IntentsBlock(
        quest_intent=quest_intent,
        combat_intent=combat_intent,
        poi_intent=poi_intent,
        meta=None
    )
    
    # Create intent summary
    summary = turn_logger.create_intent_summary(intents)
    
    # Verify summary structure
    assert summary is not None
    assert 'quest' in summary
    assert summary['quest']['action'] == 'offer'
    assert summary['quest']['has_title'] == True
    assert summary['quest']['has_summary'] == True
    
    assert 'combat' in summary
    assert summary['combat']['action'] == 'start'
    assert summary['combat']['enemy_count'] == 2
    
    assert 'poi' in summary
    assert summary['poi']['action'] == 'create'
    assert summary['poi']['has_name'] == True
    assert summary['poi']['tag_count'] == 2
    
    # Test with None intents
    assert turn_logger.create_intent_summary(None) is None
