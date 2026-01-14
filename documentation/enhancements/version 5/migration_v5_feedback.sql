-- Migration Phase 4: Feedback Loop & Pattern Library

-- Feedack table for RAG recommendations
CREATE TABLE IF NOT EXISTS rag_feedback (
    id SERIAL PRIMARY KEY,
    pr_analysis_id INTEGER NOT NULL REFERENCES pr_analysis(id) ON DELETE CASCADE,
    recommendation_id TEXT, -- Optional identifier if recommendation came from a specific pattern
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    is_helpful BOOLEAN,
    user_comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for quick feedback lookups per PR
CREATE INDEX IF NOT EXISTS idx_rag_feedback_pr ON rag_feedback(pr_analysis_id);

-- Pattern library for recurring code issues/practices
CREATE TABLE IF NOT EXISTS rag_pattern_library (
    id SERIAL PRIMARY KEY,
    pattern_name VARCHAR(255) UNIQUE NOT NULL,
    category VARCHAR(100), -- security, concurrency, quality, memory
    description TEXT,
    frequency INTEGER DEFAULT 1,
    success_rate FLOAT DEFAULT 0.0,
    example_prs JSONB, -- Array of PR numbers/links showing this pattern
    avg_resolution_time INTERVAL,
    recommended_solutions TEXT[], -- Array of strings
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for category-based pattern searches
CREATE INDEX IF NOT EXISTS idx_rag_patterns_category ON rag_pattern_library(category);
