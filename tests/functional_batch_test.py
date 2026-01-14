import os
import sys
import time
import tempfile
import shutil
from unittest.mock import MagicMock
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from models.pr_event import PREvent, PRAuthor, PRFile
from agents.dispatcher import AgentDispatcher

def create_patch(code):
    """Create a unified diff format patch from code."""
    lines = code.strip().split('\n')
    patch_lines = ['@@ -0,0 +1,{} @@'.format(len(lines))]
    for line in lines:
        patch_lines.append('+' + line)
    return '\n'.join(patch_lines)

def run_batch_test():
    """Run a batch of 10 PR analysis scenarios with 10s delays."""
    print("🚀 Starting Functional Batch Testing: 10 PRs with 10s Delays\n")
    
    test_dir = tempfile.mkdtemp()
    mock_db = MagicMock()
    dispatcher = AgentDispatcher(db_service=mock_db)
    
    scenarios = [
        # 1. Python Security
        {
            "name": "Python: Security Vulnerabilities",
            "files": [
                ("security_vuln.py", "import os\ndef run_cmd(cmd):\n    os.system(cmd)\napi_key = 'sk-test-123'")
            ]
        },
        # 2. JavaScript Quality
        {
            "name": "JS: Modern Best Practices",
            "files": [
                ("best_practices.js", "var x = 10;\nif (x == '10') {\n    console.log('bad');\n}")
            ]
        },
        # 3. Python Broad Exception
        {
            "name": "Python: Broad Exceptions",
            "files": [
                ("utils.py", "def fetch():\n    try:\n        return r.get()\n    except:\n        pass")
            ]
        },
        # 4. JS Security (eval)
        {
            "name": "JS: Script Security",
            "files": [
                ("eval_risk.js", "function run(code) {\n    eval(code);\n}")
            ]
        },
        # 5. Mixed Languages
        {
            "name": "Mixed: Python & JS PR",
            "files": [
                ("logic.py", "print('hello')"),
                ("styles.js", "console.log('world')")
            ]
        },
        # 6. Python Quality (Large function)
        {
            "name": "Python: Maintainability",
            "files": [
                ("complex.py", "def large_func():\n" + "    print('line')\n" * 30)
            ]
        },
        # 7. JS DOM Manipulation
        {
            "name": "JS: DOM Security",
            "files": [
                ("danger.js", "element.innerHTML = user_input;")
            ]
        },
        # 8. Python SQL Injection
        {
            "name": "Python: SQL Patterns",
            "files": [
                ("db.py", "cursor.execute(f'SELECT * FROM users WHERE id = {user_id}')")
            ]
        },
        # 9. Code Quality (TODOs)
        {
            "name": "Quality: Technical Debt",
            "files": [
                ("debt.py", "# TODO: Fix this later\ndef temp(): pass")
            ]
        },
        # 10. Large PR (Multiple files)
        {
            "name": "Overall: Multi-file PR",
            "files": [
                ("f1.py", "print(1)"),
                ("f2.py", "print(2)"),
                ("f3.js", "console.log(3)")
            ]
        }
    ]
    
    results = []
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"--- [PR {i}/10] {scenario['name']} ---")
        
        pr_files = []
        for filename, content in scenario['files']:
            file_path = os.path.join(test_dir, f"pr_{i}_{filename}")
            with open(file_path, 'w') as f:
                f.write(content)
            
            pr_files.append(PRFile(
                filename=file_path,
                status='added',
                additions=len(content.split('\n')),
                deletions=0,
                changes=len(content.split('\n')),
                patch=create_patch(content)
            ))
            
        pr_event = PREvent(
            action='opened',
            id=1000 + i,
            pr_number=200 + i,
            pr_title=scenario['name'],
            pr_description='Batch test PR',
            pr_url=f'https://github.com/repo/pr/{200+i}',
            repository='test/repo',
            repository_url='',
            author=PRAuthor(login='tester', id=i, avatar_url=''),
            base_branch='main',
            head_branch='feature/test',
            files=pr_files,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            is_draft=False
        )
        
        start_time = time.time()
        result = dispatcher.dispatch(pr_event)
        duration = time.time() - start_time
        
        print(f"✅ Result: {result.success}, Issues: {len(result.issues)}, Time: {duration:.2f}s")
        results.append({
            "name": scenario['name'],
            "success": result.success,
            "issues": len(result.issues),
            "time": duration
        })
        
        if i < len(scenarios):
            print(f"⏳ Sleeping 10 seconds before next PR...\n")
            time.sleep(10)
            
    print("\n📊 --- Batch Testing Summary ---")
    print(f"{'Scenario':<30} | {'Success':<8} | {'Issues':<8} | {'Time (s)':<8}")
    print("-" * 65)
    for res in results:
        success_str = "✅" if res['success'] else "❌"
        print(f"{res['name']:<30} | {success_str:<8} | {res['issues']:<8} | {res['time']:<8.2f}")
    
    shutil.rmtree(test_dir)
    print("\n🏁 Batch Testing Complete.")

if __name__ == "__main__":
    run_batch_test()
