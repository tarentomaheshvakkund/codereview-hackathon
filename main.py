"""Main application entry point."""
import time
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
from flask import Flask, request, jsonify
from flask_cors import CORS
from functools import wraps
from sqlalchemy import text, desc
from models.pr_event import PREvent
from models.feedback import FeedbackFormatter
from models.database import PRAnalysis
from agents.dispatcher import AgentDispatcher
from agents.auto_merge_agent import AutoMergeAgent
from services.github_service import GitHubService
from services.slack_service import SlackService
from services.dashboard_service import DashboardService
from services.database_service import DatabaseService
from services.analytics_service import AnalyticsService
from services.auth_service import AuthService
from utils.logger import logger
from utils.config import config


# Constants
ERROR_DB_SERVICE_UNAVAILABLE = 'Database service not available'
ERROR_ANALYTICS_AGENT_UNAVAILABLE = 'Analytics Processing Agent not available'
ERROR_REQUEST_BODY_REQUIRED = 'Request body is required'
ERROR_MISSING_REPO_PR = 'Missing required fields: repository and pr_number'
ERROR_AUTH_SERVICE_UNAVAILABLE = 'Authentication service not available'
ERROR_EMAIL_REQUIRED = 'Email is required in request body'

# Config keys
CONFIG_OUTPUT_SLACK_ENABLED = 'output.slack.enabled'

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})  # Enable CORS for all API routes

# Initialize database services first (needed by dispatcher for RAG)
db_service = None
analytics_service = None
auth_service = None
db_persistence_agent = None
analytics_processing_agent = None

if config.get('database.enabled', False):
    try:
        db_service = DatabaseService()
        analytics_service = AnalyticsService(db_service)
        auth_service = AuthService(db_service)
        
        # Initialize specialized agents
        from agents.database_persistence_agent import DatabasePersistenceAgent
        from agents.analytics_processing_agent import AnalyticsProcessingAgent
        
        db_persistence_agent = DatabasePersistenceAgent(db_service)
        analytics_processing_agent = AnalyticsProcessingAgent(db_service, analytics_service)
        
        logger.info("Database services and agents initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize database services", error=str(e))
        logger.warning("Running without database persistence")

# Initialize components (after db_service for RAG support)
dispatcher = AgentDispatcher(db_service=db_service)
github_service = GitHubService()
slack_service = SlackService()
dashboard_service = DashboardService()
auto_merge_agent = AutoMergeAgent()

# Initialize PR Comment Agent
pr_comment_agent = None
if config.get('pr_comments.enabled', False):
    try:
        from agents.pr_comment_agent import PRCommentAgent
        pr_comment_agent = PRCommentAgent(
            github_service=github_service,
            db_service=db_service,
            config=config.get('pr_comments', {})
        )
        logger.info("PR Comment Agent initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize PR Comment Agent", error=str(e))
        logger.warning("Running without automated PR comments")


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'multi-agent-pr-review',
        'version': '1.0.0'
    })


# ============================================================================
# AUTHENTICATION MIDDLEWARE
# ============================================================================

