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
from typing import Dict, Any, List, Optional
from models.pr_event import PREvent
from agents.base_agent import BaseAgent, AgentResult
from utils.logger import logger

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
            logger.warning(f"RAG Agent disabled - missing dependencies (vector_db={bool(self.vector_db)}, embeddings={bool(self.embedding_model)}, ai_client={ai_client_ready})")
            logger.warning("RAG Agent disabled - missing dependencies")
    
    def _init_vector_db(self):
        """Initialize vector database (ChromaDB)."""
        if not CHROMADB_AVAILABLE:
            logger.warning("ChromaDB not available. Install: pip install chromadb")
            self.vector_db = None
            return
        
        try:
            # Initialize ChromaDB (persistent storage) - NEW API
            persist_directory = os.getenv('VECTOR_DB_PATH', './vector_db')
            
            # Use new PersistentClient API
            self.chroma_client = chromadb.PersistentClient(path=persist_directory)
            
            # Get or create collection for PR analyses
            self.vector_db = self.chroma_client.get_or_create_collection(
                name="pr_analyses",
                metadata={"description": "Historical PR analyses for RAG"}
            )
            
            logger.info(f"Vector DB initialized: {self.vector_db.count()} documents")
            
        except Exception as e:
            logger.error(f"Failed to initialize vector DB: {e}")
            self.vector_db = None
    
    def _init_embeddings(self):
        """Initialize embedding model."""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.warning("SentenceTransformers not available. Install: pip install sentence-transformers")
            self.embedding_model = None
            return
        
        try:
            # Use a lightweight, fast model
            model_name = os.getenv('EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
            self.embedding_model = SentenceTransformer(model_name)
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
            logger.info(f"Initializing AI client - provider: {self.ai_provider}, OPENAI_AVAILABLE: {OPENAI_AVAILABLE}, GEMINI_AVAILABLE: {GEMINI_AVAILABLE}")
            logger.info(f"API key present: {bool(self.api_key)}, API key length: {len(self.api_key) if self.api_key else 0}")
            
            if self.ai_provider == 'gemini' and GEMINI_AVAILABLE:
                genai.configure(api_key=self.api_key)
                # Get Gemini model from config or use default
                from utils.config import config
                gemini_model = config.get('agents.rag_enhanced.gemini_model', 'gemini-1.5-flash')
                self.model = genai.GenerativeModel(gemini_model)
                self.model_name = gemini_model
                logger.info(f"Initialized Gemini model: {gemini_model}")
                return True
            elif self.ai_provider == 'openai' and OPENAI_AVAILABLE:
                # Initialize OpenAI client with just the API key
                self.client = OpenAI(api_key=self.api_key)
                # Get OpenAI model from config or use default
                from utils.config import config
                openai_model = config.get('agents.rag_enhanced.openai_model', 'gpt-4o-mini')
                self.model_name = openai_model
                logger.info(f"Initialized OpenAI model: {openai_model} - client type: {type(self.client)}")
                return True
            else:
                logger.error(f"AI provider {self.ai_provider} not available - OPENAI_AVAILABLE={OPENAI_AVAILABLE}, GEMINI_AVAILABLE={GEMINI_AVAILABLE}")
                return False
        except Exception as e:
            logger.error(f"Failed to initialize AI client: {e}", exc_info=True)
            return False
    
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
        
        Args:
            pr_event: Current PR being analyzed
            
        Returns:
            Dictionary with similar PRs and best practices
        """
        context = {
            'similar_prs': [],
            'best_practices': [],
            'historical_issues': []
        }
        
        if not self.vector_db or not self.embedding_model:
            return context
        
        try:
            # Create query from PR content
            query_text = self._create_query_text(pr_event)
            
            # Generate embedding for query
            query_embedding = self.embedding_model.encode(query_text).tolist()
            
            # Determine max results - limit to 5 for performance
            max_results = min(5, self.vector_db.count() if hasattr(self.vector_db, 'count') else 5)
            
            # Search for similar PRs
            results = self.vector_db.query(
                query_embeddings=[query_embedding],
                n_results=max_results,
                include=['metadatas', 'documents', 'distances']
            )
            
            # Process results and filter by similarity threshold
            # ChromaDB returns squared L2 distance - smaller is better
            # For normalized embeddings, L2 distance ≈ sqrt(2 * (1 - cosine_similarity))
            # So distance of 0.8 ≈ cosine similarity of 0.68
            max_distance = 1.2  # Corresponds to ~0.28 cosine similarity threshold
            
            if results and results['documents']:
                for i, doc in enumerate(results['documents'][0]):
                    metadata = results['metadatas'][0][i]
                    distance = results['distances'][0][i]
                    
                    # Convert L2 distance to approximate cosine similarity
                    # For normalized vectors: cosine_sim ≈ 1 - (L2_distance² / 2)
                    similarity = max(0, 1 - (distance / 2))
                    
                    # Only include PRs that are reasonably similar (distance < 1.2)
                    if distance < max_distance:
                        context['similar_prs'].append({
                            'pr_number': metadata.get('pr_number'),
                            'pr_title': metadata.get('pr_title'),
                            'issues_found': metadata.get('issues_found'),
                            'similarity_score': similarity,
                            'similarity': similarity,  # For compatibility
                            'summary': doc[:200],  # First 200 chars
                            'distance': distance  # Include raw distance for debugging
                        })
            
            logger.info(f"Retrieved {len(context['similar_prs'])} similar PRs (max_distance: {max_distance})")
            
        except Exception as e:
            logger.error(f"Context retrieval failed: {e}")
        
        return context
    
    def _create_query_text(self, pr_event: PREvent) -> str:
        """Create search query from PR content."""
        # Combine PR title, description, and file names
        query_parts = [
            pr_event.pr_title,
            pr_event.pr_description[:500] if pr_event.pr_description else '',
            ' '.join([f.filename for f in pr_event.files[:10]])
        ]
        return ' '.join(filter(None, query_parts))
    
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
        """Build concise prompt with retrieved context."""
        
        # Format similar PRs context - limit to top 2 for speed
        similar_prs_text = ""
        if relevant_context['similar_prs']:
            similar_prs_text = "\n**Similar PRs:**\n"
            for pr in relevant_context['similar_prs'][:2]:  # Top 2 only
                similar_prs_text += f"- PR #{pr['pr_number']}: {pr['pr_title']} ({pr['issues_found']} issues)\n"
        
        # Limit description to 300 chars
        pr_description = pr_event.pr_description[:300] if pr_event.pr_description else "No description"
        
        prompt = f"""Analyze this PR using historical data:

**Current PR:** {pr_event.pr_title}
- Description: {pr_description}
- Files: {len(pr_event.files)} | Branch: {pr_event.head_branch} → {pr_event.base_branch}
{similar_prs_text}

Provide brief, actionable insights (1-2 points each):
1. **Lessons**: Common issues from similar PRs
2. **Recommendations**: Key review focus areas  
3. **Pitfalls**: Mistakes to avoid
4. **Best Practices**: Patterns to follow
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
            embedding = self.embedding_model.encode(doc_text).tolist()
            
            # Store in vector DB
            self.vector_db.add(
                embeddings=[embedding],
                documents=[doc_text],
                metadatas=[{
                    'pr_number': pr_event.pr_number,
                    'pr_title': pr_event.pr_title,
                    'repository': pr_event.repository,
                    'author': pr_event.author.login,
                    'files_count': len(pr_event.files),
                    'issues_found': 0  # Will be updated after analysis
                }],
                ids=[f"pr_{pr_event.repository}_{pr_event.pr_number}"]
            )
            
            logger.info(f"Stored PR #{pr_event.pr_number} in vector DB")
            
        except Exception as e:
            logger.error(f"Failed to store PR in vector DB: {e}")
    
    def index_historical_prs(self, limit: int = 100):
        """
        Index historical PRs from database into vector DB.
        Run this once to build the initial index.
        
        Args:
            limit: Number of PRs to index (start with recent ones)
        """
        if not self.db_service or not self.vector_db:
            logger.error("Cannot index: DB service or vector DB not available")
            return
        
        try:
            logger.info(f"Indexing up to {limit} historical PRs...")
            
            # Fetch PRs from database
            with self.db_service.Session() as session:
                from models.database import PRAnalysis
                
                prs = session.query(PRAnalysis)\
                    .order_by(PRAnalysis.analyzed_at.desc())\
                    .limit(limit)\
                    .all()
                
                indexed = 0
                for pr in prs:
                    doc_text = f"{pr.pr_title}\n\n{pr.pr_description or ''}\n\nRepository: {pr.repository}"
                    
                    # Generate embedding
                    embedding = self.embedding_model.encode(doc_text).tolist()
                    
                    # Store in vector DB
                    self.vector_db.add(
                        embeddings=[embedding],
                        documents=[doc_text],
                        metadatas=[{
                            'pr_number': pr.pr_number,
                            'pr_title': pr.pr_title,
                            'repository': pr.repository,
                            'author': pr.author_login,
                            'issues_found': pr.total_issues,
                            'quality_score': pr.overall_quality_score or 0
                        }],
                        ids=[f"pr_{pr.repository}_{pr.pr_number}"]
                    )
                    indexed += 1
                
                logger.info(f"Successfully indexed {indexed} PRs")
                
        except Exception as e:
            logger.error(f"Failed to index historical PRs: {e}")
    
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

