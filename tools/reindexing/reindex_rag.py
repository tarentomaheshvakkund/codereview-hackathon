
import os
import sys
import argparse

# SQLite version workaround for ChromaDB
try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.rag_enhanced_agent import RAGEnhancedAgent
from services.database_service import DatabaseService

def run_reindex(limit=200):
    print(f"🚀 Re-indexing up to {limit} historical PRs with enriched metadata...")
    db_service = DatabaseService()
    agent = RAGEnhancedAgent(db_service=db_service)
    
    if not agent.enabled:
        print("❌ RAG Agent not enabled. Check dependencies/API keys.")
        return
        
    # Clear existing collection for a clean start if needed (optional)
    # agent.chroma_client.delete_collection("pr_analyses")
    # agent.vector_db = agent.chroma_client.get_or_create_collection("pr_analyses")
    
    agent.index_historical_prs(limit=limit)
    print("✨ Indexing complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    
    run_reindex(limit=args.limit)
