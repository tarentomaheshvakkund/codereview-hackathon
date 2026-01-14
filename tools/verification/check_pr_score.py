import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Database configuration (matching other tools)
DB_USER = "postgres"
DB_PASS = "postgres"
DB_HOST = "localhost"
DB_PORT = "5433"
DB_NAME = "pr_analysis"
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def check_pr(pr_number):
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as connection:
            # Query pr_analysis
            result = connection.execute(
                text("SELECT id, pr_number, rag_novelty_score, rag_risk_score, rag_similar_prs_count FROM pr_analysis WHERE pr_number = :pr_num"),
                {"pr_num": pr_number}
            ).fetchone()
            
            if result:
                print(f"PR #{result[1]}:")
                print(f"  Novelty Score: {result[2]}")
                print(f"  Risk Score: {result[3]}")
                print(f"  Similar PRs: {result[4]}")
                
                # Also check rag_insights if available
                insight = connection.execute(
                    text("SELECT novelty_score, similar_prs_found, full_text FROM rag_insights WHERE pr_analysis_id = :id"),
                    {"id": result[0]}
                ).fetchone()
                
                if insight:
                    print(f"  [RAG Insights Table] Novelty: {insight[0]}, Found: {insight[1]}")
            else:
                print(f"PR #{pr_number} not found in database.")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        pr_num = int(sys.argv[1])
        check_pr(pr_num)
    else:
        print("Usage: python tools/check_pr_score.py <pr_number>")
