import os
import sys
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from main import app
from models.pr_event import PREvent, PRAuthor, PRFile

def create_patch(code):
    """Create a unified diff format patch from code."""
    lines = code.strip().split('\n')
    patch_lines = ['@@ -0,0 +1,{} @@'.format(len(lines))]
    for line in lines:
        patch_lines.append('+' + line)
    return '\n'.join(patch_lines)

def check_analyze_api_functionally():
    """ hit the /api/analyze endpoint with a test client and verify the full flow."""
    print("🚀 Starting Functional API Check: /api/analyze\n")
    
    test_dir = tempfile.mkdtemp()
    client = app.test_client()
    
    dirty_python = """import os
def insecure():
    print("hello")
    os.system("ls")
    api_key = "abc123"
"""
    file_path = os.path.join(test_dir, 'dirty.py')
    with open(file_path, 'w') as f:
        f.write(dirty_python)
        
    # Prepare mocks for external services
    mock_pr_details = {
        'id': 12345,
        'number': 101,
        'title': 'Functional API Check',
        'body': 'Testing the API end-to-end',
        'user': {'login': 'tester', 'id': 1},
        'base': {'ref': 'main'},
        'head': {'ref': 'branch', 'sha': 'sha123'},
        'html_url': 'http://github.com/test/repo/pull/101',
        'created_at': '2026-01-14T08:00:00Z',
        'updated_at': '2026-01-14T08:00:00Z',
        'draft': False
    }
    
    pr_event = PREvent(
        action='opened',
        id=12345,
        pr_number=101,
        pr_title='Functional API Check',
        pr_description='Testing the API end-to-end',
        pr_url='http://github.com/test/repo/pull/101',
        repository='test/repo',
        repository_url='',
        author=PRAuthor(login='tester', id=1, avatar_url=''),
        base_branch='main',
        head_branch='branch',
        files=[
            PRFile(
                filename=file_path,
                status='added',
                additions=5,
                deletions=0,
                changes=5,
                patch=create_patch(dirty_python)
            )
        ],
        created_at=datetime.now(),
        updated_at=datetime.now(),
        is_draft=False
    )

    print("🔍 Sending POST request to /api/analyze...")
    
    # Patch the parts of main.py that hit external dependencies
    with patch('main._fetch_pr_event') as mock_fetch:
        mock_fetch.return_value = ((pr_event, mock_pr_details), None, None)
        
        with patch('main._persist_analysis') as mock_persist:
            mock_persist.return_value = {'pr_analysis_id': 55555}
            
            with patch('main.slack_service') as mock_slack:
                with patch('main.pr_comment_agent') as mock_comments:
                    mock_comments.post_analysis_comments.return_value = {
                        'summary_posted': True,
                        'files_commented': 1,
                        'total_comments': 1
                    }
                    
                    response = client.post(
                        '/api/analyze',
                        data=json.dumps({
                            'repository': 'test/repo',
                            'pr_number': 101
                        }),
                        content_type='application/json'
                    )
                    
                    print(f"📡 API Response Status: {response.status_code}")
                    data = json.loads(response.data)
                    
                    if response.status_code == 200:
                        print(f"✅ API Request Successful!")
                        print(f"📊 Status: {data.get('status')}")
                        print(f"🎯 PR Number: {data.get('pr_number')}")
                        issues_count = data.get('issues_found', 0)
                        print(f"🐛 Issues Found: {issues_count}")
                        
                        # Verify that the analysis actually found issues
                        if issues_count > 0:
                            print("🔍 Issues identified in dirty code:")
                            for issue in data.get('issues', []):
                                print(f"  - [{issue.get('severity')}] {issue.get('message')}")
                        else:
                            print("⚠️  No issues found! Check analysis logic.")
                            sys.exit(1)
                    else:
                        print(f"❌ API Request Failed! Error: {data.get('error')}")
                        sys.exit(1)

    shutil.rmtree(test_dir)
    print("\n🏁 Functional API Check Complete.")

if __name__ == "__main__":
    check_analyze_api_functionally()
