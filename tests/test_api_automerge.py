"""
Comprehensive tests for Auto-Merge logic endpoints.
"""
import pytest
import json
from unittest.mock import patch, MagicMock

class TestAutoMergeAPI:
    """Tests for /api/auto-merge/* endpoints."""

    @pytest.fixture
    def mock_services(self):
        with patch('main.auto_merge_agent') as mock_agent, \
             patch('main.db_service') as mock_db, \
             patch('main.github_service') as mock_gh:
            # Mock session
            mock_session = MagicMock()
            mock_db.get_session.return_value.__enter__.return_value = mock_session
            yield mock_agent, mock_db, mock_gh

    def test_evaluate_auto_merge_success(self, client, mock_services):
        """Test PR evaluation for auto-merge."""
        mock_agent, _, mock_gh = mock_services
        
        # Mock DB record
        mock_pr_rec = MagicMock()
        mock_pr_rec.overall_quality_score = 90
        mock_pr_rec.security_score = 100
        mock_pr_rec.maintainability_score = 80
        mock_pr_rec.id = 1
        # mock_services[1].get_session...
        mock_session = mock_services[1].get_session.return_value.__enter__.return_value
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_pr_rec
        mock_session.query.return_value.filter_by.return_value.all.return_value = [] # Issues
        
        # Mock GitHub calls
        mock_gh.get_pr_details.return_value = {'title': 'Test', 'user': {'login': 'tester'}}
        mock_gh.get_pr_reviews.return_value = []
        mock_gh.check_pr_status_checks.return_value = {'state': 'success'}
        
        mock_agent.should_auto_merge.return_value = (True, "All conditions met", {
            "checks_passed": ["quality", "security"],
            "checks_failed": []
        })
        
        response = client.post(
            '/api/auto-merge/evaluate',
            data=json.dumps({'repository': 'test/repo', 'pr_number': 123}),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['should_merge'] is True
        assert "conditions met" in data['reason']

    def test_evaluate_auto_merge_failed(self, client, mock_services):
        """Test PR evaluation failure for auto-merge."""
        mock_agent, _, mock_gh = mock_services
        
        # Mock DB record
        mock_pr_rec = MagicMock()
        mock_pr_rec.overall_quality_score = 60
        mock_pr_rec.security_score = 70
        mock_pr_rec.maintainability_score = 50
        mock_pr_rec.id = 1
        mock_session = mock_services[1].get_session.return_value.__enter__.return_value
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_pr_rec
        mock_session.query.return_value.filter_by.return_value.all.return_value = [] # Issues
        
        mock_gh.get_pr_details.return_value = {'title': 'Test', 'user': {'login': 'tester'}}
        
        mock_agent.should_auto_merge.return_value = (False, "Quality too low", {
            "checks_passed": ["security"],
            "checks_failed": ["quality"]
        })
        
        response = client.post(
            '/api/auto-merge/evaluate',
            data=json.dumps({'repository': 'test/repo', 'pr_number': 123}),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['should_merge'] is False
        assert data['evaluation']['checks_failed'] == ["quality"]

    def test_auto_merge_config_success(self, client, mock_services):
        """Test retrieving auto-merge configuration."""
        # Note: This endpoint reads from 'config', so we patch that
        with patch('main.config') as mock_config:
            mock_config.get.return_value = {
                'enabled': True,
                'merge_method': 'squash',
                'delete_branch': True
            }
            
            response = client.get('/api/auto-merge/config')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['merge_settings']['merge_method'] == 'squash'
            assert data['merge_settings']['delete_branch'] is True

    def test_execute_auto_merge_success(self, client, mock_services):
        """Test execution of auto-merge."""
        mock_agent, _, mock_gh = mock_services
        
        mock_agent.should_auto_merge.return_value = (True, "OK", {})
        mock_agent.get_merge_config.return_value = {
            'merge_method': 'merge',
            'delete_branch': True,
            'post_merge_comment': True
        }
        mock_gh.merge_pr.return_value = {
            'success': True,
            'merged': True,
            'message': "Merged",
            'sha': 'abc123'
        }
        
        # Need to mock the DB lookup inside evaluate_auto_merge component
        mock_session = mock_services[1].get_session.return_value.__enter__.return_value
        mock_pr_rec = MagicMock()
        mock_pr_rec.overall_quality_score = 90
        mock_pr_rec.security_score = 100
        mock_pr_rec.maintainability_score = 80
        mock_pr_rec.files_changed = 5
        mock_pr_rec.lines_added = 100
        mock_pr_rec.lines_deleted = 10
        mock_pr_rec.id = 1
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_pr_rec
        mock_session.query.return_value.filter_by.return_value.all.return_value = [] # Issues
        
        mock_gh.get_pr_details.return_value = {'title': 'Test', 'user': {'login': 'tester'}}
        mock_gh.get_pr_reviews.return_value = []
        mock_gh.check_pr_status_checks.return_value = {'state': 'success'}
        
        response = client.post(
            '/api/auto-merge/execute',
            data=json.dumps({'repository': 'test/repo', 'pr_number': 123}),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['message'] == "Merged"
