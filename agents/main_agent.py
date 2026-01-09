"""Main orchestrator agent that calls all other agents."""
from typing import List
from models.pr_event import PREvent
from models.analysis_result import AgentResult, Issue
from agents.base_agent import BaseAgent
from agents.multilanguage_static_analysis_agent import MultiLanguageStaticAnalysisAgent
from agents.multilanguage_security_agent import MultiLanguageSecurityAgent
from agents.multilanguage_code_quality_agent import MultiLanguageCodeQualityAgent
from agents.context_agent import ContextAgent
from agents.coverage_agent import CoverageAgent
from utils.logger import logger


class MainAgent(BaseAgent):
    """
    Main orchestrator agent that coordinates all specialized agents.
    Runs all agents in sequence and aggregates results.
    """
    
    def __init__(self, config: dict):
        """Initialize the main agent with all sub-agents."""
        super().__init__("Main Orchestrator Agent", config)
        
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
        
        self.logger.info(f"Main Agent initialized with {len(self.agents)} sub-agents")
    
    def _analyze_impl(self, pr_event: PREvent) -> List[Issue]:
        """
        Run all agents and aggregate their results.
        
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
        
        # Run each agent sequentially
        for agent in self.agents:
            try:
                self.logger.info(f"Running {agent.name}...")
                
                # Analyze with this agent
                agent_result = agent.analyze(pr_event)
                
                # Store results (include metrics for database persistence)
                agent_results[agent.name] = {
                    'issues_count': len(agent_result.issues),
                    'issues': agent_result.issues,
                    'metadata': agent_result.metrics  # Include agent metrics
                }
                
                # Add to aggregated results
                all_issues.extend(agent_result.issues)
                
                self.logger.info(
                    f"{agent.name} completed",
                    issues_found=len(agent_result.issues)
                )
                
            except Exception as e:
                self.logger.error(
                    f"Error in {agent.name}",
                    error=str(e),
                    exc_info=True
                )
                # Continue with other agents even if one fails
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
        # We construct a temporary AgentResult-like object with all issues
        from collections import namedtuple
        temp_result = namedtuple('TempResult', ['issues'])(all_issues)
        
        for agent in rag_agents:
            if hasattr(agent, '_update_pr_analysis_results'):
                try:
                    agent._update_pr_analysis_results(pr_event, temp_result)
                except Exception as e:
                    self.logger.error(f"Failed to update RAG learning for {agent.name}: {e}")
        
        return all_issues
    
    def get_agent_breakdown(self) -> dict:
        """Get breakdown of issues by agent."""
        return getattr(self, '_agent_breakdown', {})
