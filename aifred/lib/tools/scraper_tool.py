"""
Web Scraper Tool - Content Extraction

Extracted from agent_tools.py for better modularity.
Supports HTML (trafilatura/Playwright) and PDF (PyMuPDF) content extraction.
"""

import io
import logging
import re
import time
import trafilatura
from trafilatura.settings import DEFAULT_CONFIG
from copy import deepcopy
from typing import Dict, Optional
import requests

from .base import BaseTool
from ..logging_utils import log_message
from ..config import PLAYWRIGHT_FALLBACK_THRESHOLD

# Optional: PyMuPDF for PDF extraction (best quality)
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    fitz = None

# Logging Setup
logger = logging.getLogger(__name__)

# ============================================================
# WEB SCRAPER TOOL (unverändert)
# ============================================================

class WebScraperTool(BaseTool):
    """
    Web-Scraper mit trafilatura + Playwright Fallback

    Extrahiert sauberen Text-Content von Webseiten.
    trafilatura filtert automatisch Werbung, Navigation und Cookie-Banner.
    """

    # Konstanten
    # PLAYWRIGHT_FALLBACK_THRESHOLD aus config.py importiert (Modul-Level)
    MAX_RETRY_ATTEMPTS = 2  # Maximum retry attempts for Cloudflare/rate-limit blocks
    RETRY_DELAY = 3.0  # Seconds to wait before retry

    def __init__(self):
        super().__init__()
        self.name = "Web Scraper"
        self.description = "Extrahiert Text-Content von Webseiten"
        self.min_call_interval = 1.0

        # trafilatura Config mit 10s Timeout (statt default 30s)
        self.trafilatura_config = deepcopy(DEFAULT_CONFIG)
        self.trafilatura_config.set('DEFAULT', 'DOWNLOAD_TIMEOUT', '10')
        self.trafilatura_config.set('DEFAULT', 'MAX_REDIRECTS', '2')  # Max 2 Redirects (default ist mehr)
    def execute(self, query: str, **kwargs) -> Dict:
        """
        Scraped eine Webseite komplett ohne Längenlimit

        Args:
            query: URL der Webseite (umbenennung von 'url' zu 'query' für BaseTool-Kompatibilität)

        Strategie (3-Stufen):
        0. PDF-Erkennung: Content-Type prüfen → PyMuPDF
        1. trafilatura (sauberster Content, filtert Werbung/Navigation/Cookies automatisch)
        2. Falls < threshold ODER fehlgeschlagen → Playwright (JavaScript-Rendering)

        trafilatura funktioniert für 95% aller Websites (News, Blogs, Wetter).
        Playwright nur für JavaScript-heavy Single-Page-Apps (React, Vue, etc.).
        PyMuPDF für PDFs (AWMF Leitlinien, Orphananesthesia, etc.)

        Ollama's dynamisches num_ctx übernimmt die Context-Größen-Kontrolle!
        """
        self._rate_limit_check()

        # Intern verwenden wir 'url' für Klarheit
        url = query

        # ============================================================
        # STEP 0: PDF-Erkennung (Content-Type Header Check)
        # ============================================================
        is_pdf = self._is_pdf_url(url)
        if is_pdf:
            logger.info(f"📄 PDF erkannt: {url}")
            log_message(f"📄 PDF erkannt: {url}")
            return self._scrape_pdf(url)

        # ============================================================
        # STEP 1: trafilatura (schnell + sauber für HTML)
        # ============================================================
        result = self._scrape_with_trafilatura(url)

        # Intelligente Playwright-Fallback-Strategie:
        # 1. Download failed (404, timeout, bot-protection) → KEIN Playwright (sinnlos!)
        # 2. Zu wenig Content (< threshold) → Playwright (JS-heavy Site!)

        if not result['success']:
            # Download failed → Site blockiert/down → Playwright bringt nichts!
            log_message("⚠️ trafilatura Download failed → SKIP Playwright (Site blockiert/down)")
            return result

        # Trafilatura erfolgreich, aber zu wenig Content? → JS-heavy Site!
        if result.get('word_count', 0) < PLAYWRIGHT_FALLBACK_THRESHOLD:
            log_message(f"⚠️ trafilatura nur {result['word_count']} Wörter → Retry mit Playwright (JavaScript)")
            playwright_result = self._scrape_with_playwright(url)
            if playwright_result['success']:
                log_message(f"✅ Playwright: {playwright_result['word_count']} Wörter (trafilatura: {result.get('word_count', 0)})")
                return playwright_result

        return result

    def _scrape_with_trafilatura(self, url: str, retry_attempt: int = 1) -> Dict:
        """
        Scraped mit trafilatura (sauberster Content)

        trafilatura ist spezialisiert auf Content-Extraktion und filtert automatisch:
        - Werbung und Tracking-Code
        - Navigation und Menüs
        - Cookie-Banner
        - Footer/Header Content
        - Social Media Widgets

        Perfekt für News-Artikel, Blog-Posts, Wetter-Seiten!

        Args:
            url: URL to scrape
            retry_attempt: Current retry attempt (1 = first try, 2 = retry)
        """
        try:
            if retry_attempt == 1:
                logger.info(f"🌐 Web Scraping: {url}")
                logger.debug("   Methode: trafilatura (Content-Extraktion)")
            else:
                logger.info(f"🔄 Retry {retry_attempt}/{self.MAX_RETRY_ATTEMPTS}: {url}")

            # Download HTML mit 10s Timeout (via config)
            downloaded = trafilatura.fetch_url(url, config=self.trafilatura_config)

            if not downloaded:
                error_msg = self._classify_error("Download failed")
                logger.error(f"❌ trafilatura: {error_msg}")

                # Retry Logic: If Cloudflare/Timeout and first attempt, retry after delay
                if retry_attempt < self.MAX_RETRY_ATTEMPTS:
                    logger.info(f"⏳ Waiting {self.RETRY_DELAY}s before retry...")
                    time.sleep(self.RETRY_DELAY)
                    return self._scrape_with_trafilatura(url, retry_attempt=retry_attempt + 1)

                return {
                    'success': False,
                    'method': 'trafilatura',
                    'source': url,
                    'error': error_msg,
                    'retry_attempts': retry_attempt
                }

            # Extract sauberen Content
            text = trafilatura.extract(
                downloaded,
                include_comments=False,  # Keine Kommentare
                include_tables=True,     # Tabellen behalten (wichtig für Wetter!)
                no_fallback=False,       # Fallback auf basic extraction wenn nötig
                favor_precision=True,    # Weniger Content, aber präziser (filtert mehr Werbung)
                output_format='txt'      # Plain text (nicht JSON/XML)
            )

            if not text:
                logger.warning("⚠️ trafilatura: Kein Content extrahiert")
                return {
                    'success': False,
                    'method': 'trafilatura',
                    'source': url,
                    'error': 'No content extracted'
                }

            # Titel extrahieren (optional, trafilatura kann das auch)
            metadata = trafilatura.extract_metadata(downloaded)
            title = metadata.title if metadata and metadata.title else ''

            # Text bereinigen
            text = self._clean_text(text)
            word_count = len(text.split())

            logger.info(f"  ✅ {word_count} Wörter extrahiert")

            return {
                'success': True,
                'source': url,
                'title': title,
                'content': text,
                'url': url,
                'word_count': word_count,
                'truncated': False,
                'method': 'trafilatura'
            }

        except Exception as e:
            error_msg = self._classify_error(str(e))
            logger.error(f"❌ trafilatura Fehler bei {url}: {error_msg}")

            # Retry Logic for transient errors (timeout, connection)
            if retry_attempt < self.MAX_RETRY_ATTEMPTS and any(keyword in str(e).lower() for keyword in ['timeout', 'connection', 'refused']):
                logger.info(f"⏳ Waiting {self.RETRY_DELAY}s before retry...")
                time.sleep(self.RETRY_DELAY)
                return self._scrape_with_trafilatura(url, retry_attempt=retry_attempt + 1)

            return {
                'success': False,
                'method': 'trafilatura',
                'source': url,
                'error': error_msg,
                'retry_attempts': retry_attempt
            }

    def _scrape_with_playwright(self, url: str) -> Dict:
        """Scraped mit Playwright (langsamer, aber JavaScript-fähig)"""
        try:
            from playwright.sync_api import sync_playwright

            logger.info(f"🌐 Web Scraping: {url}")
            logger.debug("   Methode: Playwright (JavaScript-Rendering)")

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                # Navigiere zur Seite und warte auf Netzwerk-Idle
                page.goto(url, wait_until='networkidle', timeout=10000)

                # Warte noch 2s für lazy-loaded Content
                page.wait_for_timeout(2000)

                # Titel
                title = page.title()

                # Extrahiere Text (nur sichtbarer Content)
                text = page.inner_text('body')
                text = self._clean_text(text)

                word_count = len(text.split())

                browser.close()

                return {
                    'success': True,
                    'source': url,
                    'title': title,
                    'content': text,
                    'url': url,
                    'word_count': word_count,
                    'truncated': False,
                    'method': 'playwright'
                }

        except Exception as e:
            error_msg = self._classify_error(str(e))
            logger.error(f"❌ Playwright Fehler bei {url}: {error_msg}")
            return {
                'success': False,
                'method': 'playwright',
                'source': url,
                'url': url,
                'error': error_msg
            }

    def _clean_text(self, text: str) -> str:
        """Säubert Text"""
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n+', '\n', text)
        return text.strip()

    def _classify_error(self, error_msg: str, downloaded_content: str = None) -> str:
        """
        Klassifiziert Fehler und gibt aussagekräftige Nachricht zurück

        Args:
            error_msg: Original error message
            downloaded_content: Downloaded HTML content (if any)

        Returns:
            Human-readable error classification
        """
        error_lower = error_msg.lower() if error_msg else ""

        # Cloudflare Detection
        if downloaded_content and ('cloudflare' in downloaded_content.lower() or
                                   'challenge' in downloaded_content.lower() or
                                   'just a moment' in downloaded_content.lower()):
            return "Cloudflare Challenge (Bot-Protection)"

        # HTTP Status Codes
        if '404' in error_msg or 'not found' in error_lower:
            return "404 Not Found"
        if '403' in error_msg or 'forbidden' in error_lower:
            return "403 Forbidden (Access Denied)"
        if '500' in error_msg or 'internal server error' in error_lower:
            return "500 Server Error"
        if '503' in error_msg or 'service unavailable' in error_lower:
            return "503 Service Unavailable"

        # Timeout
        if 'timeout' in error_lower or 'timed out' in error_lower:
            return "Timeout (Server zu langsam)"

        # Connection Issues
        if 'connection' in error_lower or 'refused' in error_lower:
            return "Connection Failed"

        # Generic Fallback
        return f"Download Failed ({error_msg[:50]})"

    # ============================================================
    # PDF SUPPORT (PyMuPDF)
    # ============================================================

    def _is_pdf_url(self, url: str) -> bool:
        """
        Erkennt ob eine URL auf ein PDF zeigt.

        Prüft:
        1. URL-Endung (.pdf)
        2. HEAD-Request Content-Type Header

        Args:
            url: URL zu prüfen

        Returns:
            True wenn PDF, False sonst
        """
        # Schnelle Prüfung: URL endet mit .pdf
        if url.lower().endswith('.pdf'):
            return True

        # Langsame Prüfung: HEAD-Request für Content-Type
        try:
            response = requests.head(url, timeout=5, allow_redirects=True, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; AIfred/1.0)'
            })
            content_type = response.headers.get('Content-Type', '').lower()
            return 'application/pdf' in content_type
        except Exception:
            # Bei Fehlern: Kein PDF annehmen (trafilatura wird es versuchen)
            return False

    def _scrape_pdf(self, url: str) -> Dict:
        """
        Extrahiert Text aus PDF-Dokumenten mit PyMuPDF.

        PyMuPDF (fitz) bietet:
        - Schnellste Text-Extraktion
        - Beste Qualität
        - Gute Tabellen-Erkennung
        - Metadaten-Extraktion (Titel, Autor)

        Args:
            url: URL des PDF-Dokuments

        Returns:
            Dict mit extrahiertem Content oder Fehler
        """
        if not PYMUPDF_AVAILABLE:
            logger.warning("⚠️ PyMuPDF nicht installiert → PDF-Support deaktiviert")
            return {
                'success': False,
                'method': 'pdf',
                'source': url,
                'error': 'PyMuPDF not installed (pip install pymupdf)'
            }

        try:
            logger.info(f"📄 PDF-Download: {url}")

            # Download PDF with timeout (use real browser User-Agent to avoid hotlink protection)
            # Extract domain for Referer header (required by some servers)
            from urllib.parse import urlparse
            parsed = urlparse(url)
            referer = f"{parsed.scheme}://{parsed.netloc}/"

            response = requests.get(url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': referer,
                'Accept': 'application/pdf,*/*'
            })
            response.raise_for_status()

            # Verify it's actually a PDF
            content_type = response.headers.get('Content-Type', '').lower()
            if 'application/pdf' not in content_type and not url.lower().endswith('.pdf'):
                logger.warning(f"⚠️ Kein PDF: Content-Type={content_type}")
                # Fallback zu trafilatura
                return self._scrape_with_trafilatura(url)

            # Open PDF from memory
            pdf_data = io.BytesIO(response.content)
            doc = fitz.open(stream=pdf_data, filetype="pdf")

            # Extract metadata
            metadata = doc.metadata
            title = metadata.get('title', '') if metadata else ''
            if not title:
                # Fallback: Use filename from URL
                title = url.split('/')[-1].replace('.pdf', '')

            # Extract text from all pages
            text_parts = []
            page_count = len(doc)  # Save before closing!
            for page_num, page in enumerate(doc):
                page_text = page.get_text("text")
                if page_text.strip():
                    text_parts.append(page_text)

            doc.close()

            # Combine and clean text
            full_text = '\n\n'.join(text_parts)
            full_text = self._clean_text(full_text)
            word_count = len(full_text.split())

            if not full_text:
                logger.warning("⚠️ PDF: Kein Text extrahiert (möglicherweise Scan/Bild-PDF)")
                return {
                    'success': False,
                    'method': 'pdf',
                    'source': url,
                    'error': 'No text extracted (possibly scanned PDF)'
                }

            logger.info(f"  ✅ PDF: {word_count} Wörter, {page_count} Seiten")
            log_message(f"  ✅ PDF: {word_count} Wörter extrahiert")

            return {
                'success': True,
                'source': url,
                'title': title,
                'content': full_text,
                'url': url,
                'word_count': word_count,
                'truncated': False,
                'method': 'pdf',
                'pages': page_count
            }

        except requests.exceptions.Timeout:
            error_msg = "PDF Download Timeout"
            logger.error(f"❌ {error_msg}: {url}")
            return {
                'success': False,
                'method': 'pdf',
                'source': url,
                'error': error_msg
            }

        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}"
            logger.error(f"❌ {error_msg}: {url}")
            return {
                'success': False,
                'method': 'pdf',
                'source': url,
                'error': error_msg
            }

        except Exception as e:
            error_msg = str(e)[:100]
            logger.error(f"❌ PDF-Fehler bei {url}: {error_msg}")
            return {
                'success': False,
                'method': 'pdf',
                'source': url,
                'error': f"PDF extraction failed: {error_msg}"
            }

