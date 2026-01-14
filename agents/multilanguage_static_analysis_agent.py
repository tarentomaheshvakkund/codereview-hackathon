"""Multi-language static analysis agent."""
from typing import List, Dict
import subprocess  # nosec B404
import json
import os
from models.pr_event import PREvent
from models.analysis_result import Issue, IssueType, Severity
from agents.base_agent import BaseAgent


class MultiLanguageStaticAnalysisAgent(BaseAgent):
    """Agent that performs static code analysis across multiple languages."""

    # Language detection based on file extensions
    LANGUAGE_EXTENSIONS = {
        'python': ['.py'],
        'java': ['.java'],
        'scala': ['.scala'],
        'javascript': ['.js', '.jsx', '.mjs'],
        'typescript': ['.ts', '.tsx'],
        'nodejs': ['.js', '.mjs']  # Node.js uses JavaScript extensions
    }

    def __init__(self, config: dict):
        """Initialize the multi-language static analysis agent."""
        super().__init__("Multi-Language Static Analysis Agent", config)
        self.languages_config = config.get('languages', {})
        self.severity_threshold = config.get('severity_threshold', 'medium')

    def _analyze_impl(self, pr_event: PREvent) -> List[Issue]:
        """Run static analysis on PR files for all supported languages."""
        issues = []

        # Group files by language
        files_by_language = self._group_files_by_language(pr_event.files)

        # Analyze each language
        for language, files in files_by_language.items():
            if not files:
                continue

            lang_config = self.languages_config.get(language, {})
            if not lang_config.get('enabled', False):
                self.logger.info(f"Skipping {language} - not enabled")
                continue

            self.logger.info(f"Analyzing {len(files)} {language} file(s)")

            # Run language-specific analysis
            if language == 'python':
                issues.extend(self._analyze_python(files, lang_config))
            elif language == 'java':
                issues.extend(self._analyze_java(files, lang_config))
            elif language == 'scala':
                issues.extend(self._analyze_scala(files, lang_config))
            elif language in ['javascript', 'typescript', 'nodejs']:
                issues.extend(self._analyze_javascript_typescript(files, lang_config, language))

        return issues

    def _group_files_by_language(self, files: List) -> Dict[str, List]:
        """Group files by their programming language."""
        grouped = {lang: [] for lang in self.LANGUAGE_EXTENSIONS.keys()}

        for file in files:
            if file.status == 'removed':
                continue

            # Detect language by extension
            filename = file.filename.lower()
            for language, extensions in self.LANGUAGE_EXTENSIONS.items():
                if any(filename.endswith(ext) for ext in extensions):
                    grouped[language].append(file)
                    break

        return grouped

    # ========== PYTHON ANALYSIS ==========

    def _analyze_python(self, files: List, config: dict) -> List[Issue]:
        """Analyze Python files."""
        issues = []
        tools = config.get('tools', ['pylint', 'flake8'])

        # First, try pattern-based analysis on patch content
        issues.extend(self._analyze_python_patterns(files))

        # Only run external tools if they're installed
        if 'pylint' in tools:
            issues.extend(self._run_pylint(files))

        if 'flake8' in tools:
            issues.extend(self._run_flake8(files))

        return issues

    def _analyze_python_patterns(self, files: List) -> List[Issue]:
        """Analyze Python code using pattern matching on patches."""
        issues = []

        for file in files:
            if file.patch:
                file_issues = self._analyze_python_file(file)
                issues.extend(file_issues)

        return issues

    def _analyze_python_file(self, file) -> List[Issue]:
        """Analyze a single Python file for issues."""
        issues = []
        lines = file.patch.split('\n')
        line_number = 0

        for line in lines:
            line_number = self._update_line_number(line, line_number)

            if line.startswith('@@') or not line.startswith('+'):
                if not line.startswith('-'):
                    line_number += 1
                continue

            code = line[1:]  # Remove the '+' prefix
            line_number += 1

            # Check for various Python patterns
            self._check_python_print_statements(code, file.filename, line_number, issues)
            self._check_python_bare_except(code, file.filename, line_number, issues)
            self._check_todo_comments(code, file.filename, line_number, issues, 'python')
            self._check_hardcoded_secrets(code, file.filename, line_number, issues, 'python')
            self._check_sql_injection(code, file.filename, line_number, issues, 'python')
            self._check_eval_usage(code, file.filename, line_number, issues, 'python')

        return issues

    def _update_line_number(self, line: str, current_line: int) -> int:
        """Extract and return line number from patch header."""
        if line.startswith('@@'):
            parts = line.split('+')[1].split(',')[0] if '+' in line else '1'
            try:
                return int(parts.strip().split()[0])
            except (ValueError, IndexError):
                return 1
        return current_line

    def _check_python_print_statements(self, code: str, filename: str, line_number: int, issues: List[Issue]):
        """Check for print statements in Python code."""
        if 'print(' in code:
            issues.append(Issue(
                type=IssueType.STYLE,
                severity=Severity.LOW,
                message='Use logging instead of print statements',
                file=filename,
                line=line_number,
                code='NO_PRINT',
                suggestion='Replace with logger.info(), logger.debug(), etc.',
                metadata={'tool': 'pattern-analysis', 'language': 'python'}
            ))

    def _check_python_bare_except(self, code: str, filename: str, line_number: int, issues: List[Issue]):
        """Check for bare except clauses in Python code."""
        if code.strip() == 'except:' or code.strip().startswith('except:'):
            issues.append(Issue(
                type=IssueType.QUALITY,
                severity=Severity.HIGH,
                message='Bare except clause - catch specific exceptions',
                file=filename,
                line=line_number,
                code='BARE_EXCEPT',
                suggestion='Specify exception types: except ValueError, TypeError:',
                metadata={'tool': 'pattern-analysis', 'language': 'python'}
            ))

    def _check_todo_comments(self, code, filename, line_number, issues, language):
        """Check for TODO/FIXME comments."""
        if 'TODO' in code or 'FIXME' in code or 'XXX' in code:
            issues.append(Issue(
                type=IssueType.QUALITY,
                severity=Severity.LOW,
                message='TODO/FIXME comment found',
                file=filename,
                line=line_number,
                code='TODO_FOUND',
                suggestion='Complete implementation or create a ticket',
                metadata={'tool': 'pattern-analysis', 'language': language}
            ))

    def _check_hardcoded_secrets(self, code, filename, line_number, issues, language):
        """Check for hardcoded secrets."""
        suspicious_keywords = ['password', 'secret', 'api_key', 'apikey', 'token', 'credential']
        code_lower = code.lower()
        if '=' in code and any(keyword in code_lower for keyword in suspicious_keywords):
            if '"' in code or "'" in code:
                issues.append(Issue(
                    type=IssueType.SECURITY,
                    severity=Severity.CRITICAL,
                    message='Possible hardcoded credential detected',
                    file=filename,
                    line=line_number,
                    code='HARDCODED_SECRET',
                    suggestion='Use environment variables or config files',
                    metadata={'tool': 'pattern-analysis', 'language': language}
                ))

    def _check_sql_injection(self, code, filename, line_number, issues, language):
        """Check for SQL injection vulnerabilities."""
        if 'execute(' in code or 'executemany(' in code:
            if '%' in code or '.format(' in code or 'f"' in code or "f'" in code:
                issues.append(Issue(
                    type=IssueType.SECURITY,
                    severity=Severity.HIGH,
                    message='Possible SQL injection - use parameterized queries',
                    file=filename,
                    line=line_number,
                    code='SQL_INJECTION',
                    suggestion='Use parameterized queries: execute(query, (param1, param2))',
                    metadata={'tool': 'pattern-analysis', 'language': language}
                ))

    def _check_eval_usage(self, code, filename, line_number, issues, language):
        """Check for dangerous eval() usage."""
        if 'eval(' in code:
            issues.append(Issue(
                type=IssueType.SECURITY,
                severity=Severity.CRITICAL,
                message='Use of eval() is dangerous - arbitrary code execution risk',
                file=filename,
                line=line_number,
                code='EVAL_USED',
                suggestion='Use ast.literal_eval() for safe evaluation or redesign',
                metadata={'tool': 'pattern-analysis', 'language': language}
            ))

    def _run_pylint(self, files: List) -> List[Issue]:
        """Run pylint on Python files."""
        issues = []

        for file in files:
            try:
                result = subprocess.run(
                    ['pylint', '--output-format=json', file.filename],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False
                )  # nosec B603 B607

                if result.stdout:
                    pylint_issues = json.loads(result.stdout)

                    for item in pylint_issues:
                        issues.append(Issue(
                            type=IssueType.QUALITY,
                            severity=self._map_pylint_severity(item.get('type')),
                            message=item.get('message', ''),
                            file=file.filename,
                            line=item.get('line'),
                            column=item.get('column'),
                            code=item.get('message-id'),
                            metadata={'tool': 'pylint', 'language': 'python'}
                        ))

            except subprocess.TimeoutExpired:
                self.logger.warning(f"Pylint timeout for {file.filename}")
            except Exception as e:
                self.logger.error(f"Pylint error: {e}")

        return issues

    def _parse_flake8_output(self, stdout: str, filename: str) -> List[Issue]:
        """Parse flake8 JSON output into issues."""
        issues = []

        if not stdout or not stdout.strip():
            self.logger.debug(f"Flake8: No issues found in {filename}")
            return issues

        try:
            flake8_data = json.loads(stdout)

            for file_path, file_issues in flake8_data.items():
                for item in file_issues:
                    issues.append(Issue(
                        type=IssueType.STYLE,
                        severity=Severity.LOW,
                        message=item.get('text', ''),
                        file=file_path,
                        line=item.get('line_number'),
                        code=item.get('code'),
                        metadata={'tool': 'flake8', 'language': 'python'}
                    ))
        except json.JSONDecodeError as je:
            self.logger.warning(f"Flake8 returned invalid JSON for {filename}: {je}")
            self.logger.debug(f"Flake8 stdout: {stdout[:200]}")

        return issues

    def _run_flake8(self, files: List) -> List[Issue]:
        """Run flake8 on Python files."""
        issues = []
        flake8_available = True

        for file in files:
            if not flake8_available:
                break

            try:
                result = subprocess.run(
                    ['flake8', '--format=json', file.filename],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False
                )  # nosec B603 B607

                file_issues = self._parse_flake8_output(result.stdout, file.filename)
                issues.extend(file_issues)

            except subprocess.TimeoutExpired:
                self.logger.error(f"Flake8 timeout for {file.filename}")
            except FileNotFoundError:
                self.logger.warning("Flake8 not installed - skipping Python linting")
                flake8_available = False
            except Exception as e:
                self.logger.error(f"Flake8 error for {file.filename}: {e}")

        return issues

    # ========== JAVA ANALYSIS ==========

    def _analyze_java(self, files: List, config: dict) -> List[Issue]:
        """Analyze Java files."""
        issues = []
        tools = config.get('tools', ['checkstyle', 'pmd'])

        # First, try pattern-based analysis on patch content
        issues.extend(self._analyze_java_patterns(files))

        # Only run external tools if they're installed
        if 'checkstyle' in tools:
            issues.extend(self._run_checkstyle(files))

        if 'pmd' in tools:
            issues.extend(self._run_pmd(files))

        return issues

    def _analyze_java_patterns(self, files: List) -> List[Issue]:
        """Analyze Java code using pattern matching on patches."""
        issues = []

        for file in files:
            if file.patch:
                file_issues = self._analyze_java_file(file)
                issues.extend(file_issues)

        return issues

    def _analyze_java_file(self, file) -> List[Issue]:
        """Analyze a single Java file for issues."""
        issues = []
        lines = file.patch.split('\n')
        line_number = 0

        for i, line in enumerate(lines):
            line_number = self._update_line_number(line, line_number)

            if line.startswith('@@') or not line.startswith('+'):
                if not line.startswith('-'):
                    line_number += 1
                continue

            code = line[1:]  # Remove the '+' prefix
            line_number += 1

            # Check for various Java patterns
            self._check_java_system_out(code, file.filename, line_number, issues)
            self._check_java_print_stack_trace(code, file.filename, line_number, issues)
            self._check_java_empty_catch(code, lines, i, file.filename, line_number, issues)
            self._check_todo_comments(code, file.filename, line_number, issues, 'java')
            self._check_hardcoded_secrets(code, file.filename, line_number, issues, 'java')
            self._check_java_sql_injection(code, file.filename, line_number, issues)

        return issues

    def _check_java_system_out(self, code: str, filename: str, line_number: int, issues: List[Issue]):
        """Check for System.out.println usage in Java code."""
        if 'System.out.println' in code or 'System.err.println' in code:
            issues.append(Issue(
                type=IssueType.STYLE,
                severity=Severity.LOW,
                message='Use logging framework instead of System.out.println',
                file=filename,
                line=line_number,
                code='NO_SYSTEM_OUT',
                suggestion='Replace with logger.info(), logger.error(), etc.',
                metadata={'tool': 'pattern-analysis', 'language': 'java'}
            ))

    def _check_java_print_stack_trace(self, code: str, filename: str, line_number: int, issues: List[Issue]):
        """Check for printStackTrace usage in Java code."""
        if '.printStackTrace()' in code:
            issues.append(Issue(
                type=IssueType.QUALITY,
                severity=Severity.MEDIUM,
                message='Use proper logging instead of printStackTrace',
                file=filename,
                line=line_number,
                code='NO_PRINT_STACK_TRACE',
                suggestion='Log the exception with logger.error("message", exception)',
                metadata={'tool': 'pattern-analysis', 'language': 'java'}
            ))

    def _check_java_empty_catch(self, code: str, lines: List[str], current_index: int,
                                filename: str, line_number: int, issues: List[Issue]):
        """Check for empty catch blocks in Java code."""
        if code.strip() == 'catch' or (code.strip().startswith('catch') and '{' in code):
            # Check if next few lines are just closing brace
            next_lines = lines[current_index+1:current_index+3] if current_index+1 < len(lines) else []
            if any(line.strip() == '+}' or line.strip() == '}' for line in next_lines):
                issues.append(Issue(
                    type=IssueType.QUALITY,
                    severity=Severity.HIGH,
                    message='Empty catch block - exceptions should be handled properly',
                    file=filename,
                    line=line_number,
                    code='EMPTY_CATCH',
                    suggestion='Add proper exception handling or at least log the error',
                    metadata={'tool': 'pattern-analysis', 'language': 'java'}
                ))

    def _check_java_sql_injection(self, code: str, filename: str, line_number: int, issues: List[Issue]):
        """Check for SQL injection risks in Java code."""
        if 'executeQuery' in code or 'executeUpdate' in code:
            if '+' in code or 'concat' in code.lower():
                issues.append(Issue(
                    type=IssueType.SECURITY,
                    severity=Severity.HIGH,
                    message='Possible SQL injection vulnerability - string concatenation in query',
                    file=filename,
                    line=line_number,
                    code='SQL_INJECTION',
                    suggestion='Use PreparedStatement with parameterized queries',
                    metadata={'tool': 'pattern-analysis', 'language': 'java'}
                ))

    def _run_checkstyle(self, files: List) -> List[Issue]:
        """Run Checkstyle on Java files."""
        issues = []
        file_paths = [f.filename for f in files]

        try:
            # Checkstyle command: checkstyle -f json -c /google_checks.xml file.java
            result = subprocess.run(
                ['checkstyle', '-f', 'json', '-c', '/google_checks.xml'] + file_paths,
                capture_output=True,
                text=True,
                timeout=60,
                check=False
            )  # nosec B603 B607

            if result.stdout:
                data = json.loads(result.stdout)

                for file_result in data.get('files', []):
                    filename = file_result.get('filename', '')

                    for error in file_result.get('errors', []):
                        issues.append(Issue(
                            type=IssueType.STYLE,
                            severity=self._map_checkstyle_severity(error.get('severity')),
                            message=error.get('message', ''),
                            file=filename,
                            line=error.get('line'),
                            column=error.get('column'),
                            metadata={'tool': 'checkstyle', 'language': 'java'}
                        ))

        except FileNotFoundError:
            self.logger.warning("Checkstyle not installed. Install: https://checkstyle.org/")
        except Exception as e:
            self.logger.error(f"Checkstyle error: {e}")

        return issues

    def _run_pmd(self, files: List) -> List[Issue]:
        """Run PMD on Java files."""
        issues = []
        file_paths = [f.filename for f in files]

        try:
            # PMD command: pmd -d file.java -f json -R rulesets/java/quickstart.xml
            result = subprocess.run(
                ['pmd', '-d', ','.join(file_paths), '-f', 'json', '-R', 'rulesets/java/quickstart.xml'],
                capture_output=True,
                text=True,
                timeout=60,
                check=False
            )  # nosec B603 B607

            if result.stdout:
                data = json.loads(result.stdout)

                for file_result in data.get('files', []):
                    filename = file_result.get('filename', '')

                    for violation in file_result.get('violations', []):
                        issues.append(Issue(
                            type=IssueType.QUALITY,
                            severity=self._map_pmd_severity(violation.get('priority')),
                            message=violation.get('description', ''),
                            file=filename,
                            line=violation.get('beginline'),
                            code=violation.get('rule'),
                            metadata={'tool': 'pmd', 'language': 'java'}
                        ))

        except FileNotFoundError:
            self.logger.warning("PMD not installed. Install: https://pmd.github.io/")
        except Exception as e:
            self.logger.error(f"PMD error: {e}")

        return issues

    # ========== SCALA ANALYSIS ==========

    def _analyze_scala(self, files: List, config: dict) -> List[Issue]:
        """Analyze Scala files."""
        issues = []
        tools = config.get('tools', ['scalastyle'])

        if 'scalastyle' in tools:
            issues.extend(self._run_scalastyle(files))

        return issues

    def _run_scalastyle(self, files: List) -> List[Issue]:
        """Run Scalastyle on Scala files."""
        issues = []
        file_paths = [f.filename for f in files]

        try:
            # Scalastyle command: scalastyle -c scalastyle_config.xml file.scala
            subprocess.run(
                ['scalastyle', '-c', 'scalastyle_config.xml', '--xmlOutput', 'scalastyle-output.xml'] + file_paths,
                capture_output=True,
                text=True,
                timeout=60,
                check=False
            )  # nosec B603 B607

            # Parse XML output (Scalastyle outputs XML by default)
            # Note: In production, use proper XML parsing with xml.etree.ElementTree
            if os.path.exists('scalastyle-output.xml'):
                self.logger.info("Scalastyle output generated")
                # Future enhancement: Parse XML and extract issues

        except FileNotFoundError:
            self.logger.warning("Scalastyle not installed. Install: http://www.scalastyle.org/")
        except Exception as e:
            self.logger.error(f"Scalastyle error: {e}")

        return issues

    # ========== JAVASCRIPT/TYPESCRIPT ANALYSIS ==========

    def _analyze_javascript_typescript(self, files: List, config: dict, language: str) -> List[Issue]:
        """Analyze JavaScript/TypeScript files."""
        issues = []
        tools = config.get('tools', ['eslint'])

        # First, try pattern-based analysis
        issues.extend(self._analyze_js_ts_patterns(files, language))

        # Only run external tools if installed
        if 'eslint' in tools:
            issues.extend(self._run_eslint(files, language))

        return issues

    def _analyze_js_ts_patterns(self, files: List, language: str) -> List[Issue]:
        """Analyze JS/TS code using pattern matching."""
        issues = []

        for file in files:
            if file.patch:
                file_issues = self._analyze_js_ts_file(file, language)
                issues.extend(file_issues)

        return issues

    def _analyze_js_ts_file(self, file, language: str) -> List[Issue]:
        """Analyze a single JS/TS file for issues."""
        issues = []
        lines = file.patch.split('\n')
        line_number = 0

        for line in lines:
            line_number = self._update_line_number(line, line_number)

            if line.startswith('@@') or not line.startswith('+'):
                if not line.startswith('-'):
                    line_number += 1
                continue

            code = line[1:]
            line_number += 1

            # Check for various JS/TS patterns
            self._check_js_patterns(code, file.filename, line_number, issues, language)
            self._check_eval_usage(code, file.filename, line_number, issues, language)
            self._check_hardcoded_secrets(code, file.filename, line_number, issues, language)

        return issues

    def _check_js_patterns(self, code, filename, line_number, issues, language):
        """Run all JS/TS pattern checks for a line of code."""
        # 1. Console usage
        if 'console.log(' in code or 'console.error(' in code or 'console.warn(' in code:
            issues.append(Issue(
                type=IssueType.STYLE,
                severity=Severity.LOW,
                message='Use proper logging framework instead of console statements',
                file=filename,
                line=line_number,
                code='NO_CONSOLE',
                suggestion='Replace with a proper logging library',
                metadata={'tool': 'pattern-analysis', 'language': language}
            ))

        # 2. Strict equality
        if ' == ' in code or ' != ' in code:
            if '===' not in code and '!==' not in code:
                issues.append(Issue(
                    type=IssueType.QUALITY,
                    severity=Severity.MEDIUM,
                    message='Use === or !== instead of == or !=',
                    file=filename,
                    line=line_number,
                    code='EQEQEQ',
                    suggestion='Use strict equality operators (=== or !==)',
                    metadata={'tool': 'pattern-analysis', 'language': language}
                ))

        # 3. var usage
        if code.strip().startswith('var '):
            issues.append(Issue(
                type=IssueType.QUALITY,
                severity=Severity.LOW,
                message='Use let or const instead of var',
                file=filename,
                line=line_number,
                code='NO_VAR',
                suggestion='Replace var with const (if not reassigned) or let',
                metadata={'tool': 'pattern-analysis', 'language': language}
            ))

        # 4. empty catch
        if code.strip().startswith('catch') and code.strip().endswith('{}'):
            issues.append(Issue(
                type=IssueType.QUALITY,
                severity=Severity.HIGH,
                message='Empty catch block',
                file=filename,
                line=line_number,
                code='NO_EMPTY_CATCH',
                suggestion='Handle the error or at least log it',
                metadata={'tool': 'pattern-analysis', 'language': language}
            ))

    def _run_eslint(self, files: List, language: str) -> List[Issue]:
        """Run ESLint on JavaScript/TypeScript files."""
        issues = []
        file_paths = [f.filename for f in files]

        try:
            result = subprocess.run(
                ['eslint', '-f', 'json'] + file_paths,
                capture_output=True,
                text=True,
                timeout=60,
                check=False
            )  # nosec B603 B607

            if result.stdout:
                eslint_issues = self._parse_eslint_output(result.stdout, language)
                issues.extend(eslint_issues)

        except FileNotFoundError:
            self.logger.warning("ESLint not installed. Install: npm install -g eslint")
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error(f"ESLint error: {e}")

        return issues

    def _parse_eslint_output(self, output: str, language: str) -> List[Issue]:
        """Parse ESLint JSON output and convert to Issues."""
        issues = []

        try:
            data = json.loads(output)

            for file_result in data:
                filename = file_result.get('filePath', '')
                messages = file_result.get('messages', [])

                for message in messages:
                    issue = self._create_eslint_issue(message, filename, language)
                    issues.append(issue)
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse ESLint output: {e}")

        return issues

    def _create_eslint_issue(self, message: dict, filename: str, language: str) -> Issue:
        """Create an Issue object from ESLint message."""
        severity_level = message.get('severity', 1)
        issue_type = IssueType.QUALITY if severity_level == 2 else IssueType.STYLE
        severity = Severity.MEDIUM if severity_level == 2 else Severity.LOW

        suggestion = None
        if 'fix' in message:
            suggestion = message.get('fix', {}).get('text')

        return Issue(
            type=issue_type,
            severity=severity,
            message=message.get('message', ''),
            file=filename,
            line=message.get('line'),
            column=message.get('column'),
            code=message.get('ruleId'),
            suggestion=suggestion,
            metadata={'tool': 'eslint', 'language': language}
        )

    # ========== HELPER METHODS ==========

    def _map_pylint_severity(self, pylint_type: str) -> Severity:
        """Map pylint message type to severity."""
        mapping = {
            'error': Severity.HIGH,
            'warning': Severity.MEDIUM,
            'convention': Severity.LOW,
            'refactor': Severity.LOW,
            'info': Severity.INFO
        }
        return mapping.get(pylint_type, Severity.MEDIUM)

    def _map_checkstyle_severity(self, checkstyle_severity: str) -> Severity:
        """Map Checkstyle severity to our severity."""
        mapping = {
            'error': Severity.HIGH,
            'warning': Severity.MEDIUM,
            'info': Severity.LOW
        }
        return mapping.get(checkstyle_severity.lower(), Severity.MEDIUM)

    def _map_pmd_severity(self, priority: int) -> Severity:
        """Map PMD priority to severity."""
        if priority <= 2:
            return Severity.HIGH
        if priority == 3:
            return Severity.MEDIUM
        return Severity.LOW
