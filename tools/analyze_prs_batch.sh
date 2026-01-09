#!/bin/bash

###############################################################################
# Batch PR Analysis Script
# 
# Analyzes multiple PRs sequentially by hitting the analysis API endpoint
#
# Usage:
#   ./tools/analyze_prs_batch.sh              # Analyze PRs 1-100 (default)
#   ./tools/analyze_prs_batch.sh 1 50         # Analyze PRs 1-50
#   ./tools/analyze_prs_batch.sh 10 20        # Analyze PRs 10-20
#   ./tools/analyze_prs_batch.sh --repo owner/repo 1 10  # Specify repository
#
###############################################################################

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
API_URL="http://127.0.0.1:5000/api/analyze"
REPOSITORY="tarentomaheshvakkund/testdata-hackathon"  # Default repository from .env
START_PR=45
END_PR=100
DELAY_SECONDS=2  # Delay between requests to avoid overwhelming the system

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --repo)
            REPOSITORY="$2"
            shift 2
            ;;
        --url)
            API_URL="$2"
            shift 2
            ;;
        --delay)
            DELAY_SECONDS="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS] [START_PR] [END_PR]"
            echo ""
            echo "Options:"
            echo "  --repo REPO       Repository name (e.g., owner/repo)"
            echo "  --url URL         API endpoint URL (default: http://127.0.0.1:5000/api/analyze)"
            echo "  --delay SECONDS   Delay between requests (default: 2)"
            echo "  --help, -h        Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Analyze PRs 1-100"
            echo "  $0 1 50                               # Analyze PRs 1-50"
            echo "  $0 --repo owner/repo 1 10             # Analyze PRs 1-10 for specific repo"
            echo "  $0 --delay 5 1 20                     # Analyze PRs 1-20 with 5s delay"
            exit 0
            ;;
        *)
            if [[ -z "$START_PR_SET" ]]; then
                START_PR=$1
                START_PR_SET=1
            elif [[ -z "$END_PR_SET" ]]; then
                END_PR=$1
                END_PR_SET=1
            fi
            shift
            ;;
    esac
done

# Validate PR range
if [[ ! $START_PR =~ ^[0-9]+$ ]] || [[ ! $END_PR =~ ^[0-9]+$ ]]; then
    echo -e "${RED}❌ Error: PR numbers must be integers${NC}"
    exit 1
fi

if [[ $START_PR -gt $END_PR ]]; then
    echo -e "${RED}❌ Error: START_PR ($START_PR) must be <= END_PR ($END_PR)${NC}"
    exit 1
fi

# Print configuration
echo ""
echo "================================================================================"
echo -e "${BLUE}🚀 BATCH PR ANALYSIS${NC}"
echo "================================================================================"
echo -e "API Endpoint:    ${YELLOW}$API_URL${NC}"
echo -e "Repository:      ${YELLOW}$REPOSITORY${NC}"
echo -e "PR Range:        ${YELLOW}#$START_PR to #$END_PR${NC}"
echo -e "Total PRs:       ${YELLOW}$((END_PR - START_PR + 1))${NC}"
echo -e "Delay:           ${YELLOW}${DELAY_SECONDS}s between requests${NC}"
echo "================================================================================"
echo ""

# Ask for confirmation
read -p "Continue? (yes/no): " -r CONFIRM
if [[ ! $CONFIRM =~ ^[Yy][Ee][Ss]$ ]]; then
    echo -e "${YELLOW}⏹️  Cancelled.${NC}"
    exit 0
fi

echo ""

# Statistics
TOTAL_PRS=$((END_PR - START_PR + 1))
SUCCESS_COUNT=0
FAILURE_COUNT=0
SKIPPED_COUNT=0

# Start time
START_TIME=$(date +%s)

