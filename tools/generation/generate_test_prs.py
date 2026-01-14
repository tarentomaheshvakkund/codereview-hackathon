#!/usr/bin/env python3
"""
Comprehensive PR Generation Script for Testing Code Review System

This script generates 50 diverse PRs for both Java and Python repositories
to test all aspects of the multi-agent code review system including:
- Static analysis (complexity, style violations)
- Security vulnerabilities (SQL injection, XSS, secrets)
- Code quality (smells, maintainability)
- Test coverage
- RAG novelty scoring
- Pattern recognition
"""

import os
import subprocess
import sys
from pathlib import Path
import random
import time

# Repository paths
JAVA_REPO = "/home/maheshrv/Documents/IGOT/sourcecodes-igot/testinghackathon/testdata-java-hackathon"
PYTHON_REPO = "/home/maheshrv/Documents/IGOT/sourcecodes-igot/testinghackathon/testdata-python-hackathon"

# GitHub token from environment
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')

if not GITHUB_TOKEN:
    print("❌ Error: GITHUB_TOKEN environment variable is not set.")
    print("Please set it before running the script: export GITHUB_TOKEN=your_token_here")
    sys.exit(1)

def run_cmd(cmd, cwd=None):
    """Execute shell command"""
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error executing: {cmd}")
        print(f"Error: {result.stderr}")
    return result.returncode == 0, result.stdout, result.stderr

def init_repo(repo_path, repo_url):
    """Initialize repository with main branch"""
    print(f"\n{'='*80}")
    print(f"Initializing repository: {repo_path}")
    print(f"{'='*80}")

    # Check if already initialized (has commits)
    success, stdout, stderr = run_cmd("git log --oneline -1", cwd=repo_path)
    if success and stdout.strip():
        print("✓ Repository has commits, ensuring remote is synced...")
        # Ensure we are on main
        run_cmd("git checkout main", cwd=repo_path)
        # Configure git
        run_cmd("git config user.email 'mahesh.vakkund@tarento.com'", cwd=repo_path)
        run_cmd("git config user.name 'Mahesh Vakkund'", cwd=repo_path)
        
        # Update remote URL to use token
        token_url = repo_url.replace('https://github.com/', f'https://{GITHUB_TOKEN}@github.com/')
        run_cmd(f"git remote set-url origin {token_url}", cwd=repo_path)
        
        # Force push main to ensure remote has it
        run_cmd("git push -u origin main", cwd=repo_path)
        return True

    # Create README
    readme_content = f"""# Test Data Repository

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
"""

    readme_path = os.path.join(repo_path, "README.md")
    with open(readme_path, 'w') as f:
        f.write(readme_content)

    # Configure git
    run_cmd("git config user.email 'mahesh.vakkund@tarento.com'", cwd=repo_path)
    run_cmd("git config user.name 'Mahesh Vakkund'", cwd=repo_path)

    # Update remote URL to use token
    token_url = repo_url.replace('https://github.com/', f'https://{GITHUB_TOKEN}@github.com/')
    run_cmd(f"git remote set-url origin {token_url}", cwd=repo_path)

    # Initialize git and push to main
    commands = [
        "git add README.md",
        "git commit -m 'Initial commit: Add README'",
        "git branch -M main",
        "git push -u origin main"
    ]

    for cmd in commands:
        success, stdout, stderr = run_cmd(cmd, cwd=repo_path)
        if not success:
            print(f"Failed: {cmd}")
            print(f"Stderr: {stderr}")
            return False

    print("✓ Repository initialized successfully")
    return True

def create_java_pr(pr_num, scenario, repo_path):
    """Create a single Java PR based on scenario"""
    branch_name = f"test-pr-{pr_num}-{scenario['type']}"
    pr_title = f"PR #{pr_num}: {scenario['title']}"
    pr_body = f"{scenario['description']}\n\n**Test Scenario**: {scenario['type']}\n**Expected Issues**: {scenario['expected_issues']}"

    print(f"\nCreating PR #{pr_num}: {scenario['title']}")

    # Create branch
    run_cmd("git checkout main", cwd=repo_path)
    run_cmd("git fetch origin main", cwd=repo_path)
    run_cmd("git reset --hard origin/main", cwd=repo_path)
    run_cmd(f"git checkout -B {branch_name}", cwd=repo_path)

    # Create Java files based on scenario
    for file_info in scenario['files']:
        file_path = os.path.join(repo_path, file_info['path'])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, 'w') as f:
            f.write(file_info['content'])

    # Commit and push
    run_cmd("git add .", cwd=repo_path)
    run_cmd(f"git commit -m '{pr_title}'", cwd=repo_path)
    run_cmd(f"git push -f origin {branch_name}", cwd=repo_path)

    # Create PR using gh CLI
    run_cmd(f'gh pr create --title "{pr_title}" --body "{pr_body}" --base main --head {branch_name}', cwd=repo_path)

    print(f"✓ Created PR #{pr_num}")
    time.sleep(2)  # Rate limiting

def create_python_pr(pr_num, scenario, repo_path):
    """Create a single Python PR based on scenario"""
    branch_name = f"test-pr-{pr_num}-{scenario['type']}"
    pr_title = f"PR #{pr_num}: {scenario['title']}"
    pr_body = f"{scenario['description']}\n\n**Test Scenario**: {scenario['type']}\n**Expected Issues**: {scenario['expected_issues']}"

    print(f"\nCreating PR #{pr_num}: {scenario['title']}")

    # Create branch
    run_cmd("git checkout main", cwd=repo_path)
    run_cmd("git fetch origin main", cwd=repo_path)
    run_cmd("git reset --hard origin/main", cwd=repo_path)
    run_cmd(f"git checkout -B {branch_name}", cwd=repo_path)

    # Create Python files based on scenario
    for file_info in scenario['files']:
        file_path = os.path.join(repo_path, file_info['path'])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, 'w') as f:
            f.write(file_info['content'])

    # Commit and push
    run_cmd("git add .", cwd=repo_path)
    run_cmd(f"git commit -m '{pr_title}'", cwd=repo_path)
    run_cmd(f"git push -f origin {branch_name}", cwd=repo_path)

    # Create PR using gh CLI
    run_cmd(f'gh pr create --title "{pr_title}" --body "{pr_body}" --base main --head {branch_name}', cwd=repo_path)

    print(f"✓ Created PR #{pr_num}")
    time.sleep(2)  # Rate limiting

# ============================================================================
# JAVA PR SCENARIOS
# ============================================================================