def require_auth(f):
    """
    Decorator to require authentication for an endpoint.
    Validates JWT token from Authorization header.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not auth_service:
            return jsonify({'error': ERROR_AUTH_SERVICE_UNAVAILABLE}), 503
        
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'error': 'Authorization header required'}), 401
        
        # Extract token (format: "Bearer <token>")
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return jsonify({'error': 'Invalid authorization header format. Use: Bearer <token>'}), 401
        
        token = parts[1]
        
        # Validate token and session
        is_valid, user_data = auth_service.validate_session(token)
        if not is_valid:
            return jsonify({'error': 'Invalid or expired token. Please login again.'}), 401
        
        # Add user data to request context
        request.current_user = user_data
        
        return f(*args, **kwargs)
    
    return decorated_function


# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@app.route('/api/auth/register', methods=['POST'])
def register():
    """
    Register a new user.
    
    Request Body:
    {
        "username": "john_doe",
        "email": "john@example.com",
        "password": "securepassword123",
        "full_name": "John Doe"  // optional
    }
    
    Response:
    {
        "success": true,
        "message": "User registered successfully",
        "user": {
            "user_id": 1,
            "username": "john_doe",
            "email": "john@example.com",
            "full_name": "John Doe",
            "created_at": "2025-12-21T10:30:00"
        }
    }
    """
    if not auth_service:
        return jsonify({'error': ERROR_AUTH_SERVICE_UNAVAILABLE}), 503
    
    try:
        data = request.json
        if not data:
            return jsonify({'error': ERROR_REQUEST_BODY_REQUIRED}), 400
        
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        full_name = data.get('full_name')
        
        # Register user
        success, message, user_data = auth_service.register_user(
            username=username,
            email=email,
            password=password,
            full_name=full_name
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': message,
                'user': user_data
            }), 201
        else:
            return jsonify({
                'success': False,
                'error': message
            }), 400
            
    except Exception as e:
        logger.error("Registration error", error=str(e))
        return jsonify({'error': 'Registration failed'}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    """
    Login a user and create a session.
    
    Request Body:
    {
        "email": "john@example.com",
        "password": "securepassword123"
    }
    
    Response:
    {
        "success": true,
        "message": "Login successful",
        "session": {
            "token": "eyJhbGciOiJIUzI1NiIs...",
            "user_id": 1,
            "username": "john_doe",
            "email": "john@example.com",
            "full_name": "John Doe",
            "expires_at": "2025-12-22T10:30:00",
            "session_id": 123
        }
    }
    """
    if not auth_service:
        return jsonify({'error': ERROR_AUTH_SERVICE_UNAVAILABLE}), 503
    
    try:
        data = request.json
        if not data:
            return jsonify({'error': ERROR_REQUEST_BODY_REQUIRED}), 400
        
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        # Get client information
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent')
        
        # Login user
        success, message, session_data = auth_service.login_user(
            email=email,
            password=password,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': message,
                'session': session_data
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': message
            }), 401
            
    except Exception as e:
        logger.error("Login error", error=str(e))
        return jsonify({'error': 'Login failed'}), 500


@app.route('/api/auth/logout', methods=['POST'])
@require_auth
def logout():
    """
    Logout a user and invalidate their session.
    
    Headers:
        Authorization: Bearer <token>
    
    Response:
    {
        "success": true,
        "message": "Logout successful"
    }
    """
    if not auth_service:
        return jsonify({'error': ERROR_AUTH_SERVICE_UNAVAILABLE}), 503
    
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        token = auth_header.split()[1]
        
        # Logout user
        success, message = auth_service.logout_user(token)
        
        if success:
            return jsonify({
                'success': True,
                'message': message
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': message
            }), 400
            
    except Exception as e:
        logger.error("Logout error", error=str(e))
        return jsonify({'error': 'Logout failed'}), 500


@app.route('/api/auth/validate', methods=['GET'])
@require_auth
def validate_token():
    """
    Validate current JWT token and get user information.
    
    Headers:
        Authorization: Bearer <token>
    
    Response:
    {
        "valid": true,
        "user": {
            "user_id": 1,
            "username": "john_doe",
            "email": "john@example.com",
            "full_name": "John Doe",
            "is_admin": false
        }
    }
    """
    return jsonify({
        'valid': True,
        'user': request.current_user
    }), 200


@app.route('/api/auth/sessions', methods=['GET'])
@require_auth
def get_user_sessions():
    """
    Get all active sessions for the current user.
    
    Headers:
        Authorization: Bearer <token>
    
    Response:
    {
        "sessions": [
            {
                "session_id": 123,
                "created_at": "2025-12-21T10:30:00",
                "expires_at": "2025-12-22T10:30:00",
                "last_activity": "2025-12-21T15:45:00",
                "ip_address": "192.168.1.100",
                "user_agent": "Mozilla/5.0..."
            }
        ]
    }
    """
    if not auth_service:
        return jsonify({'error': ERROR_AUTH_SERVICE_UNAVAILABLE}), 503
    
    try:
        user_id = UUID(request.current_user['user_id'])  # Convert string back to UUID
        sessions = auth_service.get_user_active_sessions(user_id)
        
        return jsonify({
            'sessions': sessions
        }), 200
        
    except Exception as e:
        logger.error("Error getting user sessions", error=str(e))
        return jsonify({'error': 'Failed to get sessions'}), 500


# ============================================================================
# PR ANALYSIS ENDPOINTS (Original endpoints below)
# ============================================================================

def _validate_analyze_request(data):
    """Validate the analyze request and return repository and pr_number."""
    if not data:
        return None, None, jsonify({'error': ERROR_REQUEST_BODY_REQUIRED}), 400
    
    repository = data.get('repository')
    pr_number = data.get('pr_number')
    
    if not repository or not pr_number:
        return None, None, jsonify({'error': ERROR_MISSING_REPO_PR}), 400
    
    return repository, pr_number, None, None


def _fetch_pr_event(repository, pr_number):
    """Fetch PR details from GitHub and create PREvent object."""
    from datetime import datetime
    from models.pr_event import PRAuthor
    
    pr_details = github_service.get_pr_details(repository, pr_number)
    
    if not pr_details:
        return None, jsonify({
            'error': f'Could not fetch PR #{pr_number} from {repository}. Check repository name and PR number.'
        }), 404
    
    pr_event = PREvent(
        action='manual',
        id=pr_details.get('id', 0),  # GitHub's unique PR ID
        pr_number=pr_number,
        pr_title=pr_details.get('title', ''),
        pr_description=pr_details.get('body', ''),
        pr_url=f"https://github.com/{repository}/pull/{pr_number}",
        repository=repository,
        repository_url=f"https://github.com/{repository}",
        author=PRAuthor(
            login=pr_details.get('user', {}).get('login', ''),
            id=0,
            avatar_url=''
        ),
        base_branch=pr_details.get('base', {}).get('ref', 'main'),
        head_branch=pr_details.get('head', {}).get('ref', ''),
        files=[],
        created_at=datetime.now(),
        updated_at=datetime.now(),
        is_draft=False
    )
    
    pr_event.files = github_service.get_pr_files(repository, pr_number)
    return (pr_event, pr_details), None, None


def _build_response_data(pr_event, result):
    """Build API response data from analysis result."""
    critical_count = sum(1 for issue in result.issues if issue.severity == 'critical')
    high_count = sum(1 for issue in result.issues if issue.severity == 'high')
    medium_count = sum(1 for issue in result.issues if issue.severity == 'medium')
    low_count = sum(1 for issue in result.issues if issue.severity == 'low')
    
    return {
        'status': 'success',
        'message': 'Analysis completed',
        'pr_number': pr_event.pr_number,
        'repository': pr_event.repository,
        'agent_used': result.agent_name,
        'success': result.success,
        'execution_time': result.execution_time,
        'issues_found': len(result.issues),
        'critical_issues': critical_count,
        'high_issues': high_count,
        'medium_issues': medium_count,
        'low_issues': low_count,
        'issues': [
            {
                'file': issue.file,
                'line': issue.line,
                'column': issue.column,
                'type': issue.type.value if hasattr(issue.type, 'value') else str(issue.type),
                'severity': issue.severity.value if hasattr(issue.severity, 'value') else str(issue.severity),
                'code': issue.code,
                'message': issue.message,
                'suggestion': issue.suggestion,
                'metadata': issue.metadata
            }
            for issue in result.issues
        ],
        'metrics': result.metrics,
        'agent_breakdown': result.metadata.get('agent_breakdown', {}) if result.metadata else {},
        'error': result.error
    }


def _persist_analysis(pr_event, pr_details, result, data, response_data):
    """Persist analysis to database using persistence agent."""
    if not db_persistence_agent:
        return
    
    try:
        pr_data = {
            'repository': pr_event.repository,
            'pr_number': pr_event.pr_number,
            'title': pr_details.get('title', ''),
            'description': pr_details.get('body', ''),
            'url': f"https://github.com/{pr_event.repository}/pull/{pr_event.pr_number}",
            'author': {
                'login': pr_details.get('user', {}).get('login', ''),
                'email': pr_details.get('user', {}).get('email'),
                'name': pr_details.get('user', {}).get('name'),
                'id': pr_details.get('user', {}).get('id', 0)
            },
            'base_branch': pr_details.get('base', {}).get('ref', 'main'),
            'head_branch': pr_details.get('head', {}).get('ref', ''),
            'files_changed': len(pr_event.files),
            'lines_added': sum(f.additions for f in pr_event.files),
            'lines_deleted': sum(f.deletions for f in pr_event.files),
            'is_draft': pr_details.get('draft', False),
            'created_at': pr_details.get('created_at'),
            'updated_at': pr_details.get('updated_at')
        }
        
        # Get author email from multiple sources (in priority order):
        # 1. Explicitly provided in request
        # 2. From PR user object (GitHub API)
        # 3. From PR commits (fallback)
        author_email = data.get('author_email')
        if not author_email:
            author_email = pr_details.get('user', {}).get('email')
        if not author_email:
            # Try to extract from PR commits
            try:
                author_email = github_service.get_author_email_from_commits(
                    pr_event.repository,
                    pr_event.pr_number
                )
                if author_email:
                    logger.info(
                        "Extracted author email from commits",
                        repository=pr_event.repository,
                        pr_number=pr_event.pr_number,
                        email=author_email
                    )
            except Exception as email_error:
                logger.warning(
                    "Failed to extract email from commits",
                    error=str(email_error)
                )

        persistence_result = db_persistence_agent.persist_analysis(
            pr_data=pr_data,
            analysis_result=result,
            author_email=author_email
        )
        
        if persistence_result.get('success'):
            logger.info(
                "PR analysis persisted by Database Persistence Agent",
                pr_analysis_id=persistence_result.get('pr_analysis_id'),
                repository=pr_event.repository,
                pr_number=pr_event.pr_number
            )
            response_data['database_id'] = persistence_result.get('pr_analysis_id')
            return persistence_result
    
    except Exception as db_error:
        logger.error(
            "Database Persistence Agent failed",
            error=str(db_error),
            repository=pr_event.repository,
            pr_number=pr_event.pr_number
        )
    return None


def _get_head_sha_from_pr_details(pr_details: dict, repository: str, pr_number: int) -> Optional[str]:
    """Extract head SHA from PR details or fetch if missing."""
    # Try to get from pr_details
    if 'head' in pr_details and 'sha' in pr_details['head']:
        return pr_details['head']['sha']
    
    # If not found, try to fetch from GitHub
    logger.warning(
        "No head SHA found, attempting to fetch from GitHub",
        repository=repository,
        pr_number=pr_number
    )
    try:
        pr_info = github_service.get_pr_details(repository, pr_number)
        if pr_info and 'head' in pr_info and 'sha' in pr_info['head']:
            head_sha = pr_info['head']['sha']
            logger.info("Successfully fetched head SHA", head_sha=head_sha)
            return head_sha
    except Exception as fetch_error:
        logger.error("Failed to fetch head SHA", error=str(fetch_error))
    
    return None


def _handle_pr_comments_tracking(pr_event, result, pr_details, persistence_result, response_data, repository, pr_number):
    """Handle tracking comments in database (update if exists, insert if new)."""
    try:
        head_sha = _get_head_sha_from_pr_details(pr_details, repository, pr_number)
        
        logger.info(
            "Preparing to track PR comments in database",
            repository=repository,
            pr_number=pr_number,
            head_sha=head_sha
        )
        
        # Get pr_analysis_id from persistence result
        pr_analysis_id = persistence_result.get('pr_analysis_id') if persistence_result else None
        
        # Track comments in database (post_comments=False means don't post to GitHub)
        comment_result = pr_comment_agent.post_analysis_comments(
            pr_event=pr_event,
            agent_result=result,
            commit_sha=head_sha,
            pr_analysis_id=pr_analysis_id
        )
        
        response_data['comments_tracked'] = comment_result
        logger.info(
            "Tracked PR comments in database",
            repository=repository,
            pr_number=pr_number,
            summary_tracked=comment_result.get('summary_posted'),  # Note: 'posted' flag still used internally
            inline_count=comment_result.get('inline_comments_posted')
        )
        
    except Exception as comment_error:
        logger.error(
            "Failed to track PR comments",
            error=str(comment_error),
            repository=repository,
            pr_number=pr_number
        )
        response_data['comments_error'] = str(comment_error)


def _handle_slack_notifications(pr_event, result, repository, pr_number, response_data):
    """Handle sending Slack notifications."""
    if not config.get(CONFIG_OUTPUT_SLACK_ENABLED):
        return
    
    try:
        slack_message = format_slack_message(pr_event, result)
        slack_service.send_pr_notification(slack_message)
        logger.info(
            "Sent Slack notification",
            repository=repository,
            pr_number=pr_number
        )
        
        # Send critical alert if needed
        if result.critical_count > 0 and config.get('output.slack.mention_on_critical'):
            slack_service.send_critical_alert(
                pr_event.repository,
                pr_event.pr_number,
                pr_event.pr_url,
                result.critical_count
            )
            logger.info(
                "Sent Slack critical alert",
                repository=repository,
                pr_number=pr_number,
                critical_count=result.critical_count
            )
    except Exception as slack_error:
        logger.error(
            "Failed to send Slack notification",
            error=str(slack_error),
            repository=repository,
            pr_number=pr_number
        )
        response_data['slack_error'] = str(slack_error)


@app.route('/api/analyze', methods=['POST'])
def analyze_pr():
    """
    Main API endpoint to submit a PR for analysis.
    
    Request Body (Simple):
    {
        "repository": "owner/repo",
        "pr_number": 123,
        "agent_type": "security",  // optional: static_analysis, security, code_quality, context
        "author_email": "user@example.com"  // optional: override author email for tracking
    }
    
    The system will automatically fetch PR details from GitHub.
    If author_email is provided, it will be used for tracking the PR.
    Otherwise, the system will try to get email from GitHub or git commits.
    
    The system will:
    - Always analyze the PR
    - Always save comments to database
    - Update existing comments if they already exist in database
    - Never post comments to GitHub (comments stored locally only)
    """
    try:
        data = request.json
        
        # Validate request
        repository, pr_number, error_response, error_code = _validate_analyze_request(data)
        if error_response:
            return error_response, error_code
        
        agent_type = data.get('agent_type')
        
        logger.info(
            "Received PR analysis request",
            repository=repository,
            pr_number=pr_number,
            requested_agent=agent_type
        )
        
        # Fetch PR details and create PR event
        logger.info("Fetching PR details from GitHub...")
        pr_data_tuple, error_response, error_code = _fetch_pr_event(repository, pr_number)
        if error_response:
            return error_response, error_code
        
        pr_event, pr_details = pr_data_tuple
        
        # Dispatch to agent (always analyze)
        result = dispatcher.dispatch(pr_event, agent_type)
        
        # Build response
        response_data = _build_response_data(pr_event, result)
        
        # Persist to database
        persistence_result = _persist_analysis(pr_event, pr_details, result, data, response_data)
        
        # Always track comments in database (update if exists, insert if new)
        if pr_comment_agent:
            _handle_pr_comments_tracking(pr_event, result, pr_details, persistence_result, 
                                       response_data, repository, pr_number)
        
        # Send Slack Notifications
        _handle_slack_notifications(pr_event, result, repository, pr_number, response_data)
        
        return jsonify(response_data), 200
        
    except ValueError as e:
        logger.error("Validation error", error=str(e))
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error("Analysis error", error=str(e), exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/webhook/github', methods=['POST'])
def github_webhook():
    """
    GitHub webhook endpoint for PR events (optional).
    
    Receives PR events and triggers single-agent analysis.
    """
    try:
        # Verify webhook signature
        signature = request.headers.get('X-Hub-Signature-256', '')
        if not github_service.verify_webhook_signature(request.data, signature):
            logger.warning("Invalid webhook signature")
            return jsonify({'error': 'Invalid signature'}), 401
        
        payload = request.json
        
        # Check if it's a PR event we care about
        if 'pull_request' not in payload:
            return jsonify({'message': 'Not a PR event'}), 200
        
        action = payload.get('action')
        if action not in ['opened', 'synchronize', 'reopened']:
            return jsonify({'message': f'Ignoring action: {action}'}), 200
        
        # Parse PR event
        pr_event = PREvent.from_webhook(payload)
        
        logger.info(
            "Received PR webhook",
            action=action,
            pr_number=pr_event.pr_number,
            repository=pr_event.repository
        )
        
        # Skip draft PRs if configured
        if pr_event.is_draft:
            logger.info("Skipping draft PR", pr_number=pr_event.pr_number)
            return jsonify({'message': 'Draft PR skipped'}), 200
        
        # Get PR files
        pr_event.files = github_service.get_pr_files(
            pr_event.repository,
            pr_event.pr_number
        )
        
        # Dispatch to single agent (strategy determines which one)
        result = dispatcher.dispatch(pr_event)
        
        # Send feedback
        send_feedback(pr_event, result)
        
        return jsonify({
            'message': 'Analysis completed',
            'pr_number': pr_event.pr_number,
            'agent_used': result.agent_name
        }), 200
        
    except Exception as e:
        logger.error("Webhook processing error", error=str(e), exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


def create_pr_event_from_request(data: dict) -> PREvent:
    """
    Create a PREvent object from API request data.
    
    Args:
        data: Request data dictionary
        
    Returns:
        PREvent object
    """
    from datetime import datetime
    from models.pr_event import PRAuthor
    
    return PREvent(
        action=data.get('action', 'opened'),
        pr_number=data['pr_number'],
        pr_title=data.get('pr_title', f"PR #{data['pr_number']}"),
        pr_description=data.get('pr_description'),
        pr_url=data.get('pr_url', f"https://github.com/{data['repository']}/pull/{data['pr_number']}"),
        repository=data['repository'],
        repository_url=data.get('repository_url', f"https://github.com/{data['repository']}"),
        author=PRAuthor(
            login=data.get('author', 'unknown'),
            id=data.get('author_id', 0),
            avatar_url=data.get('author_avatar', '')
        ),
        base_branch=data.get('base_branch', 'main'),
        head_branch=data.get('head_branch', 'feature'),
        files=[],  # Will be populated from GitHub API
        created_at=datetime.now(),
        updated_at=datetime.now(),
        is_draft=data.get('is_draft', False)
    )


def send_feedback(pr_event: PREvent, result):
    """
    Send feedback to configured outputs.
    
    Args:
        pr_event: The PR event
        result: Agent analysis result (single agent)
    """
    # Format feedback for single agent result
    feedback_text = format_single_agent_feedback(result)
    
    # GitHub PR Comments
    if config.get('output.github.enabled'):
        github_service.post_comment(
            pr_event.repository,
            pr_event.pr_number,
            feedback_text
        )
        
        # Create review if configured
        if config.get('output.github.create_review'):
            if result.critical_count > 0:
                github_service.request_changes(
                    pr_event.repository,
                    pr_event.pr_number,
                    "Critical issues found. Please review."
                )
    
    # Slack Notifications
    if config.get(CONFIG_OUTPUT_SLACK_ENABLED):
        slack_message = format_slack_message(pr_event, result)
        slack_service.send_pr_notification(slack_message)
        
        # Send critical alert if needed
        if result.critical_count > 0 and config.get('output.slack.mention_on_critical'):
            slack_service.send_critical_alert(
                pr_event.repository,
                pr_event.pr_number,
                pr_event.pr_url,
                result.critical_count
            )
    
    # Dashboard
    if config.get('output.dashboard.enabled'):
        dashboard_payload = {
            'pr_number': pr_event.pr_number,
            'repository': pr_event.repository,
            'pr_url': pr_event.pr_url,
            'pr_title': pr_event.pr_title,
            'agent_used': result.agent_name,
            'execution_time': result.execution_time,
            'issues_found': result.total_issues,
            'critical_count': result.critical_count,
            'high_count': result.high_count,
            'metrics': result.metrics
        }
        dashboard_service.submit_analysis(dashboard_payload)


def format_single_agent_feedback(result) -> str:
    """Format feedback for a single agent result."""
    lines = []
    lines.append(f"## 🤖 PR Analysis by {result.agent_name}\n")
    
    # Summary
    lines.append("### 📊 Summary")
    lines.append(f"- **Total Issues**: {result.total_issues}")
    lines.append(f"- 🔴 Critical: {result.critical_count}")
    lines.append(f"- 🟠 High: {result.high_count}")
    lines.append(f"- ⏱️ Analysis Time: {result.execution_time:.2f}s\n")
    
    if result.critical_count > 0:
        lines.append("⚠️ **Critical issues found - please address before merging.**\n")
    
    # Issues
    if result.issues:
        lines.append(f"### Issues Found ({len(result.issues)})\n")
        
        for i, issue in enumerate(result.issues[:10], 1):
            severity_emoji = {
                'critical': '🔴',
                'high': '🟠',
                'medium': '🟡',
                'low': '🟢',
                'info': 'ℹ️'
            }.get(issue.severity.value, '•')
            
            location = f"{issue.file}:{issue.line}" if issue.line else issue.file
            lines.append(f"{i}. {severity_emoji} **{location}**")
            lines.append(f"   {issue.message}")
            if issue.suggestion:
                lines.append(f"   💡 *Suggestion: {issue.suggestion}*")
            lines.append("")
        
        if len(result.issues) > 10:
            lines.append(f"*...and {len(result.issues) - 10} more issues*\n")
    
    # Metrics
    if result.metrics:
        lines.append("### 📈 Metrics")
        for key, value in result.metrics.items():
            lines.append(f"- **{key}**: {value}")
    
    return "\n".join(lines)


def format_slack_message(pr_event: PREvent, result) -> dict:
    """Format Slack message for single agent result."""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🤖 PR Analysis Complete"
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Repository:*\n{pr_event.repository}"},
                {"type": "mrkdwn", "text": f"*PR:*\n#{pr_event.pr_number}"}
            ]
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Agent:*\n{result.agent_name}"},
                {"type": "mrkdwn", "text": f"*Issues:*\n{result.total_issues}"}
            ]
        }
    ]
    
    if result.critical_count > 0:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"⚠️ *{result.critical_count} critical issue(s) found*"
            }
        })
    
    return {
        'blocks': blocks,
        'pr_url': pr_event.pr_url
    }


# ============================================================================
# DASHBOARD API ENDPOINTS
# ============================================================================

@app.route('/api/dashboard/user/<author_login>/insights', methods=['GET'])
def get_user_insights(author_login: str):
    """
    Get comprehensive insights for a user.
    
    Returns best practices, bad practices, quality scores, improvement areas,
    and personalized recommendations.
    """
    if not analytics_service:
        return jsonify({'error': 'Analytics service not available'}), 503
    
    try:
        insights = analytics_service.get_user_insights(author_login)
        return jsonify(insights), 200
    except Exception as e:
        logger.error("Failed to get user insights", error=str(e), author=author_login)
        return jsonify({'error': 'Failed to generate insights'}), 500


@app.route('/api/dashboard/user/<author_identifier>/statistics', methods=['GET'])
def get_user_statistics(author_identifier: str):
    """
    Get user statistics summary.
    Accepts either author_login (username) or email address.
    """
    if not db_service:
        return jsonify({'error': ERROR_DB_SERVICE_UNAVAILABLE}), 503
    
    try:
        # Check if author_identifier is an email (contains @)
        if '@' in author_identifier:
            # It's an email - use the dedicated email method
            user_stats = db_service.get_user_statistics_by_email(author_identifier)
            if not user_stats:
                return jsonify({'error': f'No user found with email: {author_identifier}'}), 404
        else:
            # It's a username
            user_stats = db_service.get_user_statistics(author_identifier)
            if not user_stats:
                return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'author_login': user_stats.author_login,
            'author_email': user_stats.author_email,
            'total_prs': user_stats.total_prs,
            'total_issues': user_stats.total_issues_found,
            'avg_quality_score': user_stats.avg_quality_score,
            'avg_security_score': user_stats.avg_security_score,
            'avg_maintainability_score': user_stats.avg_maintainability_score,
            'avg_coverage': user_stats.avg_coverage,
            'severity_distribution': {
                'critical': user_stats.critical_issues_total,
                'high': user_stats.high_issues_total,
                'medium': user_stats.medium_issues_total,
                'low': user_stats.low_issues_total
            },
            'trends': {
                'quality': user_stats.quality_trend,
                'security': user_stats.security_trend,
                'coverage': user_stats.coverage_trend,
                'rag_risk': user_stats.rag_risk_trend,
                'rag_novelty': user_stats.rag_novelty_trend
            },
            # RAG Metrics
            'rag_metrics': {
                'total_insights': user_stats.total_rag_insights,
                'avg_risk_score': user_stats.avg_rag_risk_score,
                'avg_novelty_score': user_stats.avg_rag_novelty_score,
                'total_similar_prs_referenced': user_stats.total_similar_prs_referenced,
                'total_recommendations': user_stats.total_rag_recommendations,
                'total_patterns_identified': user_stats.total_patterns_identified,
                'high_risk_prs_count': user_stats.high_risk_prs_count,
                'novel_prs_count': user_stats.novel_prs_count,
                'most_common_patterns': user_stats.most_common_patterns,
                'learning_velocity': user_stats.learning_velocity
            },
            'common_issues': user_stats.common_issues,
            'improvement_areas': user_stats.improvement_areas,
            'strengths': user_stats.strengths,
            'first_pr_date': user_stats.first_pr_date.isoformat() if user_stats.first_pr_date else None,
            'last_pr_date': user_stats.last_pr_date.isoformat() if user_stats.last_pr_date else None
        }), 200
    except Exception as e:
        logger.error("Failed to get user statistics", error=str(e), author=author_identifier)
        return jsonify({'error': 'Failed to retrieve statistics'}), 500


@app.route('/api/dashboard/user/<author_login>/prs', methods=['GET'])
def get_user_prs(author_login: str):
    """Get recent PRs for a user."""
    if not db_service:
        return jsonify({'error': ERROR_DB_SERVICE_UNAVAILABLE}), 503
    
    try:
        limit = request.args.get('limit', 20, type=int)
        prs = db_service.get_user_prs(author_login, limit=limit)
        
        return jsonify({
            'author_login': author_login,
            'total': len(prs),
            'prs': [
                {
                    'id': pr.id,
                    'repository': pr.repository,
                    'pr_number': pr.pr_number,
                    'pr_title': pr.pr_title,
                    'pr_url': pr.pr_url,
                    'total_issues': pr.total_issues,
                    'quality_score': pr.overall_quality_score,
                    'security_score': pr.security_score,
                    'analyzed_at': pr.analyzed_at.isoformat(),
                    'severity_counts': {
                        'critical': pr.critical_issues,
                        'high': pr.high_issues,
                        'medium': pr.medium_issues,
                        'low': pr.low_issues
                    }
                }
                for pr in prs
            ]
        }), 200
    except Exception as e:
        logger.error("Failed to get user PRs", error=str(e), author=author_login)
        return jsonify({'error': 'Failed to retrieve PRs'}), 500


@app.route('/api/dashboard/repository/<path:repository>/stats', methods=['GET'])
def get_repository_stats(repository: str):
    """Get aggregated statistics for a repository."""
    if not db_service:
        return jsonify({'error': ERROR_DB_SERVICE_UNAVAILABLE}), 503
    
    try:
        stats = db_service.get_repository_stats(repository)
        
        if not stats:
            return jsonify({'error': 'No data found for repository'}), 404
        
        return jsonify(stats), 200
    except Exception as e:
        logger.error("Failed to get repository stats", error=str(e), repository=repository)
        return jsonify({'error': 'Failed to retrieve statistics'}), 500


@app.route('/api/dashboard/repository/<path:repository>/insights', methods=['GET'])
def get_repository_insights(repository: str):
    """Get comprehensive insights for a repository."""
    if not analytics_service:
        return jsonify({'error': 'Analytics service not available'}), 503
    
    try:
        insights = analytics_service.get_repository_insights(repository)
        return jsonify(insights), 200
    except Exception as e:
        logger.error("Failed to get repository insights", error=str(e), repository=repository)
        return jsonify({'error': 'Failed to generate insights'}), 500


@app.route('/api/dashboard/pr/<path:repository>/<int:pr_number>', methods=['GET'])
def get_pr_analysis(repository: str, pr_number: int):
    """Get detailed analysis for a specific PR."""
    if not db_service:
        return jsonify({'error': ERROR_DB_SERVICE_UNAVAILABLE}), 503
    
    try:
        with db_service.get_session() as session:
            pr_analysis = session.query(PRAnalysis).filter_by(
                repository=repository,
                pr_number=pr_number
            ).order_by(desc(PRAnalysis.analyzed_at)).first()
            
            if not pr_analysis:
                return jsonify({'error': 'PR analysis not found'}), 404
            
            result = _build_pr_analysis_response(pr_analysis)
            return jsonify(result), 200
    except Exception as e:
        logger.error("Failed to get PR analysis", error=str(e), repository=repository, pr_number=pr_number)
        return jsonify({'error': 'Failed to retrieve analysis'}), 500


def _build_pr_analysis_response(pr_analysis: PRAnalysis) -> dict:
    """Build PR analysis response dictionary."""
    result = {
        'id': pr_analysis.id,
        'repository': pr_analysis.repository,
        'pr_number': pr_analysis.pr_number,
        'pr_title': pr_analysis.pr_title,
        'pr_url': pr_analysis.pr_url,
        'author_login': pr_analysis.author_login,
        'author_email': pr_analysis.author_email,
        'total_issues': pr_analysis.total_issues,
        'severity_distribution': _get_severity_distribution(pr_analysis),
        'agent_breakdown': _get_agent_breakdown(pr_analysis),
        'scores': _get_scores(pr_analysis),
        'coverage_metrics': _get_coverage_metrics(pr_analysis),
        'analyzed_at': pr_analysis.analyzed_at.isoformat(),
        'analysis_duration_ms': pr_analysis.analysis_duration_ms
    }
    
    # Add RAG insights if available
    result['rag_insights'] = _get_rag_insights_for_response(pr_analysis)
    
    return result


def _get_severity_distribution(pr_analysis: PRAnalysis) -> dict:
    """Extract severity distribution from PR analysis."""
    return {
        'critical': pr_analysis.critical_issues,
        'high': pr_analysis.high_issues,
        'medium': pr_analysis.medium_issues,
        'low': pr_analysis.low_issues
    }


def _get_agent_breakdown(pr_analysis: PRAnalysis) -> dict:
    """Extract agent breakdown from PR analysis."""
    return {
        'static_analysis': pr_analysis.static_analysis_issues,
        'security': pr_analysis.security_issues,
        'code_quality': pr_analysis.code_quality_issues,
        'context': pr_analysis.context_issues,
        'coverage': pr_analysis.coverage_issues
    }


def _get_scores(pr_analysis: PRAnalysis) -> dict:
    """Extract quality scores from PR analysis."""
    return {
        'overall_quality': pr_analysis.overall_quality_score,
        'security': pr_analysis.security_score,
        'maintainability': pr_analysis.maintainability_score
    }


def _get_coverage_metrics(pr_analysis: PRAnalysis) -> dict:
    """Extract coverage metrics from PR analysis."""
    return {
        'estimated_coverage': pr_analysis.estimated_coverage,
        'test_to_code_ratio': pr_analysis.test_to_code_ratio,
        'complexity_score': pr_analysis.complexity_score
    }


def _get_rag_insights_for_response(pr_analysis: PRAnalysis) -> Optional[dict]:
    """Get RAG insights formatted for API response."""
    if not pr_analysis.has_rag_insights and not pr_analysis.rag_insights:
        return None
    
    rag_insights_data = pr_analysis.rag_insights or {}
    summary = _generate_summary_from_rag_data(rag_insights_data)
    
    return {
        'has_insights': pr_analysis.has_rag_insights or bool(pr_analysis.rag_insights),
        'risk_score': pr_analysis.rag_risk_score,
        'novelty_score': pr_analysis.rag_novelty_score,
        'summary': summary,
        'insights': rag_insights_data
    }


def _generate_summary_from_rag_data(rag_insights_data: dict) -> str:
    """Generate summary from RAG insights full_text if not present."""
    summary = rag_insights_data.get('summary')
    if not summary and 'full_text' in rag_insights_data:
        full_text = rag_insights_data['full_text']
        if full_text:
            summary = _extract_summary_from_text(full_text)
    return summary


def _extract_summary_from_text(full_text: str) -> str:
    """Extract summary from full text by finding first substantial line."""
    lines = full_text.split('\n')
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#') and len(line) > 20:
            return line
    return full_text[:200].strip() + '...' if full_text else ''


@app.route('/api/dashboard/init-db', methods=['POST'])
def initialize_database():
    """Initialize database tables (admin endpoint)."""
    if not db_service:
        return jsonify({'error': ERROR_DB_SERVICE_UNAVAILABLE}), 503
    
    try:
        db_service.create_tables()
        return jsonify({
            'status': 'success',
            'message': 'Database tables created successfully'
        }), 200
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        return jsonify({'error': 'Failed to create database tables'}), 500


# ============================================================================
# ANALYTICS PROCESSING AGENT ENDPOINTS
# ============================================================================

@app.route('/api/analytics/user/<author_login>/analyze', methods=['GET'])
def analyze_user_over_time(author_login: str):
    """
    Analyze user's performance over a time range using Analytics Processing Agent.
    
    Query Parameters:
        - start_date: ISO format date (YYYY-MM-DD) - optional
        - end_date: ISO format date (YYYY-MM-DD) - optional
        - days: Number of days to look back (alternative to start_date) - optional
        - min_prs: Minimum PRs required (default: 5)
    
    Returns comprehensive analysis with:
    - Quality metrics and code scores
    - Best practices identified
    - Bad practices to avoid
    - Improvement recommendations
    - Trend analysis
    """
    if not analytics_processing_agent:
        return jsonify({'error': ERROR_ANALYTICS_AGENT_UNAVAILABLE}), 503
    
    try:
        # Parse query parameters
        start_date = None
        end_date = None
        
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        days = request.args.get('days', type=int)
        min_prs = request.args.get('min_prs', 5, type=int)
        
        # Parse dates
        if start_date_str:
            start_date = datetime.fromisoformat(start_date_str)
        elif days:
            start_date = datetime.now() - timedelta(days=days)
        
        if end_date_str:
            end_date = datetime.fromisoformat(end_date_str)
        else:
            end_date = datetime.now()
        
        # Run analysis
        analysis = analytics_processing_agent.analyze_user_over_time(
            author_login=author_login,
            start_date=start_date,
            end_date=end_date,
            min_prs=min_prs
        )
        
        return jsonify(analysis), 200
        
    except ValueError as e:
        return jsonify({'error': f'Invalid date format: {str(e)}'}), 400
    except Exception as e:
        logger.error("Failed to analyze user over time", error=str(e), author=author_login)
        return jsonify({'error': 'Failed to generate analysis'}), 500


def _determine_quality_level(quality_score):
    """Determine quality level and description from score."""
    if quality_score >= 90:
        return "excellent", "outstanding"
    elif quality_score >= 80:
        return "very good", "strong"
    elif quality_score >= 70:
        return "good", "solid"
    elif quality_score >= 60:
        return "fair", "moderate"
    else:
        return "needs improvement", "developing"


def _determine_security_description(security_score):
    """Determine security description from score."""
    if security_score >= 95:
        return "exemplary security practices"
    elif security_score >= 85:
        return "strong security standards"
    elif security_score >= 75:
        return "good security awareness"
    else:
        return "some security concerns"


def _get_trend_text(quality_trend):
    """Get trend description text."""
    # Handle if quality_trend is a dict or other type
    if isinstance(quality_trend, dict):
        quality_trend = quality_trend.get('direction', 'stable')
    quality_trend_str = str(quality_trend) if quality_trend else 'stable'
    
    if 'improv' in quality_trend_str.lower() or 'up' in quality_trend_str.lower():
        return " Your code quality is showing positive improvement over time."
    elif 'declin' in quality_trend_str.lower() or 'down' in quality_trend_str.lower():
        return " Recent PRs show a declining quality trend that needs attention."
    else:
        return " Your code quality is maintaining a consistent level."


def _build_summary_text(days, total_prs, quality_level, quality_desc, quality_score, 
                        security_desc, security_score, avg_issues, trend_text, 
                        best_practices, bad_practices):
    """Build narrative summary text from analysis data."""
    summary_text = f"""Over the past {days} days, you have contributed {total_prs} pull requests with {quality_level} overall quality (average score: {quality_score:.1f}/100). Your contributions demonstrate {quality_desc} coding practices with {security_desc} (security score: {security_score:.1f}/100).

