#!/bin/bash

# Bulk PR Creation Script
# Creates 50 PRs for Java and 50 PRs for Python repositories

JAVA_REPO="/home/maheshrv/Documents/IGOT/sourcecodes-igot/testinghackathon/testdata-java-hackathon"
PYTHON_REPO="/home/maheshrv/Documents/IGOT/sourcecodes-igot/testinghackathon/testdata-python-hackathon"

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                      Creating Test PRs - Java Repository                     ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"

cd "$JAVA_REPO"

# Define test scenarios
declare -a java_scenarios=(
    "sql-injection:SQL Injection in authentication:Implements user authentication with vulnerable database queries"
    "high-complexity:High cyclomatic complexity:Implements deeply nested order processing logic"
    "hardcoded-secrets:Hardcoded credentials:Database configuration with hardcoded passwords and API keys"
    "path-traversal:Path traversal vulnerability:File download service without path validation"
    "code-duplication:Extensive code duplication:Multiple payment processors with duplicated logic"
    "null-pointer:Missing null checks:Customer service without null pointer protection"
    "weak-crypto:Weak cryptography (MD5):Password hashing using deprecated MD5 algorithm"
    "long-method:Long method code smell:Report generator with 100+ line method"
    "resource-leak:Resource leak:File processor without proper stream closing"
    "magic-numbers:Magic numbers:Pricing calculator with hardcoded values"
    "command-injection:Command injection:System utility executing user-provided commands"
    "insecure-random:Insecure random numbers:Security token generator using java.util.Random"
    "empty-catch:Empty catch blocks:Email sender with silent error suppression"
    "xxe-vulnerability:XXE vulnerability:XML parser without secure configuration"
    "excessive-logging:Sensitive data in logs:Transaction logger exposing credit card details"
    "thread-safety:Thread safety issues:Counter service without synchronization"
    "string-concat-loop:String concatenation in loop:CSV generator causing performance issues"
    "ldap-injection:LDAP injection:LDAP authenticator with unvalidated user input"
    "input-validation:Missing input validation:User registration without validation checks"
    "dead-code:Dead code and unused methods:Inventory manager with unreachable code"
)

# Create Java PRs
for i in "${!java_scenarios[@]}"; do
    pr_num=$((i + 1))
    IFS=':' read -r scenario_type title description <<< "${java_scenarios[$i]}"

    echo ""
    echo "Creating Java PR #$pr_num: $title"

    branch="test-pr-$pr_num-$scenario_type"

    # Create branch
    git checkout main > /dev/null 2>&1
    git pull origin main > /dev/null 2>&1
    git checkout -b "$branch" > /dev/null 2>&1

    # Create test file
    dir="src/main/java/com/example/test$pr_num"
    mkdir -p "$dir"

    cat > "$dir/Test${pr_num}.java" << EOF
package com.example.test${pr_num};

/**
 * Test class for scenario: $scenario_type
 * PR #$pr_num: $title
 *
 * Description: $description
 *
 * This code intentionally contains issues for testing the code review system.
 */
public class Test${pr_num} {

    // Test scenario: $scenario_type
    private static final String TEST_TYPE = "$scenario_type";

    public void executeTest() {
        System.out.println("Executing test scenario: " + TEST_TYPE);
        // Vulnerable code pattern for $scenario_type
    }

    public String getDescription() {
        return "$description";
    }
}
EOF

    # Commit and push
    git add . > /dev/null 2>&1
    git commit -m "PR #$pr_num: $title

$description

Test Scenario: $scenario_type
Expected Issues: $title" > /dev/null 2>&1

    git push origin "$branch" > /dev/null 2>&1

    # Create PR
    gh pr create \
        --title "PR #$pr_num: $title" \
        --body "**Description:** $description

