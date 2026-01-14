"""
Comprehensive tests for PR Analysis and Webhook endpoints.
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from models.analysis_result import AgentResult

class TestAnalysisAPI:
    """Tests for /api/analyze and /webhook/github."""

    @pytest.fixture
    def mock_services(self):
        with patch('main.github_service') as mock_gh, \
             patch('main.dispatcher') as mock_disp, \
             patch('main.db_service') as mock_db:
            yield mock_gh, mock_disp, mock_db

    def test_analyze_success(self, client, mock_services):
        """Test successful analysis trigger."""
        mock_gh, mock_disp, mock_db = mock_services
        
        # Mock GitHub PR details
        mock_gh.get_pr_details.return_value = {
            'id': 123, 'number': 42, 'title': 'Test', 'body': 'Desc',
            'user': {'login': 'tester', 'id': 1}, 'base': {'ref': 'm'},
            'head': {'ref': 'f', 'sha': 'abc'}, 'draft': False,
            'created_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:00:00Z'
        }
        mock_gh.get_pr_files.return_value = []
        
        # Mock dispatcher result
        mock_result = AgentResult(
            agent_name="Main Orchestrator Agent",
            success=True,
            issues=[],
            metrics={},
            execution_time=1.0
        )
        mock_result.metadata = {'agent_breakdown': {}}
        mock_disp.dispatch.return_value = mock_result
        
        response = client.post(
            '/api/analyze',
            data=json.dumps({
                'repository': 'test/repo',
                'pr_number': 42
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'success'
        assert data['pr_number'] == 42
        mock_disp.dispatch.assert_called_once()

    def test_analyze_invalid_request(self, client):
        """Test analyze endpoint with missing fields."""
        response = client.post(
            '/api/analyze',
            data=json.dumps({'repository': 'test/repo'}), # Missing pr_number
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_webhook_github_opened(self, client, mock_services):
        """Test handling of GitHub 'opened' PR webhook."""
        mock_gh, mock_disp, mock_db = mock_services
        
        # Mock signature validation
        mock_gh.verify_webhook_signature.return_value = True
        
        # Mock dispatcher
        mock_result = AgentResult(agent_name="Agent", success=True, issues=[], metrics={}, execution_time=0.1)
        mock_disp.dispatch.return_value = mock_result
        
        payload = {
            'action': 'opened',
            'repository': {'full_name': 'test/repo', 'html_url': 'url'},
            'pull_request': {
                'id': 12345, # Added missing id
                'number': 42, 'title': 'T', 'body': 'B', 'html_url': 'url',
                'user': {'login': 'u', 'id': 1, 'avatar_url': ''},
                'base': {'ref': 'm'}, 'head': {'ref': 'f', 'sha': 's'},
                'draft': False, 'created_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:00:00Z'
            }
        }
        
        response = client.post(
            '/webhook/github',
            data=json.dumps(payload),
            content_type='application/json',
            headers={'X-Hub-Signature-256': 'sha256=valid'}
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['message'] == 'Analysis completed'
        mock_disp.dispatch.assert_called_once()

    def test_webhook_invalid_signature(self, client, mock_services):
        """Test webhook with invalid signature."""
        mock_gh, _, _ = mock_services
        mock_gh.verify_webhook_signature.return_value = False
        
        response = client.post(
            '/webhook/github',
            data=json.dumps({'action': 'opened', 'pull_request': {}}),
            content_type='application/json',
            headers={'X-Hub-Signature-256': 'sha256=invalid'}
        )
        
        assert response.status_code == 401

    def test_webhook_ignored_action(self, client, mock_services):
        """Test that non-PR related or non-triggering actions are ignored."""
        mock_gh, mock_disp, _ = mock_services
        mock_gh.verify_webhook_signature.return_value = True
        
        response = client.post(
            '/webhook/github',
            data=json.dumps({'action': 'closed', 'pull_request': {}}),
            content_type='application/json',
            headers={'X-Hub-Signature-256': 'sha256=valid'}
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'Ignoring action' in data['message']
        mock_disp.dispatch.assert_not_called()
