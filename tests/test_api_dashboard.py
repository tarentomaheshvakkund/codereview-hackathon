"""
Comprehensive tests for Dashboard and Insights endpoints.
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime

class TestDashboardAPI:
    """Tests for /api/dashboard/* endpoints."""

    @pytest.fixture
    def mock_services(self):
        with patch('main.db_service') as mock_db, \
             patch('main.analytics_service') as mock_analytics:
            yield mock_db, mock_analytics

    def test_get_user_insights_success(self, client, mock_services):
        """Test retrieving user insights."""
        _, mock_analytics = mock_services
        mock_analytics.get_user_insights.return_value = {
            'author': 'testuser',
            'quality_score': 85,
            'recommendations': ['Refactor large methods']
        }
        
        response = client.get('/api/dashboard/user/testuser/insights')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['author'] == 'testuser'
        assert 85 in [data['quality_score']]

    def test_get_user_statistics_by_login(self, client, mock_services):
        """Test retrieving user statistics using username."""
        mock_db, _ = mock_services
        
        # Mocking the UserStatistics object returned by DB service
        mock_stats = MagicMock()
        mock_stats.author_login = "testuser"
        mock_stats.author_email = "test@example.com"
        mock_stats.total_prs = 10
        mock_stats.total_issues_found = 50
        mock_stats.avg_quality_score = 90.0
        mock_stats.avg_security_score = 95.0
        mock_stats.avg_maintainability_score = 88.0
        mock_stats.avg_coverage = 75.0
        # Distribution
        mock_stats.critical_issues_total = 1
        mock_stats.high_issues_total = 5
        mock_stats.medium_issues_total = 15
        mock_stats.low_issues_total = 29
        # Trends & RAG
        mock_stats.quality_trend = []
        mock_stats.security_trend = []
        mock_stats.coverage_trend = []
        mock_stats.rag_risk_trend = []
        mock_stats.rag_novelty_trend = []
        mock_stats.total_rag_insights = 5
        mock_stats.avg_rag_risk_score = 0.2
        mock_stats.avg_rag_novelty_score = 0.8
        mock_stats.total_similar_prs_referenced = 10
        mock_stats.total_rag_recommendations = 3
        mock_stats.total_patterns_identified = 2
        mock_stats.high_risk_prs_count = 0
        mock_stats.novel_prs_count = 5
        mock_stats.most_common_patterns = []
        mock_stats.learning_velocity = 1.0
        mock_stats.common_issues = []
        mock_stats.improvement_areas = []
        mock_stats.strengths = []
        mock_stats.first_pr_date = datetime(2025, 1, 1)
        mock_stats.last_pr_date = datetime(2025, 12, 1)
        
        mock_db.get_user_statistics.return_value = mock_stats
        
        response = client.get('/api/dashboard/user/testuser/statistics')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['author_login'] == "testuser"
        assert data['total_prs'] == 10

    def test_get_user_statistics_by_email(self, client, mock_services):
        """Test retrieving user statistics using email."""
        mock_db, _ = mock_services
        
        # Similar mock for email lookup
        mock_stats = MagicMock()
        mock_stats.author_login = "testuser"
        mock_stats.author_email = "test@user.com"
        mock_stats.total_prs = 5
        mock_stats.total_issues_found = 10
        mock_stats.avg_quality_score = 80.0
        mock_stats.avg_security_score = 80.0
        mock_stats.avg_maintainability_score = 80.0
        mock_stats.avg_coverage = 80.0
        mock_stats.critical_issues_total = 0
        mock_stats.high_issues_total = 0
        mock_stats.medium_issues_total = 0
        mock_stats.low_issues_total = 0
        mock_stats.quality_trend = []
        mock_stats.security_trend = []
        mock_stats.coverage_trend = []
        mock_stats.rag_risk_trend = []
        mock_stats.rag_novelty_trend = []
        mock_stats.total_rag_insights = 0
        mock_stats.avg_rag_risk_score = 0
        mock_stats.avg_rag_novelty_score = 0
        mock_stats.total_similar_prs_referenced = 0
        mock_stats.total_rag_recommendations = 0
        mock_stats.total_patterns_identified = 0
        mock_stats.high_risk_prs_count = 0
        mock_stats.novel_prs_count = 0
        mock_stats.most_common_patterns = []
        mock_stats.learning_velocity = 0
        mock_stats.common_issues = []
        mock_stats.improvement_areas = []
        mock_stats.strengths = []
        mock_stats.first_pr_date = None
        mock_stats.last_pr_date = None
        
        mock_db.get_user_statistics_by_email.return_value = mock_stats
        
        response = client.get('/api/dashboard/user/test@user.com/statistics')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['author_email'] == "test@user.com"

    def test_get_repository_stats_success(self, client, mock_services):
        """Test retrieving repository statistics."""
        mock_db, _ = mock_services
        mock_db.get_repository_stats.return_value = {
            'repository': 'test/repo',
            'total_prs': 100,
            'avg_score': 92.5
        }
        
        response = client.get('/api/dashboard/repository/test/repo/stats')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['repository'] == 'test/repo'

    def test_get_pr_analysis_not_found(self, client, mock_services):
        """Test PR analysis retrieval when PR doesn't exist."""
        mock_db, _ = mock_services
        
        # Mock session and query
        mock_session = MagicMock()
        mock_db.get_session.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = None
        
        response = client.get('/api/dashboard/pr/test/repo/999')
        
        assert response.status_code == 404
        assert b'PR analysis not found' in response.data