# Analyze each PR
for PR_NUMBER in $(seq $START_PR $END_PR); do
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}📊 Analyzing PR #$PR_NUMBER ($((PR_NUMBER - START_PR + 1))/$TOTAL_PRS)${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    # Build JSON payload (always include repository)
    PAYLOAD="{\"pr_number\": $PR_NUMBER, \"repository\": \"$REPOSITORY\"}"
    
    # Make API request
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL" \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD")
    
    # Extract HTTP status code (last line)
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    
    # Extract response body (all lines except last)
    BODY=$(echo "$RESPONSE" | head -n-1)
    
    # Check response
    if [[ $HTTP_CODE -eq 200 ]]; then
        # Try to parse status field from JSON (check for "status": "success")
        STATUS=$(echo "$BODY" | grep -o '"status"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/"status"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/')
        
        if [[ "$STATUS" == "success" ]]; then
            echo -e "${GREEN}✅ SUCCESS${NC} - PR #$PR_NUMBER analyzed"
            
            # Extract additional info if available
            ISSUES=$(echo "$BODY" | grep -o '"issues_found"[[:space:]]*:[[:space:]]*[0-9]*' | grep -o '[0-9]*$')
            CRITICAL=$(echo "$BODY" | grep -o '"critical_issues"[[:space:]]*:[[:space:]]*[0-9]*' | grep -o '[0-9]*$')
            HIGH=$(echo "$BODY" | grep -o '"high_issues"[[:space:]]*:[[:space:]]*[0-9]*' | grep -o '[0-9]*$')
            AGENT=$(echo "$BODY" | grep -o '"agent_used"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/"agent_used"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/')
            
            if [[ -n "$ISSUES" ]]; then
                echo -e "   ${YELLOW}Issues Found:${NC} $ISSUES"
            fi
            if [[ -n "$CRITICAL" ]] && [[ "$CRITICAL" -gt 0 ]]; then
                echo -e "   ${RED}Critical:${NC} $CRITICAL"
            fi
            if [[ -n "$HIGH" ]] && [[ "$HIGH" -gt 0 ]]; then
                echo -e "   ${YELLOW}High:${NC} $HIGH"
            fi
            if [[ -n "$AGENT" ]]; then
                echo -e "   ${BLUE}Agent:${NC} $AGENT"
            fi
            
            SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        else
            ERROR_MSG=$(echo "$BODY" | grep -o '"error"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/"error"[[:space:]]*:[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/')
            if [[ -n "$ERROR_MSG" ]]; then
                echo -e "${RED}❌ FAILED${NC} - $ERROR_MSG"
            else
                echo -e "${RED}❌ FAILED${NC} - Response doesn't contain success status"
                echo -e "${YELLOW}Response body (first 20 lines):${NC}"
                echo "$BODY" | head -20
            fi
            FAILURE_COUNT=$((FAILURE_COUNT + 1))
        fi
    elif [[ $HTTP_CODE -eq 404 ]]; then
        echo -e "${YELLOW}⏭️  SKIPPED${NC} - PR #$PR_NUMBER not found (404)"
        SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    else
        echo -e "${RED}❌ FAILED${NC} - HTTP $HTTP_CODE"
        echo -e "${RED}Response:${NC} $BODY"
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
    fi
    
    echo ""
    
    # Delay before next request (except for last PR)
    if [[ $PR_NUMBER -lt $END_PR ]]; then
        echo -e "${BLUE}⏳ Waiting ${DELAY_SECONDS}s before next request...${NC}"
        sleep $DELAY_SECONDS
        echo ""
    fi
done

# End time
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))

# Print summary
echo "================================================================================"
echo -e "${BLUE}📈 BATCH ANALYSIS SUMMARY${NC}"
echo "================================================================================"
echo -e "Total PRs:        ${YELLOW}$TOTAL_PRS${NC}"
echo -e "✅ Successful:    ${GREEN}$SUCCESS_COUNT${NC}"
echo -e "❌ Failed:        ${RED}$FAILURE_COUNT${NC}"
echo -e "⏭️  Skipped:       ${YELLOW}$SKIPPED_COUNT${NC}"
echo -e "⏱️  Duration:      ${YELLOW}${MINUTES}m ${SECONDS}s${NC}"
echo "================================================================================"

# Exit with appropriate code
if [[ $FAILURE_COUNT -gt 0 ]]; then
    echo -e "${YELLOW}⚠️  Some PRs failed to analyze${NC}"
    exit 1
else
    echo -e "${GREEN}✅ All PRs processed successfully!${NC}"
    exit 0
fi
