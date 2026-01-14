"""Main orchestrator agent that calls all other agents."""
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from models.pr_event import PREvent
from models.analysis_result import AgentResult, Issue
from agents.base_agent import BaseAgent
from agents.multilanguage_static_analysis_agent import MultiLanguageStaticAnalysisAgent
from agents.multilanguage_security_agent import MultiLanguageSecurityAgent
from agents.multilanguage_code_quality_agent import MultiLanguageCodeQualityAgent
from agents.context_agent import ContextAgent
from agents.coverage_agent import CoverageAgent
from agents.rag_enhanced_agent import RAGEnhancedAgent
from utils.logger import logger


class MainAgent(BaseAgent):
    """
    Main orchestrator agent that coordinates all specialized agents.
    Runs all agents in sequence and aggregates results.
    """
    
    def __init__(self, config: dict, db_service=None):
        """Initialize the main agent with all sub-agents."""
        super().__init__("Main Orchestrator Agent", config)
        
        # Store db_service for RAG agent
        self.db_service = db_service
        
        # Initialize all specialized agents
        self.agents = []
        
        # Static Analysis Agent
        if config.get('static_analysis', {}).get('enabled', True):
            self.agents.append(MultiLanguageStaticAnalysisAgent(
                config.get('static_analysis', {})
            ))
            self.logger.info("Static Analysis Agent enabled")
        
        # Security Agent
        if config.get('security', {}).get('enabled', True):
            self.agents.append(MultiLanguageSecurityAgent(
                config.get('security', {})
            ))
            self.logger.info("Security Agent enabled")
        
        # Code Quality Agent
        if config.get('code_quality', {}).get('enabled', True):
            self.agents.append(MultiLanguageCodeQualityAgent(
                config.get('code_quality', {})
            ))
            self.logger.info("Code Quality Agent enabled")
        
        # Context Agent
        if config.get('context', {}).get('enabled', True):
            self.agents.append(ContextAgent(
                config.get('context', {})
            ))
            self.logger.info("Context Agent enabled")
        
        # Coverage & Metrics Agent (SonarQube-like)
        if config.get('coverage', {}).get('enabled', True):
            self.agents.append(CoverageAgent(
                config.get('coverage', {})
            ))
            self.logger.info("Coverage & Metrics Agent enabled")
        
        # RAG Enhanced Agent (Optional - requires AI provider + vector DB)
        # Note: RAG includes AI summarization + historical context learning
        if config.get('rag_enhanced', {}).get('enabled', False):
            try:
                if db_service is None:
                    self.logger.warning("RAG Enhanced Agent requires db_service - skipping initialization")
                else:
                    rag_agent = RAGEnhancedAgent(db_service)
                    if rag_agent.enabled:
                        self.agents.append(rag_agent)
                        self.logger.info("RAG Enhanced Agent enabled")
                    else:
                        self.logger.warning("RAG Enhanced Agent disabled (dependencies or API key missing)")
            except Exception as e:
                self.logger.warning(f"Failed to initialize RAG Enhanced Agent: {e}")
        
        self.logger.info(f"Main Agent initialized with {len(self.agents)} sub-agents")
    
    def _analyze_impl(self, pr_event: PREvent) -> List[Issue]:
        """
        Run all agents and aggregate their results.
        Uses parallel execution for independent agents to improve performance.
        
        Args:
            pr_event: PR event to analyze
            
        Returns:
            Aggregated list of all issues from all agents
        """
        all_issues = []
        agent_results = {}
        
        self.logger.info(
            "Starting comprehensive analysis with all agents",
            pr_number=pr_event.pr_number,
            repository=pr_event.repository,
            file_count=len(pr_event.files)
        )
        
        # Separate RAG agent from others (RAG should run last)
        rag_agents = [a for a in self.agents if isinstance(a, RAGEnhancedAgent)]
        other_agents = [a for a in self.agents if not isinstance(a, RAGEnhancedAgent)]
        
        # Run non-RAG agents in parallel for faster execution
        if other_agents:
            with ThreadPoolExecutor(max_workers=min(len(other_agents), 5)) as executor:
                # Submit all agent tasks
                future_to_agent = {
                    executor.submit(self._run_single_agent, agent, pr_event): agent
                    for agent in other_agents
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_agent):
                    agent = future_to_agent[future]
                    try:
                        agent_result, agent_name = future.result()
                        agent_results[agent_name] = agent_result
                        all_issues.extend(agent_result['issues'])
                        
                        self.logger.info(
                            f"{agent_name} completed",
                            issues_found=agent_result['issues_count']
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Error in {agent.name}",
                            error=str(e),
                            exc_info=True
                        )
                        agent_results[agent.name] = {
                            'error': str(e),
                            'issues_count': 0,
                            'issues': []
                        }
        
        # Run RAG agents last (they may use context from other agents)
        for agent in rag_agents:
            try:
                self.logger.info(f"Running {agent.name}...")
                agent_result, agent_name = self._run_single_agent(agent, pr_event)
                agent_results[agent_name] = agent_result
                all_issues.extend(agent_result['issues'])
                
                self.logger.info(
                    f"{agent_name} completed",
                    issues_found=agent_result['issues_count']
                )
            except Exception as e:
                self.logger.error(
                    f"Error in {agent.name}",
                    error=str(e),
                    exc_info=True
                )
                agent_results[agent.name] = {
                    'error': str(e),
                    'issues_count': 0,
                    'issues': []
                }
        
        # Log summary
        self.logger.info(
            "All agents completed",
            total_issues=len(all_issues),
            agent_results={name: result['issues_count'] for name, result in agent_results.items()}
        )
        
        # Store agent results in metadata for reporting
        self._agent_breakdown = agent_results
        
        # Phase 1: Update RAG agents with full analysis results for "learning"
        # Pass the full agent breakdown so RAG can access metrics (coverage, complexity, etc.)
        for agent in rag_agents:
            if hasattr(agent, '_update_pr_analysis_results'):
                try:
                    # UPDATED: Pass the full breakdown + issues for richer learning
                    agent._update_pr_analysis_results(pr_event, all_issues, agent_results)
                except Exception as e:
                    self.logger.error(f"Failed to update RAG learning for {agent.name}: {e}")
        return all_issues
    
    def _run_single_agent(self, agent: BaseAgent, pr_event: PREvent) -> tuple:
        """
        Run a single agent and return its results.
        
        Args:
            agent: Agent to run
            pr_event: PR event to analyze
            
        Returns:
            Tuple of (agent_result_dict, agent_name)
        """
        agent_result = agent.analyze(pr_event)
        
        # Store results (include both metrics and metadata for database persistence)
        result_dict = {
            'issues_count': len(agent_result.issues),
            'issues': agent_result.issues,
            'metrics': agent_result.metrics,  # Standard metrics
            'metadata': agent_result.metadata  # Custom metadata (e.g., RAG data)
        }
        
        return result_dict, agent.name
    
    def get_agent_breakdown(self) -> dict:
        """Get breakdown of issues by agent."""
        return getattr(self, '_agent_breakdown', {})
