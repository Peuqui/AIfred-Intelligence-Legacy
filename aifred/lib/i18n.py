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
            "active_agent_label": "🤖 Aktiver Agent",
            "send_text": "Text senden",
            "clear_chat": "Chat löschen",
            "save_memory": "Merken",
            "share_chat": "Chat teilen",
            "llm_parameters": "⚙️ LLM-Parameter (Erweitert)",
            "temperature": "🌡️ Temperature",
            "current": "Aktuell:",
            "temperature_info": "0.0 = deterministisch, 0.2 = fakten, 0.8 = ausgewogen, 1.5+ = kreativ",
            "context_window": "📦 Context Window",
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
            # TTS Engine dropdown labels
            "tts_engine_off": "Aus",
            "tts_engine_xtts": "XTTS v2 (Lokal, Voice Cloning)",
            "tts_engine_moss": "MOSS-TTS (Batch, nach Bubble)",
            "tts_engine_dashscope": "DashScope Qwen3-TTS (Cloud, Streaming)",
            "tts_engine_piper": "Piper TTS (Lokal, Offline)",
            "tts_engine_espeak": "eSpeak (Roboter, Offline)",
            "tts_engine_edge": "Edge TTS (Cloud, Fallback)",
            
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
            "message_hub_heading": "📨 Message Hub",
            "message_hub_info": "Plugins verwalten: Channels und Tools ein-/ausschalten",
            "auto_reply": "Auto-Reply",
            "plugin_channels": "Channels",
            "plugin_tools": "Tool Plugins",
            "cred_save": "Speichern & Aktivieren",
            "cred_cancel": "Abbrechen",
            # Email credential labels (referenced by email plugin)
            "email_cred_imap_host": "IMAP Host",
            "email_cred_imap_port": "IMAP Port",
            "email_cred_smtp_host": "SMTP Host",
            "email_cred_smtp_port": "SMTP Port",
            "email_cred_user": "Benutzername / E-Mail",
            "email_cred_password": "Passwort",
            "email_cred_from": "Anzeigename (optional)",
            # Discord credential labels
            "discord_cred_bot_token": "Bot Token",
            "discord_cred_channel_ids": "Channel IDs (kommagetrennt)",
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
            "audio": "Audio",
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
            "multi_agent_symposion": "Symposion",
            # Multi-Agent Mode Descriptions
            "multi_agent_mode": "💬 Diskussionsmodus",
            "multi_agent_info_standard": "💡 Nur AIfred antwortet (klassisches Verhalten)",
            "multi_agent_info_critical_review": "💡 AIfred antwortet, Sokrates kritisiert, du entscheidest (Reasoning empfohlen)",
            "multi_agent_info_auto_consensus": "💡 AIfred, Sokrates & Salomo diskutieren bis Konsens",
            "multi_agent_info_devils_advocate": "💡 Pro & Contra Argumente für ausgewogene Analyse (Reasoning empfohlen)",
            "multi_agent_info_tribunal": "💡 AIfred vs Sokrates debattieren, Salomo urteilt am Ende",
            "multi_agent_info_symposion": "💡 Wähle Agenten für ein Gelehrten-Symposion (Multiperspektiven)",
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
            "multi_agent_help_symposion_flow": "Frei wählbare Agenten diskutieren reihum (X Runden)",
            "multi_agent_help_symposion_decision": "Keine — Multiperspektivität",
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
            "speed_switch_tooltip": "Ctx: max. Kontext, gleichmäßige GPU-Aufteilung\n⚡ Speed: 32K Kontext, aggressive GPU-Aufteilung (schneller)",
            "lgtm_tooltip": "Salomo ist zufrieden mit der Antwort",
            "consensus_agreed": "Einverstanden.",
            "consensus_continue": "Weiter diskutieren.",
            "alfred_title": "🎩 AIfred",
            # Salomo Labels
            "salomo_title": "👑 Salomo",
            "salomo_llm": "Salomo-LLM:",
            # Personality Tooltips
            "personality_aifred_tooltip": "Butler-Persönlichkeit: Britisch-höflicher Sprachstil",
            "personality_sokrates_tooltip": "Philosophen-Persönlichkeit: Sokratische Methode mit rhetorischen Fragen",
            "personality_salomo_tooltip": "König-Persönlichkeit: Weiser Richterstil mit hebräischen Weisheiten",
            "personality_vision_tooltip": "Vision-Persönlichkeit: AIfred-Butler-Stil bei Bildanalysen",
            # Reasoning & Thinking Tooltips
            "reasoning_tooltip": "Reasoning-Prompt – Schritt-für-Schritt Analyse im System-Prompt",
            "thinking_tooltip": "Model Thinking – Internes Chain-of-Thought des Modells (enable_thinking)",
            "reasoning_thinking_info": "💭 Reasoning = Analyse-Prompt im System-Prompt\n🧠 Thinking = Modell-internes Denken (CoT)",
            # Reasoning/Thinking Help Modal
            "reasoning_thinking_help_title": "Reasoning & Thinking – Übersicht",
            "reasoning_thinking_help_lightbulb_tooltip": "Was bedeuten Reasoning und Thinking?",
            "reasoning_thinking_help_reasoning_title": "💭 Reasoning-Prompt",
            "reasoning_thinking_help_reasoning_desc": "Fügt einen Analyse-Prompt in den System-Prompt ein, der das Modell anweist, strukturiert und schrittweise zu antworten. Das Modell erhält explizite Anweisungen zur methodischen Analyse.",
            "reasoning_thinking_help_reasoning_effect": "Wirkung: Strukturiertere, gründlichere Antworten durch Prompt-Engineering.",
            "reasoning_thinking_help_thinking_title": "🧠 Model Thinking (CoT)",
            "reasoning_thinking_help_thinking_desc": "Aktiviert das modell-interne Chain-of-Thought (enable_thinking). Das Modell denkt in einem versteckten <think>-Block nach, bevor es antwortet. Nur Modelle mit Thinking-Support (z.B. Qwen3, DeepSeek-R1) unterstützen dies.",
            "reasoning_thinking_help_thinking_effect": "Wirkung: Tiefere Analyse durch internes Nachdenken. Erzeugt längere Antworten und mehr Tokens.",
            "reasoning_thinking_help_combinations_title": "Kombinationen",
            "reasoning_thinking_help_both_on": "Beide AN: Maximale Analysetiefe – Prompt-Anweisung + internes Denken",
            "reasoning_thinking_help_reasoning_only": "Nur Reasoning: Strukturierte Antworten ohne internen Denkprozess",
            "reasoning_thinking_help_thinking_only": "Nur Thinking: Internes CoT ohne zusätzlichen Analyse-Prompt",
            "reasoning_thinking_help_both_off": "Beide AUS: Schnelle, direkte Antworten ohne Analyse-Overhead",
            "reasoning_thinking_help_close": "Schließen",
            "discussion_mode_tooltip": "Diskussionsmodi-Übersicht anzeigen",
            # Sampling Parameter Labels
            "sampling_section_label": "🎲 Sampling Parameter",
            "sampling_reset_tooltip": "Alle Werte auf Modell-Defaults zurücksetzen (inkl. Temp)",
            "sampling_temp_label": "Temperatur",
            "sampling_temp_toggle_tooltip": "Auto: Temperatur wird per Intent-Detection bestimmt (faktisch/gemischt/kreativ). Manual: Temperatur aus der Tabelle. Sampling-Parameter (Top-K etc.) kommen immer aus der Tabelle.",
            "sampling_auto_hint": "Temp: Intent-Detection · Sampling: immer aus Tabelle",
            "sampling_manual_hint": "Alle Werte aus der Tabelle (inkl. Temp)",
            "temp_label": "Temp",
            "top_k_label": "Top-K",
            "top_p_label": "Top-P",
            "min_p_label": "Min-P",
            "repeat_penalty_label": "Rep.P",
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
            # Agent Editor
            "agent_editor_title": "Agenten-Verwaltung",
            "agent_editor_new": "Neuer Agent",
            "agent_editor_edit": "Bearbeiten",
            "agent_editor_delete": "Loeschen",
            "agent_editor_delete_confirm": "Agent wirklich loeschen?",
            "agent_editor_forget": "Vergessen",
            "agent_editor_forget_confirm": "Wirklich vergessen?",
            "agent_editor_save": "Speichern",
            "agent_editor_cancel": "Abbrechen",
            "agent_editor_reset": "Zuruecksetzen",
            "agent_editor_name": "Name",
            "agent_editor_emoji": "Emoji",
            "agent_editor_role": "Rolle",
            "agent_editor_description": "Beschreibung",
            "agent_editor_prompts": "Prompt-Layer",
            "agent_editor_id": "Agent-ID",
            "agent_editor_id_hint": "Kleinbuchstaben, keine Leerzeichen",
            "agent_editor_role_main": "Hauptagent",
            "agent_editor_role_critic": "Kritiker",
            "agent_editor_role_judge": "Richter",
            "agent_editor_role_custom": "Benutzerdefiniert",
            "agent_editor_default_badge": "Standard",
            "agent_editor_close": "Schliessen",
            # Tool Status Messages
            "tool_search": "🔍 Recherche...",
            "tool_memory": "💾 Speichere Erkenntnis...",
            "tool_code_generating": "⚙️ Code wird generiert...",
            "tool_code_running": "⚙️ Code ausführen...",
            "tool_email": "📧 E-Mail...",
            "tool_email_check": "📧 Posteingang prüfen...",
            "tool_email_read": "📧 E-Mail {msg_id} lesen...",
            "tool_email_search": "📧 Suche: {query}",
            "tool_email_delete": "📧 E-Mail {msg_id} löschen...",
            "tool_email_send": "📧 Sende an {to}...",
            "tool_doc_search": "📄 Suche in Dokumenten...",
            "tool_doc_list": "📄 Dokumente auflisten...",
            "tool_doc_delete": "📄 Lösche {filename}...",
            "tool_epim_search": "📅 {entity}: {query}",
            "tool_epim_search_bare": "📅 {entity}...",
            "tool_epim_create": "📅 Erstelle {entity}...",
            "tool_epim_update": "📅 Aktualisiere {entity}...",
            "tool_epim_delete": "📅 Lösche {entity}...",
            # Document Upload UI
            "upload_document": "Dokument",
            "doc_hint": "PDF, Word, Excel, PowerPoint, LibreOffice, TXT, MD, CSV",
            "doc_upload_no_store": "⚠️ Dokumenten-Speicher nicht verfügbar (ChromaDB läuft nicht?)",
            "doc_upload_invalid_type": "⚠️ {filename}: Typ nicht erlaubt. Erlaubt: {allowed}",
            "doc_upload_too_large": "⚠️ {filename}: Zu groß (max {max_mb} MB)",
            "doc_upload_indexing": "📄 Analysiere {filename}...",
            "doc_upload_success": "✅ {filename}: {chunks} Abschnitte indexiert",
            "doc_delete_success": "🗑️ {filename}: {chunks} Abschnitte gelöscht",
            # Document Manager Modal
            "doc_manager_title": "📄 Dokumente",
            "doc_manager_empty": "Noch keine Dokumente hochgeladen.",
            "doc_manager_chunks": "{chunks} Abschnitte",
            "doc_manager_close": "Schließen",
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
            "active_agent_label": "🤖 Active Agent",
            "send_text": "Send Text",
            "clear_chat": "Clear Chat",
            "save_memory": "Remember",
            "share_chat": "Share Chat",
            "llm_parameters": "⚙️ LLM Parameters (Advanced)",
            "temperature": "🌡️ Temperature",
            "current": "Current:",
            "temperature_info": "0.0 = deterministic, 0.2 = factual, 0.8 = balanced, 1.5+ = creative",
            "context_window": "📦 Context Window",
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
            # TTS Engine dropdown labels
            "tts_engine_off": "Off",
            "tts_engine_xtts": "XTTS v2 (Local, voice cloning)",
            "tts_engine_moss": "MOSS-TTS (Batch, after bubble)",
            "tts_engine_dashscope": "DashScope Qwen3-TTS (Cloud, streaming)",
            "tts_engine_piper": "Piper TTS (Local, Offline)",
            "tts_engine_espeak": "eSpeak (Robot, Offline)",
            "tts_engine_edge": "Edge TTS (Cloud, Fallback)",

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
            "message_hub_heading": "📨 Message Hub",
            "message_hub_info": "Manage plugins: enable/disable channels and tools",
            "auto_reply": "Auto-Reply",
            "plugin_channels": "Channels",
            "plugin_tools": "Tool Plugins",
            "cred_save": "Save & Activate",
            "cred_cancel": "Cancel",
            # Email credential labels
            "email_cred_imap_host": "IMAP Host",
            "email_cred_imap_port": "IMAP Port",
            "email_cred_smtp_host": "SMTP Host",
            "email_cred_smtp_port": "SMTP Port",
            "email_cred_user": "Username / Email",
            "email_cred_password": "Password",
            "email_cred_from": "Display Name (optional)",
            # Discord credential labels
            "discord_cred_bot_token": "Bot Token",
            "discord_cred_channel_ids": "Channel IDs (comma-separated)",
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
            "audio": "Audio",
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
            "multi_agent_symposion": "Symposion",
            # Multi-Agent Mode Descriptions
            "multi_agent_mode": "💬 Discussion Mode",
            "multi_agent_info_standard": "💡 Only AIfred answers (classic behavior)",
            "multi_agent_info_critical_review": "💡 AIfred answers, Sokrates critiques, you decide (Reasoning recommended)",
            "multi_agent_info_auto_consensus": "💡 AIfred, Sokrates & Salomo discuss until consensus",
            "multi_agent_info_devils_advocate": "💡 Pro & Contra arguments for balanced analysis (Reasoning recommended)",
            "multi_agent_info_tribunal": "💡 AIfred vs Sokrates debate, Salomo judges at the end",
            "multi_agent_info_symposion": "💡 Select agents for a scholars' Symposion (multiperspective)",
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
            "multi_agent_help_symposion_flow": "Freely chosen agents discuss in turns (X rounds)",
            "multi_agent_help_symposion_decision": "None — multiperspectivity",
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
            "speed_switch_tooltip": "Ctx: max context, balanced GPU split\n⚡ Speed: 32K context, aggressive GPU split (faster)",
            "lgtm_tooltip": "Salomo is satisfied with the answer",
            "consensus_agreed": "Agreed.",
            "consensus_continue": "Continue discussion.",
            "alfred_title": "🎩 AIfred",
            # Salomo Labels
            "salomo_title": "👑 Salomo",
            "salomo_llm": "Salomo-LLM:",
            # Personality Tooltips
            "personality_aifred_tooltip": "Butler personality: Polite British speech style",
            "personality_sokrates_tooltip": "Philosopher personality: Socratic method with rhetorical questions",
            "personality_salomo_tooltip": "King personality: Wise arbiter style with Hebrew proverbs",
            "personality_vision_tooltip": "Vision personality: AIfred butler style for image analysis",
            # Reasoning & Thinking Tooltips
            "reasoning_tooltip": "Reasoning prompt – Step-by-step analysis in system prompt",
            "thinking_tooltip": "Model Thinking – Internal chain-of-thought (enable_thinking)",
            "reasoning_thinking_info": "💭 Reasoning = Analysis prompt in system prompt\n🧠 Thinking = Model-internal thinking (CoT)",
            # Reasoning/Thinking Help Modal
            "reasoning_thinking_help_title": "Reasoning & Thinking – Overview",
            "reasoning_thinking_help_lightbulb_tooltip": "What do Reasoning and Thinking mean?",
            "reasoning_thinking_help_reasoning_title": "💭 Reasoning Prompt",
            "reasoning_thinking_help_reasoning_desc": "Injects an analysis prompt into the system prompt that instructs the model to respond in a structured, step-by-step manner. The model receives explicit instructions for methodical analysis.",
            "reasoning_thinking_help_reasoning_effect": "Effect: More structured, thorough responses through prompt engineering.",
            "reasoning_thinking_help_thinking_title": "🧠 Model Thinking (CoT)",
            "reasoning_thinking_help_thinking_desc": "Activates the model's internal chain-of-thought (enable_thinking). The model thinks in a hidden <think> block before responding. Only models with thinking support (e.g. Qwen3, DeepSeek-R1) support this.",
            "reasoning_thinking_help_thinking_effect": "Effect: Deeper analysis through internal reasoning. Produces longer responses and more tokens.",
            "reasoning_thinking_help_combinations_title": "Combinations",
            "reasoning_thinking_help_both_on": "Both ON: Maximum analysis depth – prompt instructions + internal thinking",
            "reasoning_thinking_help_reasoning_only": "Reasoning only: Structured responses without internal thought process",
            "reasoning_thinking_help_thinking_only": "Thinking only: Internal CoT without additional analysis prompt",
            "reasoning_thinking_help_both_off": "Both OFF: Fast, direct responses without analysis overhead",
            "reasoning_thinking_help_close": "Close",
            "discussion_mode_tooltip": "Show discussion modes overview",
            # Sampling Parameter Labels
            "sampling_section_label": "🎲 Sampling Parameters",
            "sampling_reset_tooltip": "Reset all values to model defaults (incl. temp)",
            "sampling_temp_label": "Temperature",
            "sampling_temp_toggle_tooltip": "Auto: Temperature is determined by intent detection (factual/mixed/creative). Manual: Temperature from the table. Sampling parameters (Top-K etc.) always come from the table.",
            "sampling_auto_hint": "Temp: Intent Detection · Sampling: always from table",
            "sampling_manual_hint": "All values from table (incl. temp)",
            "temp_label": "Temp",
            "top_k_label": "Top-K",
            "top_p_label": "Top-P",
            "min_p_label": "Min-P",
            "repeat_penalty_label": "Rep.P",
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
            # Agent Editor
            "agent_editor_title": "Agent Management",
            "agent_editor_new": "New Agent",
            "agent_editor_edit": "Edit",
            "agent_editor_delete": "Delete",
            "agent_editor_delete_confirm": "Really delete agent?",
            "agent_editor_forget": "Forget",
            "agent_editor_forget_confirm": "Really forget?",
            "agent_editor_save": "Save",
            "agent_editor_cancel": "Cancel",
            "agent_editor_reset": "Reset",
            "agent_editor_name": "Name",
            "agent_editor_emoji": "Emoji",
            "agent_editor_role": "Role",
            "agent_editor_description": "Description",
            "agent_editor_prompts": "Prompt Layers",
            "agent_editor_id": "Agent ID",
            "agent_editor_id_hint": "Lowercase, no spaces",
            "agent_editor_role_main": "Main Agent",
            "agent_editor_role_critic": "Critic",
            "agent_editor_role_judge": "Judge",
            "agent_editor_role_custom": "Custom",
            "agent_editor_default_badge": "Default",
            "agent_editor_close": "Close",
            # Tool Status Messages
            "tool_search": "🔍 Searching...",
            "tool_memory": "💾 Saving insight...",
            "tool_code_generating": "⚙️ Generating code...",
            "tool_code_running": "⚙️ Running code...",
            "tool_email": "📧 Email...",
            "tool_email_check": "📧 Checking inbox...",
            "tool_email_read": "📧 Reading email {msg_id}...",
            "tool_email_search": "📧 Search: {query}",
            "tool_email_delete": "📧 Deleting email {msg_id}...",
            "tool_email_send": "📧 Sending to {to}...",
            "tool_doc_search": "📄 Searching documents...",
            "tool_doc_list": "📄 Listing documents...",
            "tool_doc_delete": "📄 Deleting {filename}...",
            "tool_epim_search": "📅 {entity}: {query}",
            "tool_epim_search_bare": "📅 {entity}...",
            "tool_epim_create": "📅 Creating {entity}...",
            "tool_epim_update": "📅 Updating {entity}...",
            "tool_epim_delete": "📅 Deleting {entity}...",
            # Document Upload UI
            "upload_document": "Document",
            "doc_hint": "Upload PDF, Word, Excel, PowerPoint, LibreOffice, TXT, MD, CSV",
            "doc_upload_no_store": "⚠️ Document store not available (ChromaDB not running?)",
            "doc_upload_invalid_type": "⚠️ {filename}: Type not allowed. Allowed: {allowed}",
            "doc_upload_too_large": "⚠️ {filename}: Too large (max {max_mb} MB)",
            "doc_upload_indexing": "📄 Indexing {filename}...",
            "doc_upload_success": "✅ {filename}: {chunks} chunks indexed",
            "doc_delete_success": "🗑️ {filename}: {chunks} chunks deleted",
            # Document Manager Modal
            "doc_manager_title": "📄 Documents",
            "doc_manager_empty": "No documents uploaded yet.",
            "doc_manager_chunks": "{chunks} chunks",
            "doc_manager_close": "Close",
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


def tts_label_to_key(label: str) -> str:
    """Map a translated TTS engine label back to its internal key.

    Searches all languages since get_language() is unreliable in handler context.
    """
    from .config import TTS_ENGINE_KEYS
    for lang_translations in TranslationManager._translations.values():
        for key in TTS_ENGINE_KEYS:
            if lang_translations.get(f"tts_engine_{key}") == label:
                return key
    return label


def tts_key_to_label(key: str, lang: Optional[str] = None) -> str:
    """Map an internal TTS engine key to its translated display label.

    Used by tts_engine_or_off computed var for dropdown display.
    """
    return t(f"tts_engine_{key}", lang=lang)