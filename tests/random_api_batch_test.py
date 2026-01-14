import os
import sys
import json
import time
import random
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

SCENARIOS = [
    # 1. Python Security
    {
        "name": "Python: Security Vulnerabilities",
        "description": "Hardcoded API key and command injection",
        "filename": "security_vuln.py",
        "code": "import os\ndef run_cmd(cmd):\n    os.system(cmd)\napi_key = 'sk-test-123'",
        "expected_severity": "high"
    },
    # 2. JavaScript Quality
    {
        "name": "JS: Modern Best Practices",
        "description": "Loose equality and console logs",
        "filename": "best_practices.js",
        "code": "var x = 10;\nif (x == '10') {\n    console.log('bad');\n}",
        "expected_severity": "low"
    },
    # 3. Python Broad Exception
    {
        "name": "Python: Broad Exceptions",
        "description": "Bare except clause",
        "filename": "utils.py",
        "code": "def fetch():\n    try:\n        return r.get()\n    except:\n        pass",
        "expected_severity": "medium"
    },
    # 4. JS Security (eval)
    {
        "name": "JS: Script Security",
        "description": "Use of eval()",
        "filename": "eval_risk.js",
        "code": "function run(code) {\n    eval(code);\n}",
        "expected_severity": "critical"
    },
    # 5. Mixed Languages
    {
        "name": "Mixed: Python & JS PR",
        "description": "Simple changes in multiple languages",
        "filename": "logic.py",
        "code": "print('hello')",
        "expected_severity": "low"
    },
    # 6. Python Quality (Large function)
    {
        "name": "Python: Maintainability",
        "description": "Excessively long function",
        "filename": "complex.py",
        "code": "def large_func():\n" + "    print('line')\n" * 30,
        "expected_severity": "low"
    },
    # 7. JS DOM Manipulation
    {
        "name": "JS: DOM Security",
        "description": "Unsafe innerHTML usage",
        "filename": "danger.js",
        "code": "element.innerHTML = user_input;",
        "expected_severity": "high"
    },
    # 8. Python SQL Injection
    {
        "name": "Python: SQL Patterns",
        "description": "Potential SQL injection",
        "filename": "db.py",
        "code": "cursor.execute(f'SELECT * FROM users WHERE id = {user_id}')",
        "expected_severity": "critical"
    },
    # 9. Code Quality (TODOs)
    {
        "name": "Quality: Technical Debt",
        "description": "Leftover TODOs",
        "filename": "debt.py",
        "code": "# TODO: Fix this later\ndef temp(): pass",
        "expected_severity": "low"
    },
    # 10. Large PR (Multiple files)
    {
        "name": "Overall: Multi-file PR",
        "description": "Changes spread across files",
        "filename": "f1.py",
        "code": "print(1)",
        "expected_severity": "low"
    },
    # 11. Empty Block
    {
        "name": "Python: Empty Block",
        "description": "Pass as placeholder",
        "filename": "placeholder.py",
        "code": "if True:\n    pass",
        "expected_severity": "low"
    },
    # 12. Debug Prints
    {
        "name": "Python: Debug leftovers",
        "description": "Leftover print statements",
        "filename": "debug.py",
        "code": "def calc(x):\n    print(x)\n    return x*2",
        "expected_severity": "low"
    },
    # 13. Secrets in comments
    {
        "name": "General: Secrets",
        "description": "Secret token in comment",
        "filename": "config.py",
        "code": "# Token: gh_secret_123\nTIMEOUT=10",
        "expected_severity": "high"
    },
    # 14. Infinite Loop Risk
    {
        "name": "Logic: Infinite Loop",
        "description": "While True loop",
        "filename": "worker.py",
        "code": "while True:\n    process()",
        "expected_severity": "medium"
    },
    # 15. Import Star
    {
        "name": "Python: Wildcard Import",
        "description": "from module import *",
        "filename": "imports.py",
        "code": "from math import *",
        "expected_severity": "low"
    }
]

