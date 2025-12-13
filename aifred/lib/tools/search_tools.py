"""
Search Tool Classes - Web Search APIs

Extracted from agent_tools.py for better modularity.
Includes: Brave, Tavily, SearXNG, MultiAPI Search
"""

import requests
import logging
import os
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from .base import BaseTool, RateLimitError, APIKeyMissingError
from .url_utils import deduplicate_urls

# Logging Setup
logger = logging.getLogger(__name__)

# ============================================================
# BRAVE SEARCH API (Primary)
# ============================================================

class BraveSearchTool(BaseTool):
    """
    Brave Search API - Primary Search Engine

    - 2.000 kostenlose Queries/Monat
    - Privacy-focused, eigener Index (30B+ Seiten)
    - Beste Qualität für News/aktuelle Events
    - API Key: https://brave.com/search/api/
    """

    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self.name = "Brave Search"
        self.description = "Brave Search API (Primary)"
        self.api_key = api_key or os.getenv('BRAVE_API_KEY')
        self.api_url = "https://api.search.brave.com/res/v1/web/search"
        self.min_call_interval = 1.0

    def execute(self, query: str, **kwargs) -> Dict:
        """
        Führt Brave Search durch

        Returns:
            {
                'success': bool,
                'source': 'Brave Search',
                'query': str,
                'related_urls': List[str],
                'titles': List[str],
                'snippets': List[str],
                'content': str,
                'error': str (optional)
            }
        """
        if not self.api_key:
            raise APIKeyMissingError("Brave API Key fehlt! Setze BRAVE_API_KEY env variable.")

        self._rate_limit_check()

        try:
            logger.info(f"🦁 Brave Search: {query}")

            response = requests.get(
                self.api_url,
                params={'q': query, 'count': 10},
                headers={
                    'Accept': 'application/json',
                    'X-Subscription-Token': self.api_key
                },
                timeout=15
            )

            # Check rate limit
            if response.status_code == 429:
                logger.warning("Brave Search: Rate Limit erreicht!")
                raise RateLimitError("Brave Search API rate limit exceeded")

            response.raise_for_status()
            data = response.json()

            # Extrahiere Ergebnisse
            web_results = data.get('web', {}).get('results', [])
            related_urls, titles, snippets, content = self._extract_urls_from_results(
                web_results, url_key='url', title_key='title', content_key='description', max_results=10
            )

            result = {
                'success': True,
                'source': 'Brave Search',
                'query': query,
                'related_urls': related_urls,
                'titles': titles,
                'snippets': snippets,
                'content': content,
                'url': related_urls[0] if related_urls else ''
            }

            logger.info(f"✅ Brave Search: {len(related_urls)} URLs gefunden")

            # DEBUG: Logge alle gefundenen URLs mit Titeln
            logger.info("📋 Brave Search Rohdaten (alle URLs vor KI-Bewertung):")
            for i, (url, title) in enumerate(zip(related_urls, titles), 1):
                logger.info(f"   {i}. {title}")
                logger.info(f"      URL: {url}")

            return result

        except RateLimitError:
            raise  # Re-raise für Fallback

        except Exception as e:
            logger.error(f"❌ Brave Search Fehler: {e}")
            return {
                'success': False,
                'source': 'Brave Search',
                'query': query,
                'related_urls': [],
                'error': str(e)
            }


# ============================================================
# TAVILY AI (Fallback 1)
# ============================================================

