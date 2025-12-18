"""
Context Manager - Token and Context Window Management

Handles context limits and token estimation for LLMs:
- Query model context limits from backends (on-demand, no caching)
- Calculate optimal num_ctx for requests
- Token estimation for messages (using HuggingFace tokenizers)
- History compression (summarize_history_if_needed)
"""

import time
import asyncio
from typing import Dict, List, Optional, AsyncIterator
from .logging_utils import log_message, console_separator
from .prompt_loader import load_prompt
from .formatting import format_number
from .config import (
    HISTORY_COMPRESSION_THRESHOLD,
    HISTORY_MESSAGES_TO_COMPRESS,
    HISTORY_MAX_SUMMARIES,
    HISTORY_SUMMARY_TARGET_TOKENS,
    HISTORY_SUMMARY_TARGET_WORDS,
    HISTORY_SUMMARY_TEMPERATURE,
    HISTORY_SUMMARY_CONTEXT_LIMIT
)

# Global tokenizer cache (model_name -> tokenizer)
_tokenizer_cache = {}


def count_tokens_with_tokenizer(text: str, model_name: str) -> int:
    """
    Count tokens using HuggingFace AutoTokenizer (cached, fast after first load)

    Args:
        text: Text to tokenize
        model_name: HuggingFace model name (e.g., "Qwen/Qwen3-8B-AWQ")

    Returns:
        int: Exact token count
    """
    global _tokenizer_cache

    # Check cache first
    if model_name not in _tokenizer_cache:
        try:
            from transformers import AutoTokenizer
            # Load tokenizer (cached by HuggingFace after first download)
            _tokenizer_cache[model_name] = AutoTokenizer.from_pretrained(
                model_name,
                trust_remote_code=True,
                local_files_only=False  # Allow download if not cached
            )
            log_message(f"✅ Loaded tokenizer for {model_name}")
        except Exception as e:
            log_message(f"⚠️ Could not load tokenizer for {model_name}: {e}")
            return None

    try:
        tokenizer = _tokenizer_cache[model_name]
        tokens = tokenizer.encode(text, add_special_tokens=True)
        return len(tokens)
    except Exception as e:
        log_message(f"⚠️ Tokenization failed: {e}")
        return None


def strip_thinking_blocks(text: str) -> str:
    """
    Entfernt <think>...</think> Blöcke aus Text (für History Compression).

    Diese Blöcke enthalten:
    - DeepSeek Reasoning (thinking process)
    - Vision-LLM JSON (strukturierte Extraktion)

    Args:
        text: Text mit potentiellen <think> Blöcken

    Returns:
        Text ohne <think> Blöcke
    """
    import re
    # Entferne alle <think>...</think> Blöcke (non-greedy, multi-line)
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()


def estimate_tokens(messages: List[Dict], model_name: Optional[str] = None) -> int:
    """
    Count tokens in messages using real tokenizer (with fallback)

    Args:
        messages: Liste von Message-Dicts mit 'content' Key (str oder list)
        model_name: Optional model name for accurate tokenization

    Returns:
        int: Token count (exact with tokenizer, estimated with fallback)
    """
    # Combine all message content (handle both str and multimodal list format)
    text_parts = []
    for m in messages:
        content = m['content']
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            # Multimodal content: extract text parts only (images don't count as text tokens)
            for part in content:
                if part.get("type") == "text":
                    text_parts.append(part.get("text", ""))

    total_text = "\n".join(text_parts)
    total_chars = len(total_text)

    # Try real tokenizer first (if model_name provided)
    if model_name:
        token_count = count_tokens_with_tokenizer(total_text, model_name)
        if token_count is not None:
            return token_count

    # Fallback: Conservative estimation (2.5 chars/token)
    # This overestimates tokens by ~20% to prevent context overflow
    return int(total_chars / 2.5)


def estimate_tokens_from_history(history: List[tuple]) -> int:
    """
    Schätzt Token-Anzahl aus Chat History (Tuple-Format)

    Args:
        history: Liste von (user_msg, ai_msg) Tuples

    Returns:
        int: Geschätzte Anzahl Tokens (Faustregel: 1 Token ≈ 3.5 Zeichen für Deutsch/gemischte Texte)
    """
    total_size = sum(len(user_msg) + len(ai_msg) for user_msg, ai_msg in history)
    # 3.5 Zeichen pro Token (besser für deutsche Texte als 4)
    return int(total_size / 3.5)


