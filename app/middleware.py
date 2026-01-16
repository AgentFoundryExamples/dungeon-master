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
"""Middleware for request correlation and observability.

This module provides:
- Request ID generation and propagation
- Request/response logging with latency
- Context variable management for correlation IDs
- Optional metrics recording
"""

import logging
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.logging import set_request_id, clear_context, get_request_id
from app.metrics import get_metrics_collector, MetricsTimer

logger = logging.getLogger(__name__)


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Middleware for request correlation and observability.
    
    Features:
    - Generates request_id (UUID) if not provided via X-Trace-Id header
    - Sets request_id in context variables for logging
    - Adds X-Request-Id header to responses
    - Logs request start/end with method, path, status, and latency
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with correlation ID and logging.
        
        Args:
            request: Incoming HTTP request
            call_next: Next middleware or route handler
            
        Returns:
            HTTP response with correlation headers
        """
        # Generate or extract request ID
        # Priority: X-Trace-Id header > X-Request-Id header > generated UUID
        request_id = (
            request.headers.get('X-Trace-Id') or
            request.headers.get('X-Request-Id') or
            str(uuid.uuid4())
        )
        
        # Set request ID in context for logging
        set_request_id(request_id)
        
        # Log request start
        start_time = time.time()
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                'request_id': request_id,
                'method': request.method,
                'path': request.url.path,
                'client_ip': request.client.host if request.client else None
            }
        )
        
        try:
            # Process request with metrics timing if enabled
            # Track turn endpoint requests separately for more detailed metrics
            operation_name = "turn" if "/turn" in request.url.path else "request"
            with MetricsTimer(operation_name):
                response = await call_next(request)
            
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Record metrics if enabled
            if (collector := get_metrics_collector()):
                collector.record_request(response.status_code)
            
            # Log request completion
            logger.info(
                f"Request completed: {request.method} {request.url.path} - {response.status_code}",
                extra={
                    'request_id': request_id,
                    'method': request.method,
                    'path': request.url.path,
                    'status_code': response.status_code,
                    'duration_ms': f"{duration_ms:.2f}"
                }
            )
            
            # Add correlation ID to response headers
            response.headers['X-Request-Id'] = request_id
            
            return response
            
        except Exception as e:
            # Calculate duration even on error
            duration_ms = (time.time() - start_time) * 1000
            
            # Log request error
            logger.error(
                f"Request failed: {request.method} {request.url.path} - {type(e).__name__}",
                extra={
                    'request_id': request_id,
                    'method': request.method,
                    'path': request.url.path,
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'duration_ms': f"{duration_ms:.2f}"
                },
                exc_info=True
            )
            raise
            
        finally:
            # Clear context to prevent leaks across requests
            clear_context()
