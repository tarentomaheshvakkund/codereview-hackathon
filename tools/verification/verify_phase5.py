import os
import sys
import logging
from unittest.mock import MagicMock, patch
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock environment variables
os.environ['RAG_ENABLED'] = 'true'
os.environ['VECTOR_DB_PATH'] = ':memory:'
os.environ['AI_PROVIDER'] = 'openai'
os.environ['OPENAI_API_KEY'] = 'mock-key'

# Import models
sys.path.append(os.getcwd())
from models.pr_event import PREvent, PRAuthor, PRFile
from models.analysis_result import Issue, Severity, IssueType, AgentResult
from agents.rag_enhanced_agent import RAGEnhancedAgent

class MockDBService:
    def __init__(self):
        self.patterns = [
            {'name': 'Security: SQL Injection', 'solutions': ['Use prepared statements']},
            {'name': 'Quality: Long Method', 'solutions': ['Refactor into smaller methods']}
        ]
    
    def get_pr_feedback(self, pr_number, repository):
        return []

    def get_common_patterns(self, category=None, limit=5):
        return self.patterns

    def update_pattern_library(self, *args, **kwargs):
        pass

def test_phase5_features():
    print("\n🧪 Testing RAG Phase 5: Specialized Collections & Patterns...")
    
    mock_db = MockDBService()
    agent = RAGEnhancedAgent(db_service=mock_db)
    
    repo = "org/repo"
    now = datetime.now()
    
    # --- 1. Test Collection Routing ---
    print("\nStep 1: Testing Specialized Collection Routing...")
    
    # Security PR
    security_pr = PREvent(
        action='test', id=101, pr_number=101, pr_title="Fix SQLi", pr_description="", 
        pr_url="", repository=repo, repository_url="", 
        author=PRAuthor(login="u", id=1, avatar_url=""),
        base_branch="m", head_branch="f", 
        files=[PRFile(filename="db.py", status="modified", additions=5, deletions=5, changes=10, patch="cursor.execute(f'SELECT * FROM users WHERE id={id}')")], 
        created_at=now, updated_at=now, is_draft=False
    )
    
    security_issues = [
        Issue(type=IssueType.SECURITY, severity=Severity.CRITICAL, message="SQL injection", file="db.py", line=10, suggestion="Use params")
    ]
    
    agent_results = {'security_agent': AgentResult(agent_name='security', success=True, execution_time=0.1, issues=security_issues)}
    
    # Pre-index the PR so _update_pr_analysis_results can find it
    pr_id = f"pr_{repo}_101"
    agent.vector_db.add(
        ids=[pr_id],
        metadatas=[{'repository': repo, 'pr_number': 101}],
        documents=["Initial document"]
    )
    
    indexed = agent.vector_db.get(ids=[pr_id])
    print(f"  - Indexed metadata: {indexed['metadatas']}")
    
    # Store the PR
    agent._update_pr_analysis_results(security_pr, security_issues, agent_results)
    
    # Verify it landed in the security collection
    sec_count = agent.specialized_collections['security'].count()
    print(f"  - Security Collection Count: {sec_count}")
    
    if sec_count == 1:
        print("✅ Specialized routing (Security) works!")
    else:
        print("❌ Specialized routing (Security) failed.")

    # --- 2. Test Specialized Retrieval ---
    print("\nStep 2: Testing Context Routing (Retrieval)...")
    
    # PR with SQL keyword
    query_pr = PREvent(
        action='test', id=102, pr_number=102, pr_title="New Query", pr_description="", 
        pr_url="", repository=repo, repository_url="", 
        author=PRAuthor(login="u", id=1, avatar_url=""),
        base_branch="m", head_branch="f", 
        files=[PRFile(filename="query.py", status="modified", additions=5, deletions=0, changes=5, patch="sql = 'SELECT *'")], 
        created_at=now, updated_at=now, is_draft=False
    )
    
    # Replace collections with mocks to verify they are called
    mock_main = MagicMock()
    mock_main.query.return_value = {'ids': [['pr1']], 'metadatas': [[{}]], 'documents': [['doc']], 'distances': [[0.1]]}
    mock_main.count.return_value = 1
    agent.vector_db = mock_main
    
    mock_sec = MagicMock()
    mock_sec.query.return_value = {'ids': [['pr2']], 'metadatas': [[{}]], 'documents': [['doc']], 'distances': [[0.05]]}
    mock_sec.count.return_value = 1
    agent.specialized_collections['security'] = mock_sec
    
    # This should merge results from main and security
    results = agent._retrieve_relevant_context(query_pr)
    
    # Verify specialized collection was called
    if mock_sec.query.called:
        print("✅ Specialized retrieval (Security) was triggered!")
    else:
        print("❌ Specialized retrieval (Security) was NOT triggered.")

    # --- 3. Test Pattern Injection ---
    print("\nStep 3: Testing Pattern Injection into Prompt...")
    
    # Use the correct method name and provide required context
    prompt = agent._build_rag_prompt(query_pr, {'similar_prs': [], 'best_practices': [], 'historical_issues': []})
    
    if "APPLICABLE LEARNED PATTERNS" in prompt and "SQL Injection" in prompt:
        print("✅ Pattern injection works!")
    else:
        print("❌ Pattern injection failed.")
    
    print("\nPhase 5 Verification Complete!")

if __name__ == "__main__":
    test_phase5_features()
