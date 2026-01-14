# RAG Version 5: Advanced Learning & Optimization Reference

This document summarizes the significant enhancements made to the Retrieval-Augmented Generation (RAG) system in Version 5. These changes focus on reducing latency, improving retrieval precision, and enabling the system to learn from cross-repository data and user feedback.

## 🚀 Phase 3: Latency & Precision Optimization

### 1. Performance Enhancements
- **Embedding Cache**: Implemented LRU caching in `RAGEnhancedAgent` to store code embeddings, reducing API costs and latency for repeated file analysis.
- **Increased Retrieval Capacity**: Expanded retrieval from 5 to 10 candidates to provide richer context for complex PRs.

### 2. Intelligent Ranking
- **Temporal Decay**: Introduced a weighting factor that prioritizes recent PRs (90-day half-life), ensuring the system learns from modern coding standards rather than legacy patterns.
- **Repository Bias**: Added a 20% relevance boost for PRs from the same repository, favoring local context while still allowing cross-project learning.

### 3. Context Enrichment
- **Metadata Expansion**: Added file types, branch names, and metadata category tags to the vector database.
- **Keyword Extraction**: The agent now identifies security, concurrency, quality, and memory keywords from code patches to improve the precision of context retrieval.

---

## 🧠 Phase 4: Feedback Loop & Pattern Library

### 1. User Feedback Integration
- **[NEW] `rag_feedback` Table**: A dedicated table to capture user ratings (1-5) and specific comments on RAG suggestions.
- **Feedback-Driven Ranking**: Retrieval results are now weighted by historical feedback. Suggestions from PRs with high user ratings get boosted, while poorly rated ones are penalized.

### 2. Multi-Repository Learning
- **Cross-Repo Discovery**: The RAG agent can now search across the entire knowledge base of all indexed repositories, allowing "cross-pollination" of best practices.
- **Configurability**: Enabled via the `CROSS_REPO_RAG` environment variable.

### 3. Automated Pattern Library
- **[NEW] `rag_pattern_library` Table**: Stores recurring code patterns, their frequency, and recommended solutions.
- **Auto-Extraction**: The system automatically extracts patterns from two sources after every analysis:
    - **Issue-based Patterns**: Recurring types of issues (e.g., "Quality: Long Method").
    - **Keyword-based Patterns**: Recurring code-level patterns identified in patches (e.g., "Code Pattern: synchronized").

---

## 🛠️ Technical Components

### Database Schema Updates
- `rag_feedback`: Stores `pr_analysis_id`, `rating`, `is_helpful`, and `user_comment`.
- `rag_pattern_library`: Stores `pattern_name`, `category`, `frequency`, `example_prs`, and `recommended_solutions`.

### Key Files
- `agents/rag_enhanced_agent.py`: Core logic for caching, ranking, multi-repo search, and pattern extraction.
- `services/database_service.py`: CRUD operations for feedback and pattern persistence.
- `models/database.py`: SQLAlchemy models for the new tables.

---
**Status**: Version 5 Implementation Complete.