On average, your PRs contain {avg_issues:.1f} issues that are identified during code review.{trend_text}"""
    
    # Add best practices note
    if best_practices and len(best_practices) > 0:
        bp_names = ', '.join([bp if isinstance(bp, str) else bp.get('title', bp.get('category', 'N/A')) for bp in best_practices[:3]])
        summary_text += f"\n\nYour strongest areas include: {bp_names}."
    
    # Add improvement areas
    if bad_practices and len(bad_practices) > 0:
        bad_names = ', '.join([bp if isinstance(bp, str) else bp.get('title', bp.get('category', 'N/A')) for bp in bad_practices[:3]])
        summary_text += f"\n\nAreas for improvement: {bad_names}."
    
    return summary_text


@app.route('/api/analytics/user/summary', methods=['POST'])
def get_user_analytics_summary():
    """
    Get quick analytics summary for user (last 30 days by default).
    
    Request Body:
        - email: User email (required)
        - days: Number of days to analyze (optional, default: 30)
    """
    if not analytics_processing_agent:
        return jsonify({'error': ERROR_ANALYTICS_AGENT_UNAVAILABLE}), 503
    
    try:
        data = request.get_json()
        if not data or not data.get('email'):
            return jsonify({'error': ERROR_EMAIL_REQUIRED}), 400
        
        email = data.get('email')
        days = data.get('days', 30)
        
        # Get author_login from email
        with db_service.get_session() as session:
            from models.database import PRAnalysis
            pr = session.query(PRAnalysis).filter_by(author_email=email).first()
            if not pr:
                return jsonify({
                    'success': False,
                    'error': f'No PRs found for email: {email}',
                    'prs_analyzed': 0
                }), 200
            author_login = pr.author_login
        
        start_date = datetime.now() - timedelta(days=days)
        
        analysis = analytics_processing_agent.analyze_user_over_time(
            author_login=author_login,
            start_date=start_date,
            end_date=datetime.now(),
            min_prs=1  # Lower threshold for summary
        )
        
        if not analysis.get('success'):
            return jsonify(analysis), 200
        
        # Extract metrics
        quality_score = analysis['code_scores'].get('overall_quality', {}).get('average', 0)
        security_score = analysis['code_scores'].get('security', {}).get('average', 0)
        total_prs = analysis['analysis_period']['total_prs']
        avg_issues = analysis['quality_metrics']['avg_issues_per_pr']
        
        # Determine quality and security levels
        quality_level, quality_desc = _determine_quality_level(quality_score)
        security_desc = _determine_security_description(security_score)
        
        # Get trend text
        quality_trend = analysis.get('trend_analysis', {}).get('quality', 'stable')
        trend_text = _get_trend_text(quality_trend)
        
        # Build summary text
        summary_text = _build_summary_text(
            days, total_prs, quality_level, quality_desc, quality_score,
            security_desc, security_score, avg_issues, trend_text,
            analysis['best_practices'], analysis['bad_practices']
        )
        
        # Return condensed summary with narrative text
        summary = {
            'author_login': author_login,
            'author_email': email,
            'period_days': days,
            'total_prs': analysis['analysis_period']['total_prs'],
            'code_scores': analysis['code_scores'],
            'quality_metrics': {
                'avg_issues_per_pr': analysis['quality_metrics']['avg_issues_per_pr'],
                'severity_distribution': analysis['quality_metrics']['severity_distribution']
            },
            'top_best_practices': analysis['best_practices'][:3],
            'top_bad_practices': analysis['bad_practices'][:3],
            'trends': analysis.get('trend_analysis', {}),
            'summary_text': summary_text
        }
        
        return jsonify(summary), 200
        
    except Exception as e:
        logger.error("Failed to get analytics summary", error=str(e), email=email)
        return jsonify({'error': 'Failed to generate summary'}), 500


@app.route('/api/analytics/user/recommendations', methods=['POST'])
def get_user_recommendations():
    """
    Get personalized improvement recommendations for user.
    
    Request Body:
        - email: User email (required)
        - days: Number of days to analyze (optional, default: 90)
        - priority: Filter by priority (optional: critical, high, medium, low)
    """
    if not analytics_processing_agent:
        return jsonify({'error': ERROR_ANALYTICS_AGENT_UNAVAILABLE}), 503
    
    try:
        data = request.get_json()
        if not data or not data.get('email'):
            return jsonify({'error': ERROR_EMAIL_REQUIRED}), 400
        
        email = data.get('email')
        days = data.get('days', 90)
        priority_filter = data.get('priority')
        
        # Get author_login from email
        with db_service.get_session() as session:
            from models.database import PRAnalysis
            pr = session.query(PRAnalysis).filter_by(author_email=email).first()
            if not pr:
                return jsonify({
                    'success': False,
                    'error': f'No PRs found for email: {email}',
                    'prs_analyzed': 0
                }), 200
            author_login = pr.author_login
        
        start_date = datetime.now() - timedelta(days=days)
        
        analysis = analytics_processing_agent.analyze_user_over_time(
            author_login=author_login,
            start_date=start_date,
            end_date=datetime.now(),
            min_prs=5
        )
        
        if not analysis.get('success'):
            return jsonify(analysis), 200
        
        recommendations = analysis.get('improvement_recommendations', [])
        
        # Filter by priority if specified
        if priority_filter:
            recommendations = [r for r in recommendations if r.get('priority') == priority_filter]
        
        return jsonify({
            'author_login': author_login,
            'author_email': email,
            'analysis_period_days': days,
            'total_recommendations': len(recommendations),
            'recommendations': recommendations
        }), 200
        
    except Exception as e:
        logger.error("Failed to get recommendations", error=str(e), email=email)
        return jsonify({'error': 'Failed to generate recommendations'}), 500


@app.route('/api/analytics/user/trends', methods=['POST'])
def get_user_trends():
    """
    Get quality trends for user over time.
    
    Request Body:
        - email: User email (required)
        - days: Number of days to analyze (optional, default: 180)
    """
    if not analytics_processing_agent:
        return jsonify({'error': ERROR_ANALYTICS_AGENT_UNAVAILABLE}), 503
    
    try:
        data = request.get_json()
        if not data or not data.get('email'):
            return jsonify({'error': ERROR_EMAIL_REQUIRED}), 400
        
        email = data.get('email')
        days = data.get('days', 180)
        
        # Get author_login from email
        with db_service.get_session() as session:
            from models.database import PRAnalysis
            pr = session.query(PRAnalysis).filter_by(author_email=email).first()
            if not pr:
                return jsonify({
                    'success': False,
                    'error': f'No PRs found for email: {email}',
                    'prs_analyzed': 0
                }), 200
            author_login = pr.author_login
        
        start_date = datetime.now() - timedelta(days=days)
        
        analysis = analytics_processing_agent.analyze_user_over_time(
            author_login=author_login,
            start_date=start_date,
            end_date=datetime.now(),
            min_prs=10  # Need more data for trends
        )
        
        if not analysis.get('success'):
            return jsonify(analysis), 200
        
        return jsonify({
            'author_login': author_login,
            'author_email': email,
            'analysis_period_days': days,
            'trend_analysis': analysis.get('trend_analysis', {}),
            'code_scores': analysis.get('code_scores', {})
        }), 200
        
    except Exception as e:
        logger.error("Failed to get trends", error=str(e), email=email)
        return jsonify({'error': 'Failed to generate trends'}), 500


@app.route('/api/prs/list', methods=['POST'])
def get_prs_by_email():
    """
    Get list of PRs for a user by email and date range.
    
    Request Body:
    {
        "email": "user@example.com",
        "start_date": "2024-01-01",  // optional, format: YYYY-MM-DD
        "end_date": "2024-12-31",    // optional, format: YYYY-MM-DD
        "limit": 100                 // optional, default: 100
    }
    
    Response:
    {
        "success": true,
        "email": "user@example.com",
        "total_prs": 28,
        "prs": [
            {
                "pr_number": 123,
                "pr_title": "Add new feature",
                "pr_url": "https://github.com/...",
                "repository": "owner/repo",
                "author_login": "username",
                "analyzed_at": "2024-12-20T10:30:00Z",
                "overall_quality_score": 85.5,
                "security_score": 100.0,
                "total_issues": 10,
                "critical_issues": 0,
                "files_changed": 5,
                "lines_added": 150,
                "lines_deleted": 20
            },
            ...
        ]
    }
    """
    if not db_service:
        return jsonify({'error': ERROR_DB_SERVICE_UNAVAILABLE}), 503
    
    try:
        data = request.json
        
        if not data or 'email' not in data:
            return jsonify({'error': ERROR_EMAIL_REQUIRED}), 400
        
        email = data.get('email')
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        limit = data.get('limit', 100)
        
        # Parse dates if provided
        start_date = None
        end_date = None
        
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            except ValueError:
                return jsonify({'error': 'Invalid start_date format. Use YYYY-MM-DD'}), 400
        
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            except ValueError:
                return jsonify({'error': 'Invalid end_date format. Use YYYY-MM-DD'}), 400
        
        # Get PRs from database
        with db_service.get_session() as session:
            from models.database import PRAnalysis
            
            query = session.query(PRAnalysis).filter_by(author_email=email)
            
            if start_date:
                query = query.filter(PRAnalysis.analyzed_at >= start_date)
            if end_date:
                query = query.filter(PRAnalysis.analyzed_at <= end_date)
            
            prs = query.order_by(PRAnalysis.analyzed_at.desc()).limit(limit).all()
            
            # Format response
            pr_list = []
            for pr in prs:
                pr_list.append({
                    'pr_number': pr.pr_number,
                    'pr_title': pr.pr_title,
                    'pr_url': pr.pr_url,
                    'repository': pr.repository,
                    'author_login': pr.author_login,
                    'author_name': pr.author_name,
                    'analyzed_at': pr.analyzed_at.isoformat() if pr.analyzed_at else None,
                    'overall_quality_score': pr.overall_quality_score,
                    'security_score': pr.security_score,
                    'maintainability_score': pr.maintainability_score,
                    'total_issues': pr.total_issues,
                    'critical_issues': pr.critical_issues,
                    'high_issues': pr.high_issues,
                    'medium_issues': pr.medium_issues,
                    'low_issues': pr.low_issues,
                    'files_changed': pr.files_changed,
                    'lines_added': pr.lines_added,
                    'lines_deleted': pr.lines_deleted,
                    'estimated_coverage': pr.estimated_coverage,
                    # RAG Metrics
                    'has_rag_insights': pr.has_rag_insights,
                    'rag_risk_score': pr.rag_risk_score,
                    'rag_novelty_score': pr.rag_novelty_score,
                    'rag_similar_prs_count': pr.rag_similar_prs_count,
                    'rag_recommendations_count': pr.rag_recommendations_count
                })
            
            return jsonify({
                'success': True,
                'email': email,
                'total_prs': len(pr_list),
                'date_range': {
                    'start': start_date_str,
                    'end': end_date_str
                },
                'prs': pr_list
            }), 200
        
    except Exception as e:
        logger.error("Failed to fetch PRs by email", error=str(e), email=email)
        return jsonify({'error': 'Failed to fetch PRs'}), 500


def _fetch_rag_table_data(session, pr_id):
    """Fetch RAG insights from database tables."""
    rag_result = session.execute(
        text("""
            SELECT id, risk_score, novelty_score, complexity_assessment, 
                   summary, recommendations, lessons_learned, 
                   potential_pitfalls, best_practices_suggested,
                   context_used, similar_prs_found, similar_prs_referenced,
                   full_text
            FROM rag_insights 
            WHERE pr_analysis_id = :pr_id
        """),
        {'pr_id': pr_id}
    ).fetchone()
    return rag_result


def _fetch_similar_prs(session, rag_insight_id):
    """Fetch similar PR references."""
    return session.execute(
        text("""
            SELECT referenced_pr_analysis_id, similarity_score, 
                   similarity_type, lesson_extracted, pattern_identified
            FROM rag_similar_pr_references 
            WHERE rag_insight_id = :insight_id
        """),
        {'insight_id': rag_insight_id}
    ).fetchall()


def _fetch_rag_recommendations(session, rag_insight_id):
    """Fetch RAG recommendations."""
    return session.execute(
        text("""
            SELECT recommendation_type, priority, title, 
                   description, reasoning
            FROM rag_recommendations 
            WHERE rag_insight_id = :insight_id
        """),
        {'insight_id': rag_insight_id}
    ).fetchall()


def _build_rag_insights_data(session, pr, rag_result, similar_prs_result, recommendations_result, rag_json):
    """Build RAG insights data structure from table and JSON data."""
    from models.database import PRAnalysis
    
    return {
        'risk_score': rag_result[1] or pr.rag_risk_score,
        'novelty_score': rag_result[2] or pr.rag_novelty_score,
        'complexity_assessment': rag_result[3],
        'full_text': rag_result[12] or rag_json.get('full_text', ''),
        'summary': rag_result[4] or rag_json.get('summary', ''),
        'recommendations': rag_result[5] or rag_json.get('recommendations', ''),
        'lessons_learned': rag_result[6] or rag_json.get('lessons_learned', ''),
        'potential_pitfalls': rag_result[7] or rag_json.get('potential_pitfalls', ''),
        'best_practices_suggested': rag_result[8] or rag_json.get('best_practices', ''),
        'context_used': rag_result[9] if rag_result[9] is not None else rag_json.get('context_used', False),
        'similar_prs_found': rag_result[10] or rag_json.get('similar_prs_found', 0),
        'similar_prs_referenced': rag_result[11] or rag_json.get('similar_prs_referenced', 0),
        'generated_at': rag_json.get('generated_at'),
        'similar_prs': [
            {
                'pr_number': session.query(PRAnalysis).get(ref[0]).pr_number if ref[0] and session.query(PRAnalysis).get(ref[0]) else None,
                'similarity_score': ref[1],
                'similarity_type': ref[2],
                'lesson_extracted': ref[3],
                'pattern_identified': ref[4]
            } for ref in similar_prs_result
        ],
        'detailed_recommendations': [
            {
                'type': rec[0],
                'priority': rec[1],
                'title': rec[2],
                'description': rec[3],
                'reasoning': rec[4]
            } for rec in recommendations_result
        ]
    }


def _get_rag_insights(session, pr):
    """Get RAG insights for a PR from database and JSON field."""
    # Check if RAG insights exist (either flag is True OR JSON data exists)
    if not pr.has_rag_insights and not pr.rag_insights:
        return None
    
    try:
        rag_json = pr.rag_insights or {}
        rag_result = _fetch_rag_table_data(session, pr.id)
        
        if rag_result:
            return _build_rag_from_table_data(session, pr, rag_result, rag_json)
        else:
            return _build_rag_from_json_data(pr, rag_json)
            
    except Exception as e:
        logger.error(f"Error fetching RAG insights: {e}")
        return _build_rag_fallback_data(pr)


def _build_rag_from_table_data(session, pr, rag_result, rag_json):
    """Build RAG insights from database table data."""
    rag_insight_id = rag_result[0]
    similar_prs_result = _fetch_similar_prs(session, rag_insight_id)
    recommendations_result = _fetch_rag_recommendations(session, rag_insight_id)
    
    return _build_rag_insights_data(
        session, pr, rag_result, similar_prs_result, 
        recommendations_result, rag_json
    )


def _build_rag_from_json_data(pr, rag_json):
    """Build RAG insights from JSON field."""
    rag_insights_data = rag_json.copy()
    rag_insights_data['risk_score'] = pr.rag_risk_score
    rag_insights_data['novelty_score'] = pr.rag_novelty_score
    
    # Generate summary from full_text if needed
    _add_summary_to_rag_data(rag_insights_data)
    
    return rag_insights_data


def _build_rag_fallback_data(pr):
    """Build RAG insights from fallback data when error occurs."""
    if not pr.rag_insights:
        return None
    
    rag_insights_data = pr.rag_insights.copy()
    rag_insights_data['risk_score'] = pr.rag_risk_score
    rag_insights_data['novelty_score'] = pr.rag_novelty_score
    
    # Generate summary from full_text if needed
    _add_summary_to_rag_data(rag_insights_data)
    
    return rag_insights_data


def _add_summary_to_rag_data(rag_insights_data):
    """Add summary to RAG data if not present or empty."""
    if 'full_text' in rag_insights_data and not rag_insights_data.get('summary'):
        full_text = rag_insights_data['full_text']
        if full_text:
            summary = _extract_summary_from_full_text(full_text)
            rag_insights_data['summary'] = summary


def _extract_summary_from_full_text(full_text):
    """Extract summary from full text by finding first substantial line."""
    lines = full_text.split('\n')
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#') and len(line) > 20:
            return line
    return full_text[:200].strip() + '...' if full_text else ''


@app.route('/api/prs/details', methods=['POST'])
def get_pr_details():
    """
    Get detailed information for a specific PR.
    
    Request Body:
    {
        "pr_number": 123,
        "repository": "owner/repo"  // optional, but recommended
    }
    
    Response:
    {
        "success": true,
        "pr": {
            "pr_number": 123,
            "pr_title": "Add new feature",
            "pr_description": "...",
            "pr_url": "https://github.com/...",
            "repository": "owner/repo",
            "author_login": "username",
            "author_email": "user@example.com",
            "author_name": "User Name",
            "base_branch": "main",
            "head_branch": "feature-branch",
            "analyzed_at": "2024-12-20T10:30:00Z",
            "overall_quality_score": 85.5,
            "security_score": 100.0,
            "maintainability_score": 90.0,
            "total_issues": 10,
            "issues_by_severity": {
                "critical": 0,
                "high": 2,
                "medium": 5,
                "low": 3
            },
            "issues_by_agent": {
                "static_analysis": 3,
                "security": 0,
                "code_quality": 5,
                "context": 1,
                "coverage": 1
            },
            "code_metrics": {
                "files_changed": 5,
                "lines_added": 150,
                "lines_deleted": 20,
                "complexity_score": 15.5,
                "estimated_coverage": 75.0,
                "test_to_code_ratio": 0.8
            }
        },
        "issues": [
            {
                "issue_type": "MAGIC_NUMBER",
                "severity": "medium",
                "file_path": "src/main.py",
                "line_number": 42,
                "message": "Avoid using magic numbers...",
                "suggestion": "Use named constants..."
            },
            ...
        ]
    }
    """
    if not db_service:
        return jsonify({'error': ERROR_DB_SERVICE_UNAVAILABLE}), 503
    
    try:
        data = request.json
        
        if not data or 'pr_number' not in data:
            return jsonify({'error': 'pr_number is required in request body'}), 400
        
        pr_number = data.get('pr_number')
        repository = data.get('repository')
        
        # Get PR from database
        with db_service.get_session() as session:
            from models.database import PRAnalysis, PRIssue
            
            query = session.query(PRAnalysis).filter_by(pr_number=pr_number)
            
            if repository:
                query = query.filter_by(repository=repository)
            
            pr = query.first()
            
            if not pr:
                return jsonify({
                    'error': 'PR not found',
                    'pr_number': pr_number,
                    'repository': repository
                }), 404
            
            # Get issues for this PR
            issues = session.query(PRIssue).filter_by(pr_analysis_id=pr.id).all()
            
            # Get RAG insights if available
            rag_insights_data = _get_rag_insights(session, pr)
            
            # Format PR details
            pr_details = {
                'pr_number': pr.pr_number,
                'pr_title': pr.pr_title,
                'pr_description': pr.pr_description,
                'pr_url': pr.pr_url,
                'repository': pr.repository,
                'author_login': pr.author_login,
                'author_email': pr.author_email,
                'author_name': pr.author_name,
                'base_branch': pr.base_branch,
                'head_branch': pr.head_branch,
                'analyzed_at': pr.analyzed_at.isoformat() if pr.analyzed_at else None,
                'pr_created_at': pr.pr_created_at,
                'pr_updated_at': pr.pr_updated_at,
                'overall_quality_score': pr.overall_quality_score,
                'security_score': pr.security_score,
                'maintainability_score': pr.maintainability_score,
                'total_issues': pr.total_issues,
                'issues_by_severity': {
                    'critical': pr.critical_issues,
                    'high': pr.high_issues,
                    'medium': pr.medium_issues,
                    'low': pr.low_issues
                },
                'issues_by_agent': {
                    'static_analysis': pr.static_analysis_issues,
                    'security': pr.security_issues,
                    'code_quality': pr.code_quality_issues,
                    'context': pr.context_issues,
                    'coverage': pr.coverage_issues
                },
                'code_metrics': {
                    'files_changed': pr.files_changed,
                    'lines_added': pr.lines_added,
                    'lines_deleted': pr.lines_deleted,
                    'complexity_score': pr.complexity_score,
                    'estimated_coverage': pr.estimated_coverage,
                    'test_to_code_ratio': pr.test_to_code_ratio
                },
                # RAG Insights
                'rag_insights': rag_insights_data
            }
            
            # Format issues
            issue_list = []
            for issue in issues:
                issue_list.append({
                    'issue_type': issue.issue_type,
                    'severity': issue.severity,
                    'category': issue.category,
                    'file_path': issue.file_path,
                    'line_number': issue.line_number,
                    'title': issue.title,
                    'description': issue.description,
                    'recommendation': issue.recommendation,
                    'agent_name': issue.agent_name
                })
            
            return jsonify({
                'success': True,
                'pr': pr_details,
                'issues': issue_list,
                'total_issues': len(issue_list)
            }), 200
        
    except Exception as e:
        logger.error("Failed to fetch PR details", error=str(e), pr_number=pr_number)
        return jsonify({'error': 'Failed to fetch PR details'}), 500


def _extract_code_context(file_content: dict, line_number: int, context_lines: int = 3) -> Optional[dict]:
    """
    Extract code context around a specific line from file content.
    
    Args:
        file_content: File content dictionary with 'lines' array
        line_number: Target line number
        context_lines: Number of lines to include before and after
        
    Returns:
        Code context dictionary or None
    """
    if not file_content or 'lines' not in file_content:
        return None
    
    lines = file_content['lines']
    total_lines = len(lines)
    
    # Calculate line range
    start_line = max(1, line_number - context_lines)
    end_line = min(total_lines, line_number + context_lines)
    
    # Extract lines
    code_lines = []
    for i in range(start_line - 1, end_line):
        if i < len(lines):
            code_lines.append({
                'line_number': i + 1,
                'content': lines[i],
                'is_target': (i + 1) == line_number
            })
    
    return {
        'file_path': file_content.get('file_path'),
        'target_line': line_number,
        'start_line': start_line,
        'end_line': end_line,
        'lines': code_lines,
        'total_lines': total_lines
    }


def _find_pr_by_number(session, pr_number: int, repository: Optional[str]):
    """Find PR analysis by PR number and optionally repository."""
    from models.database import PRAnalysis
    
    query = session.query(PRAnalysis).filter_by(pr_number=pr_number)
    
    if repository:
        query = query.filter_by(repository=repository)
    
    return query.first()


def _get_pr_comments_from_db(session, pr_analysis_id: int):
    """Get all comments for a PR analysis from database."""
    from models.database import PRComment
    
    return session.query(PRComment).filter_by(
        pr_analysis_id=pr_analysis_id
    ).order_by(PRComment.file_path, PRComment.line_number).all()


def _format_comment_basic_info(comment) -> dict:
    """Format basic comment information."""
    return {
        'id': comment.id,
        'comment_type': comment.comment_type,
        'file_path': comment.file_path,
        'line_number': comment.line_number,
        'commit_sha': comment.commit_sha,
        'comment_body': comment.comment_body,
        'comment_preview': comment.comment_preview,
        'issue_severity': comment.issue_severity,
        'issue_type': comment.issue_type,
        'posted_successfully': comment.posted_successfully,
        'review_event': comment.review_event,
        'github_url': comment.github_url,
        'reactions_count': comment.reactions_count,
        'replies_count': comment.replies_count,
        'was_edited': comment.was_edited,
        'was_resolved': comment.was_resolved,
        'resolved_at': comment.resolved_at.isoformat() if comment.resolved_at else None,
        'posted_at': comment.posted_at.isoformat() if comment.posted_at else None,
        'github_comment_id': comment.github_comment_id,
        'github_review_id': comment.github_review_id
    }


def _add_code_context_if_requested(comment_dict: dict, comment, pr_repository: str, 
                                    include_code: bool, file_cache: dict):
    """Add code context to comment if requested and available."""
    if not (include_code and github_service and comment.file_path and 
            comment.line_number and comment.commit_sha):
        return
    
    # Create cache key for this file at this commit
    cache_key = f"{comment.commit_sha}:{comment.file_path}"
    
    # Get file content from cache or fetch it
    if cache_key not in file_cache:
        file_cache[cache_key] = github_service.get_file_content_at_commit(
            repository=pr_repository,
            file_path=comment.file_path,
            commit_sha=comment.commit_sha
        )
    
    # Extract lines around the comment line from cached content
    file_content = file_cache[cache_key]
    if file_content:
        code_context = _extract_code_context(
            file_content, 
            comment.line_number, 
            context_lines=3
        )
        if code_context:
            comment_dict['code_context'] = code_context


@app.route('/api/prs/comments', methods=['POST'])
def get_pr_comments():
    """
    Get comments for a specific PR with code context.
    
    Request Body:
    {
        "pr_number": 123,
        "repository": "owner/repo"  // optional
    }
    
    Response:
    {
        "success": true,
        "pr_number": 123,
        "repository": "owner/repo",
        "total_comments": 15,
        "comments": [
            {
                "id": 1,
                "comment_type": "inline",
                "file_path": "src/main.py",
                "line_number": 45,
                "comment_body": "Consider using a more descriptive variable name",
                "issue_severity": "medium",
                "issue_type": "code_quality",
                "posted_at": "2024-12-20T10:30:00Z",
                "github_url": "https://github.com/...",
                "reactions_count": 2,
                "replies_count": 1,
                "was_resolved": false,
                "code_context": {
                    "target_line": 45,
                    "start_line": 42,
                    "end_line": 48,
                    "lines": [
                        {"line_number": 42, "content": "def process():", "is_target": false},
                        {"line_number": 43, "content": "    x = 10", "is_target": false},
                        {"line_number": 44, "content": "    y = 20", "is_target": false},
                        {"line_number": 45, "content": "    z = x + y", "is_target": true},
                        ...
                    ]
                }
            },
            ...
        ]
    }
    """
    if not db_service:
        return jsonify({'error': ERROR_DB_SERVICE_UNAVAILABLE}), 503
    
    try:
        data = request.json
        
        if not data or 'pr_number' not in data:
            return jsonify({'error': 'pr_number is required in request body'}), 400
        
        pr_number = data.get('pr_number')
        repository = data.get('repository')
        include_code = data.get('include_code', False)
        
        # Get PR and its comments from database
        with db_service.get_session() as session:
            pr = _find_pr_by_number(session, pr_number, repository)
            
            if not pr:
                return jsonify({
                    'error': 'PR not found',
                    'pr_number': pr_number,
                    'repository': repository
                }), 404
            
            # Get comments for this PR
            comments = _get_pr_comments_from_db(session, pr.id)
            
            # Format comments with optional code context
            comments_list = []
            file_cache = {}  # Cache for file contents to avoid redundant GitHub API calls
            
            for comment in comments:
                comment_dict = _format_comment_basic_info(comment)
                _add_code_context_if_requested(comment_dict, comment, pr.repository, 
                                               include_code, file_cache)
                comments_list.append(comment_dict)
            
            return jsonify({
                'success': True,
                'pr_number': pr.pr_number,
                'repository': pr.repository,
                'total_comments': len(comments_list),
                'comments': comments_list
            }), 200
            
    except Exception as e:
        logger.error("Failed to fetch PR comments", error=str(e), pr_number=pr_number)
        return jsonify({'error': 'Failed to fetch PR comments'}), 500


@app.route('/api/slack/notify', methods=['POST'])
def send_slack_notification():
    """
    Send a custom Slack notification.
    
    Request Body:
    {
        "type": "pr_reviewed" | "comment_posted",
        "repository": "owner/repo",
        "pr_number": 123,
        "pr_url": "https://github.com/...",
        "pr_title": "Fix bug",
        "issues_found": 5,
        "critical_count": 0,
        "comment": {  // Optional, for comment_posted type
            "file_path": "src/main.py",
            "line_number": 45,
            "severity": "medium",
            "message": "Comment text..."
        }
    }
    
    Response:
    {
        "success": true,
        "message": "Notification sent to Slack"
    }
    """
    try:
        data = request.json
        
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        notification_type = data.get('type', 'pr_reviewed')
        repository = data.get('repository')
        pr_number = data.get('pr_number')
        pr_url = data.get('pr_url')
        
        if not all([repository, pr_number, pr_url]):
            return jsonify({'error': 'Missing required fields: repository, pr_number, pr_url'}), 400
        
        # Check if Slack is enabled
        if not config.get(CONFIG_OUTPUT_SLACK_ENABLED):
            return jsonify({'error': 'Slack notifications are disabled'}), 400
        
        success = False
        
        if notification_type == 'pr_reviewed':
            # PR Review notification
            pr_title = data.get('pr_title', f'PR #{pr_number}')
            issues_found = data.get('issues_found', 0)
            critical_count = data.get('critical_count', 0)
            
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "✅ PR Review Complete"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Repository:*\n{repository}"},
                        {"type": "mrkdwn", "text": f"*PR:*\n#{pr_number}"}
                    ]
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Title:*\n{pr_title}"},
                        {"type": "mrkdwn", "text": f"*Issues Found:*\n{issues_found}"}
                    ]
                }
            ]
            
            if critical_count > 0:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⚠️ *{critical_count} critical issue(s) found!*"
                    }
                })
            
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View PR"},
                        "url": pr_url,
                        "style": "primary" if critical_count == 0 else "danger"
                    }
                ]
            })
            
            success = slack_service.send_message(
                text=f"✅ PR Review Complete: {repository} #{pr_number}",
                blocks=blocks
            )
        
        elif notification_type == 'comment_posted':
            # Comment notification
            comment = data.get('comment', {})
            file_path = comment.get('file_path', 'Unknown file')
            line_number = comment.get('line_number', 0)
            severity = comment.get('severity', 'info')
            message = comment.get('message', 'No message')
            
            severity_emoji = {
                'critical': '🔴',
                'high': '🟠',
                'medium': '🟡',
                'low': '🔵',
                'info': 'ℹ️'
            }.get(severity.lower(), 'ℹ️')
            
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "💬 New Review Comment"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Repository:*\n{repository}"},
                        {"type": "mrkdwn", "text": f"*PR:*\n#{pr_number}"}
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*File:* `{file_path}` (Line {line_number})\n*Severity:* {severity_emoji} {severity.title()}\n\n_{message}_"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View Comment"},
                            "url": pr_url
                        }
                    ]
                }
            ]
            
            success = slack_service.send_message(
                text=f"💬 New Comment on PR #{pr_number}",
                blocks=blocks
            )
        
        else:
            return jsonify({'error': f'Invalid notification type: {notification_type}'}), 400
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Notification sent to Slack'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send notification to Slack'
            }), 500
    
    except Exception as e:
        logger.error("Failed to send Slack notification", error=str(e))
        return jsonify({'error': 'Failed to send Slack notification'}), 500


@app.route('/api/analytics/user', methods=['POST'])
def get_user_analytics():
    """
    Get analytics for a user by email and date range.
    
    Request Body:
    {
        "email": "user@example.com",
        "start_date": "2024-01-01",  // optional, format: YYYY-MM-DD
        "end_date": "2024-12-31"     // optional, format: YYYY-MM-DD
    }
    
    Response:
    {
        "success": true,
        "email": "user@example.com",
        "author_login": "username",
        "author_name": "User Name",
        "analysis_period": {
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "total_prs": 28
        },
        "quality_metrics": {
            "total_prs": 28,
            "total_issues": 587,
            "avg_issues_per_pr": 20.96,
            "severity_distribution": {
                "critical": 74,
                "high": 18,
                "medium": 423,
                "low": 72
            }
        },
        "code_scores": {
            "overall_quality": {
                "average": 82.2,
                "min": 0.0,
                "max": 100.0,
                "rating": "Good"
            },
            "security": {
                "average": 100.0,
                "min": 100.0,
                "max": 100.0,
                "rating": "Excellent"
            },
            "maintainability": {
                "average": 70.8,
                "min": 10.0,
                "max": 100.0,
                "rating": "Fair"
            }
        },
        "best_practices": [
            {
                "category": "Security",
                "title": "Excellent Security Awareness",
                "description": "You consistently avoid security vulnerabilities",
                "score": 100.0
            }
        ],
        "bad_practices": [
            {
                "category": "Quality",
                "title": "Magic Number",
                "occurrences": 458,
                "severity": "medium"
            }
        ],
        "improvement_recommendations": [
            {
                "area": "Overall Code Quality",
                "priority": "medium",
                "current_score": 82.2,
                "target_score": 85,
                "actions": ["Review and refactor...", ...]
            }
        ]
    }
    """
    if not analytics_processing_agent:
        return jsonify({'error': ERROR_ANALYTICS_AGENT_UNAVAILABLE}), 503
    
    try:
        data = request.json
        
        if not data or 'email' not in data:
            return jsonify({'error': ERROR_EMAIL_REQUIRED}), 400
        
        email = data.get('email')
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        
        # Parse dates if provided
        start_date = None
        end_date = None
        
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            except ValueError:
                return jsonify({'error': 'Invalid start_date format. Use YYYY-MM-DD'}), 400
        
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            except ValueError:
                return jsonify({'error': 'Invalid end_date format. Use YYYY-MM-DD'}), 400
        
        # Get author_login from email
        with db_service.get_session() as session:
            from models.database import PRAnalysis
            
            pr = session.query(PRAnalysis).filter_by(author_email=email).first()
            
            if not pr:
                return jsonify({
                    'error': 'No PRs found for this email',
                    'email': email
                }), 404
            
            author_login = pr.author_login
            author_name = pr.author_name
        
        # Generate analytics
        analysis = analytics_processing_agent.analyze_user_over_time(
            author_login=author_login,
            start_date=start_date,
            end_date=end_date,
            min_prs=1
        )
        
        if not analysis.get('success'):
            return jsonify(analysis), 200
        
        # Add email and name to response
        analysis['email'] = email
        analysis['author_name'] = author_name
        
        return jsonify(analysis), 200
        
    except Exception as e:
        logger.error("Failed to get user analytics", error=str(e), email=email)
        return jsonify({'error': 'Failed to generate analytics'}), 500


@app.route('/api/auto-merge/evaluate', methods=['POST'])
def evaluate_auto_merge():
    """
    Evaluate if a PR should be auto-merged based on configured conditions.
    
    Request Body:
    {
        "repository": "owner/repo",
        "pr_number": 123
    }
    
    Returns:
    {
        "success": true,
        "should_merge": true/false,
        "reason": "Explanation of the decision",
        "evaluation": {
            "checks_passed": [...],
            "checks_failed": [...]
        },
        "pr_details": {...}
    }
    """
    try:
        data = request.json
        
        if not data:
            return jsonify({'error': ERROR_REQUEST_BODY_REQUIRED}), 400
        
        repository = data.get('repository')
        pr_number = data.get('pr_number')
        
        if not repository or not pr_number:
            return jsonify({'error': ERROR_MISSING_REPO_PR}), 400
        
        logger.info(
            "Evaluating PR for auto-merge",
            repository=repository,
            pr_number=pr_number
        )
        
        # Get PR analysis from database
        if not db_service:
            return jsonify({'error': ERROR_DB_SERVICE_UNAVAILABLE}), 503
        
        with db_service.get_session() as session:
            pr_analysis_record = session.query(db_service.PRAnalysis).filter_by(
                repository=repository,
                pr_number=pr_number
            ).first()
            
            if not pr_analysis_record:
                return jsonify({
                    'error': f'No analysis found for PR #{pr_number} in {repository}'
                }), 404
            
            # Convert to dict
            pr_analysis = {
                'scores': {
                    'overall_quality_score': pr_analysis_record.overall_quality_score,
                    'security_score': pr_analysis_record.security_score,
                    'maintainability_score': pr_analysis_record.maintainability_score
                },
                'metrics': {
                    'files_changed': pr_analysis_record.files_changed,
                    'lines_added': pr_analysis_record.lines_added,
                    'lines_deleted': pr_analysis_record.lines_deleted
                },
                'issues': []
            }
            
            # Get all issues for this PR
            issues = session.query(db_service.PRIssue).filter_by(
                pr_analysis_id=pr_analysis_record.id
            ).all()
            
            for issue in issues:
                pr_analysis['issues'].append({
                    'severity': issue.severity,
                    'description': issue.description,
                    'title': issue.title,
                    'category': issue.category
                })
        
        # Get PR details from GitHub
        pr_details = github_service.get_pr_details(repository, pr_number)
        if not pr_details:
            return jsonify({'error': 'Failed to fetch PR details from GitHub'}), 500
        
        # Add repository info for auto-merge agent
        pr_details['repository'] = {'full_name': repository}
        pr_details['number'] = pr_number
        
        # Get reviews from GitHub
        reviews = github_service.get_pr_reviews(repository, pr_number)
        
        # Get status checks from GitHub
        status_checks = github_service.check_pr_status_checks(repository, pr_number)
        
        # Evaluate with auto-merge agent
        should_merge, reason, evaluation = auto_merge_agent.should_auto_merge(
            pr_analysis=pr_analysis,
            pr_details=pr_details,
            reviews=reviews,
            status_checks=status_checks
        )
        
        response = {
            'success': True,
            'should_merge': should_merge,
            'reason': reason,
            'evaluation': evaluation,
            'pr_details': {
                'repository': repository,
                'pr_number': pr_number,
                'title': pr_details.get('title'),
                'author': pr_details.get('user', {}).get('login'),
                'state': pr_details.get('state')
            },
            'analysis_summary': {
                'quality_score': pr_analysis['scores']['overall_quality_score'],
                'security_score': pr_analysis['scores']['security_score'],
                'total_issues': len(pr_analysis['issues']),
                'reviews_count': len(reviews),
                'approvals': sum(1 for r in reviews if r.get('state') == 'APPROVED')
            }
        }
        
        logger.info(
            "Auto-merge evaluation complete",
            repository=repository,
            pr_number=pr_number,
            should_merge=should_merge
        )
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error("Failed to evaluate auto-merge", error=str(e))
        return jsonify({'error': 'Failed to evaluate auto-merge'}), 500


@app.route('/api/auto-merge/execute', methods=['POST'])
def execute_auto_merge():
    """
    Execute auto-merge for a PR if it passes all conditions.
    
    Request Body:
    {
        "repository": "owner/repo",
        "pr_number": 123,
        "force": false  // Optional: skip condition checks if true (use with caution!)
    }
    
    Returns:
    {
        "success": true,
        "merged": true/false,
        "message": "Merge result message",
        "merge_sha": "abc123...",
        "evaluation": {...}  // Only if force=false
    }
    """
    try:
        data = request.json
        
        if not data:
            return jsonify({'error': ERROR_REQUEST_BODY_REQUIRED}), 400
        
        repository = data.get('repository')
        pr_number = data.get('pr_number')
        force = data.get('force', False)
        
        if not repository or not pr_number:
            return jsonify({'error': ERROR_MISSING_REPO_PR}), 400
        
        logger.info(
            "Executing auto-merge",
            repository=repository,
            pr_number=pr_number,
            force=force
        )
        
        # If not forcing, evaluate conditions first
        evaluation = None
        if not force:
            evaluation_result = _evaluate_pr_for_merge(repository, pr_number)
            if evaluation_result:
                return evaluation_result  # Return error response
            evaluation = evaluation_result
        
        # Execute the merge
        merge_response = _execute_pr_merge(repository, pr_number, evaluation)
        return merge_response
        
    except Exception as e:
        logger.error("Failed to execute auto-merge", error=str(e))
        return jsonify({'error': 'Failed to execute auto-merge'}), 500


def _evaluate_pr_for_merge(repository: str, pr_number: int):
    """Evaluate if PR meets auto-merge conditions. Returns error response if it doesn't."""
    if not db_service:
        return jsonify({'error': ERROR_DB_SERVICE_UNAVAILABLE}), 503
    
    # Get PR analysis from database
    pr_analysis = _get_pr_analysis_data(repository, pr_number)
    if isinstance(pr_analysis, tuple):  # Error response
        return pr_analysis
    
    # Get PR details from GitHub
    pr_details = github_service.get_pr_details(repository, pr_number)
    if not pr_details:
        return jsonify({'error': 'Failed to fetch PR details from GitHub'}), 500
    
    pr_details['repository'] = {'full_name': repository}
    pr_details['number'] = pr_number
    
    # Get reviews and status checks
    reviews = github_service.get_pr_reviews(repository, pr_number)
    status_checks = github_service.check_pr_status_checks(repository, pr_number)
    
    # Evaluate
    should_merge, reason, evaluation = auto_merge_agent.should_auto_merge(
        pr_analysis=pr_analysis,
        pr_details=pr_details,
        reviews=reviews,
        status_checks=status_checks
    )
    
    if not should_merge:
        logger.warning(
            "PR does not meet auto-merge conditions",
            repository=repository,
            pr_number=pr_number,
            reason=reason
        )
        return jsonify({
            'success': False,
            'merged': False,
            'message': f'PR does not meet auto-merge conditions: {reason}',
            'evaluation': evaluation
        }), 400
    
    return evaluation


