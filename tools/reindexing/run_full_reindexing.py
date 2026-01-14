import os
import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure project root is in path
sys.path.append(os.getcwd())

from services.database_service import DatabaseService
from agents.rag_enhanced_agent import RAGEnhancedAgent

def run_full_reindexing():
    print("\n🚀 Starting Full System Re-indexing (Phase 6)...")
    
    # 0. Clean start: Delete existing vector DB to resolve schema issues and ensure fresh index
    import shutil
    vector_db_path = os.getenv('VECTOR_DB_PATH', './vector_db')
    force_wipe = os.getenv('FORCE_WIPE', 'false').lower() == 'true'
    
    if force_wipe and os.path.exists(vector_db_path) and vector_db_path != ":memory:":
        print(f"🧹 FORCE_WIPE enabled. Cleaning up existing vector DB at {vector_db_path}...")
        try:
            shutil.rmtree(vector_db_path)
            print("✅ Vector DB directory removed.")
        except Exception as e:
            print(f"⚠️ Failed to remove vector DB directory: {e}")
    elif os.path.exists(vector_db_path):
        print(f"ℹ️ Vector DB exists at {vector_db_path}. Resuming index (using upsert)...")

    # Initialize services
    db_service = DatabaseService()
    rag_agent = RAGEnhancedAgent(db_service=db_service)
    
    if not rag_agent.enabled:
        print("❌ RAG Agent is not enabled. Check .env and API keys.")
        return

    # Count total PRs in DB
    from models.database import PRAnalysis
    with db_service.get_session() as session:
        total_prs = session.query(PRAnalysis).count()
        print(f"📊 Total PRs in Database: {total_prs}")

    # Start re-indexing
    # We'll use a larger limit to cover all PRs
    limit = max(500, total_prs + 100)
    print(f"🔄 Indexing up to {limit} PRs with 10s delay after each...")
    rag_agent.index_historical_prs(limit=limit, delay=10)
    
    # Verification
    print("\n🧐 Verifying Re-indexing Results...")
    
    main_count = rag_agent.vector_db.count()
    sec_count = rag_agent.specialized_collections['security'].count()
    qual_count = rag_agent.specialized_collections['quality'].count()
    gen_count = rag_agent.specialized_collections['general'].count()
    
    print(f"✅ Main Collection: {main_count} docs")
    print(f"🛡️ Security Expert: {sec_count} docs")
    print(f"💎 Quality Expert: {qual_count} docs")
    print(f"📂 General Expert: {gen_count} docs")
    
    if main_count > 0:
        print("\n🎉 Full re-indexing completed successfully!")
    else:
        print("\n❌ Re-indexing failed - main collection is empty.")

if __name__ == "__main__":
    run_full_reindexing()
