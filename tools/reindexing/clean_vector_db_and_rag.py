#!/usr/bin/env python3
"""
Clean Vector Database and RAG Data

This script removes:
1. All ChromaDB vector embeddings (deletes collections)
2. All RAG-related PostgreSQL tables data:
   - rag_insights
   - rag_similar_pr_references
   - rag_learned_patterns
   - rag_recommendations

Usage:
    python3.10 tools/clean_vector_db_and_rag.py
    python3.10 tools/clean_vector_db_and_rag.py --confirm
"""
import sys
import os
from pathlib import Path
import argparse

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from services.database_service import DatabaseService
from sqlalchemy import text
from utils.logger import logger

# SQLite version workaround for ChromaDB
__import__('pysqlite3')
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    print("⚠️  ChromaDB not available. Vector DB cleanup will be skipped.")


def clean_chromadb():
    """Clean all ChromaDB collections (vector embeddings)."""
    if not CHROMADB_AVAILABLE:
        print("\n⏭️  Skipping ChromaDB cleanup (not installed)")
        return
    
    print("\n" + "=" * 80)
    print("CLEANING CHROMADB VECTOR DATABASE")
    print("=" * 80)
    
    try:
        # Get vector DB path from environment
        persist_directory = os.getenv('VECTOR_DB_PATH', './vector_db')
        
        if not os.path.exists(persist_directory):
            print(f"\n✅ Vector DB directory doesn't exist: {persist_directory}")
            print("   Nothing to clean.")
            return
        print(f"\n📂 Vector DB Path: {persist_directory}")
        
        # Initialize ChromaDB client
        chroma_client = chromadb.PersistentClient(path=persist_directory)
        
        # List all collections
        collections = chroma_client.list_collections()
        
        if not collections:
            print("\n✅ No collections found in ChromaDB")
            return
        
        print(f"\n📊 Found {len(collections)} collection(s):")
        for collection in collections:
            print(f"   - {collection.name}")
        
        # Delete each collection
        print("\n🗑️  Deleting collections...")
        for collection in collections:
            try:
                chroma_client.delete_collection(collection.name)
                print(f"   ✅ Deleted: {collection.name}")
            except Exception as e:
                print(f"   ❌ Failed to delete {collection.name}: {e}")
        
        print("\n✅ ChromaDB cleanup complete!")
        
    except Exception as e:
        print(f"\n❌ Error cleaning ChromaDB: {e}")
        logger.error("ChromaDB cleanup failed", error=str(e), exc_info=True)


def clean_rag_tables():
    """Clean all RAG-related PostgreSQL tables."""
    print("\n" + "=" * 80)
    print("CLEANING RAG POSTGRESQL TABLES")
    print("=" * 80)
    
    db = DatabaseService()
    
    # Tables to clean (in order - respecting foreign key constraints)
    tables = [
        'rag_similar_pr_references',
        'rag_recommendations',
        'rag_learned_patterns',
        'rag_insights'
    ]
    
    try:
        with db.get_session() as session:
            print("\n🔍 Checking table counts before cleanup:")
            print("-" * 80)
            
            # Get counts before
            counts_before = {}
            for table in tables:
                try:
                    result = session.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar()
                    counts_before[table] = result
                    print(f"   {table:<30} {result:>10} rows")
                except Exception as e:
                    counts_before[table] = 0
                    print(f"   {table:<30} {'ERROR':>10} (table may not exist)")
            
            # Delete data
            print("\n🗑️  Deleting data from RAG tables...")
            print("-" * 80)
            
            for table in tables:
                try:
                    result = session.execute(text(f'DELETE FROM {table}'))
                    deleted = result.rowcount
                    session.commit()
                    print(f"   ✅ {table:<30} {deleted:>10} rows deleted")
                except Exception as e:
                    session.rollback()
                    print(f"   ❌ {table:<30} {'FAILED':>10} - {str(e)[:50]}")
            
            # Reset sequences (auto-increment counters)
            print("\n🔄 Resetting ID sequences...")
            print("-" * 80)
            
            for table in tables:
                try:
                    sequence_name = f"{table}_id_seq"
                    session.execute(text(f"ALTER SEQUENCE {sequence_name} RESTART WITH 1"))
                    session.commit()
                    print(f"   ✅ {sequence_name:<40} reset to 1")
                except Exception as e:
                    # Sequence might not exist, that's okay
                    print(f"   ⏭️  {table:<30} (sequence may not exist)")
            
            # Verify cleanup
            print("\n✅ Verification - counts after cleanup:")
            print("-" * 80)
            
            for table in tables:
                try:
                    result = session.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar()
                    status = "✅" if result == 0 else "⚠️"
                    print(f"   {status} {table:<30} {result:>10} rows")
                except Exception as e:
                    print(f"   ❌ {table:<30} {'ERROR':>10}")
            
            print("\n✅ RAG tables cleanup complete!")
            
    except Exception as e:
        print(f"\n❌ Error cleaning RAG tables: {e}")
        logger.error("RAG tables cleanup failed", error=str(e), exc_info=True)