def _get_pr_analysis_data(repository: str, pr_number: int):
    """Get PR analysis data from database. Returns error tuple if not found."""
    with db_service.get_session() as session:
        pr_analysis_record = session.query(db_service.PRAnalysis).filter_by(
            repository=repository,
            pr_number=pr_number
        ).first()
        
        if not pr_analysis_record:
            return jsonify({
                'error': f'No analysis found for PR #{pr_number} in {repository}'
            }), 404
        
        # Convert to dict
        pr_analysis = {
            'scores': {
                'overall_quality_score': pr_analysis_record.overall_quality_score,
                'security_score': pr_analysis_record.security_score,
                'maintainability_score': pr_analysis_record.maintainability_score
            },
            'metrics': {
                'files_changed': pr_analysis_record.files_changed,
                'lines_added': pr_analysis_record.lines_added,
                'lines_deleted': pr_analysis_record.lines_deleted
            },
            'issues': []
        }
        
        # Get all issues for this PR
        issues = session.query(db_service.PRIssue).filter_by(
            pr_analysis_id=pr_analysis_record.id
        ).all()
        
        for issue in issues:
            pr_analysis['issues'].append({
                'severity': issue.severity,
                'description': issue.description,
                'title': issue.title,
                'category': issue.category
            })
        
        return pr_analysis


