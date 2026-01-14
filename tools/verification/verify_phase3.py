
import os
import sys
import time
from datetime import datetime, timedelta

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

def test_phase3_features():
    print("\n🧪 Testing RAG Phase 3: Latency & Precision...")
    
    # Use in-memory DB
    os.environ['VECTOR_DB_PATH'] = ':memory:'
    
    db_service = DatabaseService()
    agent = RAGEnhancedAgent(db_service=db_service)
    
    if not agent.enabled:
        print("❌ RAG Agent not enabled.")
        return

    # 1. Test Latency (Caching)
    text = "public class LatencyTest { void test() { System.out.println('Hello'); } }"
    
    print("Step 1: Measuring Embedding Latency (First run)...")
    start = time.time()
    agent._get_code_embedding(text)
    first_duration = time.time() - start
    print(f"  - First run: {first_duration:.4f}s")
    
    print("Step 1b: Measuring Embedding Latency (Cached run)...")
    start = time.time()
    agent._get_code_embedding(text)
    cached_duration = time.time() - start
    print(f"  - Cached run: {cached_duration:.4f}s")
    
    if cached_duration < first_duration * 0.1:
        print("✅ Latency Optimization (Caching) works!")
    else:
        print("⚠️ Caching might not be effective (durations too similar).")

    # 2. Test Temporal Decay and Repo Bias
    print("\nStep 2: Testing Ranking Logic (Decay & Bias)...")
    
    # Mock some historical data
    # PR 1: Same repo, recent
    # PR 2: Same repo, old
    # PR 3: Diff repo, recent
    
    now = datetime.now()
    repo_a = "test/repo-a"
    repo_b = "test/repo-b"
    
    results = {
        'ids': [['pr1', 'pr2', 'pr3']],
        'metadatas': [[
            {'repository': repo_a, 'analyzed_at': now.isoformat()},
            {'repository': repo_a, 'analyzed_at': (now - timedelta(days=180)).isoformat()}, # Penalty: 2^(180/90) = 4x
            {'repository': repo_b, 'analyzed_at': now.isoformat()}
        ]],
        'distances': [[0.5, 0.5, 0.4]] # Raw distances
    }
    
    # Current PR is in repo-a
    mock_pr = PREvent(
        action='test', id=1, pr_number=100, pr_title="Test", pr_description="", 
        pr_url="", repository=repo_a, repository_url="", 
        author=PRAuthor(login="u", id=1, avatar_url=""),
        base_branch="m", head_branch="f", files=[], created_at=now, updated_at=now, is_draft=False
    )
    
    ranked = agent._rank_results(mock_pr, results)
    
    print("Ranking Results (Lower distance is better):")
    for i, pid in enumerate(ranked['ids'][0]):
        dist = ranked['distances'][0][i]
        meta = ranked['metadatas'][0][i]
        print(f"  - {pid}: Distance={dist:.4f} (Repo={meta['repository']}, Age={meta['analyzed_at']})")
    
    # Expected:
    # pr1: dist=0.5 * 0.8 (bias) * 1 (decay) = 0.4
    # pr3: dist=0.4 * 1.0 (no bias) * 1 (decay) = 0.4
    # pr2: dist=0.5 * 0.8 (bias) * 4 (decay) = 1.6
    
    if ranked['ids'][0][0] in ['pr1', 'pr3'] and ranked['ids'][0][2] == 'pr2':
        print("✅ Ranking logic (Temporal Decay & Repo Bias) works!")
    else:
        print("❌ Ranking logic failed expectations.")

if __name__ == "__main__":
    test_phase3_features()