def clean_pr_analysis_rag_fields():
    """Clean RAG-related fields in pr_analysis table (optional)."""
    print("\n" + "=" * 80)
    print("CLEANING RAG FIELDS IN PR_ANALYSIS TABLE (OPTIONAL)")
    print("=" * 80)
    
    db = DatabaseService()
    
    try:
        with db.get_session() as session:
            # Check how many PRs have RAG data
            result = session.execute(text('''
                SELECT COUNT(*) 
                FROM pr_analysis 
                WHERE has_rag_insights = true 
                OR rag_insights IS NOT NULL
            ''')).scalar()
            
            print(f"\n📊 Found {result} PR(s) with RAG data")
            
            if result == 0:
                print("   Nothing to clean.")
                return
            
            # Ask for confirmation
            response = input("\n⚠️  Clear RAG fields in pr_analysis? (yes/no): ")
            if response.lower() != 'yes':
                print("   Skipped.")
                return
            
            # Clear RAG fields
            session.execute(text('''
                UPDATE pr_analysis
                SET 
                    has_rag_insights = false,
                    rag_insights = NULL,
                    rag_similar_prs_count = 0,
                    rag_recommendations_count = 0,
                    rag_risk_score = NULL,
                    rag_novelty_score = NULL,
                    rag_patterns_learned = NULL
                WHERE has_rag_insights = true 
                OR rag_insights IS NOT NULL
            '''))
            
            updated = session.execute(text('''
                SELECT COUNT(*) 
                FROM pr_analysis 
                WHERE has_rag_insights = true 
                OR rag_insights IS NOT NULL
            ''')).scalar()
            
            session.commit()
            
            print(f"\n✅ Cleared RAG fields in {result - updated} PR(s)")
            
    except Exception as e:
        print(f"\n❌ Error cleaning pr_analysis RAG fields: {e}")
        logger.error("PR analysis RAG fields cleanup failed", error=str(e), exc_info=True)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Clean vector database and RAG data'
    )
    parser.add_argument(
        '--confirm',
        action='store_true',
        help='Skip confirmation prompt'
    )
    parser.add_argument(
        '--skip-chromadb',
        action='store_true',
        help='Skip ChromaDB cleanup'
    )
    parser.add_argument(
        '--skip-postgres',
        action='store_true',
        help='Skip PostgreSQL RAG tables cleanup'
    )
    parser.add_argument(
        '--clean-pr-fields',
        action='store_true',
        help='Also clean RAG fields in pr_analysis table'
    )
    
    args = parser.parse_args()
    
    print("\n" + "=" * 80)
    print("🧹 VECTOR DATABASE AND RAG DATA CLEANUP")
    print("=" * 80)
    
    print("\nThis script will clean:")
    if not args.skip_chromadb:
        print("   1. ✅ ChromaDB vector embeddings (all collections)")
    else:
        print("   1. ⏭️  ChromaDB vector embeddings (SKIPPED)")
    
    if not args.skip_postgres:
        print("   2. ✅ PostgreSQL RAG tables:")
        print("      - rag_insights")
        print("      - rag_similar_pr_references")
        print("      - rag_learned_patterns")
        print("      - rag_recommendations")
    else:
        print("   2. ⏭️  PostgreSQL RAG tables (SKIPPED)")
    
    if args.clean_pr_fields:
        print("   3. ✅ RAG fields in pr_analysis table")
    else:
        print("   3. ⏭️  RAG fields in pr_analysis table (OPTIONAL)")
    
    print("\n⚠️  WARNING: This action cannot be undone!")
    print("   All RAG insights and learned patterns will be permanently deleted.")
    
    if not args.confirm:
        response = input("\n❓ Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("\n❌ Cleanup cancelled.")
            return 1
    
    # Clean ChromaDB
    if not args.skip_chromadb:
        clean_chromadb()
    
    # Clean PostgreSQL RAG tables
    if not args.skip_postgres:
        clean_rag_tables()
    
    # Clean pr_analysis RAG fields (optional)
    if args.clean_pr_fields:
        clean_pr_analysis_rag_fields()
    
    print("\n" + "=" * 80)
    print("✅ CLEANUP COMPLETE!")
    print("=" * 80)
    print("\n💡 Next steps:")
    print("   - New PR analyses will start fresh with empty RAG database")
    print("   - ChromaDB will rebuild embeddings as PRs are analyzed")
    print("   - RAG insights will be generated from scratch")
    print()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
