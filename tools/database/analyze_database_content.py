#!/usr/bin/env python3
"""
Comprehensive Database Content Analysis Script
Queries and displays all stored data from the PR analysis
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.database_service import DatabaseService
from sqlalchemy import text
import json

def print_section(title):
    """Print a formatted section header"""
    print('\n' + '=' * 80)
    print(title.center(80))
    print('=' * 80)

def truncate_text(text, max_length=200):
    """Truncate text with ellipsis if too long"""
    if not text:
        return text
    text_str = str(text)
    if len(text_str) > max_length:
        return text_str[:max_length] + '...'
    return text_str

def print_pr_analysis(session):
    """Print PR analysis data."""
    print_section('PR ANALYSIS')
    result = session.execute(text('''
        SELECT id, repository, pr_number, pr_title, author_login, 
               total_issues, critical_issues, high_issues, medium_issues, low_issues,
               has_rag_insights, rag_risk_score, rag_novelty_score,
               rag_similar_prs_count, rag_recommendations_count,
               pr_created_at, analyzed_at
        FROM pr_analysis
        ORDER BY analyzed_at DESC
    ''')).fetchall()
    
    for row in result:
        print(f'\n📊 PR Analysis ID: {row[0]}')
        print(f'   Repository: {row[1]}')
        print(f'   PR Number: #{row[2]}')
        print(f'   Title: {row[3]}')
        print(f'   Author: {row[4]}')
        print(f'   Issues: Total={row[5]} (Critical={row[6]}, High={row[7]}, Medium={row[8]}, Low={row[9]})')
        print(f'   RAG: Has Insights={row[10]}, Risk={row[11]}, Novelty={row[12]}')
        print(f'   Similar PRs: {row[13]}, Recommendations: {row[14]}')
        print(f'   PR Created: {row[15]}')
        print(f'   Analyzed At: {row[16]}')


def print_pr_issues(session):
    """Print PR issues data."""
    print_section('PR ISSUES')
    result = session.execute(text('''
        SELECT id, pr_analysis_id, agent_name, issue_type, severity, 
               file_path, line_number, title, description, recommendation
        FROM pr_issues
        ORDER BY pr_analysis_id, severity DESC, id
    ''')).fetchall()
    
    for i, row in enumerate(result, 1):
        print(f'\n🔍 Issue #{i} (ID: {row[0]})')
        print(f'   PR Analysis ID: {row[1]}')
        print(f'   Agent: {row[2]}')
        print(f'   Type: {row[3]}')
        print(f'   Severity: {row[4]}')
        print(f'   File: {row[5]}:{row[6]}')
        print(f'   Title: {truncate_text(row[7], 100)}')
        print(f'   Description: {truncate_text(row[8], 150)}')
        if row[9]:
            print(f'   Recommendation: {truncate_text(row[9], 150)}')


def print_pr_metrics(session):
    """Print PR metrics data."""
    print_section('PR METRICS')
    result = session.execute(text('''
        SELECT pr_analysis_id, code_files_changed, test_files_changed,
               estimated_coverage_percent, average_complexity,
               hardcoded_secrets, sql_injection_risks, command_injection_risks
        FROM pr_metrics
    ''')).fetchall()
    
    for row in result:
        print(f'\n📈 Metrics for PR Analysis ID: {row[0]}')
        print(f'   Files Changed: Code={row[1]}, Tests={row[2]}')
        print(f'   Coverage: {row[3]}%')
        print(f'   Complexity: {row[4]}')
        print(f'   Security: Secrets={row[5]}, SQL Injection={row[6]}, Command Injection={row[7]}')


def print_rag_insight_details(row):
    """Print RAG insight details."""
    if row[6]:
        print('\n   📚 Lessons Learned:')
        print(f'   {truncate_text(row[6], 300)}')
    
    if row[7]:
        print('\n   💡 Recommendations:')
        print(f'   {truncate_text(row[7], 300)}')
    
    if row[8]:
        print('\n   ⚠️ Potential Pitfalls:')
        print(f'   {truncate_text(row[8], 300)}')
    
    if row[9]:
        print('\n   ✅ Best Practices:')
        print(f'   {truncate_text(row[9], 300)}')


def print_rag_insights(session):
    """Print RAG insights data."""
    print_section('RAG INSIGHTS')
    result = session.execute(text('''
        SELECT id, pr_analysis_id, novelty_score, risk_score,
               similar_prs_found, similar_prs_referenced,
               lessons_learned, recommendations, 
               potential_pitfalls, best_practices_suggested
        FROM rag_insights
    ''')).fetchall()
    
    for row in result:
        print(f'\n🤖 RAG Insight ID: {row[0]} (PR Analysis ID: {row[1]})')
        print(f'   Scores: Novelty={row[2]:.3f}, Risk={row[3]:.3f}')
        print(f'   Similar PRs: Found={row[4]}, Referenced={row[5]}')
        print_rag_insight_details(row)


def print_rag_recommendations(session):
    """Print RAG recommendations data."""
    print_section('RAG RECOMMENDATIONS')
    result = session.execute(text('''
        SELECT id, rag_insight_id, recommendation_type, priority,
               title, description, reasoning
        FROM rag_recommendations
        ORDER BY rag_insight_id, 
                 CASE priority 
                    WHEN 'critical' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3
                    WHEN 'low' THEN 4
                    ELSE 5
                 END
    ''')).fetchall()
    
    for i, row in enumerate(result, 1):
        print(f'\n💡 Recommendation #{i} (ID: {row[0]})')
        print(f'   RAG Insight ID: {row[1]}')
        print(f'   Type: {row[2]}')
        print(f'   Priority: {row[3]}')
        print(f'   Title: {row[4]}')
        print(f'   Description: {truncate_text(row[5], 200)}')
        if row[6]:
            print(f'   Reasoning: {truncate_text(row[6], 200)}')


def print_rag_learned_patterns(session):
    """Print RAG learned patterns data."""
    print_section('RAG LEARNED PATTERNS')
    result = session.execute(text('''
        SELECT id, pattern_name, pattern_category, pattern_type,
               description, times_observed, confidence_score
        FROM rag_learned_patterns
        ORDER BY times_observed DESC, confidence_score DESC
    ''')).fetchall()
    
    for i, row in enumerate(result, 1):
        print(f'\n🎯 Pattern #{i} (ID: {row[0]})')
        print(f'   Name: {row[1]}')
        print(f'   Category: {row[2]}')
        print(f'   Type: {row[3]}')
        print(f'   Description: {truncate_text(row[4], 200)}')
        print(f'   Times Observed: {row[5]}')
        print(f'   Confidence: {row[6]:.3f}')


def print_rag_similar_pr_refs(session):
    """Print RAG similar PR references data."""
    print_section('RAG SIMILAR PR REFERENCES')
    result = session.execute(text('''
        SELECT id, rag_insight_id, referenced_pr_analysis_id,
               similarity_score, similarity_type, used_in_analysis
        FROM rag_similar_pr_references
        ORDER BY similarity_score DESC
    ''')).fetchall()
    
    if result:
        for row in result:
            print(f'\n🔗 Reference ID: {row[0]}')
            print(f'   RAG Insight ID: {row[1]}')
            print(f'   Referenced PR Analysis ID: {row[2]}')
            print(f'   Similarity Score: {row[3]:.3f}')
            print(f'   Type: {row[4]}')
            print(f'   Used in Analysis: {row[5]}')
    else:
        print('\n   No similar PR references found.')


def print_pr_comments(session):
    """Print PR comments data."""
    print_section('PR COMMENTS')
    result = session.execute(text('''
        SELECT id, pr_analysis_id, comment_type, file_path, line_number,
               comment_preview, posted_successfully, github_url
        FROM pr_comments
        ORDER BY pr_analysis_id, comment_type
    ''')).fetchall()
    
    for row in result:
        print(f'\n💬 Comment ID: {row[0]} (PR Analysis ID: {row[1]})')
        print(f'   Type: {row[2]}')
        if row[3]:
            print(f'   Location: {row[3]}:{row[4]}')
        print(f'   Preview: {row[5]}')
        print(f'   Posted: {row[6]}')
        if row[7]:
            print(f'   GitHub URL: {row[7]}')


def print_summary(session):
    """Print summary statistics."""
    print_section('SUMMARY')
    summary = session.execute(text('''
        SELECT 
            (SELECT COUNT(*) FROM pr_analysis) as total_prs,
            (SELECT COUNT(*) FROM pr_issues) as total_issues,
            (SELECT COUNT(*) FROM rag_insights) as total_insights,
            (SELECT COUNT(*) FROM rag_recommendations) as total_recommendations,
            (SELECT COUNT(*) FROM rag_learned_patterns) as total_patterns,
            (SELECT COUNT(*) FROM pr_comments) as total_comments
    ''')).fetchone()
    
    print(f'\n📊 Total PRs Analyzed: {summary[0]}')
    print(f'🔍 Total Issues Found: {summary[1]}')
    print(f'🤖 Total RAG Insights: {summary[2]}')
    print(f'💡 Total Recommendations: {summary[3]}')
    print(f'🎯 Total Learned Patterns: {summary[4]}')
    print(f'💬 Total Comments: {summary[5]}')
    print()


def main():
    """Main function to analyze database content."""
    db = DatabaseService()
    
    with db.get_session() as session:
        print_pr_analysis(session)
        print_pr_issues(session)
        print_pr_metrics(session)
        print_rag_insights(session)
        print_rag_recommendations(session)
        print_rag_learned_patterns(session)
        print_rag_similar_pr_refs(session)
        print_pr_comments(session)
        print_summary(session)

if __name__ == '__main__':
    main()