class TavilySearchTool(BaseTool):
    """
    Tavily AI - RAG-optimierte Suche

    - 1.000 kostenlose Queries/Monat
    - Speziell für AI/LLM gebaut
    - News-Filter eingebaut
    - API Key: https://www.tavily.com/
    """

    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self.name = "Tavily AI"
        self.description = "Tavily AI Search (RAG-optimiert)"
        self.api_key = api_key or os.getenv('TAVILY_API_KEY')
        self.api_url = "https://api.tavily.com/search"
        self.min_call_interval = 1.0

    def execute(self, query: str, **kwargs) -> Dict:
        """Führt Tavily Search durch"""
        if not self.api_key:
            raise APIKeyMissingError("Tavily API Key fehlt! Setze TAVILY_API_KEY env variable.")

        self._rate_limit_check()

        try:
            logger.info(f"🔍 Tavily AI: {query}")

            payload = {
                'api_key': self.api_key,
                'query': query,
                'search_depth': 'basic',  # basic oder advanced
                'include_answer': False,
                'include_raw_content': False,
                'max_results': 10,
                'include_domains': [],
                'exclude_domains': []
            }

            response = requests.post(
                self.api_url,
                json=payload,
                timeout=15
            )

            if response.status_code == 429:
                logger.warning("Tavily: Rate Limit erreicht!")
                raise RateLimitError("Tavily API rate limit exceeded")

            response.raise_for_status()
            data = response.json()

            # Extrahiere Ergebnisse
            results = data.get('results', [])
            related_urls, titles, snippets, content = self._extract_urls_from_results(
                results, url_key='url', title_key='title', content_key='content', max_results=10
            )

            result = {
                'success': True,
                'source': 'Tavily AI',
                'query': query,
                'related_urls': related_urls,
                'titles': titles,
                'snippets': snippets,
                'content': content,
                'url': related_urls[0] if related_urls else ''
            }

            logger.info(f"✅ Tavily AI: {len(related_urls)} URLs gefunden")

            # DEBUG: Logge alle gefundenen URLs mit Titeln
            logger.info("📋 Tavily AI Rohdaten (alle URLs vor KI-Bewertung):")
            for i, (url, title) in enumerate(zip(related_urls, titles), 1):
                logger.info(f"   {i}. {title}")
                logger.info(f"      URL: {url}")

            return result

        except RateLimitError:
            raise

        except Exception as e:
            logger.error(f"❌ Tavily AI Fehler: {e}")
            return {
                'success': False,
                'source': 'Tavily AI',
                'query': query,
                'related_urls': [],
                'error': str(e)
            }


# ============================================================
# SEARXNG (Last Resort - Self-Hosted)
# ============================================================

class SearXNGSearchTool(BaseTool):
    """
    SearXNG - Self-Hosted Meta-Search

    - Unlimited (self-hosted)
    - Privacy-focused (keine Tracking)
    - Meta-Search (fragt Google/Bing/DDG ab)
    - Setup: docker run -p 8888:8080 searxng/searxng
    """

    def __init__(self, base_url: str = "http://localhost:8888"):
        super().__init__()
        self.name = "SearXNG"
        self.description = "Self-Hosted Meta-Search (Unlimited)"
        self.base_url = base_url.rstrip('/')
        self.min_call_interval = 0.5  # Lokal, kann schneller sein

    def execute(self, query: str, **kwargs) -> Dict:
        """Führt SearXNG Search durch"""
        self._rate_limit_check()

        try:
            logger.info(f"🌐 SearXNG (Self-Hosted): {query}")

            params = {
                'q': query,
                'format': 'json',
                'language': 'de',
                'pageno': 1
            }

            response = requests.get(
                f"{self.base_url}/search",
                params=params,
                timeout=15
            )

            response.raise_for_status()
            data = response.json()

            # Extrahiere Ergebnisse
            results = data.get('results', [])
            related_urls, titles, snippets, content = self._extract_urls_from_results(
                results, url_key='url', title_key='title', content_key='content', max_results=10
            )

            result = {
                'success': True,
                'source': 'SearXNG (Self-Hosted)',
                'query': query,
                'related_urls': related_urls,
                'titles': titles,
                'snippets': snippets,
                'content': content,
                'url': related_urls[0] if related_urls else ''
            }

            logger.info(f"✅ SearXNG: {len(related_urls)} URLs gefunden")

            # DEBUG: Logge alle gefundenen URLs mit Titeln
            logger.info("📋 SearXNG Rohdaten (alle URLs vor KI-Bewertung):")
            for i, (url, title) in enumerate(zip(related_urls, titles), 1):
                logger.info(f"   {i}. {title}")
                logger.info(f"      URL: {url}")

            return result

        except Exception as e:
            logger.error(f"❌ SearXNG Fehler: {e}")
            return {
                'success': False,
                'source': 'SearXNG',
                'query': query,
                'related_urls': [],
                'error': str(e)
            }


# ============================================================
# MULTI-API SEARCH mit FALLBACK
# ============================================================

