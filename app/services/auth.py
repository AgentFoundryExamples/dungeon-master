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
"""Firebase Authentication service."""

import logging
import firebase_admin
from firebase_admin import auth, credentials
from fastapi import HTTPException, status
from typing import Optional

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK (will be called at startup)
_firebase_app = None

def init_firebase_app():
    """Initialize the Firebase Admin SDK.
    
    This function should be called once during application startup.
    It uses the default credentials (GOOGLE_APPLICATION_CREDENTIALS env var)
    or attempts to initialize without specific credentials if running in
    an environment like Cloud Run or GKE with Workload Identity.
    """
    global _firebase_app
    if _firebase_app:
        return

    try:
        # Check if already initialized (shouldn't happen with the global check, but for safety)
        if not firebase_admin._apps:
            # Use default credentials provider chain
            _firebase_app = firebase_admin.initialize_app()
            logger.info("Firebase Admin SDK initialized successfully")
        else:
            _firebase_app = firebase_admin.get_app()
            logger.info("Firebase Admin SDK already initialized")
            
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin SDK: {e}")
        # We don't raise here to allow the app to start even if Firebase fails,
        # but protected endpoints will fail.
        # In a strict environment, you might want to raise.

def verify_id_token(id_token: str) -> str:
    """Verify a Firebase ID token and return the user ID (uid).
    
    Args:
        id_token: The Firebase ID token string (JWT).
        
    Returns:
        The user ID (uid) from the decoded token.
        
    Raises:
        HTTPException(401): If the token is invalid, expired, or revoked.
        HTTPException(500): If Firebase initialization failed.
    """
    if not firebase_admin._apps:
        # If we failed to init at startup, try one more time or fail
        logger.warning("Firebase app not initialized, attempting lazy initialization")
        try:
            init_firebase_app()
        except Exception:
             logger.error("Lazy initialization failed")
             raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service unavailable"
            )

    try:
        # Verify the ID token
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token.get("uid")
        
        if not uid:
             raise ValueError("Token does not contain a user ID")
             
        return uid
        
    except auth.InvalidIdTokenError:
        logger.warning("Invalid Firebase ID token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credential",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except auth.ExpiredIdTokenError:
        logger.warning("Expired Firebase ID token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credential expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except auth.RevokedIdTokenError:
        logger.warning("Revoked Firebase ID token provided")
        raise HTTPException(
             status_code=status.HTTP_401_UNAUTHORIZED,
             detail="Authentication credential revoked",
             headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Unexpected error verifying token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )
