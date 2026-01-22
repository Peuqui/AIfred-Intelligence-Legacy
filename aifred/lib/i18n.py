"""
Internationalization (i18n) Module for AIfred Intelligence

Provides UI string translation functionality
"""

from typing import Dict, Optional
from .prompt_loader import get_language


class TranslationManager:
    """Manages UI translations"""

    # Research mode mappings (separate from translations for type safety)
    _research_mode_maps: Dict[str, Dict[str, str]] = {
        "de": {
            "💡 Eigenes Wissen (schnell)": "none",
            "⚡ Web-Suche Schnell (3 beste)": "quick",
            "🌍 Web-Suche Ausführlich (7 beste)": "deep",
            "✨ Automatik (KI entscheidet)": "automatik"
        },
        "en": {
            "💡 Own Knowledge (fast)": "none",
            "⚡ Web Search Quick (3 best)": "quick",
            "🌍 Web Search Detailed (7 best)": "deep",
            "✨ Automatic (AI decides)": "automatik"
        }
    }

    _reverse_research_mode_maps: Dict[str, Dict[str, str]] = {
        "de": {
            "none": "💡 Eigenes Wissen (schnell)",
            "quick": "⚡ Web-Suche Schnell (3 beste)",
            "deep": "🌍 Web-Suche Ausführlich (7 beste)",
            "automatik": "✨ Automatik (KI entscheidet)"
        },
        "en": {
            "none": "💡 Own Knowledge (fast)",
            "quick": "⚡ Web Search Quick (3 best)",
            "deep": "🌍 Web Search Detailed (7 best)",
            "automatik": "✨ Automatic (AI decides)"
        }
    }

    # Translation dictionary
    _translations: Dict[str, Dict[str, str]] = {
        "de": {
            # UI Labels
            "voice_input": "🎙️ Spracheingabe",
            "audio_input_placeholder": "Audio-Eingabe (Microphone Recording)",
            "stt_not_ported": "⚠️ STT/TTS noch nicht portiert - Coming Soon!",
            "tip_automatic_transcription": "💡 Tipp: Nach dem Stoppen läuft automatisch die Transkription",
            "text_input": "⌨️ Texteingabe",
            "enter_your_question": "Oder schreibe hier deine Frage...",
            "research_mode": "🔎 Recherche-Modus",
            "research_mode_auto": "✨ Automatik (KI entscheidet)",
            "research_mode_none": "💡 Eigenes Wissen (schnell)",
            "research_mode_quick": "⚡ Web-Suche Schnell (3 beste)",
            "research_mode_deep": "🌍 Web-Suche Ausführlich (7 beste)",
            "choose_research_mode": "💡 Wähle, wie der Assistant Fragen beantwortet",
            "send_text": "💬 Text senden",
            "clear_chat": "🗑️ Chat löschen",
            "share_chat": "🔗 Chat teilen",
            "llm_parameters": "⚙️ LLM-Parameter (Erweitert)",
            "temperature": "🌡️ Temperature",
            "current": "Aktuell:",
            "temperature_info": "0.0 = deterministisch, 0.2 = fakten, 0.8 = ausgewogen, 1.5+ = kreativ",
            "context_window": "📦 Context Window (num_ctx)",
            "context_window_info": "Auto-berechnet basierend auf Message-Größe",
            
            # Progress Banner
            "automatic_decision": "Automatik-Entscheidung ...",
            "web_scraping": "Web-Scraping",
            "compressing_context": "Komprimiere Kontext ...",
            "generating_answer": "Generiere Antwort ...",
            "websites_unreachable": "Website nicht erreichbar",
            "websites_unreachable_plural": "Websites nicht erreichbar",
            
            # Chat Display
            "input": "Eingabe:",
            "ai_response": "AI Antwort:",
            
            # TTS Section
            "tts_output": "🔊 Sprachausgabe (AI-Antwort)",
            "tts_enabled": "Sprachausgabe aktiviert",
            "tts_regenerate": "🔄 Neu generieren",
            "tts_regenerate_all": "🔄 Alles neu generieren",
            "tts_not_ported": "⚠️ TTS noch nicht portiert - Coming Soon!",
            
            # Chat History
            "chat_history": "💬 Chat Verlauf",
            "messages_count": "messages",
            
            # Debug Console
            "debug_console": "🐛 Debug Console",
            "live_debug_output": "Live Debug-Output: LLM-Starts, Entscheidungen, Statistiken",
            "auto_scroll": "Auto-Scroll",
            
            # Settings
            "settings": "⚙️ Einstellungen",
            "ui_language": "🌍 UI Sprache:",
            "backend": "Backend:",
            "cloud_api_provider": "☁️ Cloud-Anbieter:",
            "cloud_api_key_configured": "✅ API-Key konfiguriert",
            "cloud_api_key_missing": "⚠️ API-Key fehlt",
            "models_found": "Modelle gefunden",
            "main_llm": "AIfred-LLM:",
            "automatic_llm": "Automatik-LLM:",
            "vision_llm": "Vision-LLM:",
            "system_control": "🔄 System-Steuerung",
            "restart_ollama": "🔄 Ollama Neustart",
            "restart_vllm": "🔄 vLLM Neustart",
            "restart_aifred": "🔄 AIfred Neustart",
            "backend_restart_info": "💡 Backend-Neustart: Entlädt Models aus VRAM",
            "aifred_restart_info": "💡 AIfred-Neustart: Debug-Logs werden geleert, Sessions bleiben erhalten",
            
            # Main Page
            "aifred_intelligence": "🎩 AIfred Intelligence",
            "subtitle": "AI at your service • Benannt nach Alfred (Großvater) und Wolfgang Alfred (Vater)",

            # Input Controls (Phase 1)
            "recording": "Aufnahme",
            "camera": "Kamera",
            "upload_image": "Bild hochladen",
            "audio": "🎤 Audio",
            "your_name": "Dein Name",
            "clear_all": "Alle löschen",
            "transcription_edit": "Transkription bearbeiten:",
            "text_edit": "✏️ Text editieren",
            "text_direct": "⚡ Direkt senden",
            "image_hint": "💡 Ziehe Bilder auf den Button oder klicke zum Auswählen",
            "crop_tooltip": "Zuschneiden",
            # Text Input (Phase 2)
            "text_input_heading": "📝 Texteingabe",
            "text_input_placeholder": "Schreibe hier deine Frage...",
            "temperature_label": "🌡️ Temperature:",
            "temp_mode_manual": "✋ Manual",
            "temp_mode_auto": "✨ Auto",
            "temp_info_manual": "Slider-Wert wird verwendet",
            "temp_info_auto": "Intent-Detection wählt optimale Temperature",
            # TTS/STT Settings (Phase 3)
            "tts_heading": "🔊 Sprachausgabe (TTS):",
            "tts_engine_label": "Engine:",
            "tts_engine_edge": "Edge TTS (Cloud)",
            "tts_engine_piper": "Piper TTS (Offline)",
            "tts_engine_espeak": "eSpeak (Roboter, Offline)",
            "tts_voice_label": "Stimme:",
            "tts_speed_label": "Tempo:",
            "tts_pitch_label": "Tonhöhe:",
            "tts_autoplay_label": "Auto-Play:",
            "stt_heading": "🎤 Spracheingabe (STT):",
            "stt_model_label": "Modell:",
            "stt_model_tiny": "tiny (39MB, schnell, englisch)",
            "stt_model_base": "base (74MB, schneller, multilingual)",
            "stt_model_small": "small (466MB, bessere Qualität, multilingual)",
            "stt_model_medium": "medium (1.5GB, hohe Qualität, multilingual)",
            "stt_model_large": "large-v3 (2.9GB, beste Qualität, multilingual)",
            # Multi-Agent Mode Options
            "multi_agent_standard": "Standard",
            "multi_agent_critical_review": "Kritische Prüfung",
            "multi_agent_auto_consensus": "Auto-Konsens",
            "multi_agent_devils_advocate": "Advocatus Diaboli",
            "multi_agent_tribunal": "Tribunal",
            # Multi-Agent Mode Descriptions
            "multi_agent_mode": "💬 Diskussionsmodus",
            "multi_agent_info_standard": "💡 Nur AIfred antwortet (klassisches Verhalten)",
            "multi_agent_info_critical_review": "💡 AIfred antwortet, Sokrates kritisiert, du entscheidest (Reasoning empfohlen)",
            "multi_agent_info_auto_consensus": "💡 AIfred, Sokrates & Salomo diskutieren bis Konsens",
            "multi_agent_info_devils_advocate": "💡 Pro & Contra Argumente für ausgewogene Analyse (Reasoning empfohlen)",
            "multi_agent_info_tribunal": "💡 AIfred vs Sokrates debattieren, Salomo urteilt am Ende",
            "multi_agent_help_title": "Diskussionsmodi - Übersicht",
            "multi_agent_help_close": "Schließen",
            "multi_agent_help_mode": "Modus",
            "multi_agent_help_flow": "Ablauf",
            "multi_agent_help_decision": "Wer entscheidet?",
            "multi_agent_help_standard_flow": "AIfred antwortet",
            "multi_agent_help_standard_decision": "—",
            "multi_agent_help_critical_review_flow": "AIfred → Sokrates → STOP",
            "multi_agent_help_critical_review_decision": "User",
            "multi_agent_help_auto_consensus_flow": "AIfred → Sokrates → Salomo (X Runden)",
            "multi_agent_help_auto_consensus_decision": "Salomo",
            "multi_agent_help_devils_advocate_flow": "AIfred → Sokrates (Pro/Contra)",
            "multi_agent_help_devils_advocate_decision": "User",
            "multi_agent_help_tribunal_flow": "AIfred ↔ Sokrates (X Runden) → Salomo",
            "multi_agent_help_tribunal_decision": "Salomo (Urteil)",
            "multi_agent_help_agents_title": "Agenten",
            "multi_agent_help_aifred_desc": "Butler & Gelehrter - beantwortet Fragen",
            "multi_agent_help_sokrates_desc": "Kritischer Philosoph - hinterfragt & liefert Alternativen",
            "multi_agent_help_salomo_desc": "Weiser Richter - synthetisiert & urteilt",
            "max_debate_rounds": "Max. Debattenrunden:",
            "consensus_type_label": "Konsens-Typ:",
            "consensus_majority": "Mehrheit (2/3)",
            "consensus_unanimous": "Einstimmig (3/3)",
            "consensus_toggle_label": "3/3",
            "consensus_toggle_tooltip_on": "Einstimmig: Alle 3 Agenten müssen zustimmen",
            "consensus_toggle_tooltip_off": "Mehrheit: 2 von 3 Agenten müssen zustimmen",
            "sokrates_title": "🏛️ Sokrates",
            "sokrates_critique_label": "Kritik:",
            "sokrates_pro_label": "Pro-Argumente:",
            "sokrates_contra_label": "Contra-Argumente:",
            "debate_round_label": "Runde",
            # Mode Labels (for agent panel markers)
            "refinement_label": "Verfeinerung",
            "critical_review_label": "Kritische Prüfung",
            "auto_consensus_label": "Auto-Konsens",
            "direct_response_label": "Direkte Antwort",
            "advocatus_diaboli_label": "Advocatus Diaboli",
            "accept_answer": "✓ Akzeptieren",
            "improve_answer": "↻ Verbessern",
            "sokrates_llm": "Sokrates-LLM:",
            "sokrates_llm_same": "(wie AIfred-LLM)",
            "lgtm_tooltip": "Salomo ist zufrieden mit der Antwort",
            "alfred_title": "🎩 AIfred",
            # Salomo Labels
            "salomo_title": "👑 Salomo",
            "salomo_llm": "Salomo-LLM:",
            # Personality Tooltips
            "personality_aifred_tooltip": "Butler-Persönlichkeit: Britisch-höflicher Sprachstil",
            "personality_sokrates_tooltip": "Philosophen-Persönlichkeit: Sokratische Methode mit rhetorischen Fragen",
            "personality_salomo_tooltip": "König-Persönlichkeit: Weiser Richterstil mit hebräischen Weisheiten",
            # Reasoning Tooltips
            "reasoning_tooltip": "Reasoning Mode – Schritt-für-Schritt Analyse",
            "salomo_synthesis_label": "Synthese:",
            "salomo_verdict_label": "Urteil:",
            "tts_player_label": "Sprachausgabe",
            "tts_regenerate_hint": "Klicke 'Neu generieren' um die letzte Antwort vorzulesen",
            "audio_play_tooltip": "Audio abspielen",
            "audio_regenerate_tooltip": "Audio neu generieren",
            # Vision & Advanced Settings (Phase 4)
            "thinking_mode_label": "🔗 Reasoning Mode:",
            "thinking_mode_info": "ℹ️ Chain-of-Thought Reasoning für komplexe Aufgaben",
            "thinking_mode_unavailable": "⚠️ Nicht verfügbar für",
            "yarn_heading": "📏 YaRN Context Extension:",
            "yarn_factor_label": "Faktor:",
            "yarn_autodetect_hint": "(auto-detect erst nach Start)",
            "yarn_apply_button": "Apply YaRN",
            "yarn_max_tested": "📏 Maximum: ~{factor}x (aus Test ermittelt)",
            "yarn_max_unknown": "📏 Maximum: Unbekannt (wird beim Start getestet)",
            "yarn_context_info": "ℹ️ Context-Limits werden beim ersten vLLM-Start automatisch erkannt",
            # Image Crop Modal (Phase 5)
            "crop_modal_title": "Bild zuschneiden",
            "crop_modal_hint": "Ziehe die Ecken oder Kanten",
            "crop_cancel": "Abbrechen",
            "crop_apply": "Zuschneiden",
            "crop_rotate": "Drehen",
            # Context Calibration
            "calibrate_context": "Context kalibrieren",
            "calibrating": "Kalibriere...",
            # Collapsible Labels (XML tags, debug accordion)
            "collapsible_thinking": "Denkprozess",
            "collapsible_data": "Strukturierte Daten",
            "collapsible_python": "Python Code",
            "collapsible_code": "Code",
            "collapsible_sql": "SQL Query",
            "collapsible_json": "JSON Daten",
            "collapsible_show_html": "📄 HTML Code anzeigen",
            "collapsible_query_optimization": "🔍 Query-Optimierung",
            "collapsible_thinking_process": "💭 Denkprozess Antwort",
            "collapsible_summary": "Zusammenfassung",
            # Failed Sources
            "sources_unavailable": "{count} Quelle nicht erreichbar",
            "sources_unavailable_plural": "{count} Quellen nicht erreichbar",
            # Login/Logout
            "logout": "Abmelden",
            "logged_in_as": "Angemeldet als",
        },
        "en": {
            # UI Labels
            "voice_input": "🎙️ Voice Input",
            "audio_input_placeholder": "Audio Input (Microphone Recording)",
            "stt_not_ported": "⚠️ STT/TTS not yet ported - Coming Soon!",
            "tip_automatic_transcription": "💡 Tip: Automatic transcription runs after stopping",
            "text_input": "⌨️ Text Input",
            "enter_your_question": "Or write your question here...",
            "research_mode": "🔎 Research Mode",
            "research_mode_auto": "✨ Automatic (AI decides)",
            "research_mode_none": "💡 Own Knowledge (fast)",
            "research_mode_quick": "⚡ Web Search Quick (3 best)",
            "research_mode_deep": "🌍 Web Search Detailed (7 best)",
            "choose_research_mode": "💡 Choose how the assistant answers questions",
            "send_text": "💬 Send Text",
            "clear_chat": "🗑️ Clear Chat",
            "share_chat": "🔗 Share Chat",
            "llm_parameters": "⚙️ LLM Parameters (Advanced)",
            "temperature": "🌡️ Temperature",
            "current": "Current:",
            "temperature_info": "0.0 = deterministic, 0.2 = factual, 0.8 = balanced, 1.5+ = creative",
            "context_window": "📦 Context Window (num_ctx)",
            "context_window_info": "Auto-calculated based on message size",
            
            # Progress Banner
            "automatic_decision": "Automatic decision ...",
            "web_scraping": "Web Scraping",
            "compressing_context": "Compressing Context ...",
            "generating_answer": "Generating Answer ...",
            "websites_unreachable": "Website unreachable",
            "websites_unreachable_plural": "Websites unreachable",
            
            # Chat Display
            "input": "Input:",
            "ai_response": "AI Response:",
            
            # TTS Section
            "tts_output": "🔊 Text-to-Speech (AI Answer)",
            "tts_enabled": "Text-to-Speech enabled",
            "tts_regenerate": "🔄 Regenerate",
            "tts_regenerate_all": "🔄 Regenerate All",
            "tts_not_ported": "⚠️ TTS not yet ported - Coming Soon!",
            
            # Chat History
            "chat_history": "💬 Chat History",
            "messages_count": "messages",
            
            # Debug Console
            "debug_console": "🐛 Debug Console",
            "live_debug_output": "Live Debug Output: LLM starts, decisions, statistics",
            "auto_scroll": "Auto-Scroll",
            
            # Settings
            "settings": "⚙️ Settings",
            "ui_language": "🌍 UI Language:",
            "backend": "Backend:",
            "cloud_api_provider": "☁️ Cloud Provider:",
            "cloud_api_key_configured": "✅ API key configured",
            "cloud_api_key_missing": "⚠️ API key missing",
            "models_found": "models found",
            "main_llm": "AIfred-LLM:",
            "automatic_llm": "Automatik-LLM:",
            "vision_llm": "Vision-LLM:",
            "system_control": "🔄 System Control",
            "restart_ollama": "🔄 Ollama Restart",
            "restart_vllm": "🔄 vLLM Restart",
            "restart_aifred": "🔄 AIfred Restart",
            "backend_restart_info": "💡 Backend restart: Unloads models from VRAM",
            "aifred_restart_info": "💡 AIfred restart: Debug logs cleared, sessions preserved",
            
            # Main Page
            "aifred_intelligence": "🎩 AIfred Intelligence",
            "subtitle": "AI at your service • Named after Alfred (grandfather) and Wolfgang Alfred (father)",

            # Input Controls (Phase 1)
            "recording": "Recording",
            "camera": "Camera",
            "upload_image": "Upload Image",
            "audio": "🎤 Audio",
            "your_name": "Your Name",
            "clear_all": "Clear All",
            "transcription_edit": "Edit transcription:",
            "text_edit": "✏️ Edit text",
            "text_direct": "⚡ Send directly",
            "image_hint": "💡 Drag images to the button or click to select",
            "crop_tooltip": "Crop",
            # Text Input (Phase 2)
            "text_input_heading": "📝 Text Input",
            "text_input_placeholder": "Write your question here...",
            "temperature_label": "🌡️ Temperature:",
            "temp_mode_manual": "✋ Manual",
            "temp_mode_auto": "✨ Auto",
            "temp_info_manual": "Slider value is used",
            "temp_info_auto": "Intent-Detection chooses optimal temperature",
            # TTS/STT Settings (Phase 3)
            "tts_heading": "🔊 Text-to-Speech (TTS):",
            "tts_engine_label": "Engine:",
            "tts_engine_edge": "Edge TTS (Cloud)",
            "tts_engine_piper": "Piper TTS (Offline)",
            "tts_engine_espeak": "eSpeak (Robot, Offline)",
            "tts_voice_label": "Voice:",
            "tts_speed_label": "Speed:",
            "tts_pitch_label": "Pitch:",
            "tts_autoplay_label": "Auto-Play:",
            "stt_heading": "🎤 Speech-to-Text (STT):",
            "stt_model_label": "Model:",
            "stt_model_tiny": "tiny (39MB, fast, english)",
            "stt_model_base": "base (74MB, faster, multilingual)",
            "stt_model_small": "small (466MB, better quality, multilingual)",
            "stt_model_medium": "medium (1.5GB, high quality, multilingual)",
            "stt_model_large": "large-v3 (2.9GB, best quality, multilingual)",
            # Multi-Agent Mode Options
            "multi_agent_standard": "Standard",
            "multi_agent_critical_review": "Critical Review",
            "multi_agent_auto_consensus": "Auto-Consensus",
            "multi_agent_devils_advocate": "Devil's Advocate",
            "multi_agent_tribunal": "Tribunal",
            # Multi-Agent Mode Descriptions
            "multi_agent_mode": "💬 Discussion Mode",
            "multi_agent_info_standard": "💡 Only AIfred answers (classic behavior)",
            "multi_agent_info_critical_review": "💡 AIfred answers, Sokrates critiques, you decide (Reasoning recommended)",
            "multi_agent_info_auto_consensus": "💡 AIfred, Sokrates & Salomo discuss until consensus",
            "multi_agent_info_devils_advocate": "💡 Pro & Contra arguments for balanced analysis (Reasoning recommended)",
            "multi_agent_info_tribunal": "💡 AIfred vs Sokrates debate, Salomo judges at the end",
            "multi_agent_help_title": "Discussion Modes - Overview",
            "multi_agent_help_close": "Close",
            "multi_agent_help_mode": "Mode",
            "multi_agent_help_flow": "Flow",
            "multi_agent_help_decision": "Who decides?",
            "multi_agent_help_standard_flow": "AIfred answers",
            "multi_agent_help_standard_decision": "—",
            "multi_agent_help_critical_review_flow": "AIfred → Sokrates → STOP",
            "multi_agent_help_critical_review_decision": "User",
            "multi_agent_help_auto_consensus_flow": "AIfred → Sokrates → Salomo (X rounds)",
            "multi_agent_help_auto_consensus_decision": "Salomo",
            "multi_agent_help_devils_advocate_flow": "AIfred → Sokrates (Pro/Contra)",
            "multi_agent_help_devils_advocate_decision": "User",
            "multi_agent_help_tribunal_flow": "AIfred ↔ Sokrates (X rounds) → Salomo",
            "multi_agent_help_tribunal_decision": "Salomo (Verdict)",
            "multi_agent_help_agents_title": "Agents",
            "multi_agent_help_aifred_desc": "Butler & Scholar - answers questions",
            "multi_agent_help_sokrates_desc": "Critical Philosopher - questions & provides alternatives",
            "multi_agent_help_salomo_desc": "Wise Judge - synthesizes & judges",
            "max_debate_rounds": "Max. Debate Rounds:",
            "consensus_type_label": "Consensus Type:",
            "consensus_majority": "Majority (2/3)",
            "consensus_unanimous": "Unanimous (3/3)",
            "consensus_toggle_label": "3/3",
            "consensus_toggle_tooltip_on": "Unanimous: All 3 agents must agree",
            "consensus_toggle_tooltip_off": "Majority: 2 of 3 agents must agree",
            "sokrates_title": "🏛️ Sokrates",
            "sokrates_critique_label": "Critique:",
            "sokrates_pro_label": "Pro Arguments:",
            "sokrates_contra_label": "Contra Arguments:",
            "debate_round_label": "Round",
            # Mode Labels (for agent panel markers)
            "refinement_label": "Refinement",
            "critical_review_label": "Critical Review",
            "auto_consensus_label": "Auto-Consensus",
            "direct_response_label": "Direct Response",
            "advocatus_diaboli_label": "Devil's Advocate",
            "accept_answer": "✓ Accept",
            "improve_answer": "↻ Improve",
            "sokrates_llm": "Sokrates-LLM:",
            "sokrates_llm_same": "(same as AIfred-LLM)",
            "lgtm_tooltip": "Salomo is satisfied with the answer",
            "alfred_title": "🎩 AIfred",
            # Salomo Labels
            "salomo_title": "👑 Salomo",
            "salomo_llm": "Salomo-LLM:",
            # Personality Tooltips
            "personality_aifred_tooltip": "Butler personality: Polite British speech style",
            "personality_sokrates_tooltip": "Philosopher personality: Socratic method with rhetorical questions",
            "personality_salomo_tooltip": "King personality: Wise arbiter style with Hebrew proverbs",
            # Reasoning Tooltips
            "reasoning_tooltip": "Reasoning Mode – Step-by-step analysis",
            "salomo_synthesis_label": "Synthesis:",
            "salomo_verdict_label": "Verdict:",
            "tts_player_label": "Text-to-Speech",
            "tts_regenerate_hint": "Click 'Regenerate' to read the last response aloud",
            "audio_play_tooltip": "Play audio",
            "audio_regenerate_tooltip": "Regenerate audio",
            # Vision & Advanced Settings (Phase 4)
            "thinking_mode_label": "🔗 Reasoning Mode:",
            "thinking_mode_info": "ℹ️ Chain-of-Thought Reasoning for complex tasks",
            "thinking_mode_unavailable": "⚠️ Not available for",
            "yarn_heading": "📏 YaRN Context Extension:",
            "yarn_factor_label": "Factor:",
            "yarn_autodetect_hint": "(auto-detect after first start)",
            "yarn_apply_button": "Apply YaRN",
            "yarn_max_tested": "📏 Maximum: ~{factor}x (determined from test)",
            "yarn_max_unknown": "📏 Maximum: Unknown (tested at startup)",
            "yarn_context_info": "ℹ️ Context limits are auto-detected at first vLLM start",
            # Image Crop Modal (Phase 5)
            "crop_modal_title": "Crop Image",
            "crop_modal_hint": "Drag corners or edges",
            "crop_cancel": "Cancel",
            "crop_apply": "Crop",
            "crop_rotate": "Rotate",
            # Context Calibration
            "calibrate_context": "Calibrate context",
            "calibrating": "Calibrating...",
            # Collapsible Labels (XML tags, debug accordion)
            "collapsible_thinking": "Thinking Process",
            "collapsible_data": "Structured Data",
            "collapsible_python": "Python Code",
            "collapsible_code": "Code",
            "collapsible_sql": "SQL Query",
            "collapsible_json": "JSON Data",
            "collapsible_show_html": "📄 Show HTML Code",
            "collapsible_query_optimization": "🔍 Query Optimization",
            "collapsible_thinking_process": "💭 Final Answer Thinking Process",
            "collapsible_summary": "Summary",
            # Failed Sources
            "sources_unavailable": "{count} source unavailable",
            "sources_unavailable_plural": "{count} sources unavailable",
            # Login/Logout
            "logout": "Logout",
            "logged_in_as": "Logged in as",
        }
    }

    @staticmethod
    def get_text(key: str, lang: Optional[str] = None) -> str:
        """
        Get translated text for a given key
        
        Args:
            key: Translation key
            lang: Language code (de, en) or None for current language
            
        Returns:
            Translated string
        """
        if lang is None:
            lang = get_language()
            # If language is auto, default to German for now
            if lang == "auto":
                lang = "de"
        
        # Fallback to German if language not found
        if lang not in TranslationManager._translations:
            lang = "de"
        
        # Get translation for the key
        translation = TranslationManager._translations[lang]
        
        if key in translation:
            return translation[key]
        
        # Fallback to English if key not found in current language
        if lang != "en" and key in TranslationManager._translations["en"]:
            return TranslationManager._translations["en"][key]
        
        # Final fallback: return the key itself
        return key

    @staticmethod
    def get_research_mode_value(display_text: str, lang: Optional[str] = None) -> str:
        """
        Get internal research mode value for display text

        Args:
            display_text: Display text of research mode
            lang: Language code or None for current language

        Returns:
            Internal mode value (none, quick, deep, automatik)
        """
        if lang is None:
            lang = get_language()
            if lang == "auto":
                lang = "de"

        if lang not in TranslationManager._research_mode_maps:
            lang = "de"

        # Get the mapping for the current language
        mode_map = TranslationManager._research_mode_maps.get(lang, {})

        # Return the internal value or default to automatik
        return mode_map.get(display_text, "automatik")

    @staticmethod
    def get_research_mode_display(mode_value: str, lang: Optional[str] = None) -> str:
        """
        Get display text for research mode value

        Args:
            mode_value: Internal mode value (none, quick, deep, automatik)
            lang: Language code or None for current language

        Returns:
            Display text for the mode
        """
        if lang is None:
            lang = get_language()
            if lang == "auto":
                lang = "de"

        if lang not in TranslationManager._reverse_research_mode_maps:
            lang = "de"

        # Get the reverse mapping for the current language
        reverse_mode_map = TranslationManager._reverse_research_mode_maps.get(lang, {})

        # Return the display text or default to automatik display
        return reverse_mode_map.get(mode_value, "✨ Automatic (AI decides)")


# Convenience function
def t(key: str, lang: Optional[str] = None, count: Optional[int] = None, **kwargs) -> str:
    """
    Convenience function to get translated text with optional formatting and pluralization.

    Args:
        key: Translation key (base key, without _plural suffix)
        lang: Language code (de, en) or None for current language
        count: If provided, auto-selects singular/plural key and adds {count} to format args
        **kwargs: Additional format arguments for placeholders like {name}, etc.

    Returns:
        Translated string (formatted if count or kwargs provided)

    Examples:
        t("greeting")  # Simple lookup
        t("sources_unavailable", count=3)  # Auto-pluralization: uses key + "_plural"
        t("sources_unavailable", count=1)  # Singular: uses key as-is
        t("welcome_user", lang="de", name="Max")  # With language + formatting
    """
    # Handle pluralization: count=1 → singular key, count>1 → key_plural
    if count is not None:
        actual_key = key if count == 1 else f"{key}_plural"
        kwargs["count"] = count
    else:
        actual_key = key

    template = TranslationManager.get_text(actual_key, lang)
    if kwargs:
        return template.format(**kwargs)
    return template