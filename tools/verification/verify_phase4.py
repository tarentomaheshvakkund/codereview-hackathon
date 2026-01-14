import os
import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict

# SQLite version workaround for ChromaDB
try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from agents.rag_enhanced_agent import RAGEnhancedAgent
from models.pr_event import PREvent, PRAuthor, PRFile
from services.database_service import DatabaseService
from utils.logger import logger

class MockDBService:
    """Mock DatabaseService for testing Phase 4 logic."""
    def __init__(self):
        self.feedback = {} # (pr_number, repo) -> List[Dict]
        self.patterns = {} # pattern_name -> Dict
        
    def save_rag_feedback(self, pr_analysis_id, rating, is_helpful, 
                         recommendation_id=None, user_comment=None):
        return None

    def get_pr_feedback(self, pr_number, repository=None):
        return self.feedback.get((pr_number, repository), [])

    def update_pattern_library(self, pattern_name, category, pr_info, solution=None):
        if pattern_name not in self.patterns:
            self.patterns[pattern_name] = {'count': 0, 'prs': []}
        self.patterns[pattern_name]['count'] += 1
        self.patterns[pattern_name]['prs'].append(pr_info)
        return None

def test_phase4_features():
    print("\n🧪 Testing RAG Phase 4: Feedback & Multi-Repo...")
    
    # Use in-memory DB for Chroma
    os.environ['VECTOR_DB_PATH'] = ':memory:'
    os.environ['RAG_ENABLED'] = 'true'
    os.environ['CROSS_REPO_RAG'] = 'true'
    
    mock_db = MockDBService()
    agent = RAGEnhancedAgent(db_service=mock_db)
    
    if not agent.enabled:
        print("❌ RAG Agent not enabled (likely missing API key for real run, using mock dependencies).")
        # For pure logic testing, we can still proceed if we mock more
        agent.enabled = True 
        agent.vector_db = type('obj', (object,), {'query': lambda **kwargs: {'metadatas': [[]], 'distances': [[]], 'ids': [[]]}})()
    
    # --- 1. Test Feedback Weighting ---
    print("\nStep 1: Testing Feedback Weighting...")
    now = datetime.now()
    repo = "test/repo"
    
    results = {
        'ids': [['pr1', 'pr2']],
        'metadatas': [[
            {'pr_number': 1, 'repository': repo, 'analyzed_at': now.isoformat()},
            {'pr_number': 2, 'repository': repo, 'analyzed_at': now.isoformat()}
        ]],
        'distances': [[0.5, 0.5]] # Equal distance
    }
    
    mock_pr = PREvent(
        action='test', id=100, pr_number=100, pr_title="Test", pr_description="", 
        pr_url="", repository=repo, repository_url="", 
        author=PRAuthor(login="u", id=1, avatar_url=""),
        base_branch="m", head_branch="f", 
        files=[PRFile(filename="test.java", status="modified", additions=10, deletions=2, changes=12, patch="public class Test { synchronized void sql() { } }")], 
        created_at=now, updated_at=now, is_draft=False
    )
    
    # Scenario A: No feedback
    import copy
    ranked_no_fb = agent._rank_results(mock_pr, copy.deepcopy(results))
    
    # Scenario B: Positive feedback on PR 1, Negative on PR 2
    mock_db.feedback[(1, repo)] = [{'rating': 5}] # PR 1 is great
    mock_db.feedback[(2, repo)] = [{'rating': 1}] # PR 2 is bad
    
    ranked_fb = agent._rank_results(mock_pr, copy.deepcopy(results))
    
    dist1 = ranked_fb['distances'][0][ranked_fb['ids'][0].index('pr1')]
    dist2 = ranked_fb['distances'][0][ranked_fb['ids'][0].index('pr2')]
    
    print(f"  - Normal Distance (with repo bias): {ranked_no_fb['distances'][0][0]:.4f}")
    print(f"  - PR 1 (Rating 5) Adjusted Distance: {dist1:.4f}")
    print(f"  - PR 2 (Rating 1) Adjusted Distance: {dist2:.4f}")
    
    if dist1 < 0.4 and dist2 > 0.4:
        print("✅ Feedback weighting logic works!")
    else:
        print("❌ Feedback weighting logic failed.")

    # --- 2. Test Pattern Extraction ---
    print("\nStep 2: Testing Pattern Extraction...")
    from models.analysis_result import Issue, Severity, IssueType
    
    mock_issues = [
        Issue(
            type=IssueType.QUALITY, 
            severity=Severity.MEDIUM,
            message="Method is too long",
            file="test.java",
            line=10,
            suggestion="Refactor it"
        ),
        Issue(
            type=IssueType.SECURITY, 
            severity=Severity.HIGH,
            message="Dangerous query",
            file="test.java",
            line=20,
            suggestion="Use prepared statements"
        )
    ]
    
    agent._extract_and_store_patterns(mock_pr, mock_issues, {})
    
    print("  - Patterns Identified:")
    for name, data in mock_db.patterns.items():
        print(f"    * {name} ({data['count']} occurrences)")
        
    if "Quality: quality" in mock_db.patterns and "Security: security" in mock_db.patterns:
        print("✅ Pattern extraction (Issues) works!")
    else:
        print("❌ Pattern extraction (Issues) failed.")

    if any("Code Pattern:" in k for k in mock_db.patterns):
         print("✅ Pattern extraction (Keywords) works!")
    else:
         print("❌ Pattern extraction (Keywords) failed.")

if __name__ == "__main__":
    test_phase4_features()