class MultiAPISearchTool(BaseTool):
    """
    Meta-Tool: Nutzt alle Search APIs mit automatischem Fallback

    Reihenfolge:
    1. Tavily AI (1.000/Monat) - AI-optimiert für RAG, aktuellste Artikel
    2. Brave Search (2.000/Monat) - Privacy-focused, gute Qualität
    3. SearXNG (unlimited) - Self-hosted, immer verfügbar
    """

    def __init__(self,
                 brave_key: Optional[str] = None,
                 tavily_key: Optional[str] = None,
                 searxng_url: str = "http://localhost:8888"):
        super().__init__()
        self.name = "Multi-API Search"
        self.description = "3-Stufen Fallback Search"

        # Initialisiere alle APIs mit explizitem Typ
        self.apis: List[BaseTool] = []

        # Tavily (Primary) - AI-optimiert, bessere Aktualität
        if tavily_key or os.getenv('TAVILY_API_KEY'):
            try:
                self.apis.append(TavilySearchTool(tavily_key))
                logger.info("✅ Tavily AI aktiviert (Primary)")
            except (APIKeyMissingError, ValueError, RuntimeError) as e:
                logger.warning(f"⚠️ Tavily AI konnte nicht initialisiert werden: {e}")

        # Brave (Fallback 1)
        if brave_key or os.getenv('BRAVE_API_KEY'):
            try:
                self.apis.append(BraveSearchTool(brave_key))
                logger.info("✅ Brave Search API aktiviert (Fallback 1)")
            except (APIKeyMissingError, ValueError, RuntimeError) as e:
                logger.warning(f"⚠️ Brave Search API konnte nicht initialisiert werden: {e}")

        # SearXNG (Last Resort - immer verfügbar wenn Server läuft)
        self.apis.append(SearXNGSearchTool(searxng_url))
        logger.info("✅ SearXNG aktiviert (Last Resort)")

    def execute(self, query: str, **kwargs) -> Dict:
        """
        Führt Suche PARALLEL durch - sammelt URLs von ALLEN APIs!

        Parallel Execution: Alle APIs starten gleichzeitig.
        Collect All: Warte auf alle APIs, sammle alle URLs.
        Deduplizierung: Entferne doppelte URLs (www, trailing slash, etc.)
        """
        if not self.apis:
            logger.error("❌ Keine Search APIs konfiguriert!")
            return {
                'success': False,
                'source': 'Multi-API Search',
                'query': query,
                'related_urls': [],
                'error': 'Keine Search APIs verfügbar'
            }

        logger.info(f"🚀 Parallel Search: {len(self.apis)} APIs gleichzeitig")

        # Parallel Execution - Sammle ALLE Ergebnisse
        all_urls = []
        successful_apis = []
        failed_apis = []

        with ThreadPoolExecutor(max_workers=len(self.apis)) as executor:
            # Starte alle APIs parallel
            future_to_api = {
                executor.submit(api.execute, query, **kwargs): api
                for api in self.apis
            }

            # Sammle Ergebnisse von ALLEN APIs
            for future in as_completed(future_to_api):
                api = future_to_api[future]
                try:
                    result = future.result(timeout=15)  # Max 15s pro API

                    # Erfolgreiche Antwort mit URLs?
                    if result.get('success') and result.get('related_urls'):
                        urls = result['related_urls']
                        logger.info(f"✅ {api.name}: {len(urls)} URLs gefunden")
                        all_urls.extend(urls)
                        successful_apis.append(api.name)
                    else:
                        logger.warning(f"⚠️ {api.name}: Keine URLs gefunden")
                        failed_apis.append((api.name, "Keine URLs"))

                except (RateLimitError, APIKeyMissingError) as e:
                    logger.warning(f"⚠️ {api.name}: {e}")
                    failed_apis.append((api.name, str(e)))

                except Exception as e:
                    logger.error(f"❌ {api.name}: {e}")
                    failed_apis.append((api.name, str(e)))

        # Mindestens eine API erfolgreich?
        if not all_urls:
            logger.error("❌ Alle Search APIs fehlgeschlagen!")
            error_summary = ", ".join([f"{name}: {err}" for name, err in failed_apis])
            return {
                'success': False,
                'source': 'Multi-API Search',
                'query': query,
                'related_urls': [],
                'error': f'Alle APIs fehlgeschlagen. Details: {error_summary}'
            }

        # Deduplizierung
        unique_urls = deduplicate_urls(all_urls)

        logger.info(f"🔄 Gesammelt: {len(all_urls)} URLs von {len(successful_apis)} APIs → {len(unique_urls)} unique URLs")

        return {
            'success': True,
            'source': 'Multi-API Search',
            'apis_used': successful_apis,
            'query': query,
            'related_urls': unique_urls,
            'stats': {
                'total_urls': len(all_urls),
                'unique_urls': len(unique_urls),
                'duplicates_removed': len(all_urls) - len(unique_urls),
                'successful_apis': len(successful_apis),
                'failed_apis': len(failed_apis)
            }
        }

    def execute_multi_query(self, queries: List[str], **kwargs) -> Dict:
        """
        Verteilt mehrere Queries auf verfügbare APIs (1:1 Mapping)

        Query 1 → API 1 (Tavily)
        Query 2 → API 2 (Brave)
        Query 3 → API 3 (SearXNG)

        Falls mehr Queries als APIs: Round-Robin (Query 4 → API 1, etc.)
        Falls weniger Queries als APIs: Nur die ersten N APIs werden genutzt

        Args:
            queries: Liste von Such-Queries (1-3 typischerweise)

        Returns:
            Dict mit aggregierten Ergebnissen und detaillierten Stats
        """
        if not queries:
            logger.error("❌ Keine Queries übergeben!")
            return {
                'success': False,
                'source': 'Multi-API Search (Multi-Query)',
                'queries': [],
                'related_urls': [],
                'error': 'Keine Queries übergeben'
            }

        if not self.apis:
            logger.error("❌ Keine Search APIs konfiguriert!")
            return {
                'success': False,
                'source': 'Multi-API Search (Multi-Query)',
                'queries': queries,
                'related_urls': [],
                'error': 'Keine Search APIs verfügbar'
            }

        num_queries = len(queries)
        num_apis = len(self.apis)

        logger.info(f"🚀 Multi-Query Search: {num_queries} Queries → {num_apis} APIs")

        # Erstelle Query-API Zuordnung (Round-Robin bei mehr Queries als APIs)
        query_api_pairs = []
        for i, query in enumerate(queries):
            api = self.apis[i % num_apis]  # Round-Robin
            query_api_pairs.append((query, api))
            logger.info(f"   Query {i+1} → {api.name}: {query[:50]}...")

        # Parallel Execution
        all_urls = []
        successful_apis = []
        failed_apis = []
        query_results = []  # Detaillierte Ergebnisse pro Query

        with ThreadPoolExecutor(max_workers=len(query_api_pairs)) as executor:
            # Starte alle Query-API Kombinationen parallel
            future_to_pair = {
                executor.submit(api.execute, query, **kwargs): (query, api)
                for query, api in query_api_pairs
            }

            # Sammle Ergebnisse
            for future in as_completed(future_to_pair):
                query, api = future_to_pair[future]
                try:
                    result = future.result(timeout=15)

                    if result.get('success') and result.get('related_urls'):
                        urls = result['related_urls']
                        logger.info(f"✅ {api.name} ({query[:30]}...): {len(urls)} URLs")
                        all_urls.extend(urls)
                        successful_apis.append(api.name)
                        query_results.append({
                            'query': query,
                            'api': api.name,
                            'urls_found': len(urls),
                            'success': True
                        })
                    else:
                        logger.warning(f"⚠️ {api.name} ({query[:30]}...): Keine URLs")
                        failed_apis.append((api.name, "Keine URLs"))
                        query_results.append({
                            'query': query,
                            'api': api.name,
                            'urls_found': 0,
                            'success': False,
                            'error': 'Keine URLs gefunden'
                        })

                except (RateLimitError, APIKeyMissingError) as e:
                    logger.warning(f"⚠️ {api.name}: {e}")
                    failed_apis.append((api.name, str(e)))
                    query_results.append({
                        'query': query,
                        'api': api.name,
                        'urls_found': 0,
                        'success': False,
                        'error': str(e)
                    })

                except Exception as e:
                    logger.error(f"❌ {api.name}: {e}")
                    failed_apis.append((api.name, str(e)))
                    query_results.append({
                        'query': query,
                        'api': api.name,
                        'urls_found': 0,
                        'success': False,
                        'error': str(e)
                    })

        # Mindestens eine Query erfolgreich?
        if not all_urls:
            logger.error("❌ Alle Queries fehlgeschlagen!")
            error_summary = ", ".join([f"{name}: {err}" for name, err in failed_apis])
            return {
                'success': False,
                'source': 'Multi-API Search (Multi-Query)',
                'queries': queries,
                'related_urls': [],
                'query_results': query_results,
                'error': f'Alle Queries fehlgeschlagen. Details: {error_summary}'
            }

        # Deduplizierung
        unique_urls = deduplicate_urls(all_urls)

        logger.info(f"🔄 Multi-Query Ergebnis: {len(all_urls)} URLs → {len(unique_urls)} unique")

        return {
            'success': True,
            'source': 'Multi-API Search (Multi-Query)',
            'apis_used': list(set(successful_apis)),  # Unique API names
            'queries': queries,
            'related_urls': unique_urls,
            'query_results': query_results,
            'stats': {
                'total_queries': num_queries,
                'successful_queries': len([r for r in query_results if r['success']]),
                'total_urls': len(all_urls),
                'unique_urls': len(unique_urls),
                'duplicates_removed': len(all_urls) - len(unique_urls),
                'successful_apis': len(set(successful_apis)),
                'failed_apis': len(failed_apis)
            }
        }

