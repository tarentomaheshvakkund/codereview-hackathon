"""
Comprehensive tests for Authentication API endpoints.
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from uuid import uuid4

class TestAuthAPI:
    """Tests for /api/auth/* endpoints."""

    @pytest.fixture
    def mock_auth_service(self):
        with patch('main.auth_service') as mock:
            yield mock

    def test_register_success(self, client, mock_auth_service):
        """Test successful user registration."""
        mock_auth_service.register_user.return_value = (True, "User registered successfully", {
            "user_id": str(uuid4()),
            "username": "testuser",
            "email": "test@example.com"
        })
        
        response = client.post(
            '/api/auth/register',
            data=json.dumps({
                "username": "testuser",
                "email": "test@example.com",
                "password": "password123"
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['user']['username'] == "testuser"

    def test_register_duplicate_email(self, client, mock_auth_service):
        """Test registration with existing email."""
        mock_auth_service.register_user.return_value = (False, "Email already registered", None)
        
        response = client.post(
            '/api/auth/register',
            data=json.dumps({
                "username": "newuser",
                "email": "existing@example.com",
                "password": "password123"
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert "already registered" in data['error']

    def test_login_success(self, client, mock_auth_service):
        """Test successful login."""
        mock_auth_service.login_user.return_value = (True, "Login successful", {
            "token": "fake-jwt-token",
            "user_id": str(uuid4()),
            "username": "testuser"
        })
        
        response = client.post(
            '/api/auth/login',
            data=json.dumps({
                "email": "test@example.com",
                "password": "password123"
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['session']['token'] == "fake-jwt-token"

    def test_login_invalid_credentials(self, client, mock_auth_service):
        """Test login with wrong password."""
        mock_auth_service.login_user.return_value = (False, "Invalid email or password", None)
        
        response = client.post(
            '/api/auth/login',
            data=json.dumps({
                "email": "test@example.com",
                "password": "wrongpassword"
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 401
        data = json.loads(response.data)
        assert data['success'] is False
        assert "Invalid" in data['error']

    def test_validate_token_success(self, client, mock_auth_service):
        """Test token validation via @require_auth decorator."""
        user_uuid = str(uuid4())
        mock_auth_service.validate_session.return_value = (True, {
            "user_id": user_uuid,
            "username": "testuser",
            "email": "test@example.com"
        })
        
        response = client.get(
            '/api/auth/validate',
            headers={'Authorization': 'Bearer valid-token'}
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['valid'] is True
        assert data['user']['user_id'] == user_uuid

    def test_validate_token_invalid(self, client, mock_auth_service):
        """Test validation with invalid token."""
        mock_auth_service.validate_session.return_value = (False, None)
        
        response = client.get(
            '/api/auth/validate',
            headers={'Authorization': 'Bearer invalid-token'}
        )
        
        assert response.status_code == 401
        data = json.loads(response.data)
        assert "Invalid or expired" in data['error']

    def test_logout_success(self, client, mock_auth_service):
        """Test successful logout."""
        # Fix mock for decorator first
        mock_auth_service.validate_session.return_value = (True, {"user_id": str(uuid4())})
        # Mock logout call
        mock_auth_service.logout_user.return_value = (True, "Logout successful")
        
        response = client.post(
            '/api/auth/logout',
            headers={'Authorization': 'Bearer valid-token'}
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert "Logout successful" in data['message']

    def test_get_sessions_success(self, client, mock_auth_service):
        """Test retrieving active sessions."""
        user_uuid = str(uuid4())
        mock_auth_service.validate_session.return_value = (True, {"user_id": user_uuid})
        mock_auth_service.get_user_active_sessions.return_value = [
            {"session_id": 1, "ip_address": "127.0.0.1", "user_agent": "Pytest"}
        ]
        
        response = client.get(
            '/api/auth/sessions',
            headers={'Authorization': 'Bearer valid-token'}
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data['sessions']) == 1
        assert data['sessions'][0]['ip_address'] == "127.0.0.1"
