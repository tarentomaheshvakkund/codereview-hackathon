#!/bin/bash

# Create PRs from existing branches for Java repository
# This script creates PRs using the GitHub API directly

# Check if GITHUB_TOKEN is set
if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ Error: GITHUB_TOKEN environment variable is not set."
    echo "Please set it before running the script: export GITHUB_TOKEN=your_token_here"
    exit 1
fi

JAVA_REPO="tarentomaheshvakkund/testdata-java-hackathon"

# First, let's get the README commit as base
cd /home/maheshrv/Documents/IGOT/sourcecodes-igot/testinghackathon/testdata-java-hackathon

# Find the base commit (should be README)
BASE_SHA=$(git rev-parse HEAD)
echo "Base SHA: $BASE_SHA"

# Create master branch from current main if it doesn't exist
git push origin main:master --force

echo "Waiting for master branch to be created..."
sleep 3

# Now create PRs using GitHub API
for i in {1..50}; do
    # Determine branch name based on PR number
    if [ $i -le 20 ]; then
        # First 20 have specific names
        case $i in
            1) branch="test-pr-1-sql-injection"; title="SQL Injection in authentication" ;;
            2) branch="test-pr-2-high-complexity"; title="High cyclomatic complexity" ;;
            3) branch="test-pr-3-hardcoded-secrets"; title="Hardcoded credentials" ;;
            4) branch="test-pr-4-path-traversal"; title="Path traversal vulnerability" ;;
            5) branch="test-pr-5-code-duplication"; title="Extensive code duplication" ;;
            6) branch="test-pr-6-null-pointer"; title="Missing null checks" ;;
            7) branch="test-pr-7-weak-crypto"; title="Weak cryptography (MD5)" ;;
            8) branch="test-pr-8-long-method"; title="Long method code smell" ;;
            9) branch="test-pr-9-resource-leak"; title="Resource leak" ;;
            10) branch="test-pr-10-magic-numbers"; title="Magic numbers" ;;
            11) branch="test-pr-11-command-injection"; title="Command injection" ;;
            12) branch="test-pr-12-insecure-random"; title="Insecure random numbers" ;;
            13) branch="test-pr-13-empty-catch"; title="Empty catch blocks" ;;
            14) branch="test-pr-14-xxe-vulnerability"; title="XXE vulnerability" ;;
            15) branch="test-pr-15-excessive-logging"; title="Sensitive data in logs" ;;
            16) branch="test-pr-16-thread-safety"; title="Thread safety issues" ;;
            17) branch="test-pr-17-string-concat-loop"; title="String concatenation in loop" ;;
            18) branch="test-pr-18-ldap-injection"; title="LDAP injection" ;;
            19) branch="test-pr-19-input-validation"; title="Missing input validation" ;;
            20) branch="test-pr-20-dead-code"; title="Dead code and unused methods" ;;
        esac
    else
        branch="test-pr-$i-scenario-$i"
        title="Test scenario $i"
    fi

    echo "Creating PR #$i: $title"

    curl -s -X POST \
        -H "Authorization: token $GITHUB_TOKEN" \
        -H "Accept: application/vnd.github.v3+json" \
        "https://api.github.com/repos/$JAVA_REPO/pulls" \
        -d "{\"title\":\"PR #$i: $title\",\"body\":\"Test scenario for code review system\",\"head\":\"$branch\",\"base\":\"master\"}" \
        > /dev/null

    sleep 1  # Rate limiting
done

echo ""
echo "✓ All Java PRs created!"
echo ""
echo "View PRs at: https://github.com/$JAVA_REPO/pulls"