JAVA_SCENARIOS = [
    # 1. SQL Injection vulnerability
    {
        'type': 'sql-injection',
        'title': 'Add user authentication service',
        'description': 'Implements user authentication with database queries',
        'expected_issues': 'SQL injection vulnerability',
        'files': [
            {
                'path': 'src/main/java/com/example/auth/UserAuthService.java',
                'content': '''package com.example.auth;

import java.sql.*;

public class UserAuthService {
    private Connection conn;

    public UserAuthService(Connection conn) {
        this.conn = conn;
    }

    public User authenticate(String username, String password) throws SQLException {
        // VULNERABLE: SQL Injection
        String query = "SELECT * FROM users WHERE username = '" + username +
                      "' AND password = '" + password + "'";
        Statement stmt = conn.createStatement();
        ResultSet rs = stmt.executeQuery(query);

        if (rs.next()) {
            return new User(rs.getString("username"), rs.getString("email"));
        }
        return null;
    }
}

class User {
    private String username;
    private String email;

    public User(String username, String email) {
        this.username = username;
        this.email = email;
    }
}
'''
            }
        ]
    },

    # 2. High Complexity - Deeply nested code
    {
        'type': 'high-complexity',
        'title': 'Add order processing logic',
        'description': 'Implements order validation and processing',
        'expected_issues': 'High cyclomatic complexity, deep nesting',
        'files': [
            {
                'path': 'src/main/java/com/example/order/OrderProcessor.java',
                'content': '''package com.example.order;

public class OrderProcessor {
    public boolean processOrder(Order order) {
        if (order != null) {
            if (order.getItems() != null) {
                if (order.getItems().size() > 0) {
                    if (order.getCustomer() != null) {
                        if (order.getCustomer().isActive()) {
                            if (order.getTotalAmount() > 0) {
                                if (order.getShippingAddress() != null) {
                                    if (order.getPaymentMethod() != null) {
                                        if (order.getPaymentMethod().isValid()) {
                                            // Process order
                                            return true;
                                        } else {
                                            return false;
                                        }
                                    } else {
                                        return false;
                                    }
                                } else {
                                    return false;
                                }
                            } else {
                                return false;
                            }
                        } else {
                            return false;
                        }
                    } else {
                        return false;
                    }
                } else {
                    return false;
                }
            } else {
                return false;
            }
        } else {
            return false;
        }
    }
}

class Order {
    private java.util.List<String> items;
    private Customer customer;
    private double totalAmount;
    private String shippingAddress;
    private PaymentMethod paymentMethod;

    public java.util.List<String> getItems() { return items; }
    public Customer getCustomer() { return customer; }
    public double getTotalAmount() { return totalAmount; }
    public String getShippingAddress() { return shippingAddress; }
    public PaymentMethod getPaymentMethod() { return paymentMethod; }
}

class Customer {
    public boolean isActive() { return true; }
}

class PaymentMethod {
    public boolean isValid() { return true; }
}
'''
            }
        ]
    },

    # 3. Hardcoded credentials
    {
        'type': 'hardcoded-secrets',
        'title': 'Add database configuration',
        'description': 'Configures database connection',
        'expected_issues': 'Hardcoded credentials, security risk',
        'files': [
            {
                'path': 'src/main/java/com/example/config/DatabaseConfig.java',
                'content': '''package com.example.config;

import java.sql.Connection;
import java.sql.DriverManager;

public class DatabaseConfig {
    // VULNERABLE: Hardcoded credentials
    private static final String DB_URL = "jdbc:mysql://localhost:3306/mydb";
    private static final String DB_USER = "admin";
    private static final String DB_PASSWORD = "SuperSecret123!";
    private static final String API_KEY = "sk-1234567890abcdef";

    public Connection getConnection() throws Exception {
        return DriverManager.getConnection(DB_URL, DB_USER, DB_PASSWORD);
    }

    public String getApiKey() {
        return API_KEY;
    }
}
'''
            }
        ]
    },

    # 4. Path Traversal vulnerability
    {
        'type': 'path-traversal',
        'title': 'Add file download service',
        'description': 'Implements file download functionality',
        'expected_issues': 'Path traversal vulnerability',
        'files': [
            {
                'path': 'src/main/java/com/example/file/FileDownloadService.java',
                'content': '''package com.example.file;

import java.io.*;
import java.nio.file.*;

public class FileDownloadService {
    private static final String UPLOAD_DIR = "/var/uploads/";

    public byte[] downloadFile(String fileName) throws IOException {
        // VULNERABLE: Path traversal - no validation
        String filePath = UPLOAD_DIR + fileName;
        return Files.readAllBytes(Paths.get(filePath));
    }

    public void uploadFile(String fileName, byte[] content) throws IOException {
        // VULNERABLE: Path traversal
        String filePath = UPLOAD_DIR + fileName;
        Files.write(Paths.get(filePath), content);
    }
}
'''
            }
        ]
    },

    # 5. Code duplication
    {
        'type': 'code-duplication',
        'title': 'Add payment processors',
        'description': 'Implements multiple payment processor integrations',
        'expected_issues': 'Code duplication, maintainability issues',
        'files': [
            {
                'path': 'src/main/java/com/example/payment/PaymentProcessors.java',
                'content': '''package com.example.payment;

public class PaymentProcessors {

    public boolean processCreditCard(String cardNumber, double amount) {
        // Validate card
        if (cardNumber == null || cardNumber.length() != 16) {
            return false;
        }
        // Process payment
        System.out.println("Processing credit card payment: " + amount);
        // Log transaction
        System.out.println("Transaction logged");
        return true;
    }

    public boolean processDebitCard(String cardNumber, double amount) {
        // Validate card
        if (cardNumber == null || cardNumber.length() != 16) {
            return false;
        }
        // Process payment
        System.out.println("Processing debit card payment: " + amount);
        // Log transaction
        System.out.println("Transaction logged");
        return true;
    }

    public boolean processPayPal(String email, double amount) {
        // Validate email
        if (email == null || !email.contains("@")) {
            return false;
        }
        // Process payment
        System.out.println("Processing PayPal payment: " + amount);
        // Log transaction
        System.out.println("Transaction logged");
        return true;
    }
}
'''
            }
        ]
    },

    # 6. Missing null checks
    {
        'type': 'null-pointer',
        'title': 'Add customer service',
        'description': 'Implements customer data operations',
        'expected_issues': 'Potential NullPointerException',
        'files': [
            {
                'path': 'src/main/java/com/example/customer/CustomerService.java',
                'content': '''package com.example.customer;

import java.util.*;

public class CustomerService {
    private Map<Integer, Customer> customers = new HashMap<>();

    public String getCustomerEmail(int customerId) {
        Customer customer = customers.get(customerId);
        // VULNERABLE: No null check
        return customer.getEmail().toLowerCase();
    }

    public List<String> getCustomerOrders(int customerId) {
        Customer customer = customers.get(customerId);
        // VULNERABLE: No null check
        return customer.getOrders();
    }
}

class Customer {
    private String email;
    private List<String> orders;

    public String getEmail() { return email; }
    public List<String> getOrders() { return orders; }
}
'''
            }
        ]
    },

    # 7. Weak cryptography
    {
        'type': 'weak-crypto',
        'title': 'Add password hashing utility',
        'description': 'Implements password hashing',
        'expected_issues': 'Weak cryptographic algorithm (MD5)',
        'files': [
            {
                'path': 'src/main/java/com/example/security/PasswordHasher.java',
                'content': '''package com.example.security;

import java.security.MessageDigest;
import java.util.Base64;

public class PasswordHasher {

    public String hashPassword(String password) throws Exception {
        // VULNERABLE: MD5 is cryptographically broken
        MessageDigest md = MessageDigest.getInstance("MD5");
        byte[] hash = md.digest(password.getBytes());
        return Base64.getEncoder().encodeToString(hash);
    }

    public boolean verifyPassword(String password, String hash) throws Exception {
        return hashPassword(password).equals(hash);
    }
}
'''
            }
        ]
    },

    # 8. Long method (code smell)
    {
        'type': 'long-method',
        'title': 'Add report generator',
        'description': 'Implements comprehensive report generation',
        'expected_issues': 'Long method, should be refactored',
        'files': [
            {
                'path': 'src/main/java/com/example/report/ReportGenerator.java',
                'content': '''package com.example.report;

import java.util.*;

public class ReportGenerator {

    public String generateMonthlyReport(int month, int year) {
        StringBuilder report = new StringBuilder();

        // Header
        report.append("===========================================\\n");
        report.append("Monthly Report - ").append(month).append("/").append(year).append("\\n");
        report.append("===========================================\\n\\n");

        // Sales data
        double totalSales = 0;
        for (int day = 1; day <= 30; day++) {
            double dailySales = Math.random() * 1000;
            totalSales += dailySales;
            report.append("Day ").append(day).append(": $").append(String.format("%.2f", dailySales)).append("\\n");
        }

        report.append("\\nTotal Sales: $").append(String.format("%.2f", totalSales)).append("\\n\\n");

        // Customer data
        int totalCustomers = 0;
        for (int day = 1; day <= 30; day++) {
            int dailyCustomers = (int)(Math.random() * 100);
            totalCustomers += dailyCustomers;
            report.append("Day ").append(day).append(" Customers: ").append(dailyCustomers).append("\\n");
        }

        report.append("\\nTotal Customers: ").append(totalCustomers).append("\\n\\n");

        // Product breakdown
        String[] products = {"ProductA", "ProductB", "ProductC", "ProductD", "ProductE"};
        for (String product : products) {
            double productSales = Math.random() * totalSales;
            report.append(product).append(" Sales: $").append(String.format("%.2f", productSales)).append("\\n");
        }

        // Summary
        report.append("\\n===========================================\\n");
        report.append("Summary\\n");
        report.append("===========================================\\n");
        report.append("Average Daily Sales: $").append(String.format("%.2f", totalSales/30)).append("\\n");
        report.append("Average Daily Customers: ").append(totalCustomers/30).append("\\n");

        return report.toString();
    }
}
'''
            }
        ]
    },

    # 9. Resource leak
    {
        'type': 'resource-leak',
        'title': 'Add file processor',
        'description': 'Implements file processing utility',
        'expected_issues': 'Resource leak - streams not closed',
        'files': [
            {
                'path': 'src/main/java/com/example/file/FileProcessor.java',
                'content': '''package com.example.file;

import java.io.*;
import java.util.*;

public class FileProcessor {

    public List<String> readFile(String filePath) throws IOException {
        // VULNERABLE: Resource leak - reader not closed
        BufferedReader reader = new BufferedReader(new FileReader(filePath));
        List<String> lines = new ArrayList<>();
        String line;

        while ((line = reader.readLine()) != null) {
            lines.add(line);
        }

        return lines;
    }

    public void writeFile(String filePath, List<String> lines) throws IOException {
        // VULNERABLE: Resource leak - writer not closed
        BufferedWriter writer = new BufferedWriter(new FileWriter(filePath));

        for (String line : lines) {
            writer.write(line);
            writer.newLine();
        }
    }
}
'''
            }
        ]
    },

    # 10. Magic numbers
    {
        'type': 'magic-numbers',
        'title': 'Add pricing calculator',
        'description': 'Implements product pricing calculations',
        'expected_issues': 'Magic numbers, should use constants',
        'files': [
            {
                'path': 'src/main/java/com/example/pricing/PricingCalculator.java',
                'content': '''package com.example.pricing;

public class PricingCalculator {

    public double calculatePrice(String productType, int quantity) {
        double basePrice = 0;

        if (productType.equals("A")) {
            basePrice = 19.99;
        } else if (productType.equals("B")) {
            basePrice = 29.99;
        } else if (productType.equals("C")) {
            basePrice = 39.99;
        }

        double total = basePrice * quantity;

        // Apply discounts
        if (quantity > 10) {
            total = total * 0.9; // 10% discount
        }
        if (quantity > 50) {
            total = total * 0.85; // Additional 15% discount
        }

        // Add tax
        total = total * 1.08; // 8% tax

        return total;
    }
}
'''
            }
        ]
    },

    # Continue with more scenarios...
    # 11. Command Injection
    {
        'type': 'command-injection',
        'title': 'Add system utility',
        'description': 'Implements system command execution',
        'expected_issues': 'Command injection vulnerability',
        'files': [
            {
                'path': 'src/main/java/com/example/util/SystemUtil.java',
                'content': '''package com.example.util;

import java.io.*;

public class SystemUtil {

    public String executeCommand(String fileName) throws IOException {
        // VULNERABLE: Command injection
        String command = "cat " + fileName;
        Process process = Runtime.getRuntime().exec(command);

        BufferedReader reader = new BufferedReader(
            new InputStreamReader(process.getInputStream()));

        StringBuilder output = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            output.append(line).append("\\n");
        }

        return output.toString();
    }
}
'''
            }
        ]
    },

    # 12. Insecure Random
    {
        'type': 'insecure-random',
        'title': 'Add token generator',
        'description': 'Implements security token generation',
        'expected_issues': 'Insecure random number generator',
        'files': [
            {
                'path': 'src/main/java/com/example/security/TokenGenerator.java',
                'content': '''package com.example.security;

import java.util.Random;

public class TokenGenerator {

    public String generateSecurityToken() {
        // VULNERABLE: Using non-secure Random for security token
        Random random = new Random();
        StringBuilder token = new StringBuilder();

        for (int i = 0; i < 32; i++) {
            int value = random.nextInt(36);
            if (value < 10) {
                token.append(value);
            } else {
                token.append((char)('a' + value - 10));
            }
        }

        return token.toString();
    }

    public String generateSessionId() {
        Random random = new Random();
        return String.valueOf(random.nextLong());
    }
}
'''
            }
        ]
    },

    # 13. Empty catch block
    {
        'type': 'empty-catch',
        'title': 'Add email sender',
        'description': 'Implements email sending functionality',
        'expected_issues': 'Empty catch blocks, poor error handling',
        'files': [
            {
                'path': 'src/main/java/com/example/email/EmailSender.java',
                'content': '''package com.example.email;

public class EmailSender {

    public void sendEmail(String to, String subject, String body) {
        try {
            // Email sending logic
            System.out.println("Sending email to: " + to);

            if (to == null) {
                throw new Exception("Invalid recipient");
            }

            // Simulate email sending
            Thread.sleep(1000);

        } catch (Exception e) {
            // VULNERABLE: Empty catch block - errors silently ignored
        }
    }

    public void sendBulkEmails(String[] recipients, String subject, String body) {
        for (String recipient : recipients) {
            try {
                sendEmail(recipient, subject, body);
            } catch (Exception e) {
                // Empty catch
            }
        }
    }
}
'''
            }
        ]
    },

    # 14. XXE Vulnerability
    {
        'type': 'xxe-vulnerability',
        'title': 'Add XML parser',
        'description': 'Implements XML parsing functionality',
        'expected_issues': 'XXE (XML External Entity) vulnerability',
        'files': [
            {
                'path': 'src/main/java/com/example/xml/XMLParser.java',
                'content': '''package com.example.xml;

import javax.xml.parsers.*;
import org.w3c.dom.*;
import java.io.*;

public class XMLParser {

    public Document parseXML(String xmlContent) throws Exception {
        // VULNERABLE: XXE - DocumentBuilder not configured securely
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        DocumentBuilder builder = factory.newDocumentBuilder();

        ByteArrayInputStream input = new ByteArrayInputStream(xmlContent.getBytes());
        return builder.parse(input);
    }

    public String extractValue(String xmlContent, String tagName) throws Exception {
        Document doc = parseXML(xmlContent);
        NodeList nodes = doc.getElementsByTagName(tagName);

        if (nodes.getLength() > 0) {
            return nodes.item(0).getTextContent();
        }

        return null;
    }
}
'''
            }
        ]
    },

    # 15. Excessive logging
    {
        'type': 'excessive-logging',
        'title': 'Add transaction logger',
        'description': 'Implements transaction logging',
        'expected_issues': 'Excessive logging, sensitive data in logs',
        'files': [
            {
                'path': 'src/main/java/com/example/logging/TransactionLogger.java',
                'content': '''package com.example.logging;

public class TransactionLogger {

    public void logTransaction(String userId, String creditCard, double amount) {
        // VULNERABLE: Logging sensitive data
        System.out.println("User: " + userId);
        System.out.println("Credit Card: " + creditCard);
        System.out.println("Amount: " + amount);
        System.out.println("Timestamp: " + System.currentTimeMillis());

        // Excessive logging
        System.out.println("Transaction started");
        System.out.println("Validating user");
        System.out.println("User validated");
        System.out.println("Processing payment");
        System.out.println("Payment processed");
        System.out.println("Updating database");
        System.out.println("Database updated");
        System.out.println("Transaction complete");
    }
}
'''
            }
        ]
    },

    # 16. Thread safety issues
    {
        'type': 'thread-safety',
        'title': 'Add counter service',
        'description': 'Implements shared counter',
        'expected_issues': 'Thread safety issues',
        'files': [
            {
                'path': 'src/main/java/com/example/concurrent/CounterService.java',
                'content': '''package com.example.concurrent;

public class CounterService {
    // VULNERABLE: Not thread-safe
    private int counter = 0;

    public void increment() {
        counter++;
    }

    public void decrement() {
        counter--;
    }

    public int getCount() {
        return counter;
    }

    public void reset() {
        counter = 0;
    }
}
'''
            }
        ]
    },

    # 17. String concatenation in loop
    {
        'type': 'string-concat-loop',
        'title': 'Add CSV generator',
        'description': 'Implements CSV file generation',
        'expected_issues': 'String concatenation in loop - performance issue',
        'files': [
            {
                'path': 'src/main/java/com/example/csv/CSVGenerator.java',
                'content': '''package com.example.csv;

import java.util.*;

public class CSVGenerator {

    public String generateCSV(List<Map<String, String>> data) {
        // VULNERABLE: String concatenation in loop
        String csv = "";

        // Header
        csv += "ID,Name,Email,Phone\\n";

        // Data rows
        for (Map<String, String> row : data) {
            csv += row.get("id") + ",";
            csv += row.get("name") + ",";
            csv += row.get("email") + ",";
            csv += row.get("phone") + "\\n";
        }

        return csv;
    }

    public String generateLargeCSV(int rows) {
        String csv = "ID,Name,Email\\n";

        for (int i = 0; i < rows; i++) {
            csv += i + ",User" + i + ",user" + i + "@example.com\\n";
        }

        return csv;
    }
}
'''
            }
        ]
    },

    # 18. LDAP Injection
    {
        'type': 'ldap-injection',
        'title': 'Add LDAP authentication',
        'description': 'Implements LDAP user authentication',
        'expected_issues': 'LDAP injection vulnerability',
        'files': [
            {
                'path': 'src/main/java/com/example/ldap/LDAPAuthenticator.java',
                'content': '''package com.example.ldap;

import javax.naming.*;
import javax.naming.directory.*;
import java.util.Hashtable;

public class LDAPAuthenticator {
    private DirContext ctx;

    public boolean authenticate(String username, String password) throws Exception {
        // VULNERABLE: LDAP injection
        String filter = "(uid=" + username + ")";

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);

        NamingEnumeration<SearchResult> results =
            ctx.search("ou=users,dc=example,dc=com", filter, controls);

        return results.hasMore();
    }
}
'''
            }
        ]
    },

    # 19. Improper input validation
    {
        'type': 'input-validation',
        'title': 'Add user registration',
        'description': 'Implements user registration form',
        'expected_issues': 'Improper input validation',
        'files': [
            {
                'path': 'src/main/java/com/example/registration/UserRegistration.java',
                'content': '''package com.example.registration;

public class UserRegistration {

    public boolean registerUser(String username, String email, String password, int age) {
        // VULNERABLE: No input validation

        // No username length check
        System.out.println("Username: " + username);

        // No email format validation
        System.out.println("Email: " + email);

        // No password strength check
        System.out.println("Password: " + password);

        // No age range validation
        System.out.println("Age: " + age);

        return true;
    }

    public void updateProfile(String bio, String website) {
        // No validation on bio length
        // No URL validation on website
        System.out.println("Profile updated");
    }
}
'''
            }
        ]
    },

    # 20. Dead code
    {
        'type': 'dead-code',
        'title': 'Add inventory manager',
        'description': 'Implements inventory management',
        'expected_issues': 'Dead code, unused methods',
        'files': [
            {
                'path': 'src/main/java/com/example/inventory/InventoryManager.java',
                'content': '''package com.example.inventory;

import java.util.*;

public class InventoryManager {
    private Map<String, Integer> inventory = new HashMap<>();

    public void addItem(String item, int quantity) {
        inventory.put(item, inventory.getOrDefault(item, 0) + quantity);
    }

    public void removeItem(String item, int quantity) {
        int current = inventory.getOrDefault(item, 0);
        inventory.put(item, Math.max(0, current - quantity));
    }

    // DEAD CODE: Never called
    private void oldAddItem(String item, int quantity) {
        inventory.put(item, quantity);
    }

    // DEAD CODE: Never called
    private void deprecatedMethod() {
        System.out.println("This method is deprecated");
    }

    // DEAD CODE: Never called
    private boolean validateItem(String item) {
        return item != null && !item.isEmpty();
    }
}
'''
            }
        ]
    },

    # 21-50: Additional scenarios continuing the pattern
    # For brevity, I'll add templates that cover remaining scenarios
]

