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
"""API dependencies for authentication and services."""

import logging
from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from app.services.auth import verify_id_token
from app.config import get_settings

logger = logging.getLogger(__name__)

# Define security scheme (auto_error=False allows optional auth for dev bypass)
security = HTTPBearer(auto_error=False)

def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    x_dev_user_id: Optional[str] = Header(None, alias="X-Dev-User-Id")
) -> str:
    """Dependency to verify Firebase ID token and return user ID (uid).
    
    In production mode, this dependency expects a standard Bearer token in the
    Authorization header and verifies it using Firebase Admin SDK.
    
    In development mode (when dev_bypass_auth=true), this dependency allows
    authentication via the X-Dev-User-Id header instead of a Firebase token.
    This is useful for local testing without setting up Firebase.
    
    Args:
        credentials: The Bearer token extracted by FastAPI security (optional in dev mode).
        x_dev_user_id: Development user ID header (only used when dev_bypass_auth=true).
        
    Returns:
        The authenticated user's UID.
        
    Raises:
        HTTPException(401): If token is invalid/expired or dev header is missing in dev mode.
        HTTPException(500): If auth service is unavailable.
    """
    settings = get_settings()
    
    # Development bypass mode
    if settings.dev_bypass_auth:
        if x_dev_user_id:
            logger.debug(f"DEV MODE: Using X-Dev-User-Id header: {x_dev_user_id}")
            return x_dev_user_id
        else:
            logger.warning("DEV MODE: X-Dev-User-Id header missing")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="X-Dev-User-Id header required in development mode",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    # Production mode - require Firebase token
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    uid = verify_id_token(token)
    return uid