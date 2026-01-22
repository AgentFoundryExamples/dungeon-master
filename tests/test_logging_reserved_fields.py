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
"""Tests for logging with reserved field names."""

import pytest
import logging
from app.logging import StructuredLogger


class TestLoggingReservedFields:
    """Test suite for logging reserved field handling."""

    def test_character_name_logging(self, caplog):
        """Test that character_name can be logged without errors."""
        logger = StructuredLogger(__name__)
        
        with caplog.at_level(logging.INFO):
            # This should not raise a KeyError
            logger.info(
                "Character created",
                character_name="Gandalf",
                race="Wizard",
                class_name="Mage"
            )
        
        # Should not raise an error and message should be logged
        assert "Character created" in caplog.text
        # The extra fields may not appear in caplog.text without a custom formatter,
        # but the important thing is no exception was raised

    def test_poi_name_logging(self, caplog):
        """Test that poi_name can be logged without errors."""
        logger = StructuredLogger(__name__)
        
        with caplog.at_level(logging.DEBUG):
            logger.debug("POI created", poi_name="Ancient Temple")
        
        assert "POI created" in caplog.text

    def test_reserved_field_warning(self, caplog):
        """Test that using reserved field 'name' triggers a warning."""
        logger = StructuredLogger(__name__)
        
        with caplog.at_level(logging.WARNING):
            # This should trigger a warning but not fail
            logger.info("Test message", name="test_value")
        
        # Check that a warning was logged about reserved attribute
        warning_found = any(
            "reserved LogRecord attribute" in record.message 
            for record in caplog.records 
            if record.levelname == "WARNING"
        )
        assert warning_found, "Expected warning about reserved attribute 'name'"

    def test_multiple_reserved_fields_warning(self, caplog):
        """Test that using multiple reserved fields triggers warnings."""
        logger = StructuredLogger(__name__)
        
        with caplog.at_level(logging.WARNING):
            logger.info(
                "Test message",
                name="test_name",
                msg="test_msg",
                module="test_module"
            )
        
        # Should have warnings for each reserved field
        warnings = [
            record for record in caplog.records 
            if record.levelname == "WARNING" and "reserved LogRecord attribute" in record.message
        ]
        assert len(warnings) >= 3, f"Expected at least 3 warnings, got {len(warnings)}"

    def test_non_reserved_fields_work(self, caplog):
        """Test that non-reserved fields work without warnings."""
        logger = StructuredLogger(__name__)
        
        with caplog.at_level(logging.INFO):
            logger.info(
                "Test message",
                character_name="Hero",
                poi_name="Castle",
                quest_id="quest_123",
                custom_field="value"
            )
        
        # Should not have any warnings
        warnings = [
            record for record in caplog.records 
            if record.levelname == "WARNING"
        ]
        assert len(warnings) == 0, f"Expected no warnings, got {len(warnings)}"