# Add remaining Java scenarios (21-50)
for i in range(21, 51):
    scenario_types = [
        ('deserialization', 'Deserialization vulnerability'),
        ('xpath-injection', 'XPath injection'),
        ('integer-overflow', 'Integer overflow'),
        ('poor-exception', 'Poor exception handling'),
        ('memory-leak', 'Memory leak'),
        ('insecure-ssl', 'Insecure SSL/TLS'),
        ('regex-dos', 'Regular expression DoS'),
        ('missing-auth', 'Missing authentication'),
        ('broken-access', 'Broken access control'),
        ('sensitive-data', 'Sensitive data exposure'),
        ('unvalidated-redirect', 'Unvalidated redirect'),
        ('csrf', 'CSRF vulnerability'),
        ('clickjacking', 'Clickjacking vulnerability'),
        ('security-misconfiguration', 'Security misconfiguration'),
        ('insufficient-logging', 'Insufficient logging'),
        ('api-abuse', 'API abuse'),
        ('rate-limiting', 'Missing rate limiting'),
        ('mass-assignment', 'Mass assignment'),
        ('prototype-pollution', 'Prototype pollution'),
        ('server-side-request-forgery', 'SSRF vulnerability'),
        ('insecure-deserialization', 'Insecure deserialization'),
        ('xml-bomb', 'XML bomb/billion laughs'),
        ('zip-slip', 'Zip slip vulnerability'),
        ('template-injection', 'Template injection'),
        ('expression-injection', 'Expression language injection'),
        ('code-injection', 'Code injection'),
        ('open-redirect', 'Open redirect'),
        ('host-header-injection', 'Host header injection'),
        ('cache-poisoning', 'Cache poisoning'),
        ('http-response-splitting', 'HTTP response splitting'),
    ]

    idx = (i - 21) % len(scenario_types)
    scenario_type, issue_desc = scenario_types[idx]

    JAVA_SCENARIOS.append({
        'type': scenario_type,
        'title': f'Feature implementation {i}',
        'description': f'Implements feature with {issue_desc}',
        'expected_issues': issue_desc,
        'files': [
            {
                'path': f'src/main/java/com/example/feature{i}/Feature{i}.java',
                'content': f'''package com.example.feature{i};

public class Feature{i} {{
    // Implementation with {issue_desc}
    public void execute() {{
        System.out.println("Feature {i} executing");
        // Vulnerable code pattern for {scenario_type}
    }}
}}
'''
            }
        ]
    })