# Global cache für VRAM-Limit (verhindert Neuberechnung bei History-Kompression)
_last_vram_limit_cache = {"limit": 0}

# Reserve-Stufen für LLM-Output (stufenweise Reduzierung bevor Content gekürzt wird)
OUTPUT_RESERVE_PREFERRED = 32768  # 32K - Ideal für ausführliche Antworten (4x erhöht für 108K+ Context)
OUTPUT_RESERVE_REDUCED = 6144     # 6K - Akzeptabel wenn VRAM knapp
OUTPUT_RESERVE_MINIMUM = 4096     # 4K - Minimum, darunter wird Content gekürzt

# Für Abwärtskompatibilität (wird in calculate_dynamic_num_ctx verwendet)
OUTPUT_RESERVE_TOKENS = OUTPUT_RESERVE_PREFERRED


def calculate_adaptive_reserve(
    available_context: int,
    base_input: int,
    max_rag_target: int
) -> tuple[int, int]:
    """
    Berechnet adaptive Reserve und RAG-Budget.

    Priorität: Maximiere Reserve (32K), dann reduziere stufenweise wenn RAG zu knapp wird.

    Stufen:
    1. Versuche mit 32K Reserve → wenn RAG >= max_rag_target: perfekt
    2. Falls 32K RAG knapp, aber > min threshold: nutze 32K mit reduziertem RAG
    3. Falls RAG < min threshold: Reduziere Reserve auf 6K
    4. Falls 6K RAG knapp: nutze 6K mit reduziertem RAG
    5. Falls RAG < min threshold: Reduziere auf 4K (Minimum)
    6. Erst DANN: Kürze RAG-Content auf verfügbares Budget

    Args:
        available_context: Max verfügbarer Context (VRAM/Model-limitiert)
        base_input: Geschätzter Input ohne RAG (System-Prompt + History + User)
        max_rag_target: Ziel-Größe für RAG-Context (z.B. MAX_RAG_CONTEXT_TOKENS = 20K)

    Returns:
        tuple[int, int]: (actual_reserve, max_rag_tokens)
    """
    from .logging_utils import log_message
    from .formatting import format_number

    # Minimum RAG bevor Reserve reduziert wird (80% vom Ziel)
    min_rag_threshold = int(max_rag_target * 0.8)  # z.B. 16K bei 20K Ziel

    # Stufe 1: Versuche mit voller Reserve (32K)
    rag_budget_32k = available_context - base_input - OUTPUT_RESERVE_PREFERRED
    if rag_budget_32k >= max_rag_target:
        return OUTPUT_RESERVE_PREFERRED, max_rag_target
    if rag_budget_32k >= min_rag_threshold:
        # RAG etwas knapp, aber akzeptabel - behalte 32K Reserve
        log_message(f"ℹ️ RAG leicht reduziert: {format_number(max_rag_target)} → {format_number(rag_budget_32k)} tok (Reserve: 32K)")
        return OUTPUT_RESERVE_PREFERRED, rag_budget_32k

    # Stufe 2: Reduziere auf 6K Reserve (VRAM knapp)
    rag_budget_6k = available_context - base_input - OUTPUT_RESERVE_REDUCED
    if rag_budget_6k >= max_rag_target:
        log_message(f"⚠️ Reserve reduziert: 32K → 6K (RAG-Budget: {format_number(rag_budget_6k)} tok)")
        return OUTPUT_RESERVE_REDUCED, max_rag_target
    if rag_budget_6k >= min_rag_threshold:
        # RAG etwas knapp, aber akzeptabel - behalte 6K Reserve
        log_message(f"⚠️ Reserve reduziert: 32K → 6K, RAG: {format_number(rag_budget_6k)} tok")
        return OUTPUT_RESERVE_REDUCED, rag_budget_6k

    # Stufe 3: Reduziere auf 4K Reserve (Minimum)
    rag_budget_4k = available_context - base_input - OUTPUT_RESERVE_MINIMUM
    if rag_budget_4k >= max_rag_target:
        log_message(f"⚠️ Reserve reduziert: 32K → 4K (RAG-Budget: {format_number(rag_budget_4k)} tok)")
        return OUTPUT_RESERVE_MINIMUM, max_rag_target

    # Stufe 4: Reserve auf Minimum, RAG wird gekürzt
    if rag_budget_4k > 0:
        log_message(f"⚠️ RAG-Content wird gekürzt: {format_number(max_rag_target)} → {format_number(rag_budget_4k)} tok (Reserve: 4K)")
        return OUTPUT_RESERVE_MINIMUM, max(4096, rag_budget_4k)  # Mindestens 4K RAG

    # Extremfall: Kein Platz für RAG (sollte nie passieren)
    log_message(f"❌ Kritisch: Kein Platz für RAG-Content! (available: {format_number(available_context)}, base: {format_number(base_input)})")
    return OUTPUT_RESERVE_MINIMUM, 4096  # Fallback: Minimum RAG


