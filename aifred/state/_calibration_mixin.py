"""Calibration mixin for AIfred state.

Handles context calibration for Ollama and llama.cpp backends,
including backend restart and vLLM restart.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import reflex as rx

from ..lib.logging_utils import CONSOLE_SEPARATOR


class CalibrationMixin(rx.State, mixin=True):
    """Mixin for context calibration and server restart."""

    # ------------------------------------------------------------------
    # State vars
    # ------------------------------------------------------------------
    is_calibrating: bool = False  # Shows spinner during context calibration

    # ------------------------------------------------------------------
    # Calibration entry point
    # ------------------------------------------------------------------

    async def calibrate_context(self):
        """
        Calibrate maximum context window for current model.

        Supported backends:
        - Ollama: Binary search via /api/ps (size == size_vram check)
        - llama.cpp: Binary search via direct llama-server start/health check
        """
        if self.backend_type not in ("ollama", "llamacpp"):  # type: ignore[attr-defined]
            self.add_debug("⚠️ Calibration only for Ollama and llama.cpp")  # type: ignore[attr-defined]
            return

        if not self.aifred_model_id:  # type: ignore[attr-defined]
            self.add_debug("⚠️ No model selected")  # type: ignore[attr-defined]
            return

        if self.is_calibrating:
            self.add_debug("⚠️ Calibration already in progress")  # type: ignore[attr-defined]
            return

        self.is_calibrating = True
        self.add_debug(f"🔧 Starting calibration for {self.aifred_model_id}...")  # type: ignore[attr-defined]
        yield

        # Dispatch to backend-specific calibration
        if self.backend_type == "llamacpp":  # type: ignore[attr-defined]
            async for _ in self._calibrate_llamacpp():
                yield
            return

        try:
            from ..backends import BackendFactory
            from ..lib.formatting import format_number
            from ..lib.model_vram_cache import add_ollama_calibration
            from ..lib.gpu_utils import get_gpu_model_name

            backend = BackendFactory.create(
                self.backend_type,  # type: ignore[attr-defined]
                base_url=self.backend_url  # type: ignore[attr-defined]
            )

            # Get native context limit first
            native_ctx, _ = await backend.get_model_context_limit(self.aifred_model_id)  # type: ignore[attr-defined]
            calibration_results = {}

            # === STEP 1: Calibrate Native (1.0x) ===
            self.add_debug("📐 Calibrating Native (1.0x)...")  # type: ignore[attr-defined]
            yield

            calibrated_ctx = None
            is_hybrid_mode = False  # Track if 1.0x resulted in hybrid mode
            async for progress_msg in backend.calibrate_max_context_generator(  # type: ignore[attr-defined]
                self.aifred_model_id,  # type: ignore[attr-defined]
                rope_factor=1.0
            ):
                if progress_msg.startswith("__RESULT__:"):
                    # Parse result: __RESULT__:{ctx}:{mode} where mode is gpu/hybrid/error
                    parts = progress_msg.split(":")
                    calibrated_ctx = int(parts[1])
                    calibration_results[1.0] = calibrated_ctx
                    if len(parts) > 2 and parts[2] == "hybrid":
                        is_hybrid_mode = True
                else:
                    self.add_debug(f"📊 {progress_msg}")  # type: ignore[attr-defined]
                    yield

            # === STEP 2: Check calibration result ===
            # Determine if RoPE calibration makes sense
            skip_rope_calibration = False

            # Check for calibration failure (model doesn't fit)
            if not calibrated_ctx or calibrated_ctx == 0:
                self.add_debug(CONSOLE_SEPARATOR)  # type: ignore[attr-defined]
                self.add_debug("❌ Calibration failed - model doesn't fit in memory")  # type: ignore[attr-defined]
                self.add_debug("   → Skipping RoPE calibration")  # type: ignore[attr-defined]
                yield
                skip_rope_calibration = True
            elif calibrated_ctx < native_ctx:
                # Memory is the bottleneck (VRAM or RAM) - RoPE scaling won't help
                # This applies to BOTH GPU-only and Hybrid mode
                skip_rope_calibration = True
                self.add_debug(CONSOLE_SEPARATOR)  # type: ignore[attr-defined]
                if is_hybrid_mode:
                    self.add_debug(f"🔀 Hybrid mode: {format_number(calibrated_ctx)} < {format_number(native_ctx)} native")  # type: ignore[attr-defined]
                    self.add_debug("   → RAM is the limit - RoPE scaling won't increase context")  # type: ignore[attr-defined]
                else:
                    self.add_debug(f"⚡ VRAM-limited: {format_number(calibrated_ctx)} < {format_number(native_ctx)} native")  # type: ignore[attr-defined]
                    self.add_debug("   → VRAM is the limit - RoPE scaling won't increase context")  # type: ignore[attr-defined]
                self.add_debug(f"   → Auto-setting RoPE 1.5x and 2.0x to {format_number(calibrated_ctx)}")  # type: ignore[attr-defined]
                yield
            elif is_hybrid_mode:
                # Hybrid mode but native context fits - RoPE might give us more!
                self.add_debug(CONSOLE_SEPARATOR)  # type: ignore[attr-defined]
                self.add_debug(f"🔀 Hybrid mode: {format_number(calibrated_ctx)} (native fits)")  # type: ignore[attr-defined]
                self.add_debug("   → Testing if RoPE scaling can extend context further...")  # type: ignore[attr-defined]
                yield
                # Don't skip - let it calibrate RoPE 1.5x and 2.0x

            if skip_rope_calibration and calibrated_ctx:
                # Save same value for 1.5x and 2.0x (no separate calibration needed)
                # Only if we have a valid context (not on error)
                gpu_model = get_gpu_model_name() or "Unknown"
                for rope_factor in [1.5, 2.0]:
                    add_ollama_calibration(
                        model_name=self.aifred_model_id,  # type: ignore[attr-defined]
                        max_context_gpu_only=calibrated_ctx,
                        native_context=native_ctx,
                        gpu_model=gpu_model,
                        rope_factor=rope_factor,
                        is_hybrid=is_hybrid_mode
                    )
                    calibration_results[rope_factor] = calibrated_ctx

            elif not skip_rope_calibration:
                # === STEP 3: Calibrate RoPE 1.5x and 2.0x ===
                # Start from 1.0x result, then use previous RoPE result as new minimum
                from ..lib.config import CALIBRATION_MIN_CONTEXT
                prev_ctx = calibration_results.get(1.0, CALIBRATION_MIN_CONTEXT)

                for rope_factor in [1.5, 2.0]:
                    self.add_debug(CONSOLE_SEPARATOR)  # type: ignore[attr-defined]
                    self.add_debug(f"📐 Calibrating RoPE {rope_factor}x...")  # type: ignore[attr-defined]
                    yield

                    rope_calibrated_ctx = None
                    async for progress_msg in backend.calibrate_max_context_generator(  # type: ignore[attr-defined]
                        self.aifred_model_id,  # type: ignore[attr-defined]
                        rope_factor=rope_factor,
                        min_context=prev_ctx,  # Start from previous result (1.0x or 1.5x)
                        force_hybrid=is_hybrid_mode  # Continue in hybrid mode if 1.0x was hybrid
                    ):
                        if progress_msg.startswith("__RESULT__:"):
                            # Parse result: __RESULT__:{ctx}:{mode}
                            parts = progress_msg.split(":")
                            rope_calibrated_ctx = int(parts[1])
                            calibration_results[rope_factor] = rope_calibrated_ctx
                            # Update prev_ctx for next iteration (2.0x uses 1.5x result)
                            prev_ctx = rope_calibrated_ctx
                        else:
                            self.add_debug(f"📊 {progress_msg}")  # type: ignore[attr-defined]
                            yield

            # Summary
            self.add_debug("═" * 20)  # type: ignore[attr-defined]
            mode_info = " (Hybrid)" if is_hybrid_mode else ""
            self.add_debug(f"✅ Calibration complete for {self.aifred_model_id}{mode_info}:")  # type: ignore[attr-defined]
            for factor, ctx in calibration_results.items():
                label = "Native" if factor == 1.0 else f"RoPE {factor}x"
                suffix = " (auto)" if skip_rope_calibration and factor > 1.0 else ""
                self.add_debug(f"   {label}: {format_number(ctx)} tok{suffix}")  # type: ignore[attr-defined]
            self.add_debug("   → Values will be used automatically based on RoPE setting")  # type: ignore[attr-defined]

            # Test thinking capability if calibration was successful (shared helper)
            if calibration_results.get(1.0, 0) > 0:
                async for _ in self._test_and_save_thinking(backend, self.aifred_model_id):  # type: ignore[attr-defined]
                    yield

            self.add_debug(CONSOLE_SEPARATOR)  # type: ignore[attr-defined]

        except Exception as e:
            self.add_debug(f"❌ Calibration failed: {e}")  # type: ignore[attr-defined]

        finally:
            self.is_calibrating = False
            yield

    # ------------------------------------------------------------------
    # Thinking capability test (shared between Ollama and llama.cpp)
    # ------------------------------------------------------------------

    async def _test_and_save_thinking(self, backend: Any, model_id: str) -> AsyncGenerator[None, None]:
        """
        Test thinking capability and save result to cache + state.

        Shared between Ollama and llama.cpp calibration flows.
        """
        self.add_debug("─" * 20)  # type: ignore[attr-defined]
        self.add_debug("🧠 Testing reasoning capability...")  # type: ignore[attr-defined]
        yield

        try:
            supports_thinking = await backend.test_thinking_capability(model_id)

            from ..lib.model_vram_cache import set_thinking_support_for_model
            set_thinking_support_for_model(model_id, supports_thinking)

            # Update state for ALL agents using this model
            if self.aifred_model_id == model_id:  # type: ignore[attr-defined]
                self.aifred_supports_thinking = supports_thinking  # type: ignore[attr-defined]
            if self.sokrates_model_id == model_id:  # type: ignore[attr-defined]
                self.sokrates_supports_thinking = supports_thinking  # type: ignore[attr-defined]
            if self.salomo_model_id == model_id:  # type: ignore[attr-defined]
                self.salomo_supports_thinking = supports_thinking  # type: ignore[attr-defined]

            if supports_thinking:
                self.add_debug("✅ Reasoning mode: Supported (<think> tags)")  # type: ignore[attr-defined]
            else:
                self.add_debug("⚠️ Reasoning mode: Not supported")  # type: ignore[attr-defined]

        except Exception as e:
            self.add_debug(f"⚠️ Thinking test failed: {e}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # llama.cpp calibration
    # ------------------------------------------------------------------

    async def _calibrate_llamacpp(self):
        """
        llama.cpp calibration via direct llama-server binary search.

        Workflow:
        1. Stop llama-swap service (free VRAM)
        2. Phase 1: GPU-only binary search (ngl=99)
        3. Phase 2: Speed variant calibration (multi-GPU tensor-split, if Phase 1 succeeds)
        4. Phase 3: Hybrid NGL+context search (if GPU-only < MIN_USEFUL_CONTEXT_TOKENS)
        4. Update llama-swap YAML with calibrated -c and -ngl values
        5. Restart llama-swap service
        6. Test thinking capability
        """
        import subprocess
        from ..lib.formatting import format_number
        from ..lib.llamacpp_calibration import (
            update_llamaswap_context,
            update_llamaswap_ngl,
            add_llamaswap_speed_variant,
        )
        from ..lib.config import LLAMASWAP_CONFIG_PATH, MIN_USEFUL_CONTEXT_TOKENS

        llama_swap_stopped = False

        try:
            from ..backends import BackendFactory

            backend = BackendFactory.create(
                self.backend_type,  # type: ignore[attr-defined]
                base_url=self.backend_url  # type: ignore[attr-defined]
            )

            # Step 1: Stop llama-swap system service to free VRAM
            self.add_debug("🛑 Stopping llama-swap service...")  # type: ignore[attr-defined]
            yield
            try:
                subprocess.run(
                    ["systemctl", "stop", "llama-swap"],
                    check=True, timeout=15,
                )
                llama_swap_stopped = True
                self.add_debug("   llama-swap stopped via systemctl")  # type: ignore[attr-defined]
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                self.add_debug(f"⚠️ Could not stop llama-swap: {e}")  # type: ignore[attr-defined]
                self.add_debug("   Continuing anyway (VRAM may be limited)")  # type: ignore[attr-defined]
            yield

            # Step 2: Run calibration (Phase 1: GPU-only, Phase 2: Hybrid if needed,
            #          Phase 3: Speed split for multi-GPU models)
            # Result format: __RESULT__:{ctx}:{ngl}:{mode}:{thinks|nothink}
            # Speed format:  __SPEED__:{N}  (N:1 tensor-split for speed variant, 0=none)
            calibrated_ctx = None
            calibrated_ngl = 99
            calibrated_mode = "gpu"
            thinking_tested = False
            speed_split_n = 0
            async for progress_msg in backend.calibrate_max_context_generator(  # type: ignore[attr-defined]
                self.aifred_model_id  # type: ignore[attr-defined]
            ):
                if progress_msg.startswith("__RESULT__:"):
                    parts = progress_msg.split(":")
                    calibrated_ctx = int(parts[1])
                    calibrated_ngl = int(parts[2]) if len(parts) > 2 else 99
                    calibrated_mode = parts[3] if len(parts) > 3 else "gpu"
                    if len(parts) > 4:
                        thinking_tested = True
                        supports_thinking = parts[4] == "thinks"
                elif progress_msg.startswith("__SPEED__:"):
                    speed_split_n = int(progress_msg.split(":")[1])
                else:
                    self.add_debug(f"📊 {progress_msg}")  # type: ignore[attr-defined]
                    yield

            # Step 3: Process result
            if not calibrated_ctx or calibrated_ctx == 0:
                self.add_debug(CONSOLE_SEPARATOR)  # type: ignore[attr-defined]
                self.add_debug("❌ Calibration failed")  # type: ignore[attr-defined]
                yield
                return

            self.add_debug(CONSOLE_SEPARATOR)  # type: ignore[attr-defined]
            mode_str = f" (hybrid, ngl={calibrated_ngl})" if calibrated_mode == "hybrid" else ""
            self.add_debug(f"✅ Calibrated: {format_number(calibrated_ctx)} tokens{mode_str}")  # type: ignore[attr-defined]

            # Step 4: Update llama-swap YAML (-c and optionally -ngl)
            self.add_debug("📝 Updating llama-swap config...")  # type: ignore[attr-defined]
            updated_ctx = update_llamaswap_context(
                LLAMASWAP_CONFIG_PATH,
                self.aifred_model_id,  # type: ignore[attr-defined]
                calibrated_ctx
            )
            if updated_ctx:
                self.add_debug(  # type: ignore[attr-defined]
                    f"   -c {format_number(calibrated_ctx)} written to "
                    f"{LLAMASWAP_CONFIG_PATH.name}"
                )
            else:
                self.add_debug("⚠️ Could not update -c in llama-swap config")  # type: ignore[attr-defined]

            # Always write ngl: gpu-mode uses 99, hybrid uses the calculated value.
            # Without this, a stale ngl (e.g. from a previous hybrid calibration) stays.
            updated_ngl = update_llamaswap_ngl(
                LLAMASWAP_CONFIG_PATH,
                self.aifred_model_id,  # type: ignore[attr-defined]
                calibrated_ngl
            )
            if updated_ngl:
                mode_label = "hybrid mode" if calibrated_mode == "hybrid" else "gpu mode"
                self.add_debug(f"   -ngl {calibrated_ngl} written ({mode_label})")  # type: ignore[attr-defined]
            else:
                self.add_debug("⚠️ Could not update -ngl in llama-swap config")  # type: ignore[attr-defined]

            # Write speed variant YAML entry (only for multi-GPU models with valid split)
            if speed_split_n > 0:
                added_speed = add_llamaswap_speed_variant(
                    LLAMASWAP_CONFIG_PATH,
                    self.aifred_model_id,  # type: ignore[attr-defined]
                    speed_split_n,
                    MIN_USEFUL_CONTEXT_TOKENS,
                )
                if added_speed:
                    self.add_debug(  # type: ignore[attr-defined]
                        f"   ⚡ Speed variant: {self.aifred_model_id}-speed "  # type: ignore[attr-defined]
                        f"(split {speed_split_n}:1, ctx {format_number(MIN_USEFUL_CONTEXT_TOKENS)})"
                    )
                    # Patch speed_split into the latest calibration entry (already saved)
                    from ..lib.model_vram_cache import update_llamacpp_speed_split
                    update_llamacpp_speed_split(self.aifred_model_id, speed_split_n)  # type: ignore[attr-defined]
                    # Toggle immediately visible without restart
                    self.aifred_has_speed_variant = True  # type: ignore[attr-defined]
                else:
                    self.add_debug("⚠️ Could not write speed variant to llama-swap config")  # type: ignore[attr-defined]
            yield

            # Step 5: Restart llama-swap
            self.add_debug("🔄 Restarting llama-swap service...")  # type: ignore[attr-defined]
            try:
                subprocess.run(
                    ["systemctl", "start", "llama-swap"],
                    check=True, timeout=15,
                )
                llama_swap_stopped = False
                self.add_debug("   llama-swap started")  # type: ignore[attr-defined]
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                self.add_debug("⚠️ Could not restart llama-swap")  # type: ignore[attr-defined]
            yield

            # Step 6: Save thinking result (tested during calibration)
            if thinking_tested:
                from ..lib.model_vram_cache import set_thinking_support_for_model
                set_thinking_support_for_model(self.aifred_model_id, supports_thinking)  # type: ignore[attr-defined]
                self.aifred_supports_thinking = supports_thinking  # type: ignore[attr-defined]
                self.add_debug(  # type: ignore[attr-defined]
                    f"🧠 Reasoning: {'yes' if supports_thinking else 'no'} "
                    f"(tested during calibration)"
                )

            self.add_debug(CONSOLE_SEPARATOR)  # type: ignore[attr-defined]

        except Exception as e:
            self.add_debug(f"❌ Calibration failed: {e}")  # type: ignore[attr-defined]

        finally:
            # Always restart llama-swap if we stopped it
            if llama_swap_stopped:
                try:
                    subprocess.run(
                        ["systemctl", "start", "llama-swap"],
                        timeout=15,
                    )
                except Exception:
                    pass
            self.is_calibrating = False
            yield

    # ------------------------------------------------------------------
    # Calibration info display
    # ------------------------------------------------------------------

    def _show_model_calibration_info(self, model_id: str):
        """Show calibration info in debug console.

        Displays calibrated context values or a warning
        if the model hasn't been calibrated yet.
        """
        if not model_id:
            return

        from ..lib.formatting import format_number

        if self.backend_type == "llamacpp":  # type: ignore[attr-defined]
            from ..lib.model_vram_cache import get_llamacpp_calibration
            calibrated = get_llamacpp_calibration(model_id)
            if calibrated:
                self.add_debug(f"   🎯 Calibrated: {format_number(calibrated)} tokens")  # type: ignore[attr-defined]
            else:
                self.add_debug("   ⚠️ Not calibrated - please run calibration for optimal context")  # type: ignore[attr-defined]
            return

        if self.backend_type != "ollama":  # type: ignore[attr-defined]
            return

        from ..lib.model_vram_cache import get_ollama_calibrated_max_context

        native_ctx = get_ollama_calibrated_max_context(model_id, rope_factor=1.0)
        rope_1_5x_ctx = get_ollama_calibrated_max_context(model_id, rope_factor=1.5)
        rope_2x_ctx = get_ollama_calibrated_max_context(model_id, rope_factor=2.0)

        if native_ctx is not None or rope_1_5x_ctx is not None or rope_2x_ctx is not None:
            parts = []
            if native_ctx is not None:
                parts.append(f"Native: {format_number(native_ctx)}")
            if rope_1_5x_ctx is not None:
                parts.append(f"RoPE 1.5x: {format_number(rope_1_5x_ctx)}")
            if rope_2x_ctx is not None:
                parts.append(f"RoPE 2x: {format_number(rope_2x_ctx)}")
            self.add_debug(f"   🎯 Calibrated: {', '.join(parts)}")  # type: ignore[attr-defined]
        else:
            self.add_debug("   ⚠️ Not calibrated - please run calibration for optimal context")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Backend restart
    # ------------------------------------------------------------------

    async def restart_backend(self):
        """Restart current LLM backend service and reload model list"""
        import httpx
        import asyncio

        from ..lib.formatting import format_number
        from ..lib.model_manager import sort_models_grouped

        # Prevent concurrent restarts
        if self.backend_switching:  # type: ignore[has-type]
            self.add_debug("⚠️ Backend restart already in progress, please wait...")  # type: ignore[attr-defined]
            return

        self.backend_switching = True  # type: ignore[attr-defined]
        yield  # Update UI to disable buttons

        try:
            backend_name = self.backend_type.upper()  # type: ignore[attr-defined]
            self.add_debug(f"🔄 Restarting {backend_name} service...")  # type: ignore[attr-defined]
            yield  # Update UI

            if self.backend_type == "ollama":  # type: ignore[attr-defined]
                from ..lib.process_utils import restart_service
                restart_service("ollama", check=True)
                self.add_debug(f"✅ {backend_name} service restarted")  # type: ignore[attr-defined]
                yield  # Update UI after restart

                # Wait for Ollama to be ready (active polling with retry)
                self.add_debug("⏳ Waiting for Ollama API to be ready...")  # type: ignore[attr-defined]
                yield  # Update UI

                max_retries = 10
                ollama_ready = False

                for attempt in range(max_retries):
                    try:
                        endpoint = f'{self.backend_url}/api/tags'  # type: ignore[attr-defined]
                        response = httpx.get(endpoint, timeout=2.0)

                        if response.status_code == 200:
                            # Parse JSON to verify API is actually ready
                            data = response.json()
                            # Build dict: {model_id: display_label}
                            unsorted_dict = {
                                m['name']: f"{m['name']} ({format_number(m['size'] / (1024**3), 1)} GB)"
                                for m in data.get("models", [])
                            }
                            # Sort by model family, then by size
                            self.available_models_dict = sort_models_grouped(unsorted_dict)  # type: ignore[attr-defined]
                            # Keep list for compatibility (DEPRECATED)
                            self.available_models = list(self.available_models_dict.values())  # type: ignore[attr-defined]

                            # Update global state
                            from . import _base
                            _base._global_backend_state["available_models"] = self.available_models  # type: ignore[attr-defined]

                            elapsed_time = (attempt + 1) * 0.5
                            self.add_debug(f"✅ Ollama ready after {elapsed_time:.1f}s ({len(self.available_models)} models found)")  # type: ignore[attr-defined]
                            ollama_ready = True
                            break
                    except httpx.RequestError:
                        pass  # Retry on connection error

                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5)  # Short polling interval
                        yield  # Update UI during polling

                if not ollama_ready:
                    self.add_debug("⚠️ Ollama API might not be ready yet (timeout after 5s)")  # type: ignore[attr-defined]
                    yield

            elif self.backend_type == "vllm":  # type: ignore[attr-defined]
                # vLLM: Stop and restart with current model
                self.add_debug("⏹️ Stopping vLLM server...")  # type: ignore[attr-defined]
                yield  # Update UI
                await self._stop_vllm_server()  # type: ignore[attr-defined]

                self.add_debug("🚀 Starting vLLM server...")  # type: ignore[attr-defined]
                yield  # Update UI
                await self._start_vllm_server()  # type: ignore[attr-defined]

                # Verify vLLM is ready
                self.add_debug("⏳ Waiting for vLLM API to be ready...")  # type: ignore[attr-defined]
                yield

                max_retries = 10
                vllm_ready = False

                for attempt in range(max_retries):
                    try:
                        # vLLM health check endpoint
                        response = httpx.get(
                            f"{self.backend_url}/health",  # type: ignore[attr-defined]
                            timeout=2.0
                        )

                        if response.status_code == 200:
                            elapsed_time = (attempt + 1) * 0.5
                            self.add_debug(f"✅ vLLM ready after {elapsed_time:.1f}s")  # type: ignore[attr-defined]
                            vllm_ready = True
                            break
                    except httpx.RequestError:
                        pass  # Retry on connection error

                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5)
                        yield

                if not vllm_ready:
                    self.add_debug("⚠️ vLLM might not be ready yet (timeout after 5s)")  # type: ignore[attr-defined]

                yield  # Update UI
            elif self.backend_type == "llamacpp":  # type: ignore[attr-defined]
                # llama-swap: restart via systemctl (system service)
                import subprocess as _sp

                result = _sp.run(
                    ["systemctl", "restart", "llama-swap"],
                    capture_output=True,
                )

                if result.returncode == 0:
                    self.add_debug("✅ llama-swap service restarted (autoscan running...)")  # type: ignore[attr-defined]
                else:
                    err = result.stderr.decode(errors='replace').strip()
                    self.add_debug(f"⚠️ llama-swap restart failed: {err or 'unknown error'}")  # type: ignore[attr-defined]
                yield

                # Wait for llama-swap to be ready (ExecStartPre/autoscan may take a few seconds)
                self.add_debug("⏳ Waiting for llama-swap to be ready...")  # type: ignore[attr-defined]
                yield

                max_retries = 20  # up to 10s — autoscan ExecStartPre can take time
                llamacpp_ready = False
                for attempt in range(max_retries):
                    try:
                        response = httpx.get(f"{self.backend_url}/v1/models", timeout=2.0)  # type: ignore[attr-defined]
                        if response.status_code == 200:
                            elapsed = (attempt + 1) * 0.5
                            self.add_debug(f"✅ llama-swap ready after {elapsed:.1f}s")  # type: ignore[attr-defined]
                            llamacpp_ready = True
                            break
                    except httpx.RequestError:
                        pass
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5)
                        yield

                if not llamacpp_ready:
                    self.add_debug("⚠️ llama-swap might not be ready yet (timeout after 10s)")  # type: ignore[attr-defined]
                yield

            elif self.backend_type == "tabbyapi":  # type: ignore[attr-defined]
                # TabbyAPI: Unload and reload model via API
                self.add_debug("⏹️ Unloading TabbyAPI model...")  # type: ignore[attr-defined]
                yield  # Update UI

                try:
                    # Unload current model
                    response = httpx.post(
                        f"{self.backend_url}/v1/model/unload",  # type: ignore[attr-defined]
                        headers={"Content-Type": "application/json"},
                        timeout=10.0
                    )

                    if response.status_code == 200:
                        self.add_debug("✅ Model unloaded successfully")  # type: ignore[attr-defined]
                        yield

                        # Reload model
                        self.add_debug("🚀 Reloading TabbyAPI model...")  # type: ignore[attr-defined]
                        yield

                        load_response = httpx.post(
                            f"{self.backend_url}/v1/model/load",  # type: ignore[attr-defined]
                            json={"name": self.aifred_model},  # type: ignore[attr-defined]
                            headers={"Content-Type": "application/json"},
                            timeout=30.0
                        )

                        if load_response.status_code == 200:
                            self.add_debug("✅ Model load command successful")  # type: ignore[attr-defined]
                            yield

                            # Verify model is actually loaded
                            self.add_debug("⏳ Verifying model is loaded...")  # type: ignore[attr-defined]
                            yield

                            max_retries = 10
                            model_ready = False

                            for attempt in range(max_retries):
                                try:
                                    verify_response = httpx.get(
                                        f"{self.backend_url}/v1/models",  # type: ignore[attr-defined]
                                        headers={"Content-Type": "application/json"},
                                        timeout=2.0
                                    )

                                    if verify_response.status_code == 200:
                                        data = verify_response.json()
                                        # Check if any model is loaded
                                        if data.get("data") and len(data["data"]) > 0:
                                            elapsed_time = (attempt + 1) * 0.5
                                            self.add_debug(f"✅ TabbyAPI ready after {elapsed_time:.1f}s")  # type: ignore[attr-defined]
                                            model_ready = True
                                            break
                                except httpx.RequestError:
                                    pass

                                if attempt < max_retries - 1:
                                    await asyncio.sleep(0.5)
                                    yield

                            if not model_ready:
                                self.add_debug("⚠️ Model might not be fully loaded yet (timeout after 5s)")  # type: ignore[attr-defined]
                        else:
                            self.add_debug(f"⚠️ Model reload failed: {load_response.status_code}")  # type: ignore[attr-defined]
                    else:
                        self.add_debug(f"⚠️ Model unload failed: {response.status_code}")  # type: ignore[attr-defined]

                except httpx.RequestError as e:
                    self.add_debug(f"⚠️ TabbyAPI restart failed: {e}")  # type: ignore[attr-defined]

                yield  # Update UI

        except Exception as e:
            self.add_debug(f"❌ {backend_name} restart failed: {e}")  # type: ignore[attr-defined]
        finally:
            self.backend_switching = False  # type: ignore[attr-defined]
            yield  # Re-enable buttons

    async def restart_ollama(self):
        """Legacy method - calls restart_backend()"""
        await self.restart_backend()

    # ------------------------------------------------------------------
    # AIfred service restart
    # ------------------------------------------------------------------

    def restart_aifred(self):
        """Restart AIfred service via systemctl"""
        import threading

        try:
            self.add_debug("🔄 Restarting AIfred service...")  # type: ignore[attr-defined]

            # Schedule systemd restart in background thread
            # This allows us to return rx.call_script() BEFORE the service dies
            from ..lib.process_utils import restart_service as do_restart_service

            def delayed_restart():
                import time
                time.sleep(0.5)  # Short delay to let browser script execute first
                do_restart_service("aifred-intelligence", check=False)

            thread = threading.Thread(target=delayed_restart, daemon=True)
            thread.start()

            self.add_debug("✅ AIfred service restart initiated")  # type: ignore[attr-defined]
            self.add_debug("🔄 Browser will reload in 0.5s...")  # type: ignore[attr-defined]

            # Return the reload script IMMEDIATELY
            # This executes in browser BEFORE systemd kills the service
            # Browser will reload, wait for service to come back up, then reconnect
            return rx.call_script("window.location.reload(true)")

        except Exception as e:
            self.add_debug(f"❌ AIfred service restart failed: {e}")  # type: ignore[attr-defined]
