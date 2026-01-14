#!/bin/bash

# PR Generation Script for Testing Code Review System
# This script creates 50 PRs each for Java and Python repositories

set -e  # Exit on error

# Check if GITHUB_TOKEN is set
if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ Error: GITHUB_TOKEN environment variable is not set."
    echo "Please set it before running the script: export GITHUB_TOKEN=your_token_here"
    exit 1
fi

JAVA_REPO="/home/maheshrv/Documents/IGOT/sourcecodes-igot/testinghackathon/testdata-java-hackathon"
PYTHON_REPO="/home/maheshrv/Documents/IGOT/sourcecodes-igot/testinghackathon/testdata-python-hackathon"

# Function to initialize repository
init_repo() {
    local repo_path=$1
    local repo_name=$2
    local repo_url=$3

    echo ""
    echo "================================================================================"
    echo "Initializing $repo_name Repository"
    echo "================================================================================"

    cd "$repo_path"

    # Configure git
    git config user.email "mahesh.vakkund@tarento.com"
    git config user.name "Mahesh Vakkund"

    # Set remote with token
    git remote set-url origin "https://${GITHUB_TOKEN}@github.com/${repo_url}.git"

    # Create README if doesn't exist
    if [ ! -f "README.md" ]; then
        cat > README.md << 'EOF'
# Test Data Repository

This repository contains test data for the AI-Powered Code Review System.

## Purpose

This repository is used to test various scenarios including:
- Code quality issues
- Security vulnerabilities
- Complexity analysis
- Test coverage estimation
- RAG novelty scoring
- Pattern recognition

## Generated PRs

This repository contains 50 PRs with diverse scenarios to test all aspects of the code review system.
EOF

        git add README.md
        git commit -m "Initial commit: Add README"
        git branch -M main
        git push -u origin main --force
    fi

    echo "✓ Repository initialized successfully"
}

# Initialize both repositories
init_repo "$JAVA_REPO" "Java" "tarentomaheshvakkund/testdata-java-hackathon"
init_repo "$PYTHON_REPO" "Python" "tarentomaheshvakkund/testdata-python-hackathon"

echo ""
echo "================================================================================"
echo "✓ Both repositories initialized"
echo "================================================================================"
echo ""
echo "Now run the Python script to create PRs:"
echo "  python3 tools/generate_test_prs.py"
