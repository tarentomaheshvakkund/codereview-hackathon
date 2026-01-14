# 🗄️ ChromaDB Data Schema & Retrieval Strategy

The RAG (Retrieval-Augmented Generation) system utilizes **ChromaDB** as a vector store to provide historical context and "learning" capabilities. This document outlines the data structure, metadata, and retrieval logic.

## 1. Vector Collections
We utilize a multi-collection architecture to partition knowledge:

| Collection Name | Purpose | Routing Logic |
| :--- | :--- | :--- |
| `pr_analysis_knowledge` | **Master Index** | Stores all analyzed PRs for general semantic matching. |
| `security_expert_knowledge` | **Security Expert** | Stores PRs identified with security/vulnerability findings. |
| `quality_expert_knowledge` | **Quality Expert** | Stores PRs with code quality, style, or maintainability issues. |
| `general_expert_knowledge` | **General History** | Default storage for standard PRs without major issues. |

## 2. Document Content (The "Vectorized" Data)
Every PR is represented as a text document which is converted into a 384-dimensional embedding (using `all-MiniLM-L6-v2`):
- **Title & Description**: Complete textual context of the PR.
- **File List**: Basenames of the first 10 modified files.
- **Repository Name**: For context-aware semantic matching.

## 3. Metadata Fields
Each vector is enriched with over 20 metadata fields to enable precise filtering and ranking.

### Core Identification
- `pr_number`: PR number within repo.
- `pr_title`: Original title.
- `repository`: Name of the source repository.
- `author`: GitHub login of the developer.
- `analyzed_at`: ISO timestamp (used for temporal decay).

### Code Metrics
- `files_count`: Number of modified files.
- `lines_added` / `lines_deleted`: Scale of the change.
- `file_types`: Comma-separated list of extensions (e.g., `java,xml`).
- `has_tests`: Boolean flag for test file presence.
- `language`: Primary language (e.g., `java`).

### Analysis Results (Learning Loop)
*Updated post-analysis to enable retrieval by "issue similarity":*
- `issues_found`: Total count of all findings.
- `security_issues`: Count of vulnerabilities.
- `performance_issues`: Count of bottlenecks found.
- `quality_issues`: Count of style/quality findings.
- `critical_issues`: Count of high-severity findings.
- `estimated_coverage`: Coverage percentage (cached for RAG).

## 4. Retrieval & Ranking Logic
The system uses the captured data in three stages:

### A. Semantic Search
The current PR's code patterns and title are encoded into a vector and searched against the collections using **Cosine Similarity**.

### B. Weighted Ranking
Distances returned by ChromaDB are adjusted using:
1. **Temporal Decay**: Older PRs have their distance increased exponentially (half-life of 90 days), favoring fresh patterns.
2. **Repository Bias**: PRs from the same repository get a **20% relevance boost** (0.8x distance).
3. **Feedback Weighting**: Rating 5 PRs get a **30% boost**; Rating 1 PRs get a **2x penalty**.

### C. Expert Routing
The system extracts keywords (e.g., `sql`, `synchronized`) from the current PR to decide which expert collections to query alongside the main index.

---
*Last Updated: 2026-01-13*