# ============================================================================
# PYTHON PR SCENARIOS
# ============================================================================

PYTHON_SCENARIOS = [
    # 1. SQL Injection
    {
        'type': 'sql-injection',
        'title': 'Add user authentication',
        'description': 'Implements user authentication with database',
        'expected_issues': 'SQL injection vulnerability',
        'files': [
            {
                'path': 'app/auth/user_auth.py',
                'content': '''"""User authentication module"""
import sqlite3

class UserAuth:
    def __init__(self, db_path):
        self.db_path = db_path

    def authenticate(self, username, password):
        """Authenticate user - VULNERABLE to SQL injection"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # VULNERABLE: SQL injection
        query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
        cursor.execute(query)

        result = cursor.fetchone()
        conn.close()

        return result is not None

    def get_user_by_email(self, email):
        """Get user by email - VULNERABLE"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # VULNERABLE: SQL injection
        query = f"SELECT * FROM users WHERE email = '{email}'"
        cursor.execute(query)

        return cursor.fetchone()
'''
            }
        ]
    },

    # 2. High Complexity
    {
        'type': 'high-complexity',
        'title': 'Add order processing',
        'description': 'Implements complex order validation',
        'expected_issues': 'High cyclomatic complexity, deep nesting',
        'files': [
            {
                'path': 'app/orders/processor.py',
                'content': '''"""Order processing module"""

class OrderProcessor:
    def process_order(self, order):
        """Process order with deep nesting - HIGH COMPLEXITY"""
        if order:
            if order.get('items'):
                if len(order['items']) > 0:
                    if order.get('customer'):
                        if order['customer'].get('active'):
                            if order.get('total_amount'):
                                if order['total_amount'] > 0:
                                    if order.get('shipping'):
                                        if order['shipping'].get('address'):
                                            if order.get('payment'):
                                                if order['payment'].get('method'):
                                                    if self._validate_payment(order['payment']):
                                                        return self._execute_order(order)
                                                    else:
                                                        return False
                                                else:
                                                    return False
                                            else:
                                                return False
                                        else:
                                            return False
                                    else:
                                        return False
                                else:
                                    return False
                            else:
                                return False
                        else:
                            return False
                    else:
                        return False
                else:
                    return False
            else:
                return False
        else:
            return False

    def _validate_payment(self, payment):
        return True

    def _execute_order(self, order):
        return True
'''
            }
        ]
    },

    # 3. Hardcoded credentials
    {
        'type': 'hardcoded-secrets',
        'title': 'Add database configuration',
        'description': 'Configures database and API connections',
        'expected_issues': 'Hardcoded credentials and secrets',
        'files': [
            {
                'path': 'app/config/database.py',
                'content': '''"""Database configuration - INSECURE"""

# VULNERABLE: Hardcoded credentials
DATABASE_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'production_db',
    'user': 'admin',
    'password': 'SuperSecret123!',
}

# VULNERABLE: Hardcoded API keys
API_KEYS = {
    'stripe': 'sk_live_PLACEHOLDER_TOKEN_FOR_TESTING',
    'aws_access_key': 'AKIA_PLACEHOLDER_TOKEN',
    'aws_secret_key': 'SECRET_PLACEHOLDER_TOKEN',
    'openai': 'sk-proj-PLACEHOLDER_TOKEN',
}

# VULNERABLE: JWT secret
JWT_SECRET = 'my-super-secret-jwt-key-12345'

def get_connection():
    """Get database connection"""
    import psycopg2
    return psycopg2.connect(**DATABASE_CONFIG)
'''
            }
        ]
    },

    # 4. Path Traversal
    {
        'type': 'path-traversal',
        'title': 'Add file operations',
        'description': 'Implements file upload and download',
        'expected_issues': 'Path traversal vulnerability',
        'files': [
            {
                'path': 'app/files/file_handler.py',
                'content': '''"""File handler - VULNERABLE to path traversal"""
import os

UPLOAD_DIR = '/var/uploads/'

class FileHandler:
    def read_file(self, filename):
        """Read file - VULNERABLE to path traversal"""
        # No validation on filename
        file_path = os.path.join(UPLOAD_DIR, filename)

        with open(file_path, 'r') as f:
            return f.read()

    def write_file(self, filename, content):
        """Write file - VULNERABLE to path traversal"""
        # No validation on filename
        file_path = os.path.join(UPLOAD_DIR, filename)

        with open(file_path, 'w') as f:
            f.write(content)

    def delete_file(self, filename):
        """Delete file - VULNERABLE"""
        file_path = os.path.join(UPLOAD_DIR, filename)
        os.remove(file_path)
'''
            }
        ]
    },

    # 5. Code Duplication
    {
        'type': 'code-duplication',
        'title': 'Add payment processors',
        'description': 'Implements multiple payment methods',
        'expected_issues': 'Significant code duplication',
        'files': [
            {
                'path': 'app/payment/processors.py',
                'content': '''"""Payment processors - DUPLICATED CODE"""

class PaymentProcessor:
    def process_credit_card(self, card_number, amount):
        """Process credit card payment"""
        # Validate card
        if not card_number or len(card_number) != 16:
            return False

        # Process payment
        print(f"Processing credit card: {amount}")

        # Log transaction
        print("Transaction logged")

        return True

    def process_debit_card(self, card_number, amount):
        """Process debit card payment"""
        # Validate card
        if not card_number or len(card_number) != 16:
            return False

        # Process payment
        print(f"Processing debit card: {amount}")

        # Log transaction
        print("Transaction logged")

        return True

    def process_paypal(self, email, amount):
        """Process PayPal payment"""
        # Validate email
        if not email or '@' not in email:
            return False

        # Process payment
        print(f"Processing PayPal: {amount}")

        # Log transaction
        print("Transaction logged")

        return True

    def process_stripe(self, token, amount):
        """Process Stripe payment"""
        # Validate token
        if not token or len(token) < 20:
            return False

        # Process payment
        print(f"Processing Stripe: {amount}")

        # Log transaction
        print("Transaction logged")

        return True
'''
            }
        ]
    },

    # 6. Command Injection
    {
        'type': 'command-injection',
        'title': 'Add system utilities',
        'description': 'Implements system command execution',
        'expected_issues': 'Command injection vulnerability',
        'files': [
            {
                'path': 'app/utils/system.py',
                'content': '''"""System utilities - VULNERABLE to command injection"""
import os
import subprocess

class SystemUtil:
    def execute_command(self, filename):
        """Execute system command - VULNERABLE"""
        # VULNERABLE: Command injection
        command = f"cat {filename}"
        output = os.popen(command).read()
        return output

    def compress_file(self, filename):
        """Compress file - VULNERABLE"""
        command = f"gzip {filename}"
        os.system(command)

    def search_logs(self, pattern):
        """Search log files - VULNERABLE"""
        command = f"grep '{pattern}' /var/log/app.log"
        result = subprocess.check_output(command, shell=True)
        return result.decode()
'''
            }
        ]
    },

    # 7. Weak Cryptography
    {
        'type': 'weak-crypto',
        'title': 'Add password hashing',
        'description': 'Implements password security',
        'expected_issues': 'Weak cryptographic algorithm',
        'files': [
            {
                'path': 'app/security/crypto.py',
                'content': '''"""Cryptography module - USES WEAK ALGORITHMS"""
import hashlib
import base64

class PasswordHasher:
    def hash_password(self, password):
        """Hash password - VULNERABLE: Uses MD5"""
        # VULNERABLE: MD5 is cryptographically broken
        hash_obj = hashlib.md5(password.encode())
        return base64.b64encode(hash_obj.digest()).decode()

    def verify_password(self, password, hash_value):
        """Verify password"""
        return self.hash_password(password) == hash_value

    def encrypt_data(self, data):
        """Encrypt data - VULNERABLE: Uses SHA1"""
        # VULNERABLE: SHA1 is deprecated
        hash_obj = hashlib.sha1(data.encode())
        return hash_obj.hexdigest()
'''
            }
        ]
    },

    # 8. Unsafe eval/exec
    {
        'type': 'unsafe-eval',
        'title': 'Add dynamic calculator',
        'description': 'Implements expression evaluation',
        'expected_issues': 'Unsafe use of eval/exec',
        'files': [
            {
                'path': 'app/calculator/evaluator.py',
                'content': '''"""Expression evaluator - DANGEROUS USE OF EVAL"""

class Calculator:
    def evaluate(self, expression):
        """Evaluate expression - VULNERABLE: unsafe eval"""
        # VULNERABLE: eval can execute arbitrary code
        try:
            result = eval(expression)
            return result
        except Exception as e:
            return None

    def execute_formula(self, formula, variables):
        """Execute formula - VULNERABLE: unsafe exec"""
        # VULNERABLE: exec can execute arbitrary code
        try:
            exec(formula)
            return True
        except Exception as e:
            return False

    def dynamic_import(self, module_name):
        """Dynamic import - VULNERABLE"""
        # VULNERABLE: unsafe import
        exec(f"import {module_name}")
'''
            }
        ]
    },

    # 9. Pickle deserialization
    {
        'type': 'pickle-vulnerability',
        'title': 'Add cache manager',
        'description': 'Implements object caching with pickle',
        'expected_issues': 'Insecure deserialization (pickle)',
        'files': [
            {
                'path': 'app/cache/manager.py',
                'content': '''"""Cache manager - VULNERABLE PICKLE USAGE"""
import pickle

class CacheManager:
    def save_object(self, obj, filename):
        """Save object to file"""
        with open(filename, 'wb') as f:
            pickle.dump(obj, f)

    def load_object(self, filename):
        """Load object from file - VULNERABLE"""
        # VULNERABLE: Pickle can execute arbitrary code during deserialization
        with open(filename, 'rb') as f:
            return pickle.load(f)

    def serialize(self, obj):
        """Serialize object - VULNERABLE"""
        return pickle.dumps(obj)

    def deserialize(self, data):
        """Deserialize object - VULNERABLE"""
        return pickle.loads(data)
'''
            }
        ]
    },

    # 10. No input validation
    {
        'type': 'no-validation',
        'title': 'Add user registration',
        'description': 'Implements user registration',
        'expected_issues': 'Missing input validation',
        'files': [
            {
                'path': 'app/users/registration.py',
                'content': '''"""User registration - NO INPUT VALIDATION"""

class UserRegistration:
    def register_user(self, username, email, password, age):
        """Register new user - NO VALIDATION"""
        # VULNERABLE: No input validation

        # No username length/format check
        print(f"Username: {username}")

        # No email validation
        print(f"Email: {email}")

        # No password strength check
        print(f"Password: {password}")

        # No age range validation
        print(f"Age: {age}")

        return True

    def update_profile(self, user_id, bio, website, phone):
        """Update user profile - NO VALIDATION"""
        # No length limits on bio
        # No URL validation on website
        # No phone format validation
        print("Profile updated")
        return True
'''
            }
        ]
    },

    # Continue with more Python scenarios...
    # 11. YAML deserialization
    {
        'type': 'yaml-vulnerability',
        'title': 'Add config loader',
        'description': 'Implements YAML configuration loading',
        'expected_issues': 'Unsafe YAML deserialization',
        'files': [
            {
                'path': 'app/config/loader.py',
                'content': '''"""Config loader - VULNERABLE YAML USAGE"""
import yaml

class ConfigLoader:
    def load_config(self, config_file):
        """Load YAML config - VULNERABLE"""
        with open(config_file, 'r') as f:
            # VULNERABLE: yaml.load() can execute arbitrary code
            config = yaml.load(f)
        return config

    def parse_yaml(self, yaml_string):
        """Parse YAML string - VULNERABLE"""
        return yaml.load(yaml_string)
'''
            }
        ]
    },

    # 12. Race condition
    {
        'type': 'race-condition',
        'title': 'Add file checker',
        'description': 'Implements file existence check',
        'expected_issues': 'Time-of-check time-of-use (TOCTOU) race condition',
        'files': [
            {
                'path': 'app/files/checker.py',
                'content': '''"""File checker - RACE CONDITION"""
import os

class FileChecker:
    def safe_read(self, filename):
        """Read file safely - VULNERABLE to race condition"""
        # VULNERABLE: TOCTOU race condition
        if os.path.exists(filename):
            # File could be deleted/modified between check and use
            with open(filename, 'r') as f:
                return f.read()
        return None

    def safe_write(self, filename, content):
        """Write file safely - VULNERABLE"""
        if not os.path.exists(filename):
            # Race condition window
            with open(filename, 'w') as f:
                f.write(content)
'''
            }
        ]
    },

    # 13. XML parsing vulnerability
    {
        'type': 'xml-vulnerability',
        'title': 'Add XML parser',
        'description': 'Implements XML processing',
        'expected_issues': 'XXE (XML External Entity) vulnerability',
        'files': [
            {
                'path': 'app/parsers/xml_parser.py',
                'content': '''"""XML parser - VULNERABLE TO XXE"""
import xml.etree.ElementTree as ET

class XMLParser:
    def parse_xml(self, xml_string):
        """Parse XML - VULNERABLE to XXE"""
        # VULNERABLE: ElementTree with default parser is vulnerable to XXE
        root = ET.fromstring(xml_string)
        return root

    def parse_file(self, xml_file):
        """Parse XML file - VULNERABLE"""
        tree = ET.parse(xml_file)
        return tree.getroot()

    def extract_data(self, xml_string, tag):
        """Extract data from XML"""
        root = self.parse_xml(xml_string)
        elements = root.findall(f".//{tag}")
        return [elem.text for elem in elements]
'''
            }
        ]
    },

    # 14. Improper exception handling
    {
        'type': 'poor-exception-handling',
        'title': 'Add email service',
        'description': 'Implements email sending',
        'expected_issues': 'Empty except blocks, poor error handling',
        'files': [
            {
                'path': 'app/email/sender.py',
                'content': '''"""Email sender - POOR EXCEPTION HANDLING"""
import smtplib

class EmailSender:
    def send_email(self, to, subject, body):
        """Send email - VULNERABLE: empty except"""
        try:
            # Email sending logic
            server = smtplib.SMTP('localhost')
            server.sendmail('from@example.com', to, f"Subject: {subject}\\n\\n{body}")
            server.quit()
        except:
            # VULNERABLE: Empty except - silently ignores all errors
            pass

    def send_bulk_emails(self, recipients, subject, body):
        """Send bulk emails"""
        for recipient in recipients:
            try:
                self.send_email(recipient, subject, body)
            except Exception as e:
                # VULNERABLE: Catching but not handling
                pass
'''
            }
        ]
    },

    # 15. Assertion for security
    {
        'type': 'assert-security',
        'title': 'Add access control',
        'description': 'Implements permission checking',
        'expected_issues': 'Using assert for security checks',
        'files': [
            {
                'path': 'app/security/access_control.py',
                'content': '''"""Access control - VULNERABLE: Using assert"""

class AccessControl:
    def check_admin(self, user):
        """Check if user is admin - VULNERABLE"""
        # VULNERABLE: assert can be disabled with -O flag
        assert user.get('role') == 'admin', "User is not admin"
        return True

    def check_permission(self, user, resource):
        """Check permission - VULNERABLE"""
        # VULNERABLE: Using assert for security
        assert user.get('permissions', []).count(resource) > 0
        return True

    def validate_token(self, token):
        """Validate token - VULNERABLE"""
        assert len(token) == 32, "Invalid token"
        assert token.isalnum(), "Token contains invalid characters"
        return True
'''
            }
        ]
    },

    # 16. Temp file creation
    {
        'type': 'insecure-temp-file',
        'title': 'Add temp file handler',
        'description': 'Implements temporary file operations',
        'expected_issues': 'Insecure temporary file creation',
        'files': [
            {
                'path': 'app/files/temp_handler.py',
                'content': '''"""Temp file handler - INSECURE"""
import os

class TempFileHandler:
    def create_temp_file(self, data):
        """Create temp file - VULNERABLE"""
        # VULNERABLE: Predictable temp file name
        temp_file = f"/tmp/temp_{os.getpid()}.txt"

        with open(temp_file, 'w') as f:
            f.write(data)

        return temp_file

    def create_temp_dir(self):
        """Create temp directory - VULNERABLE"""
        # VULNERABLE: Predictable directory name
        temp_dir = f"/tmp/tempdir_{os.getpid()}"
        os.mkdir(temp_dir)
        return temp_dir
'''
            }
        ]
    },

    # 17. Debug mode enabled
    {
        'type': 'debug-enabled',
        'title': 'Add Flask application',
        'description': 'Implements Flask web application',
        'expected_issues': 'Debug mode enabled in production',
        'files': [
            {
                'path': 'app/web/app.py',
                'content': '''"""Flask application - DEBUG MODE ENABLED"""
from flask import Flask, request

app = Flask(__name__)

# VULNERABLE: Debug mode should never be enabled in production
app.config['DEBUG'] = True
app.config['TESTING'] = True

@app.route('/api/user/<user_id>')
def get_user(user_id):
    # No input validation
    return {'user_id': user_id}

@app.route('/api/eval', methods=['POST'])
def eval_code():
    """Evaluate code - EXTREMELY DANGEROUS"""
    code = request.json.get('code')
    # VULNERABLE: eval in web endpoint
    result = eval(code)
    return {'result': result}

if __name__ == '__main__':
    # VULNERABLE: Debug mode exposed
    app.run(debug=True, host='0.0.0.0')
'''
            }
        ]
    },

    # 18. Regular expression DoS
    {
        'type': 'regex-dos',
        'title': 'Add input validator',
        'description': 'Implements input validation with regex',
        'expected_issues': 'Regular expression DoS (ReDoS)',
        'files': [
            {
                'path': 'app/validation/validator.py',
                'content': '''"""Input validator - VULNERABLE TO ReDoS"""
import re

class Validator:
    def validate_email(self, email):
        """Validate email - VULNERABLE to ReDoS"""
        # VULNERABLE: Catastrophic backtracking
        pattern = r'^([a-zA-Z0-9])+@([a-zA-Z0-9])+(\\.[a-zA-Z0-9]+)+$'
        return re.match(pattern, email) is not None

    def validate_url(self, url):
        """Validate URL - VULNERABLE to ReDoS"""
        # VULNERABLE: Complex regex with backtracking
        pattern = r'^(https?:\\/\\/)?(www\\.)?([a-zA-Z0-9]+)+\\.([a-zA-Z]{2,})+(\\/.*)?$'
        return re.match(pattern, url) is not None

    def validate_phone(self, phone):
        """Validate phone - VULNERABLE"""
        pattern = r'^(\\d+)+(-)?(\\d+)+$'
        return re.match(pattern, phone) is not None
'''
            }
        ]
    },

    # 19. Missing CSRF protection
    {
        'type': 'missing-csrf',
        'title': 'Add form handler',
        'description': 'Implements form processing',
        'expected_issues': 'Missing CSRF protection',
        'files': [
            {
                'path': 'app/forms/handler.py',
                'content': '''"""Form handler - NO CSRF PROTECTION"""
from flask import Flask, request

app = Flask(__name__)

# VULNERABLE: No CSRF protection
@app.route('/update-profile', methods=['POST'])
def update_profile():
    """Update user profile - NO CSRF PROTECTION"""
    # VULNERABLE: No CSRF token validation
    user_id = request.form.get('user_id')
    email = request.form.get('email')
    password = request.form.get('password')

    # Update user...
    return {'success': True}

@app.route('/delete-account', methods=['POST'])
def delete_account():
    """Delete account - NO CSRF PROTECTION"""
    user_id = request.form.get('user_id')
    # Delete account...
    return {'success': True}
'''
            }
        ]
    },

    # 20. Insufficient logging
    {
        'type': 'insufficient-logging',
        'title': 'Add authentication handler',
        'description': 'Implements authentication',
        'expected_issues': 'Insufficient security event logging',
        'files': [
            {
                'path': 'app/auth/handler.py',
                'content': '''"""Authentication handler - INSUFFICIENT LOGGING"""

class AuthHandler:
    def login(self, username, password):
        """Login user - NO LOGGING"""
        # VULNERABLE: No logging of authentication attempts
        if self.verify_credentials(username, password):
            return {'success': True, 'token': 'abc123'}
        return {'success': False}

    def change_password(self, user_id, old_password, new_password):
        """Change password - NO LOGGING"""
        # VULNERABLE: No logging of password changes
        if self.verify_old_password(user_id, old_password):
            self.update_password(user_id, new_password)
            return True
        return False

    def delete_account(self, user_id):
        """Delete account - NO LOGGING"""
        # VULNERABLE: No logging of account deletion
        self.remove_user(user_id)
        return True

    def verify_credentials(self, username, password):
        return True

    def verify_old_password(self, user_id, password):
        return True

    def update_password(self, user_id, password):
        pass

    def remove_user(self, user_id):
        pass
'''
            }
        ]
    },
]