def run_random_batch_test():
    """Run 10 random PR analysis scenarios via the /api/analyze endpoint with 10s delays."""
    print("🚀 Starting Randomized Batch API Testing: 10 PRs with 10s Delays\n")
    
    test_dir = tempfile.mkdtemp()
    client = app.test_client()
    
    # Select 10 random scenarios
    selected_scenarios = random.sample(SCENARIOS, 10)
    
    results = []
    
    # Mock external services once for the whole batch
    with patch('main._fetch_pr_event') as mock_fetch:
        with patch('main._persist_analysis') as mock_persist:
            with patch('main.slack_service') as mock_slack:
                with patch('main.pr_comment_agent') as mock_comments:
                    
                    # Common mocks
                    mock_persist.return_value = {'pr_analysis_id': 1}
                    mock_comments.post_analysis_comments.return_value = {
                        'summary_posted': True, 
                        'files_commented': 1, 
                        'total_comments': 1
                    }

                    for i, scenario in enumerate(selected_scenarios, 1):
                        print(f"--- [PR {i}/10] {scenario['name']} ---")
                        print(f"📝 Description: {scenario['description']}")
                        
                        file_path = os.path.join(test_dir, scenario['filename'])
                        with open(file_path, 'w') as f:
                            f.write(scenario['code'])
                            
                        # Prepare PR Event mock
                        pr_files = [PRFile(
                            filename=file_path,
                            status='added',
                            additions=len(scenario['code'].split('\n')),
                            deletions=0,
                            changes=len(scenario['code'].split('\n')),
                            patch=create_patch(scenario['code'])
                        )]
                        
                        pr_event = PREvent(
                            action='opened',
                            id=random.randint(1000, 9999),
                            pr_number=random.randint(500, 900),
                            pr_title=scenario['name'],
                            pr_description=scenario['description'],
                            pr_url=f'http://github.com/test/repo/pull/{i}',
                            repository='test/repo',
                            repository_url='',
                            author=PRAuthor(login='tester', id=i, avatar_url=''),
                            base_branch='main',
                            head_branch='feature',
                            files=pr_files,
                            created_at=datetime.now(),
                            updated_at=datetime.now(),
                            is_draft=False
                        )
                        
                        mock_pr_details = {
                            'id': pr_event.id,
                            'number': pr_event.pr_number,
                            'title': pr_event.pr_title,
                            'body': pr_event.pr_description,
                            'user': {'login': 'tester', 'id': i},
                            'base': {'ref': 'main'},
                            'head': {'ref': 'feature', 'sha': 'abc12345'},
                            'html_url': pr_event.pr_url,
                            'created_at': datetime.now().isoformat(),
                            'updated_at': datetime.now().isoformat(),
                            'draft': False
                        }
                        
                        # Configure per-iteration mock return
                        mock_fetch.return_value = ((pr_event, mock_pr_details), None, None)
                        
                        start_time = time.time()
                        
                        # Call API
                        response = client.post(
                            '/api/analyze',
                            data=json.dumps({
                                'repository': 'test/repo',
                                'pr_number': pr_event.pr_number
                            }),
                            content_type='application/json'
                        )
                        
                        duration = time.time() - start_time
                        
                        if response.status_code == 200:
                            data = json.loads(response.data)
                            issues_count = data.get('issues_found', 0)
                            print(f"✅ Success! Found {issues_count} issues in {duration:.2f}s")
                            results.append({
                                "name": scenario['name'],
                                "success": True,
                                "issues": issues_count,
                                "time": duration
                            })
                        else:
                            print(f"❌ Failed: {response.data}")
                            results.append({
                                "name": scenario['name'],
                                "success": False,
                                "issues": 0,
                                "time": duration
                            })
                        
                        if i < 10:
                            print(f"⏳ Sleeping 10 seconds...\n")
                            time.sleep(10)

    print("\n📊 --- Random Batch Test Summary ---")
    print(f"{'Scenario':<30} | {'Status':<8} | {'Issues':<8} | {'Time (s)':<8}")
    print("-" * 65)
    for res in results:
        status = "✅" if res['success'] else "❌"
        print(f"{res['name']:<30} | {status:<8} | {res['issues']:<8} | {res['time']:<8.2f}")
    
    shutil.rmtree(test_dir)
    print("\n🏁 Test Complete.")

if __name__ == "__main__":
    run_random_batch_test()
