"""
Centralized constants for the PR Analysis System.

This module contains all constant values used across the application
including agent names, API configurations, file paths, and thresholds.
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# ============================================================================
# AGENT NAMES
# ============================================================================
AGENT_MAIN = 'Main Orchestrator Agent'
AGENT_STATIC_ANALYSIS = 'Multi-Language Static Analysis Agent'
AGENT_SECURITY = 'Multi-Language Security Agent'
AGENT_CODE_QUALITY = 'Multi-Language Code Quality Agent'
AGENT_CONTEXT = 'Context Agent'
AGENT_COVERAGE = 'Coverage & Metrics Agent'


# ============================================================================
# GITHUB API CONFIGURATION
# ============================================================================
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_BASE_URL = 'https://api.github.com'
GITHUB_API_HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

# Default repository (can be overridden)
DEFAULT_REPOSITORY = os.getenv('GITHUB_REPOSITORY', 'tarentomaheshvakkund/testdata-hackathon')

# Rate limiting
GITHUB_API_DELAY = float(os.getenv('GITHUB_API_DELAY', '0.5'))  # seconds between requests
GITHUB_RATE_LIMIT_THRESHOLD = int(os.getenv('GITHUB_RATE_LIMIT_THRESHOLD', '100'))


# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', '5433'))
DB_NAME = os.getenv('DB_NAME', 'pr_analysis')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

# Connection pool settings
DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', '10'))
DB_MAX_OVERFLOW = int(os.getenv('DB_MAX_OVERFLOW', '20'))


# ============================================================================
# FILE EXTENSIONS AND PATHS
# ============================================================================
JAVA_EXTENSIONS = ['.java']
PYTHON_EXTENSIONS = ['.py']
JAVASCRIPT_EXTENSIONS = ['.js', '.jsx', '.ts', '.tsx']
SUPPORTED_CODE_EXTENSIONS = JAVA_EXTENSIONS + PYTHON_EXTENSIONS + JAVASCRIPT_EXTENSIONS

# Test file indicators
TEST_PATH_PATTERNS = ['/test/', '/tests/', '__tests__', 'spec.', 'test.']
TEST_FILE_PATTERNS = ['test', 'spec', 'Test', 'Spec', 'TEST', 'SPEC']


# ============================================================================
# ANALYSIS THRESHOLDS
# ============================================================================
# Coverage thresholds
MIN_COVERAGE_THRESHOLD = float(os.getenv('MIN_COVERAGE_THRESHOLD', '80.0'))
WARN_COVERAGE_THRESHOLD = float(os.getenv('WARN_COVERAGE_THRESHOLD', '50.0'))

# Complexity thresholds
MAX_COMPLEXITY_THRESHOLD = int(os.getenv('MAX_COMPLEXITY_THRESHOLD', '15'))
WARN_COMPLEXITY_THRESHOLD = int(os.getenv('WARN_COMPLEXITY_THRESHOLD', '10'))

# Code quality thresholds
MAX_METHOD_LENGTH = int(os.getenv('MAX_METHOD_LENGTH', '50'))
MAX_NESTING_DEPTH = int(os.getenv('MAX_NESTING_DEPTH', '4'))
MAX_PARAMETERS = int(os.getenv('MAX_PARAMETERS', '5'))

# Security thresholds
MAX_CRITICAL_ISSUES = int(os.getenv('MAX_CRITICAL_ISSUES', '0'))
MAX_HIGH_ISSUES = int(os.getenv('MAX_HIGH_ISSUES', '5'))


# ============================================================================
# QUALITY SCORE WEIGHTS
# ============================================================================
WEIGHT_SECURITY = float(os.getenv('WEIGHT_SECURITY', '0.35'))
WEIGHT_QUALITY = float(os.getenv('WEIGHT_QUALITY', '0.25'))
WEIGHT_COVERAGE = float(os.getenv('WEIGHT_COVERAGE', '0.20'))
WEIGHT_COMPLEXITY = float(os.getenv('WEIGHT_COMPLEXITY', '0.20'))


# ============================================================================
# ISSUE TYPE MAPPINGS
# ============================================================================
ISSUE_TYPE_SECURITY = [
    'hardcoded_secret',
    'sql_injection',
    'command_injection',
    'weak_crypto',
    'path_traversal',
    'xxe',
    'deserialization'
]

ISSUE_TYPE_QUALITY = [
    'duplicate_code',
    'long_method',
    'deep_nesting',
    'magic_number',
    'todo_comment',
    'console_log',
    'system_out_println',
    'eval_used'
]

ISSUE_TYPE_COMPLEXITY = [
    'high_complexity',
    'deep_nesting',
    'long_method',
    'too_many_parameters'
]


# ============================================================================
# OUTPUT AND LOGGING
# ============================================================================
OUTPUT_DIR = os.getenv('OUTPUT_DIR', 'pr_data')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FORMAT = os.getenv('LOG_FORMAT', 'json')  # json or text


# ============================================================================
# BATCH PROCESSING
# ============================================================================
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '10'))
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '4'))
RETRY_ATTEMPTS = int(os.getenv('RETRY_ATTEMPTS', '3'))
RETRY_DELAY = float(os.getenv('RETRY_DELAY', '2.0'))


# ============================================================================
# PATTERN MATCHING (REGEX)
# ============================================================================
# Security patterns
PATTERN_HARDCODED_SECRET = (
    r'(?:password|passwd|pwd|secret|api[_-]?key|token)\s*=\s*["\'][^"\']+["\']'
)  # nosec B105
PATTERN_SQL_INJECTION = r'(?:execute|executeQuery|createQuery)\s*\([^)]*\+[^)]*\)'
PATTERN_COMMAND_INJECTION = (
    r'(?:Runtime\.getRuntime\(\)\.exec|ProcessBuilder|os\.system|subprocess\.)'
)

# Quality patterns
PATTERN_TODO_COMMENT = r'(?://|#|/\*)\s*(?:TODO|FIXME|XXX|HACK)'
PATTERN_CONSOLE_LOG = r'console\.log\s*\('
PATTERN_SYSTEM_OUT = r'System\.out\.print'
PATTERN_MAGIC_NUMBER = r'\b\d{2,}\b'

# Code style patterns
PATTERN_LONG_LINE = r'^.{121,}$'
PATTERN_TRAILING_WHITESPACE = r'\s+$'


# ============================================================================
# ERROR MESSAGES
# ============================================================================
ERROR_GITHUB_AUTH = "GitHub authentication failed. Check GITHUB_TOKEN."
ERROR_DATABASE_CONNECTION = "Database connection failed. Check database configuration."
ERROR_INVALID_PR = "Invalid PR number or PR not found."
ERROR_RATE_LIMIT = "GitHub API rate limit exceeded. Please wait and try again."
ERROR_ANALYSIS_FAILED = "Analysis failed for PR."


# ============================================================================
# SUCCESS MESSAGES
# ============================================================================
SUCCESS_PR_FETCHED = "PR fetched successfully"
SUCCESS_ANALYSIS_COMPLETE = "Analysis completed successfully"
SUCCESS_DATA_PERSISTED = "Data persisted to database"


# ============================================================================
# API ENDPOINTS (for Flask/FastAPI)
# ============================================================================
API_PREFIX = '/api/v1'
API_ENDPOINT_PR_ANALYSIS = f'{API_PREFIX}/pr/analysis'
API_ENDPOINT_USER_STATS = f'{API_PREFIX}/user/statistics'
API_ENDPOINT_REPOSITORY_STATS = f'{API_PREFIX}/repository/statistics'
API_ENDPOINT_EMAIL_SEARCH = f'{API_PREFIX}/pr/search-by-email'


# ============================================================================
# FEATURE FLAGS
# ============================================================================
ENABLE_STATIC_ANALYSIS = os.getenv('ENABLE_STATIC_ANALYSIS', 'true').lower() == 'true'
ENABLE_SECURITY_ANALYSIS = os.getenv('ENABLE_SECURITY_ANALYSIS', 'true').lower() == 'true'
ENABLE_QUALITY_ANALYSIS = os.getenv('ENABLE_QUALITY_ANALYSIS', 'true').lower() == 'true'
ENABLE_COVERAGE_ANALYSIS = os.getenv('ENABLE_COVERAGE_ANALYSIS', 'true').lower() == 'true'
ENABLE_CONTEXT_ANALYSIS = os.getenv('ENABLE_CONTEXT_ANALYSIS', 'true').lower() == 'true'

ENABLE_ANALYTICS = os.getenv('ENABLE_ANALYTICS', 'true').lower() == 'true'
ENABLE_BEST_PRACTICES = os.getenv('ENABLE_BEST_PRACTICES', 'true').lower() == 'true'


# ============================================================================
# VALIDATION
# ============================================================================
def validate_configuration():
    """Validate that all required configuration is present."""
    errors = []

    if not GITHUB_TOKEN:
        errors.append("GITHUB_TOKEN is not set in environment variables")

    if not DB_PASSWORD:
        errors.append("DB_PASSWORD is not set")

    weight_sum = WEIGHT_SECURITY + WEIGHT_QUALITY + WEIGHT_COVERAGE + WEIGHT_COMPLEXITY
    if abs(weight_sum - 1.0) > 0.0001:  # Use epsilon comparison for floating point
        errors.append(f"Quality score weights must sum to 1.0, got {weight_sum}")

    return errors


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
def get_db_connection_string() -> str:
    """Get formatted database connection string."""
    return f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


def is_test_file(filename: str) -> bool:
    """Check if a file is a test file based on path or name."""
    filename_lower = filename.lower()
    return any(pattern in filename_lower for pattern in TEST_PATH_PATTERNS + TEST_FILE_PATTERNS)


def is_code_file(filename: str) -> bool:
    """Check if a file is a supported code file."""
    return any(filename.endswith(ext) for ext in SUPPORTED_CODE_EXTENSIONS)


def get_agent_names() -> list:
    """Get list of all agent names."""
    return [
        AGENT_STATIC_ANALYSIS,
        AGENT_SECURITY,
        AGENT_CODE_QUALITY,
        AGENT_CONTEXT,
        AGENT_COVERAGE
    ]
