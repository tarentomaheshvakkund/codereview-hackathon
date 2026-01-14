"""
Centralized error handling utilities for the PR Review System.

This module provides:
- Custom API error classes
- Error response formatting
- Request ID tracking
- Standardized error responses
"""
import uuid
from functools import wraps
from typing import Optional, Dict, Any
from flask import request, jsonify, g
from utils.logger import logger


# ============================================================================
# Error Codes
# ============================================================================

class ErrorCode:
    """Standard error codes for the API."""
    # Authentication errors (1xxx)
    AUTH_REQUIRED = "AUTH_001"
    AUTH_INVALID_TOKEN = "AUTH_002"  # nosec B105
    AUTH_EXPIRED_TOKEN = "AUTH_003"  # nosec B105
    AUTH_INVALID_CREDENTIALS = "AUTH_004"
    AUTH_SERVICE_UNAVAILABLE = "AUTH_005"

    # Validation errors (2xxx)
    VALIDATION_REQUIRED_FIELD = "VAL_001"
    VALIDATION_INVALID_FORMAT = "VAL_002"
    VALIDATION_INVALID_VALUE = "VAL_003"

    # Resource errors (3xxx)
    RESOURCE_NOT_FOUND = "RES_001"
    RESOURCE_ALREADY_EXISTS = "RES_002"
    RESOURCE_CONFLICT = "RES_003"

    # External service errors (4xxx)
    GITHUB_API_ERROR = "EXT_001"
    DATABASE_ERROR = "EXT_002"
    OPENAI_API_ERROR = "EXT_003"
    SLACK_API_ERROR = "EXT_004"

    # Internal errors (5xxx)
    INTERNAL_ERROR = "INT_001"
    ANALYSIS_FAILED = "INT_002"
    TIMEOUT = "INT_003"


# ============================================================================
# Custom Exceptions
# ============================================================================

class APIError(Exception):
    """
    Base exception for API errors.

    Attributes:
        message: Human-readable error message
        code: Error code from ErrorCode class
        status_code: HTTP status code
        details: Optional additional error details
    """

    def __init__(
        self,
        message: str,
        code: str = ErrorCode.INTERNAL_ERROR,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert the error to a dictionary for JSON response."""
        error_dict = {
            'error': self.message,
            'code': self.code,
            'request_id': getattr(g, 'request_id', None)
        }
        if self.details:
            error_dict['details'] = self.details
        return error_dict


class ValidationError(APIError):
    """Raised when request validation fails."""

    def __init__(self, message: str, field: Optional[str] = None):
        details = {'field': field} if field else None
        super().__init__(
            message=message,
            code=ErrorCode.VALIDATION_REQUIRED_FIELD,
            status_code=400,
            details=details
        )


class AuthenticationError(APIError):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message=message,
            code=ErrorCode.AUTH_REQUIRED,
            status_code=401
        )


class NotFoundError(APIError):
    """Raised when a resource is not found."""

    def __init__(self, resource_type: str, identifier: Any):
        super().__init__(
            message=f"{resource_type} not found: {identifier}",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            details={'resource_type': resource_type, 'identifier': str(identifier)}
        )


class ExternalServiceError(APIError):
    """Raised when an external service fails."""

    def __init__(self, service: str, message: str, code: str = ErrorCode.INTERNAL_ERROR):
        super().__init__(
            message=f"{service} error: {message}",
            code=code,
            status_code=502,
            details={'service': service}
        )


# ============================================================================
# Request ID Middleware
# ============================================================================

def generate_request_id() -> str:
    """Generate a unique request ID."""
    return str(uuid.uuid4())[:8]


def request_id_middleware(app):
    """
    Middleware to add request ID to all requests.

    Usage:
        request_id_middleware(app)
    """
    @app.before_request
    def before_request():
        # Check if request ID is provided in header, otherwise generate one
        g.request_id = request.headers.get('X-Request-ID', generate_request_id())

    @app.after_request
    def after_request(response):
        # Add request ID to response headers
        response.headers['X-Request-ID'] = getattr(g, 'request_id', 'unknown')
        return response


# ============================================================================
# Error Response Formatting
# ============================================================================

def format_error_response(
    message: str,
    code: str = ErrorCode.INTERNAL_ERROR,
    status_code: int = 500,
    details: Optional[Dict[str, Any]] = None
) -> tuple:
    """
    Format a standardized error response.

    Args:
        message: Human-readable error message
        code: Error code
        status_code: HTTP status code
        details: Optional additional details

    Returns:
        Tuple of (response_dict, status_code)
    """
    response = {
        'success': False,
        'error': message,
        'code': code,
        'request_id': getattr(g, 'request_id', None)
    }
    if details:
        response['details'] = details

    return jsonify(response), status_code


def register_error_handlers(app):
    """
    Register error handlers for the Flask app.

    Usage:
        register_error_handlers(app)
    """

    @app.errorhandler(APIError)
    def handle_api_error(error):
        """Handle custom API errors."""
        logger.warning(
            "API error",
            error=error.message,
            code=error.code,
            request_id=getattr(g, 'request_id', None)
        )
        return jsonify(error.to_dict()), error.status_code

    @app.errorhandler(400)
    def handle_bad_request(error):
        """Handle 400 Bad Request errors."""
        return format_error_response(
            # pylint: disable=no-member
            message=str(error.description) if hasattr(error, 'description') else "Bad request",
            code=ErrorCode.VALIDATION_INVALID_FORMAT,
            status_code=400
        )

    @app.errorhandler(404)
    def handle_not_found(_error):
        """Handle 404 Not Found errors."""
        return format_error_response(
            message="Resource not found",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404
        )

    @app.errorhandler(405)
    def handle_method_not_allowed(_error):
        """Handle 405 Method Not Allowed errors."""
        return format_error_response(
            message="Method not allowed",
            code=ErrorCode.VALIDATION_INVALID_FORMAT,
            status_code=405
        )

    @app.errorhandler(500)
    def handle_internal_error(error):
        """Handle 500 Internal Server Error."""
        logger.error(
            "Internal server error",
            error=str(error),
            request_id=getattr(g, 'request_id', None)
        )
        return format_error_response(
            message="Internal server error",
            code=ErrorCode.INTERNAL_ERROR,
            status_code=500
        )


# ============================================================================
# Health Check Utilities
# ============================================================================

def check_service_health(service_name: str, check_func: callable) -> Dict[str, Any]:
    """
    Check the health of an external service.

    Args:
        service_name: Name of the service
        check_func: Function that returns True if healthy

    Returns:
        Dictionary with health status
    """
    try:
        is_healthy = check_func()
        return {
            'service': service_name,
            'status': 'healthy' if is_healthy else 'unhealthy',
            'available': is_healthy
        }
    except Exception as e:
        return {
            'service': service_name,
            'status': 'error',
            'available': False,
            'error': str(e)
        }


# ============================================================================
# Retry Decorator
# ============================================================================

def with_retry(max_attempts: int = 3, delay: float = 1.0, exceptions: tuple = (Exception,)):
    """
    Decorator to retry a function on failure.

    Args:
        max_attempts: Maximum number of attempts
        delay: Delay between attempts in seconds
        exceptions: Tuple of exceptions to catch
    """
    import time

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"Retry attempt {attempt + 1}/{max_attempts}",
                            function=func.__name__,
                            error=str(e)
                        )
                        time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator
