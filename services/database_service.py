"""Database service for PR analysis persistence."""
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
from sqlalchemy import create_engine, func, desc
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from contextlib import contextmanager

from models.database import (
    Base, PRAnalysis, PRIssue, PRMetrics, 
    UserStatistics, BestPractice, UserAnalytics,
    RAGFeedback, RAGPatternLibrary
)
from services.rag_database_service import RAGDatabaseService
from utils.logger import logger
from utils.config import config
from utils.constants import (
    AGENT_SECURITY,
    AGENT_CODE_QUALITY,
    AGENT_COVERAGE,
    AGENT_STATIC_ANALYSIS,
    DB_HOST,
    DB_PORT,
    DB_NAME,
    DB_USER,
    DB_PASSWORD,
    DB_POOL_SIZE,
    DB_MAX_OVERFLOW
)


class DatabaseService:
    """Service for managing PR analysis data in PostgreSQL."""
    
    def __init__(self):
        """Initialize database connection."""
        # Use constants with config fallback
        host = config.get('database', {}).get('host', DB_HOST)
        port = config.get('database', {}).get('port', DB_PORT)
        database = config.get('database', {}).get('database', DB_NAME)
        username = config.get('database', {}).get('username', DB_USER)
        password = config.get('database', {}).get('password', DB_PASSWORD)
        
        self.connection_string = f"postgresql://{username}:{password}@{host}:{port}/{database}"
        
        # Create engine with optimized settings for performance
        self.engine = create_engine(
            self.connection_string,
            pool_size=DB_POOL_SIZE,
            max_overflow=DB_MAX_OVERFLOW,
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600,  # Recycle connections after 1 hour
            echo=False,  # Disable SQL echo for performance
            connect_args={
                "options": "-c statement_timeout=30000"  # 30 second query timeout
            }
        )
        
        # Create session factory
        self.session_local = sessionmaker(bind=self.engine)
        
        # Initialize RAG database service
        self.rag_service = RAGDatabaseService()
        
        logger.info("Database service initialized", database=database, host=host)
    
    @contextmanager
    def get_session(self) -> Session:
        """Context manager for database sessions."""
        session = self.session_local()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Database session error", error=str(e))
            raise
        finally:
            session.close()
    
    def create_tables(self):
        """Create all database tables."""
        try:
            Base.metadata.create_all(self.engine)
            logger.info("Database tables created successfully")
        except SQLAlchemyError as e:
            logger.error("Failed to create database tables", error=str(e))
            raise
    
    def save_pr_analysis(
        self,
        pr_data: Dict[str, Any],
        analysis_result: Dict[str, Any],
        author_email: Optional[str] = None
    ) -> PRAnalysis:
        """
        Save PR analysis results to database.
        
        Args:
            pr_data: PR information (repository, pr_number, author, etc.)
            analysis_result: Analysis results from agents
            author_email: Optional email address of PR author
            
        Returns:
            PRAnalysis: Created database record
        """
        with self.get_session() as session:
            try:
                # Get or create PR analysis record
                pr_analysis, existing_pr = self._get_or_create_pr_analysis(
                    session, pr_data, analysis_result, author_email
                )
                
                # Update severity distribution
                self._update_severity_counts(pr_analysis, analysis_result)
                
                # Set RAG summary fields
                self._set_rag_summary_fields(pr_analysis, analysis_result)
                
                session.add(pr_analysis)
                session.flush()  # Get the ID
                
                # For updates, delete existing issues and metrics before re-adding
                if existing_pr:
                    self._delete_existing_data(session, pr_analysis.id)
                
                # Save all related data
                self._save_related_data(session, pr_analysis.id, analysis_result)
                
                logger.info(
                    "PR analysis saved",
                    pr_analysis_id=pr_analysis.id,
                    repository=pr_data.get('repository'),
                    pr_number=pr_data.get('pr_number')
                )
                
                # Update user statistics (wrapped to prevent rollback on stats failure)
                try:
                    self._update_user_statistics(
                        session,
                        pr_data.get('author', {}).get('login'),
                        author_email,
                        pr_analysis
                    )
                except Exception as stats_error:
                    logger.warning(f"Failed to update user statistics: {stats_error}")
                
                # Commit the transaction explicitly
                session.commit()
                logger.info(f"Database transaction committed for PR analysis {pr_analysis.id}")
                
                # Refresh to ensure all attributes are loaded
                session.refresh(pr_analysis)
                
                # Return a dictionary with key attributes instead of the expunged object
                # This prevents "object has been deleted" errors when accessing attributes later
                return type('PRAnalysis', (), {
                    'id': pr_analysis.id,
                    'repository': pr_analysis.repository,
                    'pr_number': pr_analysis.pr_number,
                    'author_login': pr_analysis.author_login,
                    'author_email': pr_analysis.author_email,
                    'overall_quality_score': pr_analysis.overall_quality_score,
                    'security_score': pr_analysis.security_score,
                    'maintainability_score': pr_analysis.maintainability_score,
                    'total_issues': pr_analysis.total_issues
                })()
                
            except SQLAlchemyError as e:
                session.rollback()
                logger.error("Failed to save PR analysis", error=str(e))
                raise
    
    def _get_or_create_pr_analysis(
        self, 
        session: Session, 
        pr_data: Dict[str, Any], 
        analysis_result: Dict[str, Any],
        author_email: Optional[str]
    ) -> tuple[PRAnalysis, bool]:
        """
        Get existing PR analysis or create a new one.
        
        Returns:
            Tuple of (PRAnalysis, is_existing)
        """
        existing_pr = session.query(PRAnalysis).filter_by(
            repository=pr_data.get('repository'),
            pr_number=pr_data.get('pr_number') or pr_data.get('number')
        ).first()
        
        if existing_pr:
            pr_analysis = self._update_existing_pr(existing_pr, pr_data, author_email)
            return pr_analysis, True
        else:
            pr_analysis = self._create_new_pr(pr_data, analysis_result, author_email)
            return pr_analysis, False
    
    def _update_existing_pr(
        self, 
        pr_analysis: PRAnalysis, 
        pr_data: Dict[str, Any],
        author_email: Optional[str]
    ) -> PRAnalysis:
        """Update existing PR analysis record with new data."""
        pr_analysis.pr_title = pr_data.get('title')
        pr_analysis.pr_description = pr_data.get('description') or pr_data.get('body')
        pr_analysis.pr_url = pr_data.get('url') or pr_data.get('html_url')
        
        # Update author info (especially if email was previously missing)
        if author_email:
            pr_analysis.author_email = author_email
        elif pr_data.get('author', {}).get('email'):
            pr_analysis.author_email = pr_data.get('author', {}).get('email')
        
        if pr_data.get('author', {}).get('name'):
            pr_analysis.author_name = pr_data.get('author', {}).get('name')
        
        logger.info(
            "Updating existing PR analysis",
            repository=pr_data.get('repository'),
            pr_number=pr_data.get('pr_number'),
            author_email=pr_analysis.author_email
        )
        
        return pr_analysis
    
    def _create_new_pr(
        self, 
        pr_data: Dict[str, Any], 
        analysis_result: Dict[str, Any],
        author_email: Optional[str]
    ) -> PRAnalysis:
        """Create new PR analysis record."""
        return PRAnalysis(
            repository=pr_data.get('repository'),
            pr_id=pr_data.get('id'),  # GitHub's unique PR ID
            pr_number=pr_data.get('pr_number') or pr_data.get('number'),
            pr_title=pr_data.get('title'),
            pr_description=pr_data.get('description') or pr_data.get('body'),
            pr_url=pr_data.get('url') or pr_data.get('html_url'),
            
            # Author information
            author_login=pr_data.get('author', {}).get('login'),
            author_email=author_email or pr_data.get('author', {}).get('email'),
            author_name=pr_data.get('author', {}).get('name'),
            author_id=pr_data.get('author', {}).get('id'),
            
            # PR metadata
            base_branch=pr_data.get('base_branch'),
            head_branch=pr_data.get('head_branch'),
            files_changed=pr_data.get('files_changed', 0),
            lines_added=pr_data.get('lines_added', 0),
            lines_deleted=pr_data.get('lines_deleted', 0),
            is_draft=pr_data.get('is_draft', False),
            
            # Analysis results
            total_issues=analysis_result.get('issues_found', 0),
            
            # Agent breakdown
            static_analysis_issues=analysis_result.get('agent_breakdown', {}).get(
                AGENT_STATIC_ANALYSIS, {}).get('issues_count', 0),
            security_issues=analysis_result.get('agent_breakdown', {}).get(
                AGENT_SECURITY, {}).get('issues_count', 0),
            code_quality_issues=analysis_result.get('agent_breakdown', {}).get(
                AGENT_CODE_QUALITY, {}).get('issues_count', 0),
            context_issues=analysis_result.get('agent_breakdown', {}).get(
                'Context Agent', {}).get('issues_count', 0),
            coverage_issues=analysis_result.get('agent_breakdown', {}).get(
                AGENT_COVERAGE, {}).get('issues_count', 0),
            
            # Scores (calculated)
            overall_quality_score=self._calculate_quality_score(analysis_result),
            security_score=self._calculate_security_score(analysis_result),
            maintainability_score=self._calculate_maintainability_score(analysis_result),
            
            # RAG Insights
            rag_insights=self._extract_rag_insights(analysis_result),
            
            # Metadata
            analysis_duration_ms=analysis_result.get('analysis_time_ms'),
            analyzed_at=datetime.now(timezone.utc),
            analyzer_version=analysis_result.get('version', '1.0.0'),
            
            # PR timestamps
            pr_created_at=pr_data.get('created_at'),
            pr_updated_at=pr_data.get('updated_at')
        )
    
    def _update_severity_counts(self, pr_analysis: PRAnalysis, analysis_result: Dict) -> None:
        """Update severity distribution counts on PR analysis."""
        severity_counts = self._count_severities(analysis_result)
        pr_analysis.critical_issues = severity_counts.get('critical', 0)
        pr_analysis.high_issues = severity_counts.get('high', 0)
        pr_analysis.medium_issues = severity_counts.get('medium', 0)
        pr_analysis.low_issues = severity_counts.get('low', 0)
    
    def _delete_existing_data(self, session: Session, pr_analysis_id: int) -> None:
        """Delete existing issues and metrics before re-adding."""
        session.query(PRIssue).filter_by(pr_analysis_id=pr_analysis_id).delete()
        session.query(PRMetrics).filter_by(pr_analysis_id=pr_analysis_id).delete()
    
    def _save_related_data(self, session: Session, pr_analysis_id: int, analysis_result: Dict) -> None:
        """Save all related data (issues, metrics, RAG insights)."""
        # Save individual issues
        self._save_issues(session, pr_analysis_id, analysis_result)
        
        # Save metrics
        self._save_metrics(session, pr_analysis_id, analysis_result)
        
        # Save RAG insights to structured tables
        self.rag_service.save_rag_insights(
            session,
            pr_analysis_id,
            analysis_result
        )
    
    def _save_issues(self, session: Session, pr_analysis_id: int, analysis_result: Dict):
        """Save individual issues to database using bulk insert for performance."""
        issues_to_insert = []
        
        for agent_name, agent_data in analysis_result.get('agent_breakdown', {}).items():
            for issue in agent_data.get('issues', []):
                pr_issue = PRIssue(
                    pr_analysis_id=pr_analysis_id,
                    agent_name=agent_name,
                    issue_type=issue.get('type', 'UNKNOWN'),
                    severity=issue.get('severity', 'medium').lower(),
                    category=issue.get('category', 'general'),
                    file_path=issue.get('file', ''),
                    line_number=issue.get('line'),
                    line_content=issue.get('line_content'),
                    title=issue.get('title', issue.get('type')),
                    description=issue.get('message', ''),
                    recommendation=issue.get('recommendation', ''),
                    code_snippet=issue.get('code_snippet'),
                    # PRIssue model stores metadata in attribute 'issue_metadata' to avoid
                    # colliding with Base.metadata. Map incoming 'metadata' into that field.
                    issue_metadata=issue.get('metadata', {})
                )
                issues_to_insert.append(pr_issue)
        
        # Bulk insert all issues at once for better performance
        if issues_to_insert:
            session.add_all(issues_to_insert)
    
    def _save_metrics(self, session: Session, pr_analysis_id: int, analysis_result: Dict):
        """Save detailed metrics to database."""
        # Extract coverage agent data
        coverage_data = analysis_result.get('agent_breakdown', {}).get(
            AGENT_COVERAGE, {}).get('metadata', {})
        
        # Extract quality agent data for pattern counts
        quality_issues = analysis_result.get('agent_breakdown', {}).get(
            AGENT_CODE_QUALITY, {}).get('issues', [])
        
        security_issues = analysis_result.get('agent_breakdown', {}).get(
            AGENT_SECURITY, {}).get('issues', [])
        
        static_issues = analysis_result.get('agent_breakdown', {}).get(
            AGENT_STATIC_ANALYSIS, {}).get('issues', [])
        
        # Count issue types
        issue_counts = self._count_issue_types(quality_issues, security_issues, static_issues)
        
        pr_metrics = PRMetrics(
            pr_analysis_id=pr_analysis_id,
            
            # Coverage metrics
            code_files_changed=coverage_data.get('code_files_changed', 0),
            test_files_changed=coverage_data.get('test_files_changed', 0),
            total_test_methods=coverage_data.get('total_test_methods', 0),
            code_lines_added=coverage_data.get('code_lines_added', 0),
            test_lines_added=coverage_data.get('test_lines_added', 0),
            estimated_coverage_percent=coverage_data.get('estimated_coverage'),
            coverage_status=coverage_data.get('coverage_status'),
            
            # Complexity metrics
            average_complexity=coverage_data.get('average_complexity'),
            max_complexity=coverage_data.get('max_complexity'),
            total_complexity=coverage_data.get('total_complexity'),
            
            # Code quality metrics
            duplicate_code_blocks=issue_counts.get('duplicate_code', 0),
            long_methods_count=issue_counts.get('long_method', 0),
            deep_nesting_count=issue_counts.get('deep_nesting', 0),
            magic_numbers_count=issue_counts.get('magic_number', 0),
            
            # Security metrics
            hardcoded_secrets=issue_counts.get('hardcoded_secret', 0),
            sql_injection_risks=issue_counts.get('sql_injection', 0),
            command_injection_risks=issue_counts.get('command_injection', 0),
            weak_crypto_usage=issue_counts.get('weak_crypto', 0),
            
            # Pattern detection counts
            todo_comments=issue_counts.get('todo_comment', 0),
            system_out_println=issue_counts.get('no_system_out', 0),
            console_log=issue_counts.get('console_log', 0),
            eval_usage=issue_counts.get('eval_used', 0)
        )
        
        session.add(pr_metrics)
    
    def _count_issue_types(self, quality_issues: List, security_issues: List, static_issues: List) -> Dict[str, int]:
        """Count occurrences of each issue type."""
        counts = {}
        
        for issue in quality_issues + security_issues + static_issues:
            issue_type = issue.get('type', 'UNKNOWN').lower().replace('_', '_')
            counts[issue_type] = counts.get(issue_type, 0) + 1
        
        return counts
    
    def _count_severities(self, analysis_result: Dict) -> Dict[str, int]:
        """Count issues by severity level."""
        severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        
        for agent_data in analysis_result.get('agent_breakdown', {}).values():
            for issue in agent_data.get('issues', []):
                severity = issue.get('severity', 'medium').lower()
                if severity in severity_counts:
                    severity_counts[severity] += 1
        
        return severity_counts
    
    def _calculate_quality_score(self, analysis_result: Dict) -> float:
        """
        Calculate overall quality score (0-100).
        Higher score = better quality.
        """
        # Base score starts at 100
        score = 100.0
        
        # Deduct points based on severity
        severity_counts = self._count_severities(analysis_result)
        score -= severity_counts.get('critical', 0) * 10
        score -= severity_counts.get('high', 0) * 5
        score -= severity_counts.get('medium', 0) * 2
        score -= severity_counts.get('low', 0) * 0.5
        
        # Minimum score is 0
        return max(0.0, min(100.0, score))
    
    def _calculate_security_score(self, analysis_result: Dict) -> float:
        """Calculate security score (0-100)."""
        security_issues = analysis_result.get('agent_breakdown', {}).get(
            AGENT_SECURITY, {}).get('issues_count', 0)
        
        if security_issues == 0:
            return 100.0
        
        # Deduct 15 points per security issue (capped at 0)
        score = 100.0 - (security_issues * 15)
        return max(0.0, score)
    
    def _extract_rag_insights(self, analysis_result: Dict) -> Optional[Dict]:
        """
        Extract RAG insights from analysis result.
        
        Args:
            analysis_result: Complete analysis result dictionary
            
        Returns:
            Dictionary containing RAG insights or None if not available
        """
        try:
            # Get RAG Enhanced Agent data from agent_breakdown
            rag_data = analysis_result.get('agent_breakdown', {}).get('RAG Enhanced Agent', {})
            
            if not rag_data:
                return None
            
            # Extract metadata containing RAG insights
            metadata = rag_data.get('metadata', {})
            rag_insights = metadata.get('rag_insights', {})
            
            if not rag_insights:
                return None
            
            # Structure the insights for storage
            insights_to_store = {
                'full_text': rag_insights.get('full_text', ''),
                'similar_prs_referenced': rag_insights.get('similar_prs_referenced', 0),
                'context_used': rag_insights.get('context_used', False),
                'recommendations': rag_insights.get('recommendations', ''),
                'lessons_learned': rag_insights.get('lessons_learned', ''),
                'potential_pitfalls': rag_insights.get('potential_pitfalls', ''),
                'best_practices': rag_insights.get('best_practices', ''),
                'similar_prs_found': metadata.get('similar_prs_found', 0),
                'best_practices_found': metadata.get('best_practices_found', 0),
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'novelty_score': metadata.get('novelty_score', 0.0),
                'risk_score': metadata.get('risk_score', 0.0),
                'tips': rag_insights.get('tips', []),
                'similar_prs': rag_insights.get('similar_prs', []),
                'recommendations_count': metadata.get('recommendations_count', 0),
                'patterns_identified': metadata.get('patterns_identified', [])
            }
            
            return insights_to_store
            
        except Exception as e:
            logger.error(f"Error extracting RAG insights: {e}")
            return None
    
    def _set_rag_summary_fields(self, pr_analysis: PRAnalysis, analysis_result: Dict) -> None:
        """
        Set RAG summary fields on the PRAnalysis object from the RAG insights.
        
        Args:
            pr_analysis: PRAnalysis object to update
            analysis_result: Complete analysis result dictionary
        """
        try:
            # Get RAG Enhanced Agent data
            rag_data = analysis_result.get('agent_breakdown', {}).get('RAG Enhanced Agent', {})
            
            if not rag_data:
                pr_analysis.has_rag_insights = False
                logger.info("DEBUG _set_rag: No rag_data found")
                return
            
            metadata = rag_data.get('metadata', {})
            logger.info(f"DEBUG _set_rag: metadata keys = {metadata.keys() if hasattr(metadata, 'keys') else type(metadata)}")
            
            # Set has_rag_insights flag
            pr_analysis.has_rag_insights = bool(metadata.get('rag_insights'))
            
            # Set risk and novelty scores
            pr_analysis.rag_risk_score = metadata.get('risk_score', 0.0)
            pr_analysis.rag_novelty_score = metadata.get('novelty_score', 0.0)
            
            # Set counts
            pr_analysis.rag_similar_prs_count = metadata.get('similar_prs_found', 0)
            pr_analysis.rag_recommendations_count = metadata.get('recommendations_count', 0)
            
            logger.info(f"DEBUG _set_rag: Set values - has_rag={pr_analysis.has_rag_insights}, risk={pr_analysis.rag_risk_score}, novelty={pr_analysis.rag_novelty_score}")
            
            # Set patterns (can be list or dict)
            patterns = metadata.get('patterns_identified', [])
            if isinstance(patterns, list):
                pr_analysis.rag_patterns_identified = patterns
            elif isinstance(patterns, dict):
                pr_analysis.rag_patterns_identified = list(patterns.keys())
            else:
                pr_analysis.rag_patterns_identified = []
                
        except Exception as e:
            logger.warning(f"Failed to set RAG summary fields: {e}")
            pr_analysis.has_rag_insights = False
    
    def _calculate_maintainability_score(self, analysis_result: Dict) -> float:
        """Calculate maintainability score based on code quality metrics."""
        quality_issues = analysis_result.get('agent_breakdown', {}).get(
            AGENT_CODE_QUALITY, {}).get('issues_count', 0)
        
        coverage_data = analysis_result.get('agent_breakdown', {}).get(
            AGENT_COVERAGE, {}).get('metadata', {})
        
        coverage = coverage_data.get('estimated_coverage', 0) or 0
        
        # Start with coverage score (0-50 points)
        score = (coverage / 100) * 50
        
        # Add points for low quality issues (0-50 points)
        if quality_issues == 0:
            score += 50
        elif quality_issues < 10:
            score += 40
        elif quality_issues < 50:
            score += 30
        elif quality_issues < 100:
            score += 20
        elif quality_issues < 200:
            score += 10
        
        return min(100.0, score)
    
    def _update_user_statistics(
        self,
        session: Session,
        author_login: str,
        author_email: Optional[str],
        pr_analysis: PRAnalysis
    ):
        """Update aggregated user statistics."""
        if not author_login:
            return
        
        # Get or create user statistics
        user_stats = self._get_or_create_user_stats(
            session, author_login, author_email, pr_analysis
        )
        
        # Update email and name if needed
        self._update_user_contact_info(user_stats, author_email, pr_analysis)
        
        # Update counts
        self._update_user_issue_counts(user_stats, pr_analysis)
        
        # Update averages
        self._update_user_averages(session, user_stats, author_login)
        
        # Update metadata
        user_stats.last_pr_date = pr_analysis.analyzed_at
        user_stats.last_updated = datetime.now(timezone.utc)
    
    def _get_or_create_user_stats(
        self,
        session: Session,
        author_login: str,
        author_email: Optional[str],
        pr_analysis: PRAnalysis
    ) -> UserStatistics:
        """Get existing user statistics or create new one."""
        user_stats = session.query(UserStatistics).filter_by(
            author_login=author_login
        ).first()
        
        if not user_stats:
            email_to_use = author_email or pr_analysis.author_email
            name_to_use = pr_analysis.author_name
            
            user_stats = UserStatistics(
                author_login=author_login,
                author_email=email_to_use,
                author_name=name_to_use,
                first_pr_date=pr_analysis.analyzed_at,
                total_prs=0,
                total_issues_found=0,
                critical_issues_total=0,
                high_issues_total=0,
                medium_issues_total=0,
                low_issues_total=0
            )
            session.add(user_stats)
        
        return user_stats
    
    def _update_user_contact_info(
        self,
        user_stats: UserStatistics,
        author_email: Optional[str],
        pr_analysis: PRAnalysis
    ) -> None:
        """Update user email and name if not already set."""
        email_to_update = author_email or pr_analysis.author_email
        if email_to_update and not user_stats.author_email:
            user_stats.author_email = email_to_update
        if pr_analysis.author_name and not user_stats.author_name:
            user_stats.author_name = pr_analysis.author_name
    
    def _update_user_issue_counts(
        self,
        user_stats: UserStatistics,
        pr_analysis: PRAnalysis
    ) -> None:
        """Update user issue counts from PR analysis."""
        user_stats.total_prs = (user_stats.total_prs or 0) + 1
        user_stats.total_issues_found = (user_stats.total_issues_found or 0) + (pr_analysis.total_issues or 0)
        user_stats.critical_issues_total = (user_stats.critical_issues_total or 0) + (pr_analysis.critical_issues or 0)
        user_stats.high_issues_total = (user_stats.high_issues_total or 0) + (pr_analysis.high_issues or 0)
        user_stats.medium_issues_total = (user_stats.medium_issues_total or 0) + (pr_analysis.medium_issues or 0)
        user_stats.low_issues_total = (user_stats.low_issues_total or 0) + (pr_analysis.low_issues or 0)
    
    def _calculate_basic_averages(self, all_prs: List, user_stats: UserStatistics) -> None:
        """Calculate basic average scores for user."""
        user_stats.avg_quality_score = sum(p.overall_quality_score or 0 for p in all_prs) / len(all_prs)
        user_stats.avg_security_score = sum(p.security_score or 0 for p in all_prs) / len(all_prs)
        user_stats.avg_maintainability_score = sum(p.maintainability_score or 0 for p in all_prs) / len(all_prs)
        user_stats.avg_coverage = sum(p.estimated_coverage or 0 for p in all_prs) / len(all_prs)

    def _calculate_rag_averages(self, prs_with_rag: List, user_stats: UserStatistics) -> None:
        """Calculate RAG-specific averages for user."""
        user_stats.total_rag_insights = len(prs_with_rag)
        user_stats.avg_rag_risk_score = sum(p.rag_risk_score or 0 for p in prs_with_rag) / len(prs_with_rag)
        user_stats.avg_rag_novelty_score = sum(p.rag_novelty_score or 0 for p in prs_with_rag) / len(prs_with_rag)
        user_stats.total_similar_prs_referenced = sum(p.rag_similar_prs_count or 0 for p in prs_with_rag)
        user_stats.total_rag_recommendations = sum(p.rag_recommendations_count or 0 for p in prs_with_rag)
        user_stats.high_risk_prs_count = sum(1 for p in prs_with_rag if (p.rag_risk_score or 0) > 0.7)
        user_stats.novel_prs_count = sum(1 for p in prs_with_rag if (p.rag_novelty_score or 0) > 0.8)

    def _aggregate_user_patterns(self, prs_with_rag: List, user_stats: UserStatistics) -> None:
        """Aggregate patterns from all user PRs."""
        from collections import Counter
        all_patterns = []
        for p in prs_with_rag:
            if p.rag_patterns_identified:
                if isinstance(p.rag_patterns_identified, list):
                    all_patterns.extend(p.rag_patterns_identified)
                elif isinstance(p.rag_patterns_identified, dict):
                    all_patterns.extend(p.rag_patterns_identified.keys())
        
        if all_patterns:
            pattern_counts = Counter(all_patterns)
            user_stats.most_common_patterns = dict(pattern_counts.most_common(5))
            user_stats.total_patterns_identified = len(set(all_patterns))
            user_stats.learning_velocity = len(set(all_patterns)) / len(prs_with_rag)

    def _update_user_averages(
        self,
        session: Session,
        user_stats: UserStatistics,
        author_login: str
    ) -> None:
        """Update user average scores from all PRs."""
        all_prs = session.query(PRAnalysis).filter_by(
            author_login=author_login
        ).all()
        
        if not all_prs:
            return
            
        # Calculate basic averages
        self._calculate_basic_averages(all_prs, user_stats)
        
        # Update RAG averages
        prs_with_rag = [p for p in all_prs if getattr(p, 'has_rag_insights', False)]
        if prs_with_rag:
            self._calculate_rag_averages(prs_with_rag, user_stats)
            self._aggregate_user_patterns(prs_with_rag, user_stats)
    
    def get_pr_by_id(self, pr_id: int) -> Optional[PRAnalysis]:
        """
        Get PR analysis by GitHub's unique PR ID.
        
        Args:
            pr_id: GitHub's unique PR identifier
            
        Returns:
            PRAnalysis record or None
        """
        with self.get_session() as session:
            return session.query(PRAnalysis).filter_by(pr_id=pr_id).first()
    
    def get_pr_analysis(self, repository: str, pr_number: int = None, pr_id: int = None) -> Optional[PRAnalysis]:
        """
        Get PR analysis by repository and PR number or PR ID.
        
        Args:
            repository: Repository name (owner/repo)
            pr_number: PR number within repository (optional if pr_id provided)
            pr_id: GitHub's unique PR ID (optional, preferred over pr_number)
            
        Returns:
            PRAnalysis record or None
        """
        with self.get_session() as session:
            # Prefer pr_id if provided (globally unique)
            if pr_id:
                return session.query(PRAnalysis).filter_by(
                    repository=repository,
                    pr_id=pr_id
                ).first()
            
            # Fallback to pr_number
            if pr_number:
                return session.query(PRAnalysis).filter_by(
                    repository=repository,
                    pr_number=pr_number
                ).order_by(desc(PRAnalysis.analyzed_at)).first()
            
            return None
    
    def get_user_statistics(self, author_login: str) -> Optional[UserStatistics]:
        """Get user statistics by author login."""
        with self.get_session() as session:
            return session.query(UserStatistics).filter_by(
                author_login=author_login
            ).first()
    
    def get_user_prs(self, author_login: str, limit: int = 20) -> List[PRAnalysis]:
        """Get recent PRs for a user."""
        with self.get_session() as session:
            return session.query(PRAnalysis).filter_by(
                author_login=author_login
            ).order_by(desc(PRAnalysis.analyzed_at)).limit(limit).all()
    
    def get_repository_stats(self, repository: str) -> Dict[str, Any]:
        """Get aggregated statistics for a repository."""
        with self.get_session() as session:
            prs = session.query(PRAnalysis).filter_by(repository=repository).all()
            
            if not prs:
                return {}
            
            return {
                'total_prs': len(prs),
                'total_issues': sum(p.total_issues for p in prs),
                'avg_quality_score': sum(p.overall_quality_score or 0 for p in prs) / len(prs),
                'avg_security_score': sum(p.security_score or 0 for p in prs) / len(prs),
                'avg_coverage': sum(p.estimated_coverage or 0 for p in prs) / len(prs),
                'most_common_issues': self._get_most_common_issues(session, repository)
            }
    
    def _get_most_common_issues(self, session: Session, repository: str, limit: int = 10) -> List[Dict]:
        """Get most common issue types for a repository."""
        results = session.query(
            PRIssue.issue_type,
            func.count(PRIssue.id).label('count')
        ).join(PRAnalysis).filter(
            PRAnalysis.repository == repository
        ).group_by(PRIssue.issue_type).order_by(
            desc('count')
        ).limit(limit).all()
        
        return [{'issue_type': r[0], 'count': r[1]} for r in results]
    
    def get_prs_by_email(self, author_email: str, limit: int = 50) -> List[PRAnalysis]:
        """
        Get all PRs by author email address.
        
        Args:
            author_email: Email address of the author
            limit: Maximum number of PRs to return (default: 50)
            
        Returns:
            List of PRAnalysis records for this email
        """
        with self.get_session() as session:
            prs = session.query(PRAnalysis).filter_by(
                author_email=author_email
            ).order_by(desc(PRAnalysis.analyzed_at)).limit(limit).all()
            
            # Expunge from session so they can be used outside the context
            for pr in prs:
                session.expunge(pr)
            
            return prs
    
    def get_user_statistics_by_email(self, author_email: str) -> Optional[UserStatistics]:
        """
        Get user statistics by email address.
        
        Args:
            author_email: Email address of the author
            
        Returns:
            UserStatistics record or None if not found
        """
        with self.get_session() as session:
            stats = session.query(UserStatistics).filter_by(
                author_email=author_email
            ).first()
            
            if stats:
                session.expunge(stats)
            
            return stats
    
    def search_prs_by_email_pattern(self, email_pattern: str, limit: int = 100) -> List[PRAnalysis]:
        """
        Search PRs by email pattern (supports wildcards with LIKE).
        
        Args:
            email_pattern: Email pattern (e.g., '%@example.com', 'john%')
            limit: Maximum number of PRs to return (default: 100)
            
        Returns:
            List of PRAnalysis records matching the pattern
        """
        with self.get_session() as session:
            prs = session.query(PRAnalysis).filter(
                PRAnalysis.author_email.like(email_pattern)
            ).order_by(desc(PRAnalysis.analyzed_at)).limit(limit).all()
            
            # Expunge from session so they can be used outside the context
            for pr in prs:
                session.expunge(pr)
            
            return prs
    
    def get_pr_summary_by_email(self, author_email: str) -> Dict[str, Any]:
        """
        Get aggregated summary of PRs for an author by email.
        
        Args:
            author_email: Email address of the author
            
        Returns:
            Dictionary with aggregated statistics
        """
        with self.get_session() as session:
            prs = session.query(PRAnalysis).filter_by(
                author_email=author_email
            ).all()
            
            if not prs:
                return {
                    'author_email': author_email,
                    'total_prs': 0,
                    'repositories': [],
                    'total_issues': 0,
                    'message': 'No PRs found for this email'
                }
            
            repositories = list({pr.repository for pr in prs})
            
            return {
                'author_email': author_email,
                'author_name': prs[0].author_name,
                'author_login': prs[0].author_login,
                'total_prs': len(prs),
                'repositories': repositories,
                'total_issues': sum(pr.total_issues for pr in prs),
                'critical_issues': sum(pr.critical_issues for pr in prs),
                'high_issues': sum(pr.high_issues for pr in prs),
                'medium_issues': sum(pr.medium_issues for pr in prs),
                'low_issues': sum(pr.low_issues for pr in prs),
                'avg_quality_score': sum(pr.overall_quality_score or 0 for pr in prs) / len(prs) if prs else 0,
                'avg_security_score': sum(pr.security_score or 0 for pr in prs) / len(prs) if prs else 0,
                'avg_coverage': sum(pr.estimated_coverage or 0 for pr in prs) / len(prs) if prs else 0,
                'first_pr_date': min(pr.analyzed_at for pr in prs if pr.analyzed_at),
                'last_pr_date': max(pr.analyzed_at for pr in prs if pr.analyzed_at),
                'prs': [
                    {
                        'pr_number': pr.pr_number,
                        'repository': pr.repository,
                        'title': pr.pr_title,
                        'url': pr.pr_url,
                        'total_issues': pr.total_issues,
                        'quality_score': pr.overall_quality_score,
                        'analyzed_at': pr.analyzed_at.isoformat() if pr.analyzed_at else None
                    }
                    for pr in sorted(prs, key=lambda x: x.analyzed_at or datetime.min, reverse=True)
                ]
            }
    
    def save_user_analytics(self, analytics_data: Dict[str, Any]) -> Optional[UserAnalytics]:
        """
        Save user analytics snapshot to database.
        
        Args:
            analytics_data: Analytics data from AnalyticsProcessingAgent
            
        Returns:
            UserAnalytics record or None if failed
        """
        with self.get_session() as session:
            try:
                # Extract data from analytics result
                author_login = analytics_data.get('author_login')
                author_email = analytics_data.get('author_email')
                author_name = analytics_data.get('author_name')
                
                if not author_login:
                    logger.warning("Cannot save analytics without author_login")
                    return None
                
                # Get analysis period info
                period_info = analytics_data.get('analysis_period', {})
                quality_metrics = analytics_data.get('quality_metrics', {})
                code_scores = analytics_data.get('code_scores', {})
                
                # Create UserAnalytics record
                user_analytics = UserAnalytics(
                    author_login=author_login,
                    author_email=author_email,
                    author_name=author_name,
                    
                    # Period
                    analysis_date=datetime.now(timezone.utc),
                    period_start=datetime.fromisoformat(period_info['start_date']) if period_info.get('start_date') else None,
                    period_end=datetime.fromisoformat(period_info['end_date']) if period_info.get('end_date') else datetime.now(timezone.utc),
                    total_prs_analyzed=period_info.get('total_prs', 0),
                    
                    # Quality Scores
                    avg_quality_score=code_scores.get('overall_quality', {}).get('average'),
                    avg_security_score=code_scores.get('security', {}).get('average'),
                    avg_maintainability_score=code_scores.get('maintainability', {}).get('average'),
                    avg_coverage=quality_metrics.get('coverage_metrics', {}).get('avg_coverage'),
                    avg_complexity=quality_metrics.get('coverage_metrics', {}).get('avg_complexity'),
                    
                    # Issue Stats
                    total_issues=quality_metrics.get('total_issues', 0),
                    avg_issues_per_pr=quality_metrics.get('avg_issues_per_pr'),
                    critical_issues=quality_metrics.get('severity_distribution', {}).get('critical', 0),
                    high_issues=quality_metrics.get('severity_distribution', {}).get('high', 0),
                    medium_issues=quality_metrics.get('severity_distribution', {}).get('medium', 0),
                    low_issues=quality_metrics.get('severity_distribution', {}).get('low', 0),
                    
                    # Code Metrics
                    total_files_changed=quality_metrics.get('total_files_changed', 0),
                    total_lines_added=quality_metrics.get('total_lines_added', 0),
                    total_lines_deleted=quality_metrics.get('total_lines_deleted', 0),
                    avg_files_per_pr=quality_metrics.get('avg_files_per_pr'),
                    avg_lines_per_pr=quality_metrics.get('avg_lines_per_pr'),
                    
                    # Trends
                    quality_trend=analytics_data.get('trend_analysis', {}).get('quality'),
                    security_trend=analytics_data.get('trend_analysis', {}).get('security'),
                    coverage_trend=analytics_data.get('trend_analysis', {}).get('coverage'),
                    
                    # RAG Trends and Metrics
                    rag_risk_trend=analytics_data.get('rag_metrics', {}).get('risk_trend'),
                    rag_novelty_trend=analytics_data.get('rag_metrics', {}).get('novelty_trend'),
                    avg_rag_risk_score=analytics_data.get('rag_metrics', {}).get('avg_risk_score'),
                    avg_rag_novelty_score=analytics_data.get('rag_metrics', {}).get('avg_novelty_score'),
                    total_rag_insights=analytics_data.get('rag_metrics', {}).get('total_insights', 0),
                    total_similar_prs_found=analytics_data.get('rag_metrics', {}).get('total_similar_prs', 0),
                    total_rag_recommendations=analytics_data.get('rag_metrics', {}).get('total_recommendations', 0),
                    high_risk_prs=analytics_data.get('rag_metrics', {}).get('high_risk_prs', []),
                    novel_contributions=analytics_data.get('rag_metrics', {}).get('novel_contributions', []),
                    patterns_learned=analytics_data.get('rag_metrics', {}).get('patterns_learned', []),
                    rag_insights_summary=analytics_data.get('rag_metrics', {}).get('insights_summary'),
                    
                    # Practices and Recommendations
                    best_practices=analytics_data.get('best_practices', []),
                    bad_practices=analytics_data.get('bad_practices', []),
                    recommendations=analytics_data.get('improvement_recommendations', []),
                    
                    # Distributions
                    agent_breakdown=analytics_data.get('agent_breakdown'),
                    issue_distribution=analytics_data.get('issue_distribution'),
                    
                    # Metadata
                    processing_time_ms=analytics_data.get('processing_time_ms')
                )
                
                session.add(user_analytics)
                session.flush()
                
                logger.info(
                    "User analytics saved",
                    user_analytics_id=user_analytics.id,
                    author_login=author_login,
                    total_prs=period_info.get('total_prs', 0)
                )
                
                session.expunge(user_analytics)
                return user_analytics
                
            except Exception as e:
                logger.error("Failed to save user analytics", error=str(e), author=analytics_data.get('author_login'))
                return None
    
    def get_latest_user_analytics(self, author_login: str) -> Optional[UserAnalytics]:
        """Get most recent analytics for a user."""
        with self.get_session() as session:
            analytics = session.query(UserAnalytics).filter_by(
                author_login=author_login
            ).order_by(desc(UserAnalytics.analysis_date)).first()
            
            if analytics:
                session.expunge(analytics)
            
            return analytics
    
    def get_user_analytics_by_email(self, author_email: str) -> Optional[UserAnalytics]:
        """Get most recent analytics for a user by email."""
        with self.get_session() as session:
            analytics = session.query(UserAnalytics).filter_by(
                author_email=author_email
            ).order_by(desc(UserAnalytics.analysis_date)).first()
            
            if analytics:
                session.expunge(analytics)
            
            return analytics
    
    def get_user_pr_history(
        self,
        author_login: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[PRAnalysis]:
        """
        Get PR history for a user with optional date filtering.
        Used for progress tracking over time (week/month/year).
        
        Args:
            author_login: GitHub username
            start_date: Filter PRs after this date
            end_date: Filter PRs before this date
            limit: Maximum number of PRs to return
            
        Returns:
            List of PR analysis records ordered by date
        """
        with self.get_session() as session:
            query = session.query(PRAnalysis).filter_by(author_login=author_login)
            
            if start_date:
                query = query.filter(PRAnalysis.analyzed_at >= start_date)
            if end_date:
                query = query.filter(PRAnalysis.analyzed_at <= end_date)
            
            prs = query.order_by(desc(PRAnalysis.analyzed_at)).limit(limit).all()
            
            # Expunge from session
            for pr in prs:
                session.expunge(pr)
            
            return prs
    
    def get_user_progress_summary(
        self,
        author_login: str,
        period: str = 'week'  # 'week', 'month', 'year'
    ) -> Dict[str, Any]:
        """
        Get user progress summary for a time period.
        Compares current period vs previous period.
        
        Args:
            author_login: GitHub username
            period: Time period ('week', 'month', 'year')
            
        Returns:
            Dictionary with progress metrics and trends
        """
        # Get time period boundaries
        current_start, previous_start, now = self._get_period_boundaries(period)
        
        # Get PRs for current and previous periods
        current_prs = self.get_user_pr_history(author_login, current_start, now)
        previous_prs = self.get_user_pr_history(author_login, previous_start, current_start)
        
        if not current_prs and not previous_prs:
            return {
                'author_login': author_login,
                'period': period,
                'no_data': True
            }
        
        # Calculate metrics for both periods
        current_metrics = self._calculate_period_metrics(current_prs)
        previous_metrics = self._calculate_period_metrics(previous_prs)
        
        # Build and return summary
        return self._build_progress_summary(
            author_login, period, current_start, previous_start, now,
            current_metrics, previous_metrics
        )
    
    def _get_period_boundaries(self, period: str):
        """Get start dates for current and previous periods."""
        from datetime import timedelta
        
        now = datetime.now(timezone.utc)
        if period == 'week':
            current_start = now - timedelta(days=7)
            previous_start = now - timedelta(days=14)
        elif period == 'month':
            current_start = now - timedelta(days=30)
            previous_start = now - timedelta(days=60)
        elif period == 'year':
            current_start = now - timedelta(days=365)
            previous_start = now - timedelta(days=730)
        else:
            raise ValueError(f"Invalid period: {period}")
        
        return current_start, previous_start, now
    
    def _calculate_period_metrics(self, prs):
        """Calculate metrics for a list of PRs."""
        if not prs:
            return {
                'pr_count': 0,
                'avg_quality': 0,
                'avg_security': 0,
                'total_issues': 0,
                'avg_coverage': 0
            }
        return {
            'pr_count': len(prs),
            'avg_quality': sum(p.overall_quality_score or 0 for p in prs) / len(prs),
            'avg_security': sum(p.security_score or 0 for p in prs) / len(prs),
            'total_issues': sum(p.total_issues or 0 for p in prs),
            'avg_coverage': sum(p.estimated_coverage or 0 for p in prs) / len(prs)
        }
    
    def _build_progress_summary(
        self, author_login, period, current_start, previous_start, now,
        current_metrics, previous_metrics
    ):
        """Build the final progress summary dictionary."""
        def calc_change(current, previous):
            if previous == 0:
                return 0
            return round(((current - previous) / previous) * 100, 1)
        
        return {
            'author_login': author_login,
            'period': period,
            'current_period': {
                'start_date': current_start.isoformat(),
                'end_date': now.isoformat(),
                **current_metrics
            },
            'previous_period': {
                'start_date': previous_start.isoformat(),
                'end_date': current_start.isoformat(),
                **previous_metrics
            },
            'changes': {
                'pr_count': current_metrics['pr_count'] - previous_metrics['pr_count'],
                'quality_change': calc_change(current_metrics['avg_quality'], previous_metrics['avg_quality']),
                'security_change': calc_change(current_metrics['avg_security'], previous_metrics['avg_security']),
                'issues_change': calc_change(current_metrics['total_issues'], previous_metrics['total_issues']),
                'coverage_change': calc_change(current_metrics['avg_coverage'], previous_metrics['avg_coverage'])
            },
            'trend': {
                'quality': self._get_trend_direction(current_metrics['avg_quality'], previous_metrics['avg_quality'], False),
                'security': self._get_trend_direction(current_metrics['avg_security'], previous_metrics['avg_security'], False),
                'issues': self._get_trend_direction(current_metrics['total_issues'], previous_metrics['total_issues'], True)
            }
        }
    
    def _get_trend_direction(self, current_value: float, previous_value: float, lower_is_better: bool) -> str:
        """Determine trend direction (improving/declining/stable)."""
        if current_value > previous_value:
            return 'declining' if lower_is_better else 'improving'
        elif current_value < previous_value:
            return 'improving' if lower_is_better else 'declining'
        else:
            return 'stable'
    
    def get_user_analytics_history(
        self,
        author_login: str,
        limit: int = 30
    ) -> List[UserAnalytics]:
        """
        Get analytics history for a user (all snapshots over time).
        Useful for showing analytics trends.
        
        Args:
            author_login: GitHub username
            limit: Maximum number of snapshots to return
            
        Returns:
            List of analytics snapshots ordered by date (newest first)
        """
        with self.get_session() as session:
            analytics_list = session.query(UserAnalytics).filter_by(
                author_login=author_login
            ).order_by(desc(UserAnalytics.analysis_date)).limit(limit).all()
            
            # Expunge from session
            for analytics in analytics_list:
                session.expunge(analytics)
            
            return analytics_list

    def save_rag_feedback(self, pr_analysis_id: int, rating: int, is_helpful: bool, 
                          recommendation_id: str = None, user_comment: str = None):
        """Save user feedback for a RAG recommendation."""
        with self.get_session() as session:
            feedback = RAGFeedback(
                pr_analysis_id=pr_analysis_id,
                rating=rating,
                is_helpful=is_helpful,
                recommendation_id=recommendation_id,
                user_comment=user_comment
            )
            session.add(feedback)
            session.commit()
            return feedback

    def get_pr_feedback(self, pr_number: int, repository: str = None) -> List[Dict]:
        """Get all feedback for a specific PR."""
        with self.get_session() as session:
            query = session.query(RAGFeedback).join(PRAnalysis)
            query = query.filter(PRAnalysis.pr_number == pr_number)
            if repository:
                query = query.filter(PRAnalysis.repository == repository)
            
            feedback_list = query.all()
            return [
                {
                    'rating': f.rating,
                    'is_helpful': f.is_helpful,
                    'comment': f.user_comment,
                    'created_at': f.created_at.isoformat()
                } for f in feedback_list
            ]

    def update_pattern_library(self, pattern_name: str, category: str, 
                               pr_info: Dict, solution: str = None):
        """Insert or update a pattern in the library."""
        with self.get_session() as session:
            pattern = session.query(RAGPatternLibrary).filter_by(pattern_name=pattern_name).first()
            
            if pattern:
                pattern.frequency += 1
                pattern.last_seen = datetime.now(timezone.utc)
                # Update example PRs list (avoid duplicates)
                if not pattern.example_prs:
                    pattern.example_prs = []
                if pr_info not in pattern.example_prs:
                    pattern.example_prs.append(pr_info)
                
                # Add solution if provided and not already present
                if solution:
                    if not pattern.recommended_solutions:
                        pattern.recommended_solutions = []
                    if solution not in pattern.recommended_solutions:
                        pattern.recommended_solutions.append(solution)
            else:
                pattern = RAGPatternLibrary(
                    pattern_name=pattern_name,
                    category=category,
                    example_prs=[pr_info],
                    recommended_solutions=[solution] if solution else []
                )
                session.add(pattern)
            
            session.commit()
            return pattern

    def get_common_patterns(self, category: str = None, limit: int = 10) -> List[Dict]:
        """Get most frequent patterns from the library."""
        with self.get_session() as session:
            query = session.query(RAGPatternLibrary).order_by(desc(RAGPatternLibrary.frequency))
            if category:
                query = query.filter_by(category=category)
            
            patterns = query.limit(limit).all()
            return [
                {
                    'name': p.pattern_name,
                    'category': p.category,
                    'frequency': p.frequency,
                    'solutions': p.recommended_solutions
                } for p in patterns
            ]
