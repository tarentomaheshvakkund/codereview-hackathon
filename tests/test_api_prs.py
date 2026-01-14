"""
Comprehensive tests for PR Management and Comments endpoints.
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime

from types import SimpleNamespace

from types import SimpleNamespace

class TestPRsAPI:
    """Tests for /api/prs/* endpoints."""

    @pytest.fixture
    def mock_db_session(self):
        with patch('main.db_service.get_session') as mock:
            mock_session = MagicMock()
            mock.return_value.__enter__.return_value = mock_session
            yield mock_session

    def _create_mock_query(self, result=None, is_all=True):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        if is_all:
            mock_query.all.return_value = result if result is not None else []
        else:
            mock_query.first.return_value = result
        return mock_query

    def _create_mock_pr_analysis(self):
        return SimpleNamespace(
            id=1,
            pr_number=123,
            pr_title="Test PR",
            pr_url="http://gh.com/pr/123",
            repository="test/repo",
            author_login="tester",
            author_name="Tester",
            author_email="test@example.com",
            base_branch="main",
            head_branch="feature",
            pr_description="Test Description",
            pr_created_at=datetime(2025, 12, 19).isoformat(),
            pr_updated_at=datetime(2025, 12, 20).isoformat(),
            analyzed_at=datetime(2025, 12, 20),
            overall_quality_score=85.0,
            security_score=100.0,
            maintainability_score=80.0,
            total_issues=10,
            critical_issues=0,
            high_issues=2,
            medium_issues=3,
            low_issues=5,
            files_changed=5,
            lines_added=150,
            lines_deleted=20,
            estimated_coverage=75.0,
            has_rag_insights=False,
            static_analysis_issues=0,
            security_issues=0,
            code_quality_issues=0,
            context_issues=0,
            coverage_issues=0,
            test_to_code_ratio=0.5,
            complexity_score=10,
            rag_insights=None,
            rag_risk_score=0.2,
            rag_novelty_score=0.1,
            rag_similar_prs_count=5, # Required by get_prs_by_email
            rag_recommendations_count=2, # Required by get_prs_by_email
            analysis_duration_ms=1000
        )

    def _create_mock_comment(self):
        return SimpleNamespace(
            id=1,
            comment_id='c1',
            comment_type='inline',
            file_path='a.py',
            line_number=10,
            commit_sha='sha123',
            comment_body='test body',
            comment_preview='test...',
            issue_severity='medium',
            issue_type='code_quality',
            posted_successfully=True,
            review_event='COMMENT',
            github_url='http://gh.com/comment/1',
            reactions_count=0,
            replies_count=0,
            was_edited=False,
            was_resolved=False,
            resolved_at=None,
            posted_at=datetime.now(),
            github_comment_id=1,
            github_review_id=1
        )

    def test_get_prs_by_email_success(self, client, mock_db_session):
        """Test retrieving PRs for an email address."""
        mock_pr = self._create_mock_pr_analysis()
        mock_db_session.query.return_value = self._create_mock_query(result=[mock_pr], is_all=True)

        response = client.post(
            '/api/prs/list',
            data=json.dumps({"email": "user@example.com"}),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data['prs']) == 1
        assert data['prs'][0]['pr_number'] == 123

    def test_get_prs_by_email_missing_body(self, client):
        """Test PR list endpoint without email."""
        response = client.post(
            '/api/prs/list',
            data=json.dumps({}),
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_get_pr_details_success(self, client, mock_db_session):
        """Test retrieving detailed PR analysis via /api/prs/details."""
        mock_pr = self._create_mock_pr_analysis()
        
        # Robust mocking: Handle different queries based on model
        def query_side_effect(model):
            # Check model name (handling both class object and potentially string imports)
            model_name = getattr(model, '__name__', str(model))
            
            if 'PRAnalysis' in model_name:
                # For PR lookup: return mock_pr on first()
                q = self._create_mock_query(result=mock_pr, is_all=False)
                # Also ensure filter_by(...).first() works
                q.filter_by.return_value = q
                return q
            elif 'PRIssue' in model_name:
                # For Issues lookup: return empty list on all()
                q = self._create_mock_query(result=[], is_all=True)
                return q
            else:
                # Default (e.g. RAG tables)
                return self._create_mock_query(result=[], is_all=True)

        mock_db_session.query.side_effect = query_side_effect
        
        # We can still try to patch _find_pr_by_number for double safety,
        # but the side_effect should handle the fallback if patch is bypassed.
        with patch('main._find_pr_by_number', return_value=mock_pr):
            response = client.post(
                '/api/prs/details',
                data=json.dumps({'repository': 'test/repo', 'pr_number': 123}),
                content_type='application/json'
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['pr']['pr_number'] == 123

    def test_get_pr_comments_success(self, client, mock_db_session):
        """Test retrieving PR comments tracking data."""
        mock_pr = self._create_mock_pr_analysis()
        mock_comment = self._create_mock_comment()
        
        # Sequentially return query mocks for PR lookup then Comment lookup
        mock_db_session.query.side_effect = [
            self._create_mock_query(result=mock_pr, is_all=False), # _find_pr_by_number
            self._create_mock_query(result=[mock_comment], is_all=True) # _get_pr_comments_from_db
        ]
        
        response = client.post(
            '/api/prs/comments',
            data=json.dumps({'repository': 'test/repo', 'pr_number': 123}),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['comments'][0]['id'] == 1