def _execute_pr_merge(repository: str, pr_number: int, evaluation):
    """Execute the actual PR merge."""
    # Get merge configuration
    merge_config = auto_merge_agent.get_merge_config()
    
    # Execute merge
    merge_result = github_service.merge_pr(
        repository=repository,
        pr_number=pr_number,
        merge_method=merge_config['merge_method'],
        commit_title=f"Auto-merge PR #{pr_number}",
        commit_message="This PR was automatically merged after passing all quality checks.",
        delete_branch=merge_config['delete_branch']
    )
    
    # Post comment if configured
    if merge_result['merged'] and merge_config['post_merge_comment']:
        _post_merge_success_comment(repository, pr_number, merge_result, merge_config)
    
    response = {
        'success': merge_result['success'],
        'merged': merge_result['merged'],
        'message': merge_result['message'],
        'merge_sha': merge_result.get('sha'),
        'merge_method': merge_config['merge_method']
    }
    
    if evaluation:
        response['evaluation'] = evaluation
    
    logger.info(
        "Auto-merge execution complete",
        repository=repository,
        pr_number=pr_number,
        merged=merge_result['merged']
    )
    
    return jsonify(response), 200


def _post_merge_success_comment(repository: str, pr_number: int, merge_result: dict, merge_config: dict):
    """Post a success comment after auto-merge."""
    comment = f"""✅ **Auto-Merge Successful**

This PR was automatically merged after passing all configured checks:
- Quality Score: Pass ✓
- Security Score: Pass ✓
- Issue Count: Within limits ✓
- Required Approvals: Met ✓

Merge SHA: `{merge_result.get('sha', 'N/A')}`
Merge Method: {merge_config['merge_method']}
"""
    github_service.post_comment(repository, pr_number, comment)