async def get_max_available_context(
    llm_client,
    model_name: str,
    enable_vram_limit: bool = True
) -> tuple[int, int]:
    """
    Berechnet max verfügbaren Context VOR dem Context-Building.

    Diese Funktion ermittelt das praktische Limit BEVOR der RAG-Context gebaut wird,
    damit build_context() weiß wie viel Platz zur Verfügung steht.

    Args:
        llm_client: LLMClient instance
        model_name: Name des Modells
        enable_vram_limit: Ob VRAM-basierte Begrenzung angewandt wird

    Returns:
        tuple[int, int]: (max_practical_ctx, model_limit)
    """
    # Query Model-Limit vom Backend
    model_limit, _ = await llm_client.get_model_context_limit(model_name)

    if enable_vram_limit:
        backend = llm_client._get_backend()
        max_practical_ctx, _ = await backend.calculate_practical_context(model_name)
    else:
        max_practical_ctx = model_limit

    return min(max_practical_ctx, model_limit), model_limit


async def calculate_dynamic_num_ctx(
    llm_client,
    model_name: str,
    messages: List[Dict],
    llm_options: Optional[Dict] = None,
    enable_vram_limit: bool = True,
    state = None  # Optional: AIState instance zum Speichern des VRAM-Limits
) -> tuple[int, list[str]]:
    """
    Berechnet optimales num_ctx basierend auf Message-Größe, Model-Limit UND VRAM.

    Diese Funktion ist ZENTRAL für alle Context-Berechnungen!
    Sie fragt das Modell-Limit direkt ab (~30ms) und berechnet optimales num_ctx.

    Die Berechnung berücksichtigt:
    1. Message-Größe × 2 (50/50 Regel: 50% Input, 50% Output)
    2. Model-Maximum (via Backend-Abfrage)
    3. VRAM-basiertes praktisches Limit (NEU! verhindert CPU-Offload)
    4. User-Override (falls in llm_options gesetzt)

    Args:
        llm_client: LLMClient instance (beliebiger Backend-Typ)
        model_name: Name des Modells (z.B. "qwen3:8b", "phi3:mini")
        messages: Liste von Message-Dicts mit 'content' Key
        llm_options: Dict mit optionalem 'num_ctx' Override
        enable_vram_limit: Ob VRAM-basierte Begrenzung angewandt wird (Standard: True)

    Returns:
        tuple[int, list[str]]: (num_ctx, debug_messages)
            - num_ctx: Optimales num_ctx (gerundet auf Standard-Größen, geclippt auf praktisches Limit)
            - debug_messages: VRAM debug messages for UI console (to be yielded by caller)

    Raises:
        RuntimeError: Wenn Model-Info nicht abfragbar
    """
    # Check für manuellen Override
    user_num_ctx = llm_options.get('num_ctx') if llm_options else None
    if user_num_ctx:
        log_message(f"🎯 Context Window: {user_num_ctx} Tokens (manuell gesetzt)")
        return user_num_ctx, []  # No VRAM messages for manual override

    # Berechne Tokens aus Message-Größe
    estimated_tokens = estimate_tokens(messages)  # 1 Token ≈ 3.5 Zeichen

    # Konstante 8K Reserve für LLM-Output
    # Bei Research (Summarization) ist Output KÜRZER als Input, daher reichen 8K
    # (~6000 Wörter / 4-5 A4-Seiten für ausführliche Antworten)
    reserve = OUTPUT_RESERVE_TOKENS  # 8192

    needed_tokens = estimated_tokens + reserve

    # Query Model-Limit vom Backend (~40ms, lädt Modell NICHT!)
    model_limit, _ = await llm_client.get_model_context_limit(model_name)

    # NEU: Backend-spezifisches praktisches Limit berechnen
    # - Ollama: Dynamische VRAM-Berechnung (basierend auf aktuellem freien VRAM)
    # - vLLM: Gecachter Startup-Wert (FIXED, kann nicht zur Laufzeit geändert werden)
    # - TabbyAPI: Gecachter Startup-Wert oder API-Query
    # - KoboldCPP: Gecachter Startup-Wert (FIXED, num_ctx nicht zur Laufzeit änderbar)
    vram_debug_msgs = []
    backend = llm_client._get_backend()
    backend_type = type(backend).__name__

    if enable_vram_limit:
        # Use backend-specific context calculation
        max_practical_ctx, vram_debug_msgs = await backend.calculate_practical_context(model_name)
    else:
        # VRAM-Limit deaktiviert - nutze volles Model-Limit
        max_practical_ctx = model_limit
        log_message(f"⚠️ VRAM-Limit deaktiviert - nutze volles Modell-Limit {model_limit:,} (Risiko: CPU-Offload)")

    # Backend-spezifische Context-Berechnung
    calculated_ctx = needed_tokens

    if backend_type == "KoboldCPPBackend":
        # KoboldCPP: num_ctx ist FIXED beim Server-Start, kann nicht zur Laufzeit geändert werden
        # Wir MÜSSEN immer den vollen Context verwenden (max_practical_ctx = Startup-Wert)
        final_num_ctx = max_practical_ctx
        log_message(
            f"🎯 KoboldCPP: Using fixed startup context: {format_number(final_num_ctx)} tok "
            f"(~{format_number(estimated_tokens)} benötigt, {format_number(calculated_ctx)} berechnet)"
        )
    else:
        # Ollama/vLLM/TabbyAPI: Dynamische num_ctx Berechnung möglich
        # gpu_utils.calculate_vram_based_context() liefert:
        # - Kalibriert: den gemessenen max_context_gpu_only Wert
        # - Nicht kalibriert: dynamisch berechneten VRAM-basierten Wert
        # In beiden Fällen: Auf Modell-Limit clippen
        final_num_ctx = min(max_practical_ctx, model_limit)

    # Speichere VRAM-Limit in globalem Cache für History-Kompression
    # (verhindert dass History das Limit neu berechnen muss)
    _last_vram_limit_cache["limit"] = min(max_practical_ctx, model_limit)

    # Optional: Auch in State speichern falls übergeben
    if state is not None:
        state.last_vram_limit = min(max_practical_ctx, model_limit)

    # Log Context Window Info (nur für Ollama/vLLM/TabbyAPI)
    if backend_type != "KoboldCPPBackend":
        # Berechne verfügbaren Output-Space
        available_output = final_num_ctx - estimated_tokens
        log_message(
            f"🎯 Context Window: {format_number(final_num_ctx)} tok "
            f"(Input: ~{format_number(estimated_tokens)}, Output-Platz: ~{format_number(available_output)}, "
            f"VRAM-Limit: {format_number(max_practical_ctx)}, Modell-Max: {format_number(model_limit)})"
        )

    return final_num_ctx, vram_debug_msgs


