"""
Research Module - Modular Research Pipeline

This module splits the large perform_agent_research() function into:
- orchestrator: Top-Level Research Orchestration (perform_agent_research)
- cache_handler: Cache check and metadata handling
- query_processor: Query optimization and web search
- scraper_orchestrator: Parallel web scraping
- context_builder: Context building and LLM inference
"""

from .orchestrator import perform_agent_research
from .cache_handler import handle_cache_hit
from .query_processor import process_query_and_search
from .scraper_orchestrator import orchestrate_scraping
from .context_builder import build_and_generate_response

__all__ = [
    'perform_agent_research',
    'handle_cache_hit',
    'process_query_and_search',
    'orchestrate_scraping',
    'build_and_generate_response',
]
