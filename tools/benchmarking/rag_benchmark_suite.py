import os
import sys

# SQLite version workaround for ChromaDB - MUST BE AT TOP
try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

import argparse
import time
from sqlalchemy import create_engine, text
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.dispatcher import AgentDispatcher
from services.database_service import DatabaseService
from services.github_service import GitHubService
from models.pr_event import PREvent, PRAuthor
from utils.logger import logger

def benchmark_prs(pr_numbers, repository):
    # Use In-Memory ChromaDB for benchmark to avoid flaky schema issues
    os.environ['VECTOR_DB_PATH'] = ':memory:'
    
    db_service = DatabaseService()
    github_service = GitHubService()
    dispatcher = AgentDispatcher(db_service=db_service)
    
    results = []
    
    print(f"\n🚀 Starting RAG Benchmark for {len(pr_numbers)} PRs in {repository}")
    print("=" * 100)
    
    for pr_num in pr_numbers:
        print(f"\n--- Analyzing PR #{pr_num} ---")
        
        # 1. Fetch Baseline Metrics
        baseline_data = {'novelty': 0.0, 'risk': 0.0, 'similar_prs_count': 0}
        try:
            with db_service.get_session() as session:
                from models.database import PRAnalysis
                baseline = session.query(PRAnalysis).filter_by(
                    repository=repository, 
                    pr_number=pr_num
                ).first()
                if baseline:
                    baseline_data['novelty'] = baseline.rag_novelty_score or 0.0
                    baseline_data['risk'] = baseline.rag_risk_score or 0.0
                    baseline_data['similar_prs_count'] = baseline.rag_similar_prs_count or 0
        except Exception as e:
            print(f"Error fetching baseline: {e}")
            
        # 2. Re-analyze with new model/prompts
        print(f"Fetching PR #{pr_num} from GitHub...")
        pr_details = github_service.get_pr_details(repository, pr_num)
        if not pr_details:
            print(f"Error: Could not fetch PR #{pr_num}")
            continue
            
        pr_event = PREvent(
            action='benchmark',
            id=pr_details.get('id', 0),
            pr_number=pr_num,
            pr_title=pr_details.get('title', ''),
            pr_description=pr_details.get('body', ''),
            pr_url=f"https://github.com/{repository}/pull/{pr_num}",
            repository=repository,
            repository_url=f"https://github.com/{repository}",
            author=PRAuthor(
                login=pr_details.get('user', {}).get('login', ''),
                id=0, avatar_url=''
            ),
            base_branch=pr_details.get('base', {}).get('ref', 'main'),
            head_branch=pr_details.get('head', {}).get('ref', ''),
            files=github_service.get_pr_files(repository, pr_num),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            is_draft=False
        )
        
        start_time = time.time()
        # Dispatch with RAG-enabled dispatcher
        # Dispatcher calls MainAgent -> RAGEnhancedAgent
        analysis_result = dispatcher.dispatch(pr_event)
        end_time = time.time()
        
        rag_insights = analysis_result.metadata.get('rag_insights', {})
        
        bench_data = {
            'pr_number': pr_num,
            'title': pr_event.pr_title,
            'latency': end_time - start_time,
            'baseline': baseline_data,
            'uplift': {
                'novelty': rag_insights.get('novelty_score', 0.0),
                'risk': rag_insights.get('risk_score', 0.0),
                'similar_prs': rag_insights.get('similar_prs_count', 0)
            },
            'new_recommendations': rag_insights.get('recommendations', '')[:200] + "..."
        }
        results.append(bench_data)
        
        print(f"Completed in {bench_data['latency']:.2f}s")
        print(f"  Novelty: {bench_data['baseline']['novelty']:.2f} -> {bench_data['uplift']['novelty']:.2f}")
        print(f"  Risk:    {bench_data['baseline']['risk']:.2f} -> {bench_data['uplift']['risk']:.2f}")

    # Generate Final Report
    print("\n\n" + "=" * 100)
    print("📈 FINAL RAG BENCHMARK REPORT")
    print("=" * 100)
    print(f"{'PR #':<8} | {'Latency':<10} | {'Novelty (B->U)':<20} | {'Risk (B->U)':<20}")
    print("-" * 100)
    
    total_lat = 0
    total_nov_diff = 0
    for r in results:
        total_lat += r['latency']
        total_nov_diff += (r['uplift']['novelty'] - r['baseline']['novelty'])
        n_comp = f"{r['baseline']['novelty']:.2f} -> {r['uplift']['novelty']:.2f}"
        r_comp = f"{r['baseline']['risk']:.2f} -> {r['uplift']['risk']:.2f}"
        print(f"{r['pr_number']:<8} | {r['latency']:<10.2f} | {n_comp:<20} | {r_comp:<20}")

    print("-" * 100)
    avg_uplift = (total_nov_diff / len(results)) * 100 if results else 0
    print(f"AVG Latency: {total_lat/len(results):.2f}s" if results else "")
    print(f"Average Novelty Uplift: {avg_uplift:+.2f}%")
    print("=" * 100)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Benchmark RAG Performance')
    parser.add_argument('--prs', type=str, required=True, help='Comma separated PR numbers')
    parser.add_argument('--repo', type=str, default='tarentomaheshvakkund/testdata-java-hackathon', help='Repository name')
    
    args = parser.parse_args()
    pr_list = [int(p.strip()) for p in args.prs.split(',')]
    
    benchmark_prs(pr_list, args.repo)