async def summarize_history_if_needed(
    history: List[tuple],
    llm_client,
    model_name: str,
    context_limit: int,
    max_summaries: int = None
) -> AsyncIterator[Dict]:
    """
    Komprimiert Chat-History wenn nötig (Context-Overflow-Prevention)

    Args:
        history: Chat-History als Liste von (user_msg, ai_msg) Tuples
        llm_client: LLM Client für Summarization
        model_name: Haupt-LLM Model
        context_limit: Context Window Limit des Models
        max_summaries: Maximale Anzahl Summaries bevor FIFO (default: aus config)

    Yields:
        Dict: Progress und Debug Messages

    Returns:
        None - Funktion modifiziert history in-place nicht, State-Update erfolgt über yield
    """
    # Entfernt: Unnötige Debug-Zeile über function call details

    # Verwende Config-Werte als Defaults
    if max_summaries is None:
        max_summaries = HISTORY_MAX_SUMMARIES

    # Token-Estimation & Utilization Check (IMMER zuerst, für Debug-Message)
    estimated_tokens = estimate_tokens_from_history(history)
    utilization = (estimated_tokens / context_limit) * 100
    threshold = int(context_limit * HISTORY_COMPRESSION_THRESHOLD)

    # Safety-Check: Immer mindestens 1 Message nach Kompression übrig lassen!
    # KRITISCH: Verhindert dass alle Messages komprimiert werden und Chat leer wird
    if len(history) <= HISTORY_MESSAGES_TO_COMPRESS:
        yield {"type": "debug", "message": f"📊 History: {format_number(estimated_tokens)} / {format_number(context_limit)} tok ({int(utilization)}%)"}
        log_message(f"⚠️ Compression aborted: {len(history)} Messages würden ALLE komprimiert → Chat leer!")
        return

    if estimated_tokens < threshold:
        yield {"type": "debug", "message": f"📊 History: {format_number(estimated_tokens)} / {format_number(context_limit)} tok ({int(utilization)}%)"}
        return

    log_message(f"⚠️ History zu lang: {int(utilization)}% Auslastung ({format_number(estimated_tokens)} tok) > {format_number(threshold)} Threshold → Starte Kompression")

    # Progress-Indicator: Komprimiere Kontext
    yield {"type": "progress", "phase": "compress"}
    yield {"type": "debug", "message": f"🗜️ History-Kompression startet: {int(utilization)}% Auslastung ({format_number(estimated_tokens)} / {format_number(context_limit)} tok)"}

    # 4. Zähle bestehende Summaries
    summary_count = sum(1 for user_msg, ai_msg in history if user_msg == "" and ai_msg.startswith("[📊 Komprimiert"))

    # 5. FIFO wenn bereits max_summaries erreicht
    if summary_count >= max_summaries:
        log_message(f"⚠️ Max {max_summaries} Summaries erreicht → Lösche älteste Summary (FIFO)")
        # Finde und entferne älteste Summary
        for i, (user_msg, ai_msg) in enumerate(history):
            if user_msg == "" and ai_msg.startswith("[📊 Komprimiert"):
                history.pop(i)
                yield {"type": "debug", "message": "🗑️ Älteste Summary entfernt (FIFO)"}
                break

    # 6. Extrahiere älteste Messages zum Summarizen (konfigurierbare Anzahl)
    messages_to_summarize = history[:HISTORY_MESSAGES_TO_COMPRESS]
    remaining_messages = history[HISTORY_MESSAGES_TO_COMPRESS:]

    log_message("📝 Bereite Kompression vor:")
    log_message(f"   └─ Zu komprimieren: {len(messages_to_summarize)} Messages")
    log_message(f"   └─ Model: {model_name}")
    log_message(f"   └─ Temperature: {HISTORY_SUMMARY_TEMPERATURE}")
    log_message(f"   └─ Context-Limit: {HISTORY_SUMMARY_CONTEXT_LIMIT}")

    # 7. Formatiere Konversation für LLM (ohne <think> Blöcke!)
    conversation_text = ""
    for i, (user_msg, ai_msg) in enumerate(messages_to_summarize, 1):
        # Entferne <think> Blöcke aus beiden Messages
        clean_user_msg = strip_thinking_blocks(user_msg) if user_msg else ""
        clean_ai_msg = strip_thinking_blocks(ai_msg) if ai_msg else ""

        log_message(f"   └─ Message {i}: User={len(user_msg)}→{len(clean_user_msg)} chars, AI={len(ai_msg)}→{len(clean_ai_msg)} chars")
        conversation_text += f"User: {clean_user_msg}\nAI: {clean_ai_msg}\n\n"

    # Spracherkennung für Konversation (nutze ersten User-Text als Referenz)
    from .prompt_loader import detect_language
    first_user_msg = messages_to_summarize[0][0] if messages_to_summarize else ""
    detected_language = detect_language(first_user_msg) if first_user_msg else "de"

    # 8. Load Summarization Prompt
    summary_prompt = load_prompt(
        'history_summarization',
        lang=detected_language,
        conversation=conversation_text.strip(),
        max_tokens=HISTORY_SUMMARY_TARGET_TOKENS,
        max_words=HISTORY_SUMMARY_TARGET_WORDS
    )

    # 9. LLM Summarization (Haupt-LLM für bessere Qualität)
    import datetime
    start_timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]  # Millisekunden
    log_message(f"🗜️ [START {start_timestamp}] Komprimiere {HISTORY_MESSAGES_TO_COMPRESS} Messages mit {model_name}...")
    summary_start = time.time()

    # Token-Anzahl vor Kompression
    tokens_before = estimate_tokens_from_history(messages_to_summarize)

    summary_text = ""
    tokens_generated = 0

    try:
        # VIEL EINFACHER: Nutze chat() statt chat_stream() - wir brauchen keinen Stream!
        log_message("   Rufe LLM auf (non-streaming)...")

        # Import backend types
        from ..backends.base import LLMMessage, LLMOptions

        # Create proper message and options objects
        messages = [LLMMessage(role="system", content=summary_prompt)]
        options = LLMOptions(
            temperature=HISTORY_SUMMARY_TEMPERATURE,
            num_ctx=HISTORY_SUMMARY_CONTEXT_LIMIT,
            enable_thinking=False  # Fast summarization, no reasoning needed
        )

        response = await llm_client.chat(
            model=model_name,
            messages=messages,
            options=options
        )

        # Response auswerten
        summary_time = time.time() - summary_start
        end_timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

        # Log raw response for debugging
        log_message(f"   Raw response type: {type(response)}")
        log_message(f"   Raw response: {response}")

        # Summary-Text extrahieren (response ist ein LLMResponse Objekt!)
        summary_text = response.text if response else ""

        # Metrics aus LLMResponse extrahieren
        if response:
            tokens_generated = response.tokens_generated
            tokens_per_second = response.tokens_per_second
        else:
            # Fallback: Schätze Tokens basierend auf Text-Länge
            tokens_generated = len(summary_text) // 4  # Grobe Schätzung
            tokens_per_second = tokens_generated / summary_time if summary_time > 0 else 0

        # Detaillierte Debug-Ausgabe
        log_message(f"✅ [END {end_timestamp}] Summary generiert:")
        log_message(f"   └─ Zeichen generiert: {len(summary_text)}")
        log_message(f"   └─ Tokens geschätzt: {format_number(tokens_generated)}")
        log_message(f"   └─ Zeit: {format_number(summary_time, 2)}s")
        log_message(f"   └─ Geschwindigkeit: {format_number(tokens_per_second, 1)} tok/s")
        if tokens_before > 0 and tokens_generated > 0:
            log_message(f"   └─ Kompression: {format_number(tokens_before)} → {format_number(tokens_generated)} tok ({format_number(tokens_before/tokens_generated, 1)}:1 Ratio)")
        console_separator()

    except asyncio.TimeoutError:
        log_message("⚠️ Async Timeout bei Summary-Generierung")
        yield {"type": "debug", "message": "⚠️ Summary-Generierung timeout"}
        summary_text = ""  # Sicherstellen dass leer bei Timeout
    except Exception as e:
        log_message(f"❌ Fehler bei Summary-Generierung: {e}")
        yield {"type": "debug", "message": f"❌ Summary-Fehler: {e}"}
        summary_text = ""  # Sicherstellen dass leer bei Fehler

    # 10. Nur wenn Summary erfolgreich generiert wurde
    if summary_text and len(summary_text.strip()) > 10:  # Mindestens 10 Zeichen
        # Erstelle Summary-Entry (Collapsible-Format)
        summary_entry = (
            "",  # Leerer User-Teil
            f"[📊 Komprimiert: {len(messages_to_summarize)} Messages]\n{summary_text.strip()}"
        )
        # Baue neue History: [Summary] + [Remaining Messages]
        new_history = [summary_entry] + remaining_messages
    else:
        # Bei Fehler: History unverändert lassen
        log_message("⚠️ Summary zu kurz oder leer - History bleibt unverändert")
        yield {"type": "debug", "message": "⚠️ Kompression fehlgeschlagen - History unverändert"}
        return  # Beende hier ohne Änderung

    # Berechne neue Token-Anzahl nach Kompression
    new_tokens = estimate_tokens_from_history(new_history)
    compression_ratio = estimated_tokens / new_tokens if new_tokens > 0 else 0

    log_message("✅ History erfolgreich komprimiert:")
    log_message(f"   └─ Messages: {len(history)} → {len(new_history)} (davon {len(remaining_messages)} sichtbar)")
    log_message(f"   └─ Tokens: {format_number(estimated_tokens)} → {format_number(new_tokens)} ({format_number(compression_ratio, 1)}:1 Ratio)")
    log_message(f"   └─ Platz gespart: {format_number(estimated_tokens - new_tokens)} tok")

    # Calculate new utilization after compression
    new_utilization = (new_tokens / context_limit) * 100

    # Count summaries in new history
    summaries_count = sum(1 for user_msg, ai_msg in new_history if user_msg == "" and ai_msg.startswith("[📊 Komprimiert"))

    # 12. Yield Update an State
    yield {"type": "history_update", "data": new_history}
    yield {"type": "debug", "message": f"📦 History komprimiert: {int(utilization)}% → {int(new_utilization)}% ({format_number(estimated_tokens)} → {format_number(new_tokens)} tok, {len(messages_to_summarize)}→1 messages, {summaries_count} Summaries total)"}