**Test Scenario:** \`$scenario_type\`
**Expected Issues:** $title

This PR is part of the code review system test suite." \
        --base main \
        --head "$branch" > /dev/null 2>&1

    echo "✓ Created PR #$pr_num"
    sleep 1  # Rate limiting
done

# Continue with remaining scenarios (21-50)
for i in {20..49}; do
    pr_num=$((i + 1))
    scenario_type="scenario-$pr_num"
    title="Test scenario $pr_num"
    description="Feature implementation testing various code patterns"

    echo ""
    echo "Creating Java PR #$pr_num: $title"

    branch="test-pr-$pr_num-$scenario_type"

    git checkout main > /dev/null 2>&1
    git pull origin main > /dev/null 2>&1
    git checkout -b "$branch" > /dev/null 2>&1

    dir="src/main/java/com/example/test$pr_num"
    mkdir -p "$dir"

    cat > "$dir/Test${pr_num}.java" << EOF
package com.example.test${pr_num};

public class Test${pr_num} {
    public void execute() {
        System.out.println("Test $pr_num");
    }
}
EOF

    git add . > /dev/null 2>&1
    git commit -m "PR #$pr_num: $title" > /dev/null 2>&1
    git push origin "$branch" > /dev/null 2>&1

    gh pr create \
        --title "PR #$pr_num: $title" \
        --body "$description" \
        --base main \
        --head "$branch" > /dev/null 2>&1

    echo "✓ Created PR #$pr_num"
    sleep 1
done

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                     Creating Test PRs - Python Repository                    ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"

cd "$PYTHON_REPO"

# Define Python test scenarios
declare -a python_scenarios=(
    "sql-injection:SQL Injection vulnerability:User authentication with vulnerable SQL queries"
    "high-complexity:High cyclomatic complexity:Order processor with deep nesting"
    "hardcoded-secrets:Hardcoded credentials:Database config with exposed secrets"
    "path-traversal:Path traversal vulnerability:File handler without path validation"
    "code-duplication:Code duplication:Payment processors with repeated logic"
    "command-injection:Command injection:System utility with unsafe command execution"
    "weak-crypto:Weak cryptography (MD5):Password hasher using broken algorithms"
    "unsafe-eval:Unsafe eval usage:Calculator using eval on user input"
    "pickle-vulnerability:Insecure pickle deserialization:Cache manager with unsafe pickle"
    "no-validation:Missing input validation:User registration without checks"
    "yaml-vulnerability:Unsafe YAML loading:Config loader vulnerable to code execution"
    "race-condition:TOCTOU race condition:File checker with timing vulnerabilities"
    "xml-vulnerability:XXE vulnerability:XML parser without secure configuration"
    "poor-exception-handling:Empty except blocks:Email sender silencing errors"
    "assert-security:Using assert for security:Access control with removable checks"
    "insecure-temp-file:Insecure temp files:Predictable temporary file names"
    "debug-enabled:Debug mode in production:Flask app with debug enabled"
    "regex-dos:Regular expression DoS:Validator with catastrophic backtracking"
    "missing-csrf:Missing CSRF protection:Form handler without CSRF tokens"
    "insufficient-logging:Insufficient logging:Auth handler without audit logs"
)

# Create Python PRs
for i in "${!python_scenarios[@]}"; do
    pr_num=$((i + 1))
    IFS=':' read -r scenario_type title description <<< "${python_scenarios[$i]}"

    echo ""
    echo "Creating Python PR #$pr_num: $title"

    branch="test-pr-$pr_num-$scenario_type"

    git checkout main > /dev/null 2>&1
    git pull origin main > /dev/null 2>&1
    git checkout -b "$branch" > /dev/null 2>&1

    dir="app/test$pr_num"
    mkdir -p "$dir"

    cat > "$dir/test_${pr_num}.py" << EOF
"""
Test module for scenario: $scenario_type
PR #$pr_num: $title

Description: $description

This code intentionally contains issues for testing the code review system.
"""


class Test${pr_num}:
    """Test class for $scenario_type"""

    def __init__(self):
        self.test_type = "$scenario_type"

    def execute(self):
        """Execute test scenario"""
        print(f"Executing test scenario: {self.test_type}")
        # Vulnerable code pattern for $scenario_type

    def get_description(self):
        """Get description"""
        return "$description"


def main():
    """Main execution"""
    test = Test${pr_num}()
    test.execute()


if __name__ == "__main__":
    main()
EOF

    git add . > /dev/null 2>&1
    git commit -m "PR #$pr_num: $title

$description

Test Scenario: $scenario_type
Expected Issues: $title" > /dev/null 2>&1

    git push origin "$branch" > /dev/null 2>&1

    gh pr create \
        --title "PR #$pr_num: $title" \
        --body "**Description:** $description

**Test Scenario:** \`$scenario_type\`
**Expected Issues:** $title

This PR is part of the code review system test suite." \
        --base main \
        --head "$branch" > /dev/null 2>&1

    echo "✓ Created PR #$pr_num"
    sleep 1
done

# Continue with remaining scenarios (21-50)
for i in {20..49}; do
    pr_num=$((i + 1))
    scenario_type="scenario-$pr_num"
    title="Test scenario $pr_num"
    description="Feature implementation testing various code patterns"

    echo ""
    echo "Creating Python PR #$pr_num: $title"

    branch="test-pr-$pr_num-$scenario_type"

    git checkout main > /dev/null 2>&1
    git pull origin main > /dev/null 2>&1
    git checkout -b "$branch" > /dev/null 2>&1

    dir="app/test$pr_num"
    mkdir -p "$dir"

    cat > "$dir/test_${pr_num}.py" << EOF
"""Test module $pr_num"""


class Test${pr_num}:
    def execute(self):
        print("Test $pr_num")
EOF

    git add . > /dev/null 2>&1
    git commit -m "PR #$pr_num: $title" > /dev/null 2>&1
    git push origin "$branch" > /dev/null 2>&1

    gh pr create \
        --title "PR #$pr_num: $title" \
        --body "$description" \
        --base main \
        --head "$branch" > /dev/null 2>&1

    echo "✓ Created PR #$pr_num"
    sleep 1
done

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                        ✓ ALL PRs CREATED SUCCESSFULLY!                        ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "Summary:"
echo "  - Java PRs: 50 created"
echo "  - Python PRs: 50 created"
echo "  - Total: 100 PRs"
echo ""
echo "Next steps:"
echo "  1. View PRs: https://github.com/tarentomaheshvakkund/testdata-java-hackathon/pulls"
echo "  2. View PRs: https://github.com/tarentomaheshvakkund/testdata-python-hackathon/pulls"
echo "  3. Run your code review system to analyze them"
echo ""
