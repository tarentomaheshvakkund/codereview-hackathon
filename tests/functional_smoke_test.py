import os
import sys
import unittest
import tempfile
import shutil
from unittest.mock import MagicMock, patch
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from models.pr_event import PREvent, PRAuthor, PRFile
from agents.dispatcher import AgentDispatcher

class FunctionalSmokeTest(unittest.TestCase):
    """
    Functional smoke test to verify real orchestration logic without heavy mocking.
    Verifies that AgentDispatcher correctly initializes MainAgent and 
    MainAgent coordinates sub-agents to find real issues in code patches.
    """

    def setUp(self):
        # Create a temporary directory for test files
        self.test_dir = tempfile.mkdtemp()
        
        # Mock DB Service to avoid requiring real Postgres
        self.mock_db = MagicMock()
        
        # Initialize Dispatcher (this will initialize real MainAgent and sub-agents)
        self.dispatcher = AgentDispatcher(db_service=self.mock_db)

    def tearDown(self):
        # Cleanup temporary directory
        shutil.rmtree(self.test_dir)

    def _create_patch(self, code):
        """Create a unified diff format patch from code."""
        lines = code.strip().split('\n')
        patch_lines = ['@@ -0,0 +1,{} @@'.format(len(lines))]
        for line in lines:
            patch_lines.append('+' + line)
        return '\n'.join(patch_lines)

    def test_run_analysis_on_dirty_python_code(self):
        """Test analysis on Python code with known issues."""
        print("\n🚀 Starting Functional Smoke Test: Python Analysis...")
        
        dirty_code = """import os

def insecure_function(user_input):
    print(f"Processing input: {user_input}")
    api_key = "sk-1234567890abcdef1234567890abcdef"
    try:
        os.system(f"echo {user_input}")
    except:
        pass
    return True
"""
        # Create real file on disk for Pylint/Flake8
        file_path = os.path.join(self.test_dir, 'dirty_script.py')
        with open(file_path, 'w') as f:
            f.write(dirty_code)
            
        # Create a PREvent with this file
        pr_event = PREvent(
            action='opened',
            id=9999,
            pr_number=123,
            pr_title='Test Dirty PR',
            pr_description='A PR with intentional issues for testing',
            pr_url='https://github.com/test/repo/pull/123',
            repository='test/repo',
            repository_url='https://github.com/test/repo',
            author=PRAuthor(login='testuser', id=1, avatar_url=''),
            base_branch='main',
            head_branch='feature/dirty',
            files=[
                PRFile(
                    filename=file_path,  # Use full path so tools find it
                    status='added',
                    additions=11,
                    deletions=0,
                    changes=11,
                    patch=self._create_patch(dirty_code)
                )
            ],
            created_at=datetime.now(),
            updated_at=datetime.now(),
            is_draft=False
        )
        
        # Run analysis
        print(f"🔍 Dispatching PR for real analysis on {file_path}...")
        result = self.dispatcher.dispatch(pr_event)
        
        # Verify Results
        print(f"✅ Analysis complete. Success: {result.success}")
        print(f"📊 Issues found: {len(result.issues)}")
        
        # Print breakdown for debugging
        breakdown = result.metadata.get('agent_breakdown', {})
        for agent, data in breakdown.items():
            print(f"  - {agent}: {data['issues_count']} issues")

        # Assertions
        self.assertTrue(result.success)
        self.assertGreater(len(result.issues), 0, "Should have found at least one issue")
        
        messages = [issue.message.lower() for issue in result.issues]
        
        # Check for specific expected issues
        has_print = any('print' in m for m in messages)
        has_secret = any('hardcoded' in m or 'api_key' in m or 'credential' in m for m in messages)
        has_except = any('bare except' in m or 'broad exception' in m for m in messages)

        print(f"  - Found print issue: {has_print}")
        print(f"  - Found secret issue: {has_secret}")
        print(f"  - Found except issue: {has_except}")

        self.assertTrue(has_print, "Should detect print via pattern analysis")
        self.assertTrue(has_secret, "Should detect secret via pattern analysis")
        self.assertTrue(has_except, "Should detect bare except via pattern analysis")

    def test_run_analysis_on_dirty_js_code(self):
        """Test analysis on JS code with known issues."""
        print("\n🚀 Starting Functional Smoke Test: JavaScript Analysis...")
        
        js_code = """function process(data) {
    console.log("Processing data:", data);
    if (data == "test") {
        var x = 10;
        return x;
    }
    return null;
}
"""
        file_path = os.path.join(self.test_dir, 'script.js')
        with open(file_path, 'w') as f:
            f.write(js_code)

        pr_event = PREvent(
            action='opened', id=10000, pr_number=124, pr_title='JS Test', pr_description='',
            pr_url='', repository='test/repo', repository_url='',
            author=PRAuthor(login='u', id=1, avatar_url=''),
            base_branch='m', head_branch='f',
            files=[PRFile(filename=file_path, status='added', additions=8, deletions=0, changes=8, patch=self._create_patch(js_code))],
            created_at=datetime.now(), updated_at=datetime.now(), is_draft=False
        )
        
        result = self.dispatcher.dispatch(pr_event)
        
        print(f"✅ JS Analysis complete. Issues found: {len(result.issues)}")
        messages = [issue.message.lower() for issue in result.issues]
        
        has_console = any('console' in m for m in messages)
        has_equality = any('===' in m or 'strict equality' in m or '==' in m for m in messages)
        has_var = any('var' in m for m in messages)
        
        print(f"  - Found console issue: {has_console}")
        print(f"  - Found equality issue: {has_equality}")
        print(f"  - Found var issue: {has_var}")
        
        self.assertTrue(has_console, "Should detect console.log")
        self.assertTrue(has_equality, "Should detect weak equality")
        self.assertTrue(has_var, "Should detect var usage")

if __name__ == "__main__":
    unittest.main()
