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


def estimate_tokens(messages: List[Dict], model_name: Optional[str] = None) -> int:
    """
    Count tokens in messages using real tokenizer (with fallback)

    Args:
        messages: Liste von Message-Dicts mit 'content' Key
        model_name: Optional model name for accurate tokenization

    Returns:
        int: Token count (exact with tokenizer, estimated with fallback)
    """
    # Combine all message content
    total_text = "\n".join(m['content'] for m in messages)
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


async def calculate_dynamic_num_ctx(
    llm_client,
    model_name: str,
    messages: List[Dict],
    llm_options: Optional[Dict] = None,
    enable_vram_limit: bool = True
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

    # GENERÖSE Reserve für lange Antworten:
    # Input + 8K-16K Reserve (je nach Input-Größe)
    # Verhindert abgeschnittene Antworten bei ausführlichen Erklärungen
    if estimated_tokens < 2048:
        # Kleine Anfragen: +8K Reserve
        reserve = 8192
    elif estimated_tokens < 8192:
        # Mittlere Anfragen: +12K Reserve
        reserve = 12288
    else:
        # Große Anfragen (Research): +16K Reserve
        reserve = 16384

    needed_tokens = estimated_tokens + reserve

    # Runde auf Standard-Größe
    if needed_tokens <= 2048:
        calculated_ctx = 2048
    elif needed_tokens <= 4096:
        calculated_ctx = 4096
    elif needed_tokens <= 8192:
        calculated_ctx = 8192
    elif needed_tokens <= 10240:
        calculated_ctx = 10240
    elif needed_tokens <= 12288:
        calculated_ctx = 12288
    elif needed_tokens <= 16384:
        calculated_ctx = 16384
    elif needed_tokens <= 20480:
        calculated_ctx = 20480  # 20K
    elif needed_tokens <= 24576:
        calculated_ctx = 24576  # 24K
    elif needed_tokens <= 28672:
        calculated_ctx = 28672  # 28K
    elif needed_tokens <= 32768:
        calculated_ctx = 32768  # 32K
    elif needed_tokens <= 40960:
        calculated_ctx = 40960  # 40K
    else:
        calculated_ctx = 65536  # 64K (Maximum)

    # Query Model-Limit UND Model-Size vom Backend (~40ms, lädt Modell NICHT!)
    model_limit, model_size_bytes = await llm_client.get_model_context_limit(model_name)

    # NEU: VRAM-basiertes praktisches Limit berechnen
    vram_debug_msgs = []
    if enable_vram_limit:
        from .gpu_utils import calculate_vram_based_context
        max_practical_ctx, vram_debug_msgs = calculate_vram_based_context(
            model_name=model_name,
            model_size_bytes=model_size_bytes,
            model_context_limit=model_limit
        )
    else:
        # VRAM-Limit deaktiviert - nutze volles Model-Limit
        max_practical_ctx = model_limit
        log_message(f"⚠️ VRAM-Limit deaktiviert - nutze volles Modell-Limit {model_limit:,} (Risiko: CPU-Offload)")

    # Clippe auf kleineren Wert: calculated vs. practical limit
    final_num_ctx = min(calculated_ctx, max_practical_ctx)

    # Warne wenn Context überschritten
    if calculated_ctx > max_practical_ctx:
        log_message(
            f"⚠️ Gewünschter Context {format_number(calculated_ctx)} > Praktisches Limit {format_number(max_practical_ctx)} "
            f"(VRAM-begrenzt), clippe auf {format_number(final_num_ctx)}"
        )
    elif calculated_ctx > model_limit:
        log_message(
            f"⚠️ Gewünschter Context {format_number(calculated_ctx)} > Modell-Limit {format_number(model_limit)}, "
            f"clippe auf {format_number(final_num_ctx)}"
        )

    log_message(
        f"🎯 Context Window: {format_number(final_num_ctx)} tok "
        f"(berechnet: {format_number(calculated_ctx)}, praktisch: {format_number(max_practical_ctx)}, "
        f"modell-max: {format_number(model_limit)}, ~{format_number(estimated_tokens)} benötigt)"
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
        yield {"type": "debug", "message": f"📊 History Compression: {int(utilization)}% ({format_number(estimated_tokens)} / {format_number(context_limit)} tok)"}
        log_message(f"⚠️ Compression aborted: {len(history)} Messages würden ALLE komprimiert → Chat leer!")
        return

    if estimated_tokens < threshold:
        yield {"type": "debug", "message": f"📊 History Compression: {int(utilization)}% ({format_number(estimated_tokens)} / {format_number(context_limit)} tok)"}
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

    # 7. Formatiere Konversation für LLM
    conversation_text = ""
    for i, (user_msg, ai_msg) in enumerate(messages_to_summarize, 1):
        log_message(f"   └─ Message {i}: User={len(user_msg)} chars, AI={len(ai_msg)} chars")
        conversation_text += f"User: {user_msg}\nAI: {ai_msg}\n\n"

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