@app.route('/api/auto-merge/config', methods=['GET'])
def get_auto_merge_config():
    """
    Get current auto-merge configuration.
    
    Returns:
    {
        "enabled": true/false,
        "mode": "conditional",
        "conditions": {...},
        "merge_settings": {...}
    }
    """
    try:
        config_data = config.get('auto_merge', {})
        
        response = {
            'enabled': config_data.get('enabled', False),
            'mode': config_data.get('mode', 'conditional'),
            'conditions': config_data.get('conditions', {}),
            'merge_settings': {
                'merge_method': config_data.get('merge_method', 'squash'),
                'delete_branch': config_data.get('delete_branch', True),
                'post_merge_comment': config_data.get('post_merge_comment', True)
            },
            'allowed_repositories': config_data.get('allowed_repositories', []),
            'allowed_users': config_data.get('allowed_users', [])
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error("Failed to get auto-merge config", error=str(e))
        return jsonify({'error': 'Failed to get auto-merge configuration'}), 500


if __name__ == '__main__':
    port = config.flask_port
    logger.info(f"Starting PR Review System on port {port}")
    logger.info("Main Orchestrator Agent initialized with all sub-agents")
    
    if db_persistence_agent:
        logger.info("Database Persistence Agent ready")
    if analytics_processing_agent:
        logger.info("Analytics Processing Agent ready")
    if auto_merge_agent.enabled:
        logger.info(f"Auto-Merge Agent ready (mode: {auto_merge_agent.mode})")
    
    # Initialize database tables if needed
    if db_service:
        try:
            db_service.create_tables()
            logger.info("Database tables initialized")
        except Exception as e:
            logger.warning("Database tables may already exist", error=str(e))
    
    app.run(host='0.0.0.0', port=port, debug=config.get('application.environment') == 'development')