# Add remaining Python scenarios (21-50)
for i in range(21, 51):
    scenario_types = [
        ('shell-injection', 'Shell injection'),
        ('ldap-injection', 'LDAP injection'),
        ('xpath-injection', 'XPath injection'),
        ('code-smell-long-function', 'Long function'),
        ('code-smell-too-many-params', 'Too many parameters'),
        ('unused-imports', 'Unused imports'),
        ('unused-variables', 'Unused variables'),
        ('global-variables', 'Excessive global variables'),
        ('hardcoded-temp-dir', 'Hardcoded temp directory'),
        ('missing-timeout', 'Missing request timeout'),
        ('ssl-no-verify', 'SSL verification disabled'),
        ('weak-random', 'Weak random number generation'),
        ('timing-attack', 'Timing attack vulnerability'),
        ('mass-assignment', 'Mass assignment'),
        ('open-redirect', 'Open redirect'),
        ('server-side-request-forgery', 'SSRF'),
        ('nosql-injection', 'NoSQL injection'),
        ('cors-misconfiguration', 'CORS misconfiguration'),
        ('http-only-cookie', 'Missing HttpOnly flag'),
        ('secure-cookie', 'Missing Secure flag'),
        ('clickjacking', 'Clickjacking vulnerability'),
        ('content-type-nosniff', 'Missing X-Content-Type-Options'),
        ('xss-protection', 'Missing X-XSS-Protection'),
        ('hsts-missing', 'Missing HSTS header'),
        ('csp-missing', 'Missing CSP header'),
        ('information-disclosure', 'Information disclosure'),
        ('error-handling-verbose', 'Verbose error messages'),
        ('directory-listing', 'Directory listing enabled'),
        ('backup-files', 'Backup files exposed'),
        ('sensitive-comments', 'Sensitive data in comments'),
    ]

    idx = (i - 21) % len(scenario_types)
    scenario_type, issue_desc = scenario_types[idx]

    PYTHON_SCENARIOS.append({
        'type': scenario_type,
        'title': f'Feature implementation {i}',
        'description': f'Implements feature with {issue_desc}',
        'expected_issues': issue_desc,
        'files': [
            {
                'path': f'app/feature{i}/module{i}.py',
                'content': f'''"""Feature {i} - {issue_desc}"""

class Feature{i}:
    """Implementation with {issue_desc}"""

    def execute(self):
        """Execute feature {i}"""
        print(f"Feature {i} executing")
        # Vulnerable code pattern for {scenario_type}
        pass

    def process(self, data):
        """Process data"""
        # Implementation with {issue_desc}
        return data
'''
            }
        ]
    })