async def prepare_main_llm(
    backend,
    llm_client,
    model_name: str,
    messages: list,
    num_ctx_mode: str = "auto_vram",
    num_ctx_manual: int = 4096,
    backend_type: str = "ollama"
) -> tuple[int, list[str], bool, float]:
    """
    Zentrale Funktion für Haupt-LLM Vorbereitung.

    Garantiert korrekte Reihenfolge für Ollama Multi-GPU:
    1. num_ctx berechnen (Ollama auto_vram: mit unload + VRAM-Messung)
    2. Preload mit num_ctx (Ollama lädt Modell + allokiert KV-Cache)

    WICHTIG: Diese Funktion ist NUR für das Haupt-LLM gedacht!
    Automatik-LLMs nutzen Ollama's LRU-Strategie und brauchen kein explizites
    Preloading oder Unloading.

    Args:
        backend: LLM Backend instance
        llm_client: LLMClient für Context-Limit Abfrage
        model_name: Modell-Name (pure ID ohne Suffix)
        messages: Message-Liste für Token-Schätzung
        num_ctx_mode: "manual", "auto_vram", "auto_max"
        num_ctx_manual: Manueller Wert (nur wenn mode="manual")
        backend_type: "ollama", "vllm", etc.

    Returns:
        tuple[int, list[str], bool, float]:
            - final_num_ctx: Berechneter/manueller Context
            - debug_msgs: Debug-Messages für UI
            - preload_success: Ob Preload erfolgreich
            - preload_time: Ladezeit in Sekunden
    """
    debug_msgs = []

    # 1. num_ctx berechnen (VOR Preload!)
    if num_ctx_mode == "manual":
        final_num_ctx = num_ctx_manual
        debug_msgs.append(f"🔧 Manual num_ctx: {num_ctx_manual:,}")
        log_message(f"🔧 Manual num_ctx: {num_ctx_manual:,} (VRAM calculation skipped)")
    else:
        enable_vram_limit = (num_ctx_mode == "auto_vram")

        if backend_type == "ollama" and enable_vram_limit:
            # Ollama auto_vram: calculate_practical_context() macht:
            # - unload_all_models() intern
            # - 2s warten für VRAM-Freigabe
            # - VRAM-basierte Berechnung
            final_num_ctx, vram_msgs = await backend.calculate_practical_context(model_name)
            debug_msgs.extend(vram_msgs)

            # Cache setzen für History-Kompression (wie calculate_dynamic_num_ctx() es tut)
            _last_vram_limit_cache["limit"] = final_num_ctx
        else:
            # Andere Backends oder auto_max: Standard-Berechnung
            final_num_ctx, vram_msgs = await calculate_dynamic_num_ctx(
                llm_client, model_name, messages, None,
                enable_vram_limit=enable_vram_limit
            )
            debug_msgs.extend(vram_msgs)

    # 2. Preload mit num_ctx (nur Ollama - andere Backends haben Modell beim Start)
    preload_success = True
    preload_time = 0.0

    if backend_type == "ollama":
        from .formatting import format_number
        formatted_ctx = format_number(final_num_ctx)
        debug_msgs.append(f"🚀 Haupt-LLM ({model_name}) wird vorgeladen (num_ctx={formatted_ctx})...")
        preload_success, preload_time = await backend.preload_model(model_name, num_ctx=final_num_ctx)

        if preload_success:
            debug_msgs.append(f"✅ Haupt-LLM vorgeladen ({preload_time:.1f}s)")
            log_message(f"✅ Haupt-LLM vorgeladen ({preload_time:.1f}s)")
        else:
            debug_msgs.append(f"⚠️ Haupt-LLM Preload fehlgeschlagen ({preload_time:.1f}s)")
            log_message(f"⚠️ Haupt-LLM Preload fehlgeschlagen ({preload_time:.1f}s)")

    return final_num_ctx, debug_msgs, preload_success, preload_time

