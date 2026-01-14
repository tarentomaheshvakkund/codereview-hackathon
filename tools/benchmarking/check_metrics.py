import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.database import PRMetrics

# Database configuration
DB_USER = "postgres"
DB_PASS = "postgres"
DB_HOST = "localhost"
DB_PORT = "5433"
DB_NAME = "pr_analysis"
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

try:
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    total = session.query(PRMetrics).count()
    null_coverage = session.query(PRMetrics).filter(PRMetrics.estimated_coverage_percent == None).count()
    null_complexity = session.query(PRMetrics).filter(PRMetrics.average_complexity == None).count()
    null_metrics = session.query(PRMetrics).filter(
        PRMetrics.estimated_coverage_percent == None,
        PRMetrics.average_complexity == None
    ).count()

    print(f"Total Metrics Rows: {total}")
    print(f"Null Coverage: {null_coverage} ({(null_coverage/total)*100:.1f}%)")
    print(f"Null Complexity: {null_complexity} ({(null_complexity/total)*100:.1f}%)")
    print(f"Both Null: {null_metrics}")

    # Check one that is NOT null if exists
    not_null = session.query(PRMetrics).filter(PRMetrics.estimated_coverage_percent != None).first()
    if not_null:
        print(f"Found valid metric: ID {not_null.id}, Coverage={not_null.estimated_coverage_percent}")
    else:
        print("No valid metrics found.")

except Exception as e:
    print(e)
