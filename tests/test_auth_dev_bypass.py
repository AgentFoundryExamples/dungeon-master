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
"""Tests for authentication dev bypass functionality."""

import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from unittest.mock import patch, MagicMock

from app.config import Settings
from app.api.deps import get_current_user_id


@pytest.fixture
def dev_bypass_settings():
    """Settings with dev bypass enabled."""
    settings = Settings(
        journey_log_base_url="http://test-journey-log:8000",
        openai_api_key="test-key",
        dev_bypass_auth=True,
        enable_debug_endpoints=True,
    )
    return settings


@pytest.fixture
def prod_settings():
    """Settings with dev bypass disabled (production mode)."""
    settings = Settings(
        journey_log_base_url="http://test-journey-log:8000",
        openai_api_key="test-key",
        dev_bypass_auth=False,
        enable_debug_endpoints=False,
    )
    return settings


class TestAuthDevBypass:
    """Test suite for authentication dev bypass functionality."""

    def test_dev_bypass_with_header(self, dev_bypass_settings):
        """Test that X-Dev-User-Id header works in dev bypass mode."""
        with patch("app.api.deps.get_settings", return_value=dev_bypass_settings):
            # Call the dependency directly with dev header
            user_id = get_current_user_id(
                credentials=None,
                x_dev_user_id="dev_user_123"
            )
            
            assert user_id == "dev_user_123"

    def test_dev_bypass_without_header(self, dev_bypass_settings):
        """Test that missing X-Dev-User-Id header returns 401 in dev bypass mode."""
        with patch("app.api.deps.get_settings", return_value=dev_bypass_settings):
            with pytest.raises(HTTPException) as exc_info:
                get_current_user_id(
                    credentials=None,
                    x_dev_user_id=None
                )
            
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "X-Dev-User-Id" in exc_info.value.detail

    def test_prod_mode_requires_bearer_token(self, prod_settings):
        """Test that production mode requires Bearer token and rejects dev header."""
        with patch("app.api.deps.get_settings", return_value=prod_settings):
            # Try with dev header (should be ignored in prod mode)
            with pytest.raises(HTTPException) as exc_info:
                get_current_user_id(
                    credentials=None,
                    x_dev_user_id="dev_user_123"  # This should be ignored
                )
            
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Missing authentication credentials" in exc_info.value.detail

    def test_prod_mode_with_invalid_token(self, prod_settings):
        """Test that production mode rejects invalid Firebase tokens."""
        with patch("app.api.deps.get_settings", return_value=prod_settings):
            with patch("app.services.auth.verify_id_token") as mock_verify:
                mock_verify.side_effect = HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credential"
                )
                
                credentials = HTTPAuthorizationCredentials(
                    scheme="Bearer",
                    credentials="invalid_token"
                )
                
                with pytest.raises(HTTPException) as exc_info:
                    get_current_user_id(credentials=credentials, x_dev_user_id=None)
                
                assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    def test_dev_bypass_ignores_bearer_token(self, dev_bypass_settings):
        """Test that dev bypass mode uses X-Dev-User-Id even if Bearer token present."""
        with patch("app.api.deps.get_settings", return_value=dev_bypass_settings):
            # Dev mode should use the dev header, not the bearer token
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="some_firebase_token"
            )
            
            user_id = get_current_user_id(
                credentials=credentials,
                x_dev_user_id="dev_user_456"
            )
            
            # Dev user ID should be used, not the token
            assert user_id == "dev_user_456"

    def test_prod_mode_with_valid_token(self, prod_settings):
        """Test that production mode accepts valid Firebase tokens."""
        with patch("app.api.deps.get_settings", return_value=prod_settings):
            with patch("app.api.deps.verify_id_token") as mock_verify:
                mock_verify.return_value = "firebase_user_789"
                
                credentials = HTTPAuthorizationCredentials(
                    scheme="Bearer",
                    credentials="valid_firebase_token"
                )
                
                user_id = get_current_user_id(
                    credentials=credentials,
                    x_dev_user_id=None
                )
                
                assert user_id == "firebase_user_789"
                mock_verify.assert_called_once_with("valid_firebase_token")
