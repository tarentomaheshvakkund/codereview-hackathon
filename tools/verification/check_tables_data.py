#!/usr/bin/env python3
"""
Script to check data in all database tables.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from services.database_service import DatabaseService
from sqlalchemy import text

def check_all_tables():
    """Check data counts in all tables."""
    print("=" * 80)
    print("Database Tables Data Check")
    print("=" * 80)
    
    db_service = DatabaseService()
    
    tables = [
        'pr_analysis',
        'pr_issues',
        'pr_metrics',
        'pr_comments',
        'pr_comment_statistics',
        'rag_insights',
        'rag_recommendations',
        'rag_learned_patterns',
        'rag_similar_pr_references',
        'best_practices',
        'trend_analysis',
        'user_analytics',
        'user_statistics'
    ]
    
    print("\n📊 Table Data Counts:\n")
    
    with db_service.get_session() as session:
        total_records = 0
        for table in tables:
            try:
                result = session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                total_records += count
                status = "✅" if count > 0 else "❌"
                print(f"{status} {table:30s} : {count:6d} records")
            except Exception as e:
                print(f"❌ {table:30s} : ERROR - {e}")
        
        print(f"\n{'='*80}")
        print(f"Total records across all tables: {total_records}")
        print(f"{'='*80}\n")
        
        # Show sample data from key tables
        if total_records > 0:
            print("\n📋 Sample Data from Key Tables:\n")
            
            # PR Analysis
            print("pr_analysis:")
            result = session.execute(text("""
                SELECT id, repository, pr_number, pr_created_at 
                FROM pr_analysis 
                ORDER BY pr_created_at DESC 
                LIMIT 5
            """))
            for row in result:
                print(f"  PR #{row[2]} - {row[1]} - {row[3]}")
            
            # RAG Insights
            print("\nrag_insights:")
            result = session.execute(text("""
                SELECT pr_analysis_id, novelty_score, risk_score 
                FROM rag_insights 
                LIMIT 5
            """))
            for row in result:
                print(f"  PR Analysis ID {row[0]} - Novelty: {row[1]:.2f}, Risk: {row[2]:.2f}")
            
            # RAG Recommendations
            print("\nrag_recommendations:")
            result = session.execute(text("""
                SELECT rag_insight_id, title, description 
                FROM rag_recommendations 
                LIMIT 5
            """))
            for row in result:
                desc_text = row[2][:60] + "..." if row[2] and len(row[2]) > 60 else (row[2] or "")
                print(f"  Insight ID {row[0]}: {row[1]} - {desc_text}")
            
            # RAG Learned Patterns
            print("\nrag_learned_patterns:")
            result = session.execute(text("""
                SELECT pattern_name, pattern_type, times_observed 
                FROM rag_learned_patterns 
                LIMIT 10
            """))
            for row in result:
                print(f"  {row[0]} ({row[1]}) - Observed {row[2]} times")

if __name__ == '__main__':
    try:
        check_all_tables()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
