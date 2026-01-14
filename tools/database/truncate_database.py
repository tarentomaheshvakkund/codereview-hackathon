#!/usr/bin/env python3
"""
Script to truncate all database tables.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from services.database_service import DatabaseService
from utils.logger import logger
from sqlalchemy import text

def truncate_all_tables():
    """Truncate all tables in the database."""
    print("=" * 80)
    print("Database Truncation Script")
    print("=" * 80)
    
    db_service = DatabaseService()
    
    tables = [
        'pr_comments',
        'pr_comment_statistics',
        'rag_similar_pr_references',
        'rag_recommendations',
        'rag_learned_patterns',
        'rag_insights',
        'pr_issues',
        'pr_metrics',
        'pr_analysis',
        'best_practices',
        'trend_analysis',
        'user_analytics',
        'user_statistics'
    ]
    
    print(f"\n⚠️  WARNING: About to truncate {len(tables)} tables:")
    for table in tables:
        print(f"  - {table}")
    
    response = input("\nAre you sure you want to proceed? (yes/no): ")
    if response.lower() != 'yes':
        print("❌ Truncation cancelled")
        return False
    
    print("\n🗑️  Truncating tables...")
    
    with db_service.get_session() as session:
        try:
            for table in tables:
                print(f"  Truncating {table}...", end=" ")
                session.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
                print("✓")
            
            session.commit()
            print("\n✅ All tables truncated successfully!")
            return True
            
        except Exception as e:
            print(f"\n❌ Error truncating tables: {e}")
            logger.error("Truncation failed", error=str(e))
            session.rollback()
            return False

if __name__ == '__main__':
    try:
        success = truncate_all_tables()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        logger.error("Fatal error", error=str(e))
        sys.exit(1)
