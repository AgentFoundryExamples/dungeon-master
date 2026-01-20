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
"""Tests for NarrativeBuffer class."""

import pytest
from app.streaming.buffer import NarrativeBuffer, BufferError


@pytest.mark.skip(reason="Streaming functionality deprecated")
def test_narrative_buffer_basic_append():
    """Test basic token appending to buffer."""
    buffer = NarrativeBuffer()
    
    buffer.append("Hello")
    buffer.append(" ")
    buffer.append("world")
    
    assert buffer.get_token_count() == 3
    assert buffer.get_complete_narrative() == "Hello world"
    assert not buffer.is_finalized()


@pytest.mark.skip(reason="Streaming functionality deprecated")
def test_narrative_buffer_finalization():
    """Test buffer finalization."""
    buffer = NarrativeBuffer()
    
    buffer.append("Test")
    assert buffer.get_duration_ms() is None
    
    buffer.finalize()
    assert buffer.is_finalized()
    assert buffer.get_duration_ms() is not None
    assert buffer.get_duration_ms() >= 0


@pytest.mark.skip(reason="Streaming functionality deprecated")
def test_narrative_buffer_cannot_append_after_finalize():
    """Test that appending after finalization raises error."""
    buffer = NarrativeBuffer()
    
    buffer.append("Test")
    buffer.finalize()
    
    with pytest.raises(BufferError, match="Cannot append to finalized buffer"):
        buffer.append("More")


@pytest.mark.skip(reason="Streaming functionality deprecated")
def test_narrative_buffer_finalize_idempotent():
    """Test that finalize() can be called multiple times safely."""
    buffer = NarrativeBuffer()
    
    buffer.append("Test")
    buffer.finalize()
    duration1 = buffer.get_duration_ms()
    
    # Call finalize again
    buffer.finalize()
    duration2 = buffer.get_duration_ms()
    
    # Duration should not change
    assert duration1 == duration2


@pytest.mark.skip(reason="Streaming functionality deprecated")
def test_narrative_buffer_empty():
    """Test empty buffer behavior."""
    buffer = NarrativeBuffer()
    
    assert buffer.get_token_count() == 0
    assert buffer.get_complete_narrative() == ""
    assert not buffer.is_finalized()


@pytest.mark.skip(reason="Streaming functionality deprecated")
def test_narrative_buffer_unicode():
    """Test buffer with unicode characters."""
    buffer = NarrativeBuffer()
    
    buffer.append("Hello 👋")
    buffer.append(" ")
    buffer.append("世界")
    
    assert buffer.get_complete_narrative() == "Hello 👋 世界"
    assert buffer.get_token_count() == 3


@pytest.mark.skip(reason="Streaming functionality deprecated")
def test_narrative_buffer_size_limit():
    """Test buffer size limit enforcement."""
    buffer = NarrativeBuffer()
    
    # Add tokens up to just under the limit
    large_token = "x" * 40000  # 40KB
    buffer.append(large_token)
    
    # Adding another large token should exceed 50KB limit
    with pytest.raises(BufferError, match="Buffer size limit exceeded"):
        buffer.append(large_token)
    
    # Buffer should be finalized after error
    assert buffer.is_finalized()


@pytest.mark.skip(reason="Streaming functionality deprecated")
def test_narrative_buffer_exact_limit():
    """Test buffer at exact size limit."""
    buffer = NarrativeBuffer()
    
    # Create a token that exactly fills the buffer
    # Account for the fact that when we append, we check current_size + len(token)
    # So a single token equal to MAX_BUFFER_SIZE will exceed when checked
    token = "x" * (NarrativeBuffer.MAX_BUFFER_SIZE + 1)
    
    with pytest.raises(BufferError, match="Buffer size limit exceeded"):
        buffer.append(token)


@pytest.mark.skip(reason="Streaming functionality deprecated")
def test_narrative_buffer_preserves_whitespace():
    """Test that buffer preserves all whitespace."""
    buffer = NarrativeBuffer()
    
    buffer.append("Line1\n")
    buffer.append("\n")
    buffer.append("\tIndented\n")
    buffer.append("    Spaces")
    
    narrative = buffer.get_complete_narrative()
    assert narrative == "Line1\n\n\tIndented\n    Spaces"
    assert "\n\n" in narrative
    assert "\t" in narrative


@pytest.mark.skip(reason="Streaming functionality deprecated")
def test_narrative_buffer_many_small_tokens():
    """Test buffer with many small tokens."""
    buffer = NarrativeBuffer()
    
    # Add 1000 small tokens
    for i in range(1000):
        buffer.append(f"token{i} ")
    
    assert buffer.get_token_count() == 1000
    narrative = buffer.get_complete_narrative()
    assert "token0 " in narrative
    assert "token999 " in narrative