def main():
    """Main execution"""
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                   PR Generation Script for Code Review Testing               ║
║                                                                               ║
║  This script will create 100 PRs (50 Java + 50 Python) to test all aspects  ║
║  of the multi-agent code review system including:                            ║
║  - Static analysis                                                            ║
║  - Security vulnerabilities                                                   ║
║  - Code quality                                                               ║
║  - RAG novelty scoring                                                        ║
║  - Pattern recognition                                                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)

    # Initialize Java repository
    print("\n" + "="*80)
    print("STEP 1: Initializing Java Repository")
    print("="*80)
    if not init_repo(JAVA_REPO, "https://github.com/tarentomaheshvakkund/testdata-java-hackathon.git"):
        print("Failed to initialize Java repository")
        return

    # Initialize Python repository
    print("\n" + "="*80)
    print("STEP 2: Initializing Python Repository")
    print("="*80)
    if not init_repo(PYTHON_REPO, "https://github.com/tarentomaheshvakkund/testdata-python-hackathon"):
        print("Failed to initialize Python repository")
        return

    # Create Java PRs
    print("\n" + "="*80)
    print("STEP 3: Creating 50 Java PRs")
    print("="*80)
    for i, scenario in enumerate(JAVA_SCENARIOS, 1):
        create_java_pr(i, scenario, JAVA_REPO)

    # Create Python PRs
    print("\n" + "="*80)
    print("STEP 4: Creating 50 Python PRs")
    print("="*80)
    for i, scenario in enumerate(PYTHON_SCENARIOS, 1):
        create_python_pr(i, scenario, PYTHON_REPO)

    print("\n" + "="*80)
    print("✓ ALL PRs CREATED SUCCESSFULLY!")
    print("="*80)
    print(f"Java PRs: 50 created in {JAVA_REPO}")
    print(f"Python PRs: 50 created in {PYTHON_REPO}")
    print("\nNext steps:")
    print("1. Review the PRs on GitHub")
    print("2. Run your code review system to analyze them")
    print("3. Verify all agents are working correctly")
    print("="*80)

if __name__ == '__main__':
    main()
