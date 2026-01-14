"""
RAG (Retrieval-Augmented Generation) Agent for PR Code Review

This agent enhances AI analysis by retrieving relevant context from:
- Historical PR analyses
- Past code reviews
- Best practices database
- Similar code patterns
"""
import os
import sys
import functools
from typing import Dict, Any, List, Optional
from models.pr_event import PREvent
from agents.base_agent import BaseAgent, AgentResult
from models.analysis_result import Severity
try:
    import torch
    from transformers import AutoTokenizer, AutoModel
except ImportError:
    torch = None
    AutoTokenizer = None
    AutoModel = None
from utils.logger import logger
from utils.config import config
from datetime import datetime

# SQLite version workaround for ChromaDB
# ChromaDB requires SQLite 3.35+, but system may have older version
try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass  # Use system sqlite3 if pysqlite3-binary not available

# Vector DB options
try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

# Embeddings
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

# AI providers (same as AI Summary Agent)
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class RAGEnhancedAgent(BaseAgent):
    """
    RAG-enhanced agent that retrieves relevant context from historical data
    to improve AI analysis quality.
    """

    def __init__(self, db_service=None, config=None):
        """Initialize RAG agent with vector database and embeddings."""
        # Initialize base agent with default config
        if config is None:
            config = {}
        super().__init__("RAG Enhanced Agent", config)

        self.agent_name = "RAG Enhanced Agent"
        self.db_service = db_service

        # Configure AI provider
        self.ai_provider = os.getenv('AI_PROVIDER', 'gemini')
        self.api_key = os.getenv('GEMINI_API_KEY') if self.ai_provider == 'gemini' else os.getenv('OPENAI_API_KEY')

        # Check if RAG is enabled
        self.rag_enabled = os.getenv('RAG_ENABLED', 'false').lower() == 'true'

        if not self.rag_enabled:
            logger.info("RAG Agent is disabled. Set RAG_ENABLED=true to enable.")
            self.enabled = False
            return

        if not self.api_key:
            logger.warning("No AI API key found. RAG Agent will be disabled.")
            self.enabled = False
            return

        # Initialize components
        self._init_vector_db()
        self._init_embeddings()
        ai_client_ready = self._init_ai_client()

        if self.vector_db and self.embedding_model and ai_client_ready:
            self.enabled = True
            logger.info("RAG Enhanced Agent initialized successfully")
        else:
            self.enabled = False
            missing = []
            if not self.vector_db: missing.append("vector_db")
            if not self.embedding_model: missing.append("embeddings")
            if not ai_client_ready: missing.append("ai_client")
            logger.warning(f"RAG Agent disabled - missing dependencies ({', '.join(missing)})")

    @functools.lru_cache(maxsize=128)
    def _get_code_embedding(self, text: str) -> List[float]:
        """Generate code-aware embedding with LRU caching for latency optimization."""
        if not self.embedding_model:
            return []

        if self.is_codebert and torch:
            try:
                inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
                with torch.no_grad():
                    outputs = self.embedding_model(**inputs)
                # Use mean pooling
                embedding = outputs.last_hidden_state.mean(dim=1).squeeze().tolist()
                return embedding
            except Exception as e:
                self.logger.error(f"Error generating CodeBERT embedding: {e}")
                return []
        else:
            # Fallback to SentenceTransformer
            return self.embedding_model.encode(text).tolist()

    def _init_vector_db(self):
        """Initialize vector database (ChromaDB)."""
        if not CHROMADB_AVAILABLE:
            logger.warning("ChromaDB not available. Install: pip install chromadb")
            self.vector_db = None
            return

        try:
            # Initialize ChromaDB (persistent storage) - NEW API
            # Allow environment variable to override config (critical for benchmarking/testing)
            persist_directory = os.getenv('VECTOR_DB_PATH',
                                         config.get('agents.rag_enhanced.vector_db_path', './vector_db'))

            # Support in-memory for testing/benchmarking
            if persist_directory == ":memory:":
                self.chroma_client = chromadb.Client()
                logger.info("Initialized In-Memory ChromaDB")
            else:
                self.chroma_client = chromadb.PersistentClient(path=persist_directory)
            # Initialize main collection
            self.collection_name = os.getenv('VECTOR_DB_COLLECTION', 'pr_analysis_knowledge')
            self.vector_db = self.chroma_client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )

            # Phase 5: Initialize specialized collections
            self.specialized_collections = {
                'security': self.chroma_client.get_or_create_collection(name='security_expert_knowledge', metadata={"hnsw:space": "cosine"}),
                'quality': self.chroma_client.get_or_create_collection(name='quality_expert_knowledge', metadata={"hnsw:space": "cosine"}),
                'general': self.chroma_client.get_or_create_collection(name='general_expert_knowledge', metadata={"hnsw:space": "cosine"})
            }

            logger.info(f"Connected to ChromaDB at {persist_directory} with specialized collections")

        except Exception as e:
            logger.error(f"Failed to initialize vector DB: {e}", exc_info=True)
            self.vector_db = None

    def _init_embeddings(self):
        """Initialize embedding model."""
        try:
            # Use a lightweight, fast model by default, but allow override
            model_name = os.getenv('EMBEDDING_MODEL') or \
                         self.config.get('agents.rag_enhanced.embedding_model') or \
                         'all-MiniLM-L6-v2'

            logger.info(f"Loading embedding model: {model_name}")

            if "codebert" in model_name.lower() and AUTO_MODEL_AVAILABLE:
                from transformers import AutoTokenizer, AutoModel
                self.tokenizer = AutoTokenizer.from_pretrained(model_name)
                self.embedding_model = AutoModel.from_pretrained(model_name)
                self.is_codebert = True
            else:
                if not SENTENCE_TRANSFORMERS_AVAILABLE:
                    logger.warning("SentenceTransformers not available. Install: pip install sentence-transformers")
                    self.embedding_model = None
                    return
                from sentence_transformers import SentenceTransformer
                self.embedding_model = SentenceTransformer(model_name)
                self.is_codebert = False

            logger.info(f"Embedding model loaded: {model_name}")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self.embedding_model = None

    def _init_ai_client(self) -> bool:
        """Initialize AI client for RAG-enhanced generation.

        Returns:
            True if initialization succeeded, False otherwise
        """
        try:
            # Priority: 1. AI_PROVIDER env var, 2. settings.yaml configuration
            self.ai_provider = os.getenv('AI_PROVIDER', config.get('agents.rag_enhanced.ai_provider', 'openai'))

            # Auto-switch to available provider if key is missing
            if self.ai_provider == 'openai' and not os.getenv('OPENAI_API_KEY') and os.getenv('GEMINI_API_KEY'):
                logger.info("OPENAI_API_KEY missing, auto-switching to Gemini")
                self.ai_provider = 'gemini'
                self.api_key = os.getenv('GEMINI_API_KEY')
            elif self.ai_provider == 'gemini' and not os.getenv('GEMINI_API_KEY') and os.getenv('OPENAI_API_KEY'):
                logger.info("GEMINI_API_KEY missing, auto-switching to OpenAI")
                self.ai_provider = 'openai'
                self.api_key = os.getenv('OPENAI_API_KEY')

            if self.ai_provider == 'gemini' and GEMINI_AVAILABLE:
                genai.configure(api_key=self.api_key)
                gemini_model = config.get('agents.rag_enhanced.gemini_model', 'gemini-1.5-flash')
                self.model = genai.GenerativeModel(gemini_model)
                self.model_name = gemini_model
                logger.info(f"Initialized Gemini model: {gemini_model}")
                return True
            elif self.ai_provider == 'openai' and OPENAI_AVAILABLE:
                self.client = OpenAI(api_key=self.api_key)
                openai_model = config.get('agents.rag_enhanced.openai_model', 'gpt-4o')
                self.model_name = openai_model
                logger.info(f"Initialized OpenAI model: {openai_model}")
                return True
            else:
                logger.error(f"AI provider {self.ai_provider} not available - OPENAI_AVAILABLE={OPENAI_AVAILABLE}, GEMINI_AVAILABLE={GEMINI_AVAILABLE}")
                return False
        except Exception as e:
            logger.error(f"Failed to initialize AI client: {e}", exc_info=True)
            return False

    def _rank_results(self, pr_event: PREvent, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Rank retrieval results using temporal decay, repository-local bias, and user feedback.
        """
        if not results or not results['metadatas'] or not results['metadatas'][0]:
            return results

        import math
        current_time = datetime.now()

        # We need to modify distances in place or return a new dict
        # Lower distance = more relevant

        for i, meta in enumerate(results['metadatas'][0]):
            distance = results['distances'][0][i]

            # 1. Temporal Decay (Half-life of 90 days)
            # PRs older than 90 days have their distance increased
            analyzed_at_str = meta.get('analyzed_at')
            if analyzed_at_str:
                try:
                    analyzed_at = datetime.fromisoformat(analyzed_at_str)
                    days_diff = (current_time - analyzed_at).days
                    # Penalty increases exponentially with age
                    # Factor = 2 ^ (days / 90)
                    decay_factor = math.pow(2, max(0, days_diff) / 90.0)
                    distance = distance * decay_factor
                except (ValueError, TypeError):
                    pass

            # 2. Repository Local Bias
            # PRs from the same repository get a 20% relevance boost (distance reduction)
            if meta.get('repository') == pr_event.repository:
                distance = distance * 0.8

            # 3. User Feedback Weighting (NEW in Phase 4)
            # PRs with positive feedback get a boost, negative feedback get a penalty
            if self.db_service:
                feedback = self.db_service.get_pr_feedback(meta.get('pr_number'), meta.get('repository'))
                if feedback:
                    avg_rating = sum(f['rating'] for f in feedback) / len(feedback)
                    # Rating 5 = 0.7x distance (strong boost)
                    # Rating 1 = 2.0x distance (strong penalty)
                    feedback_factor = 1.0 + (3.0 - avg_rating) * 0.25
                    distance = distance * feedback_factor

            results['distances'][0][i] = distance

        # Re-sort by updated distance
        sorted_indices = sorted(range(len(results['distances'][0])), key=lambda k: results['distances'][0][k])

        ranked_results = {
            'ids': [[results['ids'][0][i] for i in sorted_indices]],
            'metadatas': [[results['metadatas'][0][i] for i in sorted_indices]],
            'distances': [[results['distances'][0][i] for i in sorted_indices]],
            'documents': [[results['documents'][0][i] for i in sorted_indices]] if 'documents' in results else None
        }

        return ranked_results

    def analyze(self, pr_event: PREvent) -> AgentResult:
        """
        Analyze PR with RAG-enhanced context.

        Args:
            pr_event: The PR to analyze

        Returns:
            AgentResult with RAG-enhanced insights
        """
        if not self.enabled:
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                execution_time=0.0,
                issues=[],
                error="RAG Agent is disabled",
                metadata={'enabled': False}
            )

        try:
            logger.info(f"RAG analysis for PR #{pr_event.pr_number}")

            # Step 1: Retrieve relevant context
            relevant_context = self._retrieve_relevant_context(pr_event)

            # Step 2: Generate RAG-enhanced analysis
            rag_insights = self._generate_rag_insights(pr_event, relevant_context)

            # Calculate scores based on RAG analysis
            risk_score = self._calculate_risk_score(pr_event, rag_insights, relevant_context)
            novelty_score = self._calculate_novelty_score(relevant_context)

            # Calculate average similarity for database
            similar_prs = relevant_context.get('similar_prs', [])
            average_similarity = 0.0
            if similar_prs:
                average_similarity = sum(pr.get('similarity', 0) for pr in similar_prs) / len(similar_prs)

            # Step 3: Store this PR for future retrieval
            self._store_pr_for_future_retrieval(pr_event)

            return AgentResult(
                agent_name=self.agent_name,
                success=True,
                execution_time=0.0,  # Will be set by base class
                issues=[],
                metadata={
                    'rag_insights': rag_insights,
                    'similar_prs_found': len(relevant_context.get('similar_prs', [])),
                    'best_practices_found': len(relevant_context.get('best_practices', [])),
                    'risk_score': risk_score,
                    'novelty_score': novelty_score,
                    'average_similarity': average_similarity,  # FIX: Add this for database
                    'recommendations_count': len(rag_insights.get('recommendations', '').split('\n')) if rag_insights.get('recommendations') else 0,
                    'patterns_identified': self._identify_patterns(pr_event),
                    'similar_prs': relevant_context.get('similar_prs', [])  # All similar PRs above threshold
                }
            )

        except Exception as e:
            logger.error(f"RAG analysis failed: {e}")
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                execution_time=0.0,
                issues=[],
                error=str(e),
                metadata={'error': str(e)}
            )

    def _analyze_impl(self, pr_event: PREvent) -> List:
        """
        Required implementation for BaseAgent abstract method.
        RAG agent doesn't produce traditional issues, so returns empty list.
        The insights are stored in metadata via the analyze() method.
        """
        return []

    def _retrieve_relevant_context(self, pr_event: PREvent) -> Dict[str, Any]:
        """
        Retrieve relevant context from vector database.
        """
        context = {'similar_prs': [], 'best_practices': [], 'historical_issues': []}
        if not self.vector_db or not self.embedding_model:
            return context

        try:
            query_text = self._create_query_text(pr_event)
            query_embedding = self._get_code_embedding(query_text)

            # Determine target collections
            query_keywords = self._extract_code_keywords(pr_event.files)
            target_collections = self._get_target_collections(query_keywords)

            # Search collections
            max_results = min(10, self.vector_db.count() if hasattr(self.vector_db, 'count') else 10)
            if max_results > 0:
                raw_results = self._query_collections(query_embedding, target_collections, max_results, pr_event)
                # Rank and process results
                ranked_results = self._rank_results(pr_event, raw_results)
                self._process_similarity_results(ranked_results, context)

            logger.info(f"Retrieved {len(context['similar_prs'])} similar PRs")
        except Exception as e:
            logger.error(f"Context retrieval failed: {e}")

        return context

    def _get_target_collections(self, keywords: List[str]) -> List[str]:
        """
        Determine which specialized collections to search based on keywords.

        Args:
            keywords: List of keywords extracted from the current PR files

        Returns:
            List[str]: List of collection names to search
        """
        target_collections = ['general']
        if any(k in ["sql", "password", "auth", "crypto"] for k in keywords):
            target_collections.append('security')
        if any(k in ["exception", "null", "error"] for k in keywords):
            target_collections.append('quality')
        return target_collections

    def _query_collections(self, query_embedding, target_collections, max_results, pr_event) -> Dict:
        """
        Query main and specialized collections and merge results.

        Args:
            query_embedding: Vector embedding of the input PR
            target_collections: Specialized collections to query
            max_results: Maximum results to retrieve from the main collection
            pr_event: The current PR event

        Returns:
            Dict: Merged and deduplicated search results from all collections
        """
        all_raw_results = []
        where_filter = {}
        if not os.getenv('CROSS_REPO_RAG', 'true').lower() == 'true':
            where_filter = {"repository": pr_event.repository}

        # Query main collection
        all_raw_results.append(self.vector_db.query(
            query_embeddings=[query_embedding],
            n_results=max_results,
            include=['metadatas', 'documents', 'distances'],
            where=where_filter if where_filter else None
        ))

        # Query specialized collections
        for col_name in target_collections:
            col = self.specialized_collections[col_name]
            if (col.count() if hasattr(col, 'count') else 0) > 0:
                all_raw_results.append(col.query(
                    query_embeddings=[query_embedding],
                    n_results=max(1, max_results // 2),
                    include=['metadatas', 'documents', 'distances'],
                    where=where_filter if where_filter else None
                ))

        return self._merge_retrieval_results(all_raw_results)

    def _process_similarity_results(self, results, context):
        """
        Filter results by distance threshold and convert to similarity scores.

        Args:
            results: Raw results dictionary from collection query
            context: Context dictionary to be populated with similar PRs
        """
        max_distance = 1.5
        if not (results and results.get('documents')):
            return

        for i, doc in enumerate(results['documents'][0]):
            distance = results['distances'][0][i]
            if distance < max_distance:
                metadata = results['metadatas'][0][i]
                similarity = max(0, 1 - (distance / 2))
                context['similar_prs'].append({
                    'pr_number': metadata.get('pr_number'),
                    'pr_title': metadata.get('pr_title'),
                    'issues_found': metadata.get('issues_found'),
                    'similarity_score': similarity,
                    'similarity': similarity,
                    'summary': doc[:200],
                    'distance': distance
                })

    def _create_query_text(self, pr_event: PREvent) -> str:
        """
        V3 ENHANCEMENT: Create enhanced search query with richer context.
        Structured query with file types, branch info, and code patterns.
        """
        # Extract file types
        file_types = sorted({f.filename.split('.')[-1]
                            for f in pr_event.files if '.' in f.filename})

        # Extract code keywords from files
        code_keywords = self._extract_code_keywords(pr_event.files)

        # Build structured query with rich context
        query_parts = [
            f"Title: {pr_event.pr_title}",
            f"Description: {pr_event.pr_description[:400] if pr_event.pr_description else 'N/A'}",
            f"Repository: {pr_event.repository}",
            f"Base Branch: {pr_event.base_branch}",
            f"File Types: {', '.join(file_types) if file_types else 'N/A'}",
            f"Modified Files: {', '.join([f.filename for f in pr_event.files[:5]])}",
            f"Code Patterns: {', '.join(code_keywords) if code_keywords else 'N/A'}"
        ]

        return " | ".join(query_parts)

    def _extract_code_keywords(self, files) -> List[str]:
        """
        V3 ENHANCEMENT: Extract relevant code patterns from modified files.
        Returns keywords for security, concurrency, quality, and memory patterns.
        """
        # Define pattern categories
        security_patterns = ['sql', 'query', 'password', 'secret', 'key',
                            'token', 'auth', 'crypto']
        concurrency_patterns = ['synchronized', 'volatile', 'thread', 'lock',
                               'atomic', 'concurrent']
        quality_patterns = ['null', 'exception', 'try', 'catch', 'throw', 'error']
        memory_patterns = ['stream', 'close', 'dispose', 'memory', 'leak']

        all_patterns = (security_patterns + concurrency_patterns +
                       quality_patterns + memory_patterns)

        # Extract keywords from first 3 files (performance optimization)
        keywords = set()
        for file in files[:3]:
            if hasattr(file, 'patch') and file.patch:
                patch_lower = file.patch.lower()
                for pattern in all_patterns:
                    if pattern in patch_lower:
                        keywords.add(pattern)

        # Return top 8 keywords
        return sorted(keywords)[:8]

    def _generate_rag_insights(
        self,
        pr_event: PREvent,
        relevant_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate insights using RAG (retrieved context + AI generation).

        Args:
            pr_event: Current PR
            relevant_context: Retrieved similar PRs and patterns

        Returns:
            RAG-enhanced insights
        """
        try:
            # Prepare prompt with retrieved context
            prompt = self._build_rag_prompt(pr_event, relevant_context)

            # Generate insights using AI
            if self.ai_provider == 'gemini':
                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.5,  # Reduced from 0.7 for faster, more focused responses
                        max_output_tokens=500  # Reduced from default for faster generation
                    ),
                    request_options={'timeout': 10}  # 10 second timeout
                )
                insights_text = response.text
            else:  # OpenAI
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "You are a concise code review expert. Provide brief, actionable insights."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.5,  # Reduced from 0.7
                    max_tokens=500,  # Reduced from 800
                    timeout=10  # 10 second timeout
                )
                insights_text = response.choices[0].message.content

            # Parse insights
            return self._parse_rag_insights(insights_text, relevant_context)

        except Exception as e:
            logger.error(f"Failed to generate RAG insights: {e}")
            # Return a safe default structure
            return {
                'full_text': f"RAG insights generation failed: {str(e)}",
                'similar_prs_referenced': len(relevant_context.get('similar_prs', [])),
                'context_used': bool(relevant_context.get('similar_prs', [])),
                'recommendations': '',
                'lessons_learned': '',
                'potential_pitfalls': '',
                'best_practices': '',
                'error': str(e)
            }

    def _build_rag_prompt(
        self,
        pr_event: PREvent,
        relevant_context: Dict[str, Any]
    ) -> str:
        """
        V3 ENHANCEMENT: Build comprehensive prompt with explicit instructions for specificity.
        Shows 5 similar PRs instead of 2, includes similarity scores, and demands specific advice.
        """
        similar_prs = relevant_context.get('similar_prs', [])

        # Extract file types for context
        file_types = sorted({f.filename.split('.')[-1]
                           for f in pr_event.files if '.' in f.filename})
        file_types_str = ', '.join(file_types) if file_types else 'N/A'

        # Format similar PRs context - V3: Show 5 instead of 2, include similarity scores
        similar_prs_text = ""
        if relevant_context['similar_prs']:
            similar_prs_text = "\n"
            for i, pr in enumerate(relevant_context['similar_prs'][:5], 1):  # Top 5 instead of 2
                similarity = pr.get('similarity', 0)
                similar_prs_text += f"{i}. PR #{pr['pr_number']} - {pr['pr_title']} (Similarity: {similarity:.2f}, Issues: {pr['issues_found']})\n"
                desc = pr.get('summary', '')[:150] # Use 'summary' from _process_similarity_results
                if desc:
                    similar_prs_text += f"   Description: {desc}...\n"

        # V3: Longer description (400 chars instead of 300)
        pr_description = pr_event.pr_description[:400] if pr_event.pr_description else "No description"

        # Extract file types for prompt
        file_types = sorted({f.filename.split('.')[-1]
                             for f in pr_event.files if '.' in f.filename})
        file_types_str = ', '.join(file_types) if file_types else 'N/A'

        # V3 ENHANCEMENT: Comprehensive prompt with explicit anti-pattern instructions
        # Enhanced prompt for deep technical analysis
        # Phase 5: Fetch matching patterns from library
        known_patterns = []
        if self.db_service:
            keywords = self._extract_code_keywords(pr_event.files)
            for kw in keywords:
                patterns = self.db_service.get_common_patterns(category=None, limit=3)
                # Filtering logic would be more complex in prod, here we just get general patterns for context
                known_patterns.extend([p for p in patterns if kw.lower() in p['name'].lower()])

        pattern_guidance = ""
        if known_patterns:
            pattern_guidance = "\n### APPLICABLE LEARNED PATTERNS:\n"
            for p in known_patterns[:5]:
                pattern_guidance += f"- **{p['name']}**: {p['solutions'][0] if p['solutions'] else 'Follow best practices.'}\n"

        prompt = f"""
        You are an expert PR reviewer. Use the provided context from previous similar PRs and learned patterns to provide a deep, contextual analysis.

        {pattern_guidance}

        ### PR UNDER REVIEW:
Title: {pr_event.pr_title}
Repository: {pr_event.repository}
Files Changed: {len(pr_event.files)}
File Types: {file_types_str}
Branch: {pr_event.head_branch} → {pr_event.base_branch}
Description: {pr_description}

=== HISTORICAL CONTEXT (SIMILAR PRS) ===
{similar_prs_text if relevant_context['similar_prs'] else "No identical historical patterns found."}

=== YOUR ANALYTICAL TASK ===
Perform a multi-dimensional analysis leveraging the historical context provided. Focus on these specialized categories:

1. **Architectural Consistency & Patterns**:
   - Compare the current approach with patterns found in similar PRs.
   - Identify if this PR deviates from established architectural norms of the repository.
   - Mention specific historical PRs if they solved similar problems more efficiently.

2. **Security & Data Integrity**:
   - Look for vulnerabilities that recur in the repository (e.g., specific SQL patterns, auth gaps).
   - If historical PRs had security issues, explicitly check if those same mistakes are repeated here.

3. **Performance & Scalability**:
   - Based on the file types ({file_types_str}), identify potential bottlenecks.
   - Contrast this implementation with more performant alternatives found in the repo's history.

4. **Strategic Recommendations**:
   - Provide concrete, prioritized steps for the developer.
   - Reference specific lines or functions that need refactoring for long-term maintainability.

IMPORTANT:
- Be HIGHLY SPECIFIC. Avoid generic "clean code" advice.
- Use the "Deep Thinking" approach: analyze WHY a pattern from a previous PR is relevant to this one.
- If no significant issues are found, highlight the best practices this PR follows relative to history.
"""
        return prompt

    def _parse_rag_insights(
        self,
        insights_text: str,
        relevant_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse AI-generated insights into structured format."""
        return {
            'full_text': insights_text,
            'similar_prs_referenced': len(relevant_context['similar_prs']),
            'context_used': bool(relevant_context['similar_prs']),
            'recommendations': self._extract_section(insights_text, 'recommendations'),
            'lessons_learned': self._extract_section(insights_text, 'lessons'),
            'potential_pitfalls': self._extract_section(insights_text, 'pitfalls'),
            'best_practices': self._extract_section(insights_text, 'best practices')
        }

    def _extract_section(self, text: str, section_name: str) -> str:
        """Extract a specific section from the insights text."""
        lines = text.split('\n')
        section_lines = []
        in_section = False

        # Map search terms to more flexible patterns
        search_patterns = {
            'recommendations': ['recommendation'],
            'lessons': ['lesson'],
            'pitfalls': ['pitfall'],
            'best practices': ['best practice', 'practice']
        }

        patterns = search_patterns.get(section_name.lower(), [section_name.lower()])

        for line in lines:
            line_lower = line.lower()
            stripped = line.strip()

            # Check if this line is a section header:
            # - Markdown headers: starts with #
            # - Numbered lists with bold: contains **Section**: or **Section**
            # - Bold headers: **Section**
            is_section_header = (
                (stripped.startswith('#') and len(stripped) > 1) or
                ('**' in stripped and ':' in stripped) or
                (stripped.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')) and '**' in stripped)
            )

            # Check if this line matches our section
            if is_section_header and any(pattern in line_lower for pattern in patterns):
                in_section = True
                # Skip the header line itself
            # Check if we've hit a new section header (stop collecting)
            elif in_section and is_section_header:
                break
            # Collect lines if we're in the right section
            elif in_section and stripped:
                section_lines.append(line)

        return '\n'.join(section_lines).strip()

    def _store_pr_for_future_retrieval(self, pr_event: PREvent):
        """Store PR analysis in vector DB for future RAG queries."""
        if not self.vector_db or not self.embedding_model:
            return

        try:
            # Create document text
            doc_text = f"{pr_event.pr_title}\n\n{pr_event.pr_description}\n\nFiles: {', '.join([f.filename for f in pr_event.files[:10]])}"

            # Generate embedding
            embedding = self._get_code_embedding(doc_text)
            # V3 ENHANCEMENT: Store with richer metadata for better future retrieval
            # Extract file types
            file_types = sorted({f.filename.split('.')[-1]
                               for f in pr_event.files if '.' in f.filename})

            self.vector_db.add(
                embeddings=[embedding],
                documents=[doc_text],
                metadatas=[{
                    # Original fields
                    'pr_number': pr_event.pr_number,
                    'pr_title': pr_event.pr_title,
                    'repository': pr_event.repository,
                    'author': pr_event.author.login,
                    'files_count': len(pr_event.files),
                    'issues_found': 0,  # Will be updated after analysis
                    'security_issues': 0,
                    'performance_issues': 0,
                    'quality_issues': 0,
                    'critical_issues': 0,
                    # V3 NEW: Enhanced metadata for better clustering
                    'base_branch': pr_event.base_branch,
                    'head_branch': pr_event.head_branch,
                    'lines_added': sum(f.additions for f in pr_event.files) if pr_event.files else 0,
                    'lines_deleted': sum(f.deletions for f in pr_event.files) if pr_event.files else 0,
                    'has_tests': any('test' in f.filename.lower() for f in pr_event.files) if pr_event.files else False,
                    'file_types': ','.join(file_types) if file_types else '',
                    'language': 'java',
                    'analyzed_at': datetime.now().isoformat()
                }],
                ids=[f"pr_{pr_event.repository}_{pr_event.pr_number}"]
            )

            logger.info(f"Stored PR #{pr_event.pr_number} in vector DB")

        except Exception as e:
            logger.error(f"Failed to store PR in vector DB: {e}")

    def _update_pr_analysis_results(self, pr_event: PREvent, all_issues: List, agent_results: Dict):
        """
        Update vector DB with results after full analysis completes.
        This provides the 'learning' part of RAG.
        """
        if not self.vector_db:
            return

        try:
            pr_id = f"pr_{pr_event.repository}_{pr_event.pr_number}"

            # Get existing metadata from ChromaDB
            results = self.vector_db.get(ids=[pr_id])
            if not results or not results['metadatas']:
                return

            metadata = results['metadatas'][0]

            # Extract metrics and update metadata
            self._enrich_metadata_with_analysis(metadata, all_issues, agent_results)

            # Update in vector DB
            self.vector_db.update(ids=[pr_id], metadatas=[metadata])

            # Route to specialized expert collections
            self._route_to_specialized_collections(pr_id, metadata, results, all_issues)

            # Extract and store patterns
            self._extract_and_store_patterns(pr_event, all_issues, agent_results)

            logger.info(f"Updated RAG learning for PR #{pr_event.pr_number} with {len(all_issues)} issues")

        except Exception as e:
            logger.error(f"Failed to update RAG analysis results: {e}")

    def _enrich_metadata_with_analysis(self, metadata: Dict, all_issues: List, agent_results: Dict):
        """
        Extract metrics from analysis results and enrich metadata.

        Args:
            metadata: Existing metadata to be enriched
            all_issues: List of issues found during analysis
            agent_results: Detailed results from all participating agents
        """
        # Extract metrics from other agents
        coverage_data = {}
        for name, result in agent_results.items():
            if "Coverage & Metrics Agent" in name:
                coverage_data = result.get('metrics', {})
                break

        # Calculate issue counts by category
        sec_count = sum(1 for i in all_issues if self._is_issue_type(i, ['security', 'vulnerability']))
        perf_count = sum(1 for i in all_issues if self._is_issue_type(i, ['performance']))
        qual_count = sum(1 for i in all_issues if self._is_issue_type(i, ['quality']))
        crit_count = sum(1 for i in all_issues if self._is_critical(i))

        metadata.update({
            'issues_found': len(all_issues),
            'security_issues': sec_count,
            'performance_issues': perf_count,
            'quality_issues': qual_count,
            'critical_issues': crit_count,
            'estimated_coverage': coverage_data.get('estimated_coverage', 0.0),
            'analyzed_at': datetime.now().isoformat()
        })

    def _is_issue_type(self, issue, keywords: List[str]) -> bool:
        """
        Helper to check if issue type matches any of the given keywords.

        Args:
            issue: The issue object to check
            keywords: List of keywords to search for in the issue type

        Returns:
            bool: True if any keyword is found in the issue type
        """
        val = (issue.type.value if hasattr(issue.type, 'value') else str(issue.type)).lower()
        return any(k in val for k in keywords)

    def _is_critical(self, issue) -> bool:
        """
        Helper to check if an issue has critical severity.

        Args:
            issue: The issue object to check

        Returns:
            bool: True if the issue is critical
        """
        return (hasattr(issue, 'severity') and
                (issue.severity == Severity.CRITICAL or
                 (isinstance(issue.severity, str) and issue.severity.lower() == 'critical')))

    def _route_to_specialized_collections(self, pr_id: str, metadata: Dict, results: Dict, all_issues: List):
        """
        Route the PR to specialized collections based on issue types found.

        Args:
            pr_id: Unique identifier for the PR
            metadata: Enriched PR metadata
            results: Results including raw documents from vector DB
            all_issues: List of all issues identified in this PR
        """
        primary_cat = 'general'
        sec_keywords = ['security', 'vulnerability']
        qual_keywords = ['quality', 'style']

        for i in all_issues:
            if self._is_issue_type(i, sec_keywords):
                primary_cat = 'security'
                break
            elif self._is_issue_type(i, qual_keywords):
                primary_cat = 'quality'
                # continue searching, security has precedence

        doc = results['documents'][0] if results and results.get('documents') and results['documents'] else [""]
        self.specialized_collections[primary_cat].upsert(
            ids=[pr_id],
            metadatas=[metadata],
            documents=doc
        )


    def _extract_and_store_patterns(self, pr_event: PREvent, all_issues: List, agent_results: Dict):
        """Extract recurring patterns and store them in the pattern library."""
        if not self.db_service:
            return

        try:
            # 1. Identify patterns from issues
            # We group issues by type and category to find recurring patterns
            patterns = {}
            for issue in all_issues:
                # Use issue.type from the model (not issue_type)
                type_val = issue.type.value if hasattr(issue.type, 'value') else str(issue.type)
                # Note: Issue model doesn't have 'category' anymore, it uses 'type' for categorization
                category = "general"
                if hasattr(issue, 'category'):
                    category = issue.category
                elif type_val in ["security", "vulnerability"]:
                    category = "security"
                elif type_val in ["quality", "style", "complexity"]:
                    category = "quality"

                key = (type_val, category)
                if key not in patterns:
                    patterns[key] = []
                patterns[key].append(issue)

            pr_info = {
                'pr_number': pr_event.pr_number,
                'repository': pr_event.repository,
                'analyzed_at': datetime.now().isoformat()
            }

            for (issue_type, category), issues in patterns.items():
                # If we see multiple instances of the same issue type in one PR,
                # or if it's a known high-frequency issue
                pattern_name = f"{category.capitalize()}: {issue_type}"

                # Combine recommendations for this pattern (suggestion in model)
                solutions = []
                for i in issues:
                    if hasattr(i, 'suggestion') and i.suggestion:
                        solutions.append(i.suggestion)
                    elif hasattr(i, 'recommendation') and i.recommendation:
                        # Backwards compatibility/safety
                        solutions.append(i.recommendation)

                solution_text = "\n".join(list(set(solutions)))

                self.db_service.update_pattern_library(
                    pattern_name=pattern_name,
                    category=category,
                    pr_info=pr_info,
                    solution=solution_text[:500] if solution_text else None
                )

            # 2. Extract code-level patterns (from RAG metadata)
            # This uses the _extract_code_keywords logic already in place
            keywords = self._extract_code_keywords(pr_event.files)
            for kw in keywords:
                self.db_service.update_pattern_library(
                    pattern_name=f"Code Pattern: {kw}",
                    category="code_pattern",
                    pr_info=pr_info
                )

        except Exception as e:
            logger.error(f"Failed to extract and store patterns: {e}")

    def _merge_retrieval_results(self, results_list: List[Dict]) -> Dict:
        """Merge retrieval results from multiple collections and deduplicate."""
        merged = {'metadatas': [[]], 'documents': [[]], 'distances': [[]], 'ids': [[]]}
        seen_ids = set()

        for res in results_list:
            if not res or not res.get('ids'):
                continue

            for i, doc_id in enumerate(res['ids'][0]):
                if doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    merged['ids'][0].append(doc_id)
                    merged['metadatas'][0].append(res['metadatas'][0][i])
                    merged['documents'][0].append(res['documents'][0][i])
                    merged['distances'][0].append(res['distances'][0][i])

        return merged

    def index_historical_prs(self, limit: int = 100, delay: int = 0):
        """
        Index historical PRs from database into vector DB.
        Run this once to build the initial index.
        """
        if not self.db_service or not self.vector_db:
            logger.error("Cannot index: DB service or vector DB not available")
            return

        try:
            logger.info(f"Indexing up to {limit} historical PRs...")
            prs = self._fetch_historical_prs(limit)

            indexed = 0
            for pr in prs:
                self._index_single_pr_record(pr)
                indexed += 1

                if delay > 0:
                    import time
                    time.sleep(delay)

            logger.info(f"Successfully indexed {indexed} PRs")

        except Exception as e:
            logger.error(f"Failed to index historical PRs: {e}")

    def _fetch_historical_prs(self, limit: int) -> List:
        """
        Fetch PR analysis records from the database ordered by analysis time.

        Args:
            limit: Maximum number of PRs to fetch

        Returns:
            List: List of PRAnalysis database records
        """
        with self.db_service.get_session() as session:
            from models.database import PRAnalysis
            return session.query(PRAnalysis)\
                .order_by(PRAnalysis.analyzed_at.desc())\
                .limit(limit)\
                .all()

    def _index_single_pr_record(self, pr):
        """
        Embed and index a single PR record from the database.

        Args:
            pr: A PRAnalysis record object from the database
        """
        doc_text = f"{pr.pr_title}\n\n{pr.pr_description or ''}\n\nRepository: {pr.repository}"
        embedding = self._get_code_embedding(doc_text)

        metadata = {
            'pr_number': pr.pr_number,
            'pr_title': pr.pr_title,
            'repository': pr.repository,
            'author': pr.author_login,
            'files_count': pr.files_changed or 0,
            'issues_found': pr.total_issues or 0,
            'security_issues': pr.security_issues or 0,
            'performance_issues': getattr(pr, 'performance_issues', 0),
            'quality_issues': pr.code_quality_issues or 0,
            'critical_issues': pr.critical_issues or 0,
            'base_branch': pr.base_branch or 'main',
            'head_branch': pr.head_branch or '',
            'lines_added': pr.lines_added or 0,
            'lines_deleted': pr.lines_deleted or 0,
            'estimated_coverage': pr.estimated_coverage or 0.0,
            'language': 'java',
            'analyzed_at': pr.analyzed_at.isoformat() if (pr.analyzed_at and hasattr(pr.analyzed_at, 'isoformat')) else datetime.now().isoformat()
        }

        pr_id = f"pr_{pr.repository}_{pr.pr_number}"
        self.vector_db.upsert(embeddings=[embedding], documents=[doc_text], metadatas=[metadata], ids=[pr_id])

        # Route to specialized collections
        primary_cat = 'general'
        if metadata['security_issues'] > 0:
            primary_cat = 'security'
        elif metadata['quality_issues'] > 0:
            primary_cat = 'quality'

        if primary_cat in self.specialized_collections:
            self.specialized_collections[primary_cat].upsert(
                embeddings=[embedding], documents=[doc_text], metadatas=[metadata], ids=[pr_id]
            )

    def _calculate_risk_score(
        self,
        pr_event: PREvent,
        rag_insights: Dict[str, Any],
        relevant_context: Dict[str, Any]
    ) -> float:
        """
        Calculate risk score based on RAG analysis.
        Risk score: 0 (low risk) to 1 (high risk)
        """
        risk_score = 0.0

        # Factor 1: Novelty (unfamiliar patterns = higher risk)
        if len(relevant_context.get('similar_prs', [])) == 0:
            risk_score += 0.3  # No similar PRs = higher risk
        elif len(relevant_context.get('similar_prs', [])) < 2:
            risk_score += 0.15

        # Factor 2: Potential pitfalls mentioned
        pitfalls = rag_insights.get('potential_pitfalls', '')
        if pitfalls and len(pitfalls) > 100:
            risk_score += 0.3
        elif pitfalls and len(pitfalls) > 50:
            risk_score += 0.15

        # Factor 3: Number of files changed
        if len(pr_event.files) > 20:
            risk_score += 0.2
        elif len(pr_event.files) > 10:
            risk_score += 0.1

        # Factor 4: Large changes
        total_changes = sum(f.additions + f.deletions for f in pr_event.files)
        if total_changes > 1000:
            risk_score += 0.2
        elif total_changes > 500:
            risk_score += 0.1

        return min(1.0, risk_score)  # Cap at 1.0

    def _calculate_novelty_score(self, relevant_context: Dict[str, Any]) -> float:
        """
        Calculate novelty score based on similarity to past PRs.
        Novelty score: 0 (common pattern) to 1 (highly novel)
        """
        similar_prs = relevant_context.get('similar_prs', [])

        if not similar_prs:
            return 1.0  # Completely novel

        # Get average similarity score
        avg_similarity = sum(pr.get('similarity', 0) for pr in similar_prs) / len(similar_prs)

        # Novelty is inverse of similarity
        # similarity 0.9 -> novelty 0.1
        # similarity 0.1 -> novelty 0.9
        novelty = 1.0 - avg_similarity

        return round(novelty, 3)

    def _identify_patterns(
        self,
        pr_event: PREvent
    ) -> List[str]:
        """Identify code patterns from the PR and similar PRs."""
        patterns = []

        # Pattern 1: File type analysis
        file_extensions = {f.filename.split('.')[-1] for f in pr_event.files if '.' in f.filename}
        if file_extensions:
            patterns.append(f"file_types: {','.join(sorted(file_extensions))}")

        # Pattern 2: Change type
        additions = sum(f.additions for f in pr_event.files)
        deletions = sum(f.deletions for f in pr_event.files)
        if additions > deletions * 2:
            patterns.append("change_type: feature_addition")
        elif deletions > additions * 2:
            patterns.append("change_type: code_removal")
        else:
            patterns.append("change_type: refactoring")

        # Pattern 3: PR size
        if len(pr_event.files) > 20:
            patterns.append("size: large")
        elif len(pr_event.files) > 10:
            patterns.append("size: medium")
        else:
            patterns.append("size: small")

        return patterns

    def get_name(self) -> str:
        """Get agent name."""
        return self.agent_name

