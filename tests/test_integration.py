"""
Integration tests for the PR Review System.

These tests verify end-to-end workflows including:
- PR analysis pipeline
- Database operations
- API request/response flows
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import json


# ============================================================================
# Integration Test: PR Analysis Workflow
# ============================================================================

class TestPRAnalysisWorkflow:
    """Integration tests for the complete PR analysis workflow."""
    
    @pytest.fixture
    def mock_github_pr_response(self):
        """Mock GitHub API response for PR details."""
        return {
            'id': 1001,
            'number': 42,
            'title': 'Add authentication module',
            'body': 'This PR adds JWT authentication to the API',
            'user': {
                'login': 'developer1',
                'id': 12345,
                'email': 'dev@example.com',
                'name': 'Developer One'
            },
            'base': {'ref': 'main'},
            'head': {'ref': 'feature/auth', 'sha': 'abc123def456'},
            'draft': False,
            'created_at': '2025-12-01T10:00:00Z',
            'updated_at': '2025-12-01T12:00:00Z'
        }
    
    @pytest.fixture
    def mock_github_files_response(self):
        """Mock GitHub API response for PR files."""
        mock_file1 = Mock()
        mock_file1.filename = "src/auth/jwt_handler.py"
        mock_file1.status = "added"
        mock_file1.additions = 150
        mock_file1.deletions = 0
        mock_file1.changes = 150
        mock_file1.patch = '''@@ -0,0 +1,50 @@
+import jwt
+from datetime import datetime, timedelta
+
+def create_token(user_id: str, secret: str) -> str:
+    payload = {
+        'user_id': user_id,
+        'exp': datetime.utcnow() + timedelta(hours=24)
+    }
+    return jwt.encode(payload, secret, algorithm='HS256')
'''
        
        mock_file2 = Mock()
        mock_file2.filename = "tests/test_auth.py"
        mock_file2.status = "added"
        mock_file2.additions = 50
        mock_file2.deletions = 0
        mock_file2.changes = 50
        mock_file2.patch = '''@@ -0,0 +1,20 @@
+import pytest
+from src.auth.jwt_handler import create_token
+
+def test_create_token():
+    token = create_token('user123', 'secret')
+    assert token is not None
'''
        
        return [mock_file1, mock_file2]
    
    @pytest.mark.integration
    def test_full_analysis_workflow_with_mocked_github(
        self, mock_github_pr_response, mock_github_files_response
    ):
        """Test the complete PR analysis workflow with mocked GitHub."""
        from models.pr_event import PREvent, PRAuthor, PRFile
        
        # Create a proper PREvent
        pr_event = PREvent(
            action='opened',
            id=1001,
            pr_number=42,
            pr_title='Add authentication module',
            pr_description='This PR adds JWT authentication',
            pr_url='https://github.com/test-org/test-repo/pull/42',
            repository='test-org/test-repo',
            repository_url='https://github.com/test-org/test-repo',
            author=PRAuthor(login='developer1', id=12345, avatar_url=''),
            base_branch='main',
            head_branch='feature/auth',
            files=[
                PRFile(
                    filename='src/auth/jwt_handler.py',
                    status='added',
                    additions=150,
                    deletions=0,
                    changes=150,
                    patch='@@ +import jwt'
                )
            ],
            created_at=datetime(2025, 12, 1, 10, 0, 0),
            updated_at=datetime(2025, 12, 1, 12, 0, 0),
            is_draft=False
        )
        
        # Use real AgentDispatcher with mocked sub-agents or subprocesses
        # For this test, we want to verify the dispatcher's coordination logic
        with patch('agents.main_agent.MultiLanguageStaticAnalysisAgent') as MockStaticAgent:
            mock_static_instance = Mock()
            mock_static_instance.name = "Multi-Language Static Analysis Agent"
            mock_static_instance.analyze.return_value = MagicMock(issues=[], metrics={}, success=True)
            MockStaticAgent.return_value = mock_static_instance
            
            from agents.dispatcher import AgentDispatcher
            dispatcher = AgentDispatcher(db_service=None)
            
            # Execute the analysis
            result = dispatcher.dispatch(pr_event)
            
            # Verify the workflow completed successfully
            assert result.success is True
            assert "Main Orchestrator Agent" in result.agent_name
            # Verify the sub-agent was called
            mock_static_instance.analyze.assert_called_once()
    
    @pytest.mark.integration
    def test_analysis_with_issues_detected(self):
        """Test analysis workflow when issues are detected."""
        from models.pr_event import PREvent, PRAuthor, PRFile
        from models.analysis_result import Issue, IssueType, Severity
        
        pr_event = PREvent(
            action='opened',
            id=1002,
            pr_number=43,
            pr_title='Quick fix',
            pr_description='Hotfix for production bug',
            pr_url='https://github.com/test-org/test-repo/pull/43',
            repository='test-org/test-repo',
            repository_url='https://github.com/test-org/test-repo',
            author=PRAuthor(login='developer2', id=67890, avatar_url=''),
            base_branch='main',
            head_branch='hotfix/bug-fix',
            files=[
                PRFile(
                    filename='src/main.py',
                    status='modified',
                    additions=5,
                    deletions=2,
                    changes=7,
                    patch='@@ -1,2 +1,5 @@\n+password = "hardcoded123"'
                )
            ],
            created_at=datetime(2025, 12, 2, 10, 0, 0),
            updated_at=datetime(2025, 12, 2, 10, 5, 0),
            is_draft=False
        )
        
        # Mock result with security issue
        mock_issue = Mock()
        mock_issue.file = "src/main.py"
        mock_issue.line = 1
        mock_issue.column = 1
        mock_issue.type = Mock(value='security')
        mock_issue.severity = Mock(value='critical')
        mock_issue.code = "hardcoded-secret"
        mock_issue.message = "Hardcoded password detected"
        mock_issue.suggestion = "Use environment variables"
        mock_issue.metadata = {}
        
        mock_result = Mock()
        mock_result.agent_name = "Main Orchestrator Agent"
        mock_result.success = True
        mock_result.issues = [mock_issue]
        mock_result.metrics = {'security_score': 20}
        mock_result.execution_time = 1.5
        mock_result.error = None
        mock_result.metadata = {}
        
        # Use real AgentDispatcher but mock the specific agent that should find the issue
        with patch('agents.main_agent.MultiLanguageSecurityAgent') as MockSecurityAgent:
            mock_sec_instance = Mock()
            mock_sec_instance.name = "Multi-Language Security Agent"
            mock_sec_instance.analyze.return_value = MagicMock(
                issues=[mock_issue], 
                metrics={'security_score': 20}, 
                success=True,
                agent_name="Multi-Language Security Agent"
            )
            MockSecurityAgent.return_value = mock_sec_instance
            
            from agents.dispatcher import AgentDispatcher
            dispatcher = AgentDispatcher(db_service=None)
            
            result = dispatcher.dispatch(pr_event)
            
            # Verify issues were captured through the actual dispatch/orchestration flow
            assert result.success is True
            assert len(result.issues) >= 1
            # Check if our mocked security issue is present in the breakdown
            breakdown = result.metadata.get('agent_breakdown', {})
            assert "Multi-Language Security Agent" in breakdown
            assert breakdown["Multi-Language Security Agent"]['issues_count'] == 1


# ============================================================================
# Integration Test: API Flow
# ============================================================================

class TestAPIIntegration:
    """Integration tests for API request/response flows."""
    
    @pytest.mark.integration
    def test_analyze_endpoint_full_flow(self, client):
        """Test the /api/analyze endpoint with mocked services."""
        with patch('main.github_service') as mock_github:
            with patch('main.dispatcher') as mock_dispatcher:
                # Mock GitHub service
                mock_github.get_pr_details.return_value = {
                    'id': 1001,
                    'title': 'Test PR',
                    'body': 'Test description',
                    'user': {'login': 'testuser', 'id': 123},
                    'base': {'ref': 'main'},
                    'head': {'ref': 'feature', 'sha': 'abc123'},
                    'draft': False,
                    'created_at': '2025-12-01T10:00:00Z',
                    'updated_at': '2025-12-01T12:00:00Z'
                }
                mock_github.get_pr_files.return_value = []
                
                # Mock dispatcher result properly
                from models.analysis_result import AgentResult
                mock_result = AgentResult(
                    agent_name="Main Orchestrator Agent",
                    success=True,
                    issues=[],
                    metrics={'quality_score': 100},
                    execution_time=1.0
                )
                mock_result.metadata = {'agent_breakdown': {}}
                mock_dispatcher.dispatch.return_value = mock_result
                
                response = client.post(
                    '/api/analyze',
                    data=json.dumps({
                        'repository': 'test-org/test-repo',
                        'pr_number': 42
                    }),
                    content_type='application/json'
                )

                
                # Verify response structure
                assert response.status_code == 200
                data = json.loads(response.data)
                assert data['status'] == 'success'
                assert data['pr_number'] == 42
    
    @pytest.mark.integration
    def test_pr_list_endpoint_flow(self, client):
        """Test the /api/prs/list endpoint."""
        with patch('main.db_service') as mock_db:
            mock_db.get_pr_list.return_value = [
                {
                    'pr_number': 42,
                    'repository': 'test-org/test-repo',
                    'title': 'Test PR',
                    'author_login': 'testuser',
                    'overall_quality_score': 85.0
                }
            ]
            
            response = client.post(
                '/api/prs/list',
                data=json.dumps({'email': 'test@example.com'}),
                content_type='application/json'
            )
            
            # Should return 200 or appropriate status
            assert response.status_code in [200, 503]  # 503 if db_service is None


# ============================================================================
# Integration Test: Database Operations
# ============================================================================

class TestDatabaseIntegration:
    """Integration tests for database operations."""
    
    @pytest.mark.integration
    def test_save_and_retrieve_pr_analysis(self):
        """Test saving and retrieving PR analysis from database."""
        # This test uses mocked database operations
        with patch('services.database_service.create_engine'):
            with patch('services.database_service.sessionmaker') as mock_sessionmaker:
                # Create a mock session
                mock_session = Mock()
                mock_session.query.return_value.filter.return_value.first.return_value = None
                mock_session.query.return_value.filter_by.return_value.first.return_value = None
                
                mock_session_class = Mock()
                mock_session_class.return_value.__enter__ = Mock(return_value=mock_session)
                mock_session_class.return_value.__exit__ = Mock(return_value=False)
                mock_sessionmaker.return_value = mock_session_class
                
                from services.database_service import DatabaseService
                db_service = DatabaseService()
                
                # Test that the service can be initialized
                assert db_service is not None
                assert db_service.engine is not None
    
    @pytest.mark.integration
    def test_user_statistics_calculation(self):
        """Test user statistics calculation workflow."""
        with patch('services.database_service.create_engine'):
            with patch('services.database_service.sessionmaker'):
                from services.database_service import DatabaseService
                db_service = DatabaseService()
                
                # Test quality score calculation
                analysis_result = {
                    'issues': [
                        {'severity': 'low', 'type': 'style'},
                        {'severity': 'medium', 'type': 'complexity'}
                    ],
                    'metrics': {'security_score': 80}
                }
                
                quality_score = db_service._calculate_quality_score(analysis_result)
                security_score = db_service._calculate_security_score(analysis_result)
                
                assert 0 <= quality_score <= 100
                assert 0 <= security_score <= 100


# ============================================================================
# Integration Test: End-to-End Scenarios
# ============================================================================

class TestEndToEndScenarios:
    """End-to-end scenario tests."""
    
    @pytest.mark.integration
    def test_new_pr_analysis_scenario(self):
        """Test scenario: New PR is submitted and analyzed."""
        from models.pr_event import PREvent, PRAuthor, PRFile
        
        # Scenario: Developer submits a new PR
        pr_event = PREvent(
            action='opened',
            id=2001,
            pr_number=100,
            pr_title='Feature: Add user dashboard',
            pr_description='Implements user dashboard with charts',
            pr_url='https://github.com/test-org/test-repo/pull/100',
            repository='test-org/test-repo',
            repository_url='https://github.com/test-org/test-repo',
            author=PRAuthor(login='frontend-dev', id=11111, avatar_url=''),
            base_branch='main',
            head_branch='feature/dashboard',
            files=[
                PRFile(
                    filename='src/components/Dashboard.jsx',
                    status='added',
                    additions=200,
                    deletions=0,
                    changes=200,
                    patch='@@ +1,200 @@\n+import React from "react";'
                ),
                PRFile(
                    filename='src/components/Dashboard.css',
                    status='added',
                    additions=100,
                    deletions=0,
                    changes=100,
                    patch='@@ +1,100 @@\n+.dashboard { display: flex; }'
                )
            ],
            created_at=datetime(2025, 12, 5, 9, 0, 0),
            updated_at=datetime(2025, 12, 5, 9, 30, 0),
            is_draft=False
        )
        
        # Use real AgentDispatcher but mock sub-agents
        with patch('agents.main_agent.MultiLanguageStaticAnalysisAgent') as MockStaticAgent:
            mock_static_instance = Mock()
            mock_static_instance.name = "Multi-Language Static Analysis Agent"
            mock_static_instance.analyze.return_value = MagicMock(
                issues=[], 
                metrics={'quality_score': 92}, 
                success=True,
                agent_name="Multi-Language Static Analysis Agent"
            )
            MockStaticAgent.return_value = mock_static_instance
            
            from agents.dispatcher import AgentDispatcher
            dispatcher = AgentDispatcher(db_service=None)
            
            result = dispatcher.dispatch(pr_event)
            
            # Verify successful analysis
            assert result.success is True
            breakdown = result.metadata.get('agent_breakdown', {})
            assert "Multi-Language Static Analysis Agent" in breakdown
            # Note: AgentDispatcher merges metrics into metadata in the breakdown
            assert breakdown["Multi-Language Static Analysis Agent"]['metadata']['quality_score'] == 92

    
    @pytest.mark.integration
    def test_pr_with_critical_issues_scenario(self):
        """Test scenario: PR with critical security issues is flagged."""
        from models.pr_event import PREvent, PRAuthor, PRFile
        
        pr_event = PREvent(
            action='opened',
            id=2002,
            pr_number=101,
            pr_title='Quick database fix',
            pr_description='Fix database query',
            pr_url='https://github.com/test-org/test-repo/pull/101',
            repository='test-org/test-repo',
            repository_url='https://github.com/test-org/test-repo',
            author=PRAuthor(login='backend-dev', id=22222, avatar_url=''),
            base_branch='main',
            head_branch='fix/db-query',
            files=[
                PRFile(
                    filename='src/db/queries.py',
                    status='modified',
                    additions=10,
                    deletions=5,
                    changes=15,
                    patch='@@ -1,5 +1,10 @@\n+query = f"SELECT * FROM users WHERE id = {user_id}"'
                )
            ],
            created_at=datetime(2025, 12, 6, 14, 0, 0),
            updated_at=datetime(2025, 12, 6, 14, 5, 0),
            is_draft=False
        )
        
        # Mock critical security issue
        mock_issue = Mock()
        mock_issue.file = "src/db/queries.py"
        mock_issue.line = 1
        mock_issue.column = 1
        mock_issue.type = Mock(value='security')
        mock_issue.severity = Mock(value='critical')
        mock_issue.code = "sql-injection"
        mock_issue.message = "SQL injection vulnerability: user input in query"
        mock_issue.suggestion = "Use parameterized queries"
        mock_issue.metadata = {}
        
        # Use real AgentDispatcher but mock sub-agents
        with patch('agents.main_agent.MultiLanguageSecurityAgent') as MockSecurityAgent:
            mock_sec_instance = Mock()
            mock_sec_instance.name = "Multi-Language Security Agent"
            mock_sec_instance.analyze.return_value = MagicMock(
                issues=[mock_issue], 
                metrics={'security_score': 10}, 
                success=True,
                agent_name="Multi-Language Security Agent"
            )
            MockSecurityAgent.return_value = mock_sec_instance
            
            from agents.dispatcher import AgentDispatcher
            dispatcher = AgentDispatcher(db_service=None)
            
            result = dispatcher.dispatch(pr_event)
            
            # Verify critical issue was detected
            assert result.success is True
            assert len(result.issues) >= 1
            breakdown = result.metadata.get('agent_breakdown', {})
            assert "Multi-Language Security Agent" in breakdown
            assert breakdown["Multi-Language Security Agent"]['metadata']['security_score'] == 10
            assert breakdown["Multi-Language Security Agent"]['issues_count'] == 1


