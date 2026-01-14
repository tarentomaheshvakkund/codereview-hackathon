import os
import sys
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

# Add the parent directory to sys.path to import models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.database import PRAnalysis, PRIssue, PRMetrics, UserStatistics, Base

# Database configuration (using defaults from settings.yaml)
DB_USER = "postgres"
DB_PASS = "postgres"
DB_HOST = "localhost"
DB_PORT = "5433"
DB_NAME = "pr_analysis"

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def analyze_data():
    try:
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        print("Connected to database successfully.")
        
        # 1. Count rows
        pr_count = session.query(PRAnalysis).count()
        issue_count = session.query(PRIssue).count()
        metrics_count = session.query(PRMetrics).count()
        user_stats_count = session.query(UserStatistics).count()
        
        print(f"\n--- Row Counts ---")
        print(f"PRAnalysis: {pr_count}")
        print(f"PRIssue: {issue_count}")
        print(f"PRMetrics: {metrics_count}")
        print(f"UserStatistics: {user_stats_count}")
        
        if pr_count == 0:
            print("\nWARNING: No PRs found in the database.")
            return

        # 2. Check Data Quality - PRAnalysis
        print(f"\n--- Data Quality: PRAnalysis ---")
        
        # Check for nulls in important columns
        null_repo = session.query(PRAnalysis).filter(PRAnalysis.repository == None).count()
        null_author = session.query(PRAnalysis).filter(PRAnalysis.author_login == None).count()
        null_issues = session.query(PRAnalysis).filter(PRAnalysis.total_issues == None).count()
        
        print(f"PRs with NULL repository: {null_repo}")
        print(f"PRs with NULL author_login: {null_author}")
        print(f"PRs with NULL total_issues: {null_issues}")
        
        # Sample Data
        latest_pr = session.query(PRAnalysis).order_by(PRAnalysis.analyzed_at.desc()).first()
        print(f"\nLatest PR: {latest_pr.repository} #{latest_pr.pr_number}")
        print(f"  Analyzed At: {latest_pr.analyzed_at}")
        print(f"  Title: {latest_pr.pr_title}")
        print(f"  Issues: Critical={latest_pr.critical_issues}, High={latest_pr.high_issues}, Total={latest_pr.total_issues}")
        print(f"  Quality Score: {latest_pr.overall_quality_score}")

        # 3. Check Data Quality - PRIssue
        print(f"\n--- Data Quality: PRIssue ---")
        if issue_count > 0:
             # Check for nulls
            null_type = session.query(PRIssue).filter(PRIssue.issue_type == None).count()
            null_file = session.query(PRIssue).filter(PRIssue.file_path == None).count()
            print(f"Issues with NULL type: {null_type}")
            print(f"Issues with NULL file_path: {null_file}")
            
            # Sample Issue
            sample_issue = session.query(PRIssue).first()
            print(f"\nSample Issue:")
            print(f"  Type: {sample_issue.issue_type}")
            print(f"  Severity: {sample_issue.severity}")
            print(f"  File: {sample_issue.file_path}")
            print(f"  Title: {sample_issue.title}")
        else:
            print("No issues found.")

        # 4. Check Data Quality - PRMetrics
        print(f"\n--- Data Quality: PRMetrics ---")
        if metrics_count > 0:
            sample_metric = session.query(PRMetrics).first()
            print(f"Sample Metric (ID {sample_metric.id}):")
            print(f"  Coverage: {sample_metric.estimated_coverage_percent}")
            print(f"  Complexity: {sample_metric.average_complexity}")
        else:
            print("No metrics found.")

        session.close()

    except Exception as e:
        print(f"Error connecting to database or querying: {e}")

if __name__ == "__main__":
    analyze_data()
