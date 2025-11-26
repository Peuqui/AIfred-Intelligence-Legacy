"""
KoboldCPP Process Manager

Manages KoboldCPP server process lifecycle for AIfred Intelligence.
Handles starting, stopping, and health checking of KoboldCPP server.

Special Features for 2x Tesla P40 Setup:
- Context-Offloading: Model layers on GPU0, Context window on GPU1
- Fine-grained GPU layer control via --gpulayers
- Optimized for Oculink (8GB/s) + USB4 (5GB/s) dual e-GPU setup
- Minimizes inter-card communication bottleneck
"""

import asyncio
import logging
import subprocess
import httpx
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


class KoboldCPPProcessManager:
    """
    Manages KoboldCPP server process lifecycle

    Usage:
        manager = KoboldCPPProcessManager(port=5001)
        await manager.start(
            model_path="/path/to/model.gguf",
            context_size=32768,
            gpu_layers=40,  # Model on GPU0
            context_offload=True  # Context on GPU1
        )
        # ... use KoboldCPP API ...
        await manager.stop()
    """

    def __init__(
        self,
        port: int = 5001,
        host: str = "127.0.0.1"
    ):
        """
        Initialize KoboldCPP Process Manager

        Args:
            port: Port for KoboldCPP server (default: 5001)
            host: Host to bind to (default: 127.0.0.1)
        """
        self.port = port
        self.host = host
        self.process: Optional[subprocess.Popen] = None
        self.current_model: Optional[str] = None
        self.stderr_buffer: list[str] = []  # Buffer for stderr output

        # Find koboldcpp executable
        self.koboldcpp_bin = self._find_koboldcpp_binary()

    def _find_koboldcpp_binary(self) -> Path:
        """
        Find KoboldCPP binary in system PATH or common locations

        Detects NVIDIA vs AMD GPU and returns appropriate binary:
        - NVIDIA: koboldcpp (CUDA)
        - AMD: koboldcpp_rocm (ROCm fork)

        Returns:
            Path to koboldcpp binary

        Raises:
            FileNotFoundError: If koboldcpp not found
        """
        # Detect GPU vendor
        from aifred.lib.gpu_utils import detect_gpu_vendor
        vendor = detect_gpu_vendor()

        # AMD: Check for ROCm fork
        if vendor == "amd":
            rocm_paths = [
                Path("/usr/local/bin/koboldcpp_rocm"),
                Path("/usr/bin/koboldcpp_rocm"),
                Path.home() / "koboldcpp_rocm" / "koboldcpp",
                Path.home() / ".local" / "bin" / "koboldcpp_rocm",
            ]

            for path in rocm_paths:
                if path.exists() and path.is_file():
                    logger.info(f"Found KoboldCPP ROCm binary: {path}")
                    return path

            import shutil
            if shutil.which("koboldcpp_rocm"):
                logger.info("Found KoboldCPP ROCm in PATH")
                return Path(shutil.which("koboldcpp_rocm"))

            logger.warning("AMD GPU detected but koboldcpp_rocm not found, falling back to standard binary")

        # NVIDIA or fallback: Standard KoboldCPP
        common_paths = [
            Path("/usr/local/bin/koboldcpp"),
            Path("/usr/bin/koboldcpp"),
            Path.home() / "koboldcpp" / "koboldcpp",
            Path.home() / ".local" / "bin" / "koboldcpp",
            Path("/opt/koboldcpp/koboldcpp"),
        ]

        for path in common_paths:
            if path.exists() and path.is_file():
                logger.info(f"Found KoboldCPP binary: {path}")
                return path

        # Check if in PATH
        import shutil
        kobold_in_path = shutil.which("koboldcpp")
        if kobold_in_path:
            logger.info(f"Found KoboldCPP in PATH: {kobold_in_path}")
            return Path(kobold_in_path)

        raise FileNotFoundError(
            "KoboldCPP binary not found. Please install KoboldCPP or set the path manually.\n"
            "Installation: https://github.com/LostRuins/koboldcpp"
        )

    def is_running(self) -> bool:
        """Check if KoboldCPP process is running"""
        return self.process is not None and self.process.poll() is None

    async def start(
        self,
        model_path: str,
        context_size: int = 8192,
        gpu_layers: int = 0,
        context_offload: bool = False,
        tensor_split: Optional[str] = None,
        flash_attention: bool = True,
        quantized_kv: bool = True,
        timeout: int = 60
    ) -> bool:
        """
        Start KoboldCPP server with specified model

        Args:
            model_path: Path to GGUF model file
            context_size: Context window size in tokens (default: 8192)
            gpu_layers: Number of layers to offload to GPU (default: 0 = CPU only)
                       For 30B models: ~40 layers fit on 24GB GPU
            context_offload: Enable context-offloading for dual-GPU setups (default: False)
                            When True: Model layers on GPU0, Context window on GPU1
            tensor_split: GPU VRAM split ratio (e.g., "1,0" = GPU0 only, "0.5,0.5" = 50/50)
                         For 2x P40: "1,0" (model on GPU0) + context_offload=True (context on GPU1)
            flash_attention: Enable Flash Attention (faster, less VRAM) (default: True)
            quantized_kv: Enable Quantized KV Cache (less VRAM) (default: True)
            timeout: Seconds to wait for server ready (default: 60)

        Returns:
            True if started successfully

        Raises:
            RuntimeError: If KoboldCPP fails to start

        Example for 2x Tesla P40 (24GB each):
            # 30B model: Model on GPU0, Context on GPU1
            await manager.start(
                model_path="/path/to/qwen3-30b-q4_K_M.gguf",
                context_size=32768,
                gpu_layers=40,          # All layers on GPU0
                context_offload=True,   # Context on GPU1
                tensor_split="1,0",     # Model VRAM only on GPU0
                flash_attention=True,
                quantized_kv=True
            )
        """
        # Stop existing process if running
        if self.is_running():
            logger.info(f"Stopping existing KoboldCPP process (model: {self.current_model})")
            await self.stop()

        # Validate model path
        model_file = Path(model_path)
        if not model_file.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        logger.info(f"🚀 Starting KoboldCPP server with model: {model_file.name}")
        logger.info(f"   Context: {context_size:,} tokens")
        logger.info(f"   Context Offload: {context_offload}")
        logger.info(f"   Tensor Split: {tensor_split or 'auto'}")

        # Extract layer count from GGUF metadata to bypass KoboldCPP's conservative auto-detection
        # Using explicit layer count instead of -1 maximizes VRAM usage (see docs/koboldcpp_2x_p40_setup.md)
        from aifred.lib.gguf_utils import get_gguf_layer_count
        actual_gpu_layers = gpu_layers

        if gpu_layers == -1:
            # Try to get actual layer count from GGUF
            layer_count = get_gguf_layer_count(model_file)
            if layer_count:
                # GGUF returns transformer blocks (48 for 30B models)
                # Total GPU layers = blocks + 1 output layer
                actual_gpu_layers = layer_count + 1
                logger.info(f"   🎯 GPU Layers: {actual_gpu_layers} (ALL - extracted from GGUF metadata)")
                logger.info(f"      Using explicit count instead of -1 to bypass conservative auto-detection")
            else:
                actual_gpu_layers = -1
                logger.info(f"   🎯 GPU Layers: -1 (auto - could not read from GGUF)")
        else:
            logger.info(f"   🎯 GPU Layers: {gpu_layers} (explicit)")

        # Detect GPU vendor for appropriate flags
        from aifred.lib.gpu_utils import detect_gpu_vendor
        vendor = detect_gpu_vendor()

        # Build command
        # Note: KoboldCpp accepts port as positional parameter: koboldcpp model.gguf [port]
        cmd = [
            str(self.koboldcpp_bin),
            str(model_path),
            str(self.port),  # Port as positional parameter
            "--host", self.host,
            "--contextsize", str(context_size),
            "--gpulayers", str(actual_gpu_layers),
        ]

        # GPU acceleration flags (vendor-specific)
        if vendor == "amd":
            cmd.extend(["--usecublas", "mmq"])  # AMD ROCm with optimized kernels
            logger.info("   🎮 GPU: AMD ROCm (mmq kernels)")
        elif vendor == "nvidia":
            # KoboldCPP: --usecuda without parameters uses ALL GPUs
            # To use specific GPU: --usecuda 0
            cmd.append("--usecuda")  # Use all available NVIDIA GPUs
            logger.info("   🎮 GPU: NVIDIA CUDA (all GPUs)")
        else:
            logger.info("   💻 CPU-only mode")

        # Context offloading for dual-GPU setups
        if context_offload:
            cmd.append("--contextoffload")
            logger.info("   🔀 Context Offloading ENABLED (context on secondary GPU)")

        # Tensor split for multi-GPU setups
        if tensor_split:
            cmd.extend(["--tensor_split", tensor_split])
            logger.info(f"   🔢 Tensor Split: {tensor_split}")

        # Flash Attention (faster inference, less VRAM)
        if flash_attention:
            cmd.append("--flashattention")
            logger.info("   ⚡ Flash Attention ENABLED")

        # Quantized KV Cache (less VRAM usage)
        if quantized_kv:
            cmd.extend(["--quantkv", "2"])  # 2 = Q4 quantization for KV cache (75% VRAM savings)
            logger.info("   🗜️ Quantized KV Cache ENABLED (Q4 - 75% savings)")

        # Start process
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            self.current_model = str(model_file.name)

            # Start background thread to read stderr
            import threading
            self.stderr_buffer = []  # Reset buffer
            stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
            stderr_thread.start()

            logger.info(f"✅ KoboldCPP process started (PID: {self.process.pid})")
        except Exception as e:
            raise RuntimeError(f"Failed to start KoboldCPP process: {e}")

        # Wait for server to be ready
        logger.info(f"⏳ Waiting for KoboldCPP server to be ready (timeout: {timeout}s)...")
        start_time = asyncio.get_event_loop().time()

        async with httpx.AsyncClient() as client:
            while asyncio.get_event_loop().time() - start_time < timeout:
                # Check if process crashed
                if self.process.poll() is not None:
                    stderr = self.process.stderr.read() if self.process.stderr else ""
                    raise RuntimeError(f"KoboldCPP process died unexpectedly:\n{stderr}")

                # Try health check
                try:
                    response = await client.get(
                        f"http://{self.host}:{self.port}/api/v1/models",
                        timeout=2.0
                    )
                    if response.status_code == 200:
                        logger.info("✅ KoboldCPP server is ready!")
                        return True
                except (httpx.ConnectError, httpx.TimeoutException):
                    pass  # Server not ready yet

                await asyncio.sleep(1)

        # Timeout reached
        await self.stop()
        raise RuntimeError(f"KoboldCPP server did not become ready within {timeout}s")

    async def stop(self):
        """Stop KoboldCPP server gracefully"""
        if not self.is_running():
            logger.info("KoboldCPP process is not running")
            return

        logger.info(f"🛑 Stopping KoboldCPP server (PID: {self.process.pid})")

        try:
            # Try graceful shutdown first (SIGTERM)
            self.process.terminate()

            # Wait up to 5 seconds for graceful shutdown
            try:
                self.process.wait(timeout=5)
                logger.info("✅ KoboldCPP server stopped gracefully")
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown failed
                logger.warning("⚠️ Graceful shutdown timed out, force killing...")
                self.process.kill()
                self.process.wait(timeout=2)
                logger.info("✅ KoboldCPP server force killed")

        except Exception as e:
            logger.error(f"Error stopping KoboldCPP server: {e}")

        finally:
            self.process = None
            self.current_model = None
            self.stderr_buffer.clear()

    async def health_check(self) -> bool:
        """
        Check if KoboldCPP server is healthy

        Returns:
            True if server is responding, False otherwise
        """
        if not self.is_running():
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://{self.host}:{self.port}/api/v1/models",
                    timeout=2.0
                )
                return response.status_code == 200
        except Exception:
            return False

    def _read_stderr(self):
        """Read stderr in background thread (like vLLM)"""
        if not self.process or not self.process.stderr:
            return
        try:
            for line in iter(self.process.stderr.readline, ''):
                if not line:
                    break
                self.stderr_buffer.append(line)
                # Keep buffer from growing too large
                if len(self.stderr_buffer) > 1000:
                    self.stderr_buffer = self.stderr_buffer[-500:]
        except Exception:
            pass

    async def get_server_info(self) -> Dict[str, Any]:
        """
        Get KoboldCPP server information

        Returns:
            Dict with server status, model, and configuration
        """
        if not self.is_running():
            return {
                "running": False,
                "model": None,
                "port": self.port,
                "host": self.host
            }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://{self.host}:{self.port}/api/v1/models",
                    timeout=2.0
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "running": True,
                        "healthy": True,
                        "model": self.current_model,
                        "port": self.port,
                        "host": self.host,
                        "api_data": data
                    }
                else:
                    return {
                        "running": True,
                        "healthy": False,
                        "model": self.current_model,
                        "port": self.port,
                        "host": self.host,
                        "error": f"HTTP {response.status_code}"
                    }

        except Exception as e:
            return {
                "running": True,
                "healthy": False,
                "model": self.current_model,
                "port": self.port,
                "host": self.host,
                "error": str(e)
            }

    async def start_with_auto_detection(
        self,
        model_path: str,
        model_name: str,
        timeout: int = 60,
        feedback_callback=None
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Start KoboldCPP with automatic context detection (vLLM-style 3-attempt strategy)

        Strategy (identical to vLLM):
        1. Try interpolation from cache (if available)
        2. If cache fails: Try native context from GGUF metadata
        3. If native OOM: Try VRAM-calculated context
        4. If VRAM calc OOM: Apply fixed safety buffer

        Args:
            model_path: Path to GGUF model file
            model_name: Model identifier for cache (e.g., "Qwen2.5-3B-Instruct-Q4_K_M")
            timeout: Seconds to wait for server ready
            feedback_callback: Optional callback(message: str) for user feedback

        Returns:
            (success: bool, context_info: Optional[dict])
        """
        from aifred.lib.gpu_utils import detect_koboldcpp_gpu_config
        from aifred.lib.gguf_utils import extract_quantization_from_filename, get_gguf_native_context
        from aifred.lib.model_vram_cache import (
            interpolate_koboldcpp_context,
            add_koboldcpp_calibration
        )
        from aifred.lib.config import KOBOLDCPP_CONTEXT_SAFETY_TOKENS
        from pathlib import Path
        import asyncio

        def log_feedback(msg: str):
            logger.info(msg)
            if feedback_callback:
                feedback_callback(msg)

        # Stop existing process if running
        if self.is_running():
            log_feedback("🛑 Stopping existing KoboldCPP process")
            await self.stop()

        # Get model info
        model_file = Path(model_path)
        if not model_file.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        model_size_gb = model_file.stat().st_size / (1024**3)
        quantization = extract_quantization_from_filename(model_file.name)

        # Get GPU configuration
        gpu_config = detect_koboldcpp_gpu_config()
        log_feedback(f"🎮 GPU Config: {gpu_config['description']}")
        config = gpu_config["config"]

        # Get free VRAM (sum across all GPUs for dual-GPU setups)
        try:
            import pynvml
            pynvml.nvmlInit()
            gpu_count = pynvml.nvmlDeviceGetCount()

            # Sum VRAM across all GPUs (KoboldCPP distributes automatically)
            total_vram_mb = 0
            free_vram_mb = 0
            gpu_models = []

            for i in range(gpu_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                total_vram_mb += int(mem_info.total / (1024 * 1024))
                free_vram_mb += int(mem_info.free / (1024 * 1024))
                gpu_models.append(pynvml.nvmlDeviceGetName(handle))

            pynvml.nvmlShutdown()

            gpu_model = gpu_models[0] if gpu_models else "Unknown"
            if gpu_count > 1:
                log_feedback(f"📊 VRAM: {total_vram_mb:,}MB total ({gpu_count}x GPUs), {free_vram_mb:,}MB free")
            else:
                log_feedback(f"📊 VRAM: {total_vram_mb:,}MB total, {free_vram_mb:,}MB free")
        except Exception as e:
            log_feedback(f"⚠️ Could not query GPU: {e}")
            gpu_model = "Unknown"
            free_vram_mb = 20480  # Conservative default

        # Get native context from GGUF metadata
        native_context = get_gguf_native_context(model_file)
        if native_context:
            log_feedback(f"📊 Native Context: {native_context:,} tokens (from GGUF metadata)")
        else:
            log_feedback("⚠️ Could not read native context from GGUF - will use VRAM calculation")

        # STRATEGY 1: Try interpolation from cache
        interpolated_context = interpolate_koboldcpp_context(model_name, free_vram_mb)

        if interpolated_context:
            log_feedback(f"📈 Interpolated context from cache: {interpolated_context:,} tokens")
            log_feedback(f"   Based on {free_vram_mb:,}MB free VRAM")

            # Try cached value
            try:
                success = await self.start(
                    model_path=model_path,
                    context_size=interpolated_context,
                    gpu_layers=config["gpu_layers"],
                    context_offload=config["context_offload"],
                    tensor_split=config["tensor_split"],
                    flash_attention=config["flash_attention"],
                    quantized_kv=config["quantized_kv"],
                    timeout=timeout
                )

                if success:
                    log_feedback(f"✅ Started successfully with cached context: {interpolated_context:,} tokens")
                    return (True, {
                        "model_size_gb": model_size_gb,
                        "context_size": interpolated_context,
                        "gpu_config": gpu_config["description"],
                        "quantization": quantization,
                        "native_context": native_context,
                        "cached": True
                    })
                else:
                    log_feedback("⚠️ Cached value failed to start - VRAM conditions changed")
                    # Fall through to STRATEGY 2

            except Exception as e:
                from aifred.lib.koboldcpp_utils import is_koboldcpp_oom_error

                error_msg = str(e)
                stderr_output = ""
                if hasattr(self, 'stderr_buffer') and self.stderr_buffer:
                    stderr_output = "".join(self.stderr_buffer[-50:])

                log_feedback(f"⚠️ Cached value failed: {interpolated_context:,} tokens")

                if not is_koboldcpp_oom_error(error_msg + "\n" + stderr_output):
                    log_feedback("   Non-OOM error - falling back to calibration...")
                # Fall through to STRATEGY 2

        # STRATEGY 2: No cache or cache failed - use smart calibration with VRAM pre-check
        log_feedback("🔬 No cached calibrations found (or cache failed) - starting calibration...")

        # Determine MB/token for VRAM estimation
        # Using Q4 KV Cache quantization (--quantkv 2) for 75% VRAM savings
        # These values reflect Q4 quantized KV cache, not FP16
        mb_per_token_map = {
            "Q4": 0.05,   # Q4 KV cache (75% savings vs FP16's 0.17-0.20)
            "Q5": 0.06,   # Adjusted proportionally
            "Q8": 0.10,   # Adjusted proportionally
            "IQ4": 0.05,  # Same as Q4
            "IQ3": 0.04,  # Slightly lower
        }

        mb_per_token = 0.05  # Default Q4 with Q4 KV cache quantization
        for key in mb_per_token_map.keys():
            if key in quantization:
                mb_per_token = mb_per_token_map[key]
                break

        # CRITICAL: Model VRAM usage ≈ File size (GGUF is already compressed)
        # Empirical data from live measurements:
        #   @ 98K context: 720MB free, 98K × 0.05 = 4,912MB context
        #   Total: 24,564MB - 720MB - 4,912MB - 2,900MB (system) = 16,032MB model
        #   File: 17,613MB → Empirical multiplier: 16,032/17,613 = 0.91x
        # Using 0.91x (live calibrated) to target ~500MB free VRAM
        vram_multiplier = 0.91
        model_size_mb = model_size_gb * 1024 * vram_multiplier

        # KoboldCPP allocates all VRAM upfront (no lazy loading)
        # Safety margin: CUBLAS scratch buffer + driver overhead
        # Formula: batch_size × (512 kB + n_ctx × 128 B) = CUBLAS scratch
        # At 512 batch: ~150MB minimum for CUBLAS
        # Empirical target: 400-500MB free VRAM for stability
        # Using 150MB safety margin to maximize context, target ~500MB free after cache calibration
        safety_margin_mb = 150  # Very aggressive: targets 500MB free, cache will calibrate down if needed

        # PRE-CHECK: Calculate VRAM requirements for RoPE and Native
        # Skip attempts that would definitely OOM
        attempt_to_try = None  # Will be "rope", "native", or "vram_calc"

        if native_context:
            from aifred.lib.config import KOBOLDCPP_ROPE_SCALING_FACTOR
            rope_extended_context = int(native_context * KOBOLDCPP_ROPE_SCALING_FACTOR)

            # Calculate available VRAM for context
            # free_vram_mb is measured BEFORE loading model, so we must subtract:
            # 1. Model weights (model_size_mb)
            # 2. Safety margin for CUBLAS scratch buffer
            available_for_context_mb = free_vram_mb - model_size_mb - safety_margin_mb

            # Check RoPE first (highest context)
            rope_context_vram_needed = rope_extended_context * mb_per_token
            if rope_context_vram_needed <= available_for_context_mb:
                attempt_to_try = "rope"
                log_feedback(f"✅ VRAM Pre-check: RoPE-extended fits in VRAM")
                log_feedback(f"   Context needs {rope_context_vram_needed:.0f}MB ≤ {available_for_context_mb:.0f}MB available")
                log_feedback(f"   (Free: {free_vram_mb:,}MB - Model: {model_size_mb:.0f}MB - Safety: {safety_margin_mb}MB)")
            else:
                # RoPE doesn't fit, check Native
                native_context_vram_needed = native_context * mb_per_token
                if native_context_vram_needed <= available_for_context_mb:
                    attempt_to_try = "native"
                    log_feedback(f"⚠️ VRAM Pre-check: RoPE too large ({rope_context_vram_needed:.0f}MB), trying Native")
                    log_feedback(f"   Native context needs {native_context_vram_needed:.0f}MB ≤ {available_for_context_mb:.0f}MB available")
                else:
                    log_feedback(f"⚠️ VRAM Pre-check: Both RoPE and Native too large")
                    log_feedback(f"   RoPE needs: {rope_context_vram_needed:.0f}MB, Native needs: {native_context_vram_needed:.0f}MB")
                    log_feedback(f"   Available for context: {available_for_context_mb:.0f}MB (Free: {free_vram_mb:,}MB - Model: {model_size_mb:.0f}MB - Safety: {safety_margin_mb}MB)")
                    log_feedback(f"   Skipping to VRAM-calculated context")

        # ATTEMPT 1: Try RoPE (if pre-check passed)
        if attempt_to_try == "rope":
            log_feedback(f"🚀 Attempt 1: Starting with RoPE-extended context")
            log_feedback(f"   Native: {native_context:,} tokens × {KOBOLDCPP_ROPE_SCALING_FACTOR} = {rope_extended_context:,} tokens")

            try:
                success = await self.start(
                    model_path=model_path,
                    context_size=rope_extended_context,
                    gpu_layers=config["gpu_layers"],
                    context_offload=config["context_offload"],
                    tensor_split=config["tensor_split"],
                    flash_attention=config["flash_attention"],
                    quantized_kv=config["quantized_kv"],
                    timeout=timeout
                )

                if success:
                    log_feedback("✅ Calibration succeeded!")
                    log_feedback(f"   KoboldCPP started with {rope_extended_context:,} tokens (VRAM sufficient for RoPE extension)")

                    # Update cache with RoPE-extended value
                    add_koboldcpp_calibration(
                        model_id=model_name,
                        free_vram_mb=free_vram_mb,
                        max_context=rope_extended_context,
                        quantization=quantization,
                        gpu_model=gpu_model,
                        model_size_gb=model_size_gb
                    )
                    log_feedback(f"💾 Cached calibration point: {free_vram_mb:,}MB → {rope_extended_context:,} tokens")

                    return (True, {
                        "model_size_gb": model_size_gb,
                        "context_size": rope_extended_context,
                        "gpu_config": gpu_config["description"],
                        "quantization": quantization,
                        "native_context": native_context,
                        "calibrated": True
                    })

            except Exception as e:
                from aifred.lib.koboldcpp_utils import is_koboldcpp_oom_error

                error_msg = str(e)
                stderr_output = ""
                if hasattr(self, 'stderr_buffer') and self.stderr_buffer:
                    stderr_output = "".join(self.stderr_buffer[-50:])

                if is_koboldcpp_oom_error(error_msg + "\n" + stderr_output):
                    log_feedback(f"⚠️ RoPE-extended context ({rope_extended_context:,} tokens) caused OOM despite pre-check")
                    log_feedback("   Pre-check estimation was incorrect - falling back to VRAM calculation...")
                else:
                    log_feedback(f"⚠️ Attempt 1 failed (non-OOM): {str(e)[:100]}")

                # Cleanup
                await self.stop()
                await asyncio.sleep(2)
                # Fall through to VRAM-calculated context

        # ATTEMPT 2: Try Native (if pre-check passed and RoPE didn't fit)
        elif attempt_to_try == "native":
            log_feedback(f"🚀 Attempt 2: Starting with native context (no RoPE)")
            log_feedback(f"   Trying: {native_context:,} tokens (architectural limit)")

            try:
                success = await self.start(
                    model_path=model_path,
                    context_size=native_context,
                    gpu_layers=config["gpu_layers"],
                    context_offload=config["context_offload"],
                    tensor_split=config["tensor_split"],
                    flash_attention=config["flash_attention"],
                    quantized_kv=config["quantized_kv"],
                    timeout=timeout
                )

                if success:
                    log_feedback("✅ Calibration succeeded!")
                    log_feedback(f"   KoboldCPP started with {native_context:,} tokens (native context without RoPE)")

                    # Update cache
                    add_koboldcpp_calibration(
                        model_id=model_name,
                        free_vram_mb=free_vram_mb,
                        max_context=native_context,
                        quantization=quantization,
                        gpu_model=gpu_model,
                        model_size_gb=model_size_gb
                    )
                    log_feedback(f"💾 Cached calibration point: {free_vram_mb:,}MB → {native_context:,} tokens")

                    return (True, {
                        "model_size_gb": model_size_gb,
                        "context_size": native_context,
                        "gpu_config": gpu_config["description"],
                        "quantization": quantization,
                        "native_context": native_context,
                        "calibrated": True
                    })

            except Exception as e:
                from aifred.lib.koboldcpp_utils import is_koboldcpp_oom_error

                error_msg = str(e)
                stderr_output = ""
                if hasattr(self, 'stderr_buffer') and self.stderr_buffer:
                    stderr_output = "".join(self.stderr_buffer[-50:])

                if is_koboldcpp_oom_error(error_msg + "\n" + stderr_output):
                    log_feedback(f"⚠️ Native context ({native_context:,} tokens) caused OOM despite pre-check")
                    log_feedback("   Pre-check estimation was incorrect - falling back to VRAM calculation...")
                else:
                    log_feedback(f"⚠️ Attempt 2 failed (non-OOM): {str(e)[:100]}")

                # Cleanup
                await self.stop()
                await asyncio.sleep(2)
                # Fall through to VRAM-calculated context

        # ATTEMPT 3: Calculate context from available VRAM (pre-check failed or no native context)
        log_feedback("🚀 Attempt 3: Calculating context from available VRAM...")

        # free_vram_mb is measured BEFORE model load
        # So subtract model weights + safety margin to get available VRAM for context
        available_context_vram_mb = free_vram_mb - model_size_mb - safety_margin_mb
        vram_calculated_context = int(available_context_vram_mb / mb_per_token)
        vram_calculated_context = max(1024, vram_calculated_context)  # Minimum 1K

        log_feedback(f"   Calculated context: {vram_calculated_context:,} tokens")
        log_feedback(f"   ({available_context_vram_mb:.0f}MB available / {mb_per_token} MB/token)")
        log_feedback(f"   (Free: {free_vram_mb:,}MB - Model: {model_size_mb:.0f}MB - Safety: {safety_margin_mb}MB)")

        try:
            success = await self.start(
                model_path=model_path,
                context_size=vram_calculated_context,
                gpu_layers=config["gpu_layers"],
                context_offload=config["context_offload"],
                tensor_split=config["tensor_split"],
                flash_attention=config["flash_attention"],
                quantized_kv=config["quantized_kv"],
                timeout=timeout
            )

            if success:
                log_feedback("✅ Calibration succeeded!")
                log_feedback(f"   KoboldCPP started with {vram_calculated_context:,} tokens")

                # Update cache
                add_koboldcpp_calibration(
                    model_id=model_name,
                    free_vram_mb=free_vram_mb,
                    max_context=vram_calculated_context,
                    quantization=quantization,
                    gpu_model=gpu_model,
                    model_size_gb=model_size_gb
                )
                log_feedback(f"💾 Cached calibration point: {free_vram_mb:,}MB → {vram_calculated_context:,} tokens")

                return (True, {
                    "model_size_gb": model_size_gb,
                    "context_size": vram_calculated_context,
                    "gpu_config": gpu_config["description"],
                    "quantization": quantization,
                    "native_context": native_context,
                    "calibrated": True
                })

        except Exception as e:
            from aifred.lib.koboldcpp_utils import is_koboldcpp_oom_error

            error_msg = str(e)
            stderr_output = ""
            if hasattr(self, 'stderr_buffer') and self.stderr_buffer:
                stderr_output = "".join(self.stderr_buffer[-50:])

            if is_koboldcpp_oom_error(error_msg + "\n" + stderr_output):
                log_feedback(f"⚠️ VRAM-calculated context ({vram_calculated_context:,} tokens) caused OOM")
                log_feedback("   Applying fixed safety buffer for final attempt...")
            else:
                log_feedback(f"⚠️ Attempt 3 failed (non-OOM): {str(e)[:100]}")

            # Cleanup
            await self.stop()
            await asyncio.sleep(2)
            # Fall through to ATTEMPT 4

        # ATTEMPT 4: Apply fixed safety buffer
        reduced_context = max(1024, vram_calculated_context - KOBOLDCPP_CONTEXT_SAFETY_TOKENS)
        log_feedback("🚀 Attempt 4: Reduced context with safety buffer")
        log_feedback(f"   {vram_calculated_context:,} - {KOBOLDCPP_CONTEXT_SAFETY_TOKENS:,} = {reduced_context:,} tokens")

        try:
            success = await self.start(
                model_path=model_path,
                context_size=reduced_context,
                gpu_layers=config["gpu_layers"],
                context_offload=config["context_offload"],
                tensor_split=config["tensor_split"],
                flash_attention=config["flash_attention"],
                quantized_kv=config["quantized_kv"],
                timeout=timeout
            )

            if success:
                log_feedback("✅ Calibration succeeded with safety buffer!")
                log_feedback(f"   KoboldCPP started with {reduced_context:,} tokens")

                # Update cache
                add_koboldcpp_calibration(
                    model_id=model_name,
                    free_vram_mb=free_vram_mb,
                    max_context=reduced_context,
                    quantization=quantization,
                    gpu_model=gpu_model,
                    model_size_gb=model_size_gb
                )
                log_feedback(f"💾 Cached calibration point: {free_vram_mb:,}MB → {reduced_context:,} tokens")

                return (True, {
                    "model_size_gb": model_size_gb,
                    "context_size": reduced_context,
                    "gpu_config": gpu_config["description"],
                    "quantization": quantization,
                    "native_context": native_context,
                    "calibrated": True,
                    "reduced": True
                })
            else:
                log_feedback("❌ Calibration failed even with safety buffer")
                return (False, None)

        except Exception as e:
            log_feedback(f"❌ All attempts failed: {str(e)[:200]}")
            return (False, None)

    async def start_with_auto_config(
        self,
        model_path: str,
        timeout: int = 60
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Start KoboldCPP server with automatic GPU-optimized configuration

        Uses dynamic VRAM-based context calculation like vLLM (no hardcoded caps).

        Automatically detects:
        - GPU config (RTX/Dual P40/AMD)
        - Model size from GGUF file
        - Free VRAM available
        - Optimal context size based on VRAM (dynamically calculated)
        - GPU layers to offload

        Args:
            model_path: Path to GGUF model file
            timeout: Seconds to wait for server ready

        Returns:
            (success: bool, config: Dict with used settings)
        """
        from aifred.lib.gpu_utils import detect_koboldcpp_gpu_config
        from aifred.lib.gguf_utils import extract_quantization_from_filename
        from pathlib import Path

        # Get GPU configuration
        gpu_config = detect_koboldcpp_gpu_config()
        logger.info(f"🎮 Detected GPU Config: {gpu_config['description']}")

        # Get model info
        model_file = Path(model_path)
        if not model_file.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        model_size_gb = model_file.stat().st_size / (1024**3)
        logger.info(f"📦 Model Size: {model_size_gb:.1f}GB")

        # Extract quantization from filename
        quantization = extract_quantization_from_filename(model_file.name)
        logger.info(f"🔢 Quantization: {quantization}")

        # Determine MB/token based on quantization (same as gguf_utils.py)
        mb_per_token_map = {
            "Q4": 0.15,
            "Q5": 0.18,
            "Q8": 0.30,
            "IQ4": 0.15,
            "IQ3": 0.12,
        }

        mb_per_token = 0.15  # Default Q4
        for key in mb_per_token_map.keys():
            if key in quantization:
                mb_per_token = mb_per_token_map[key]
                break

        logger.info(f"💾 Context VRAM estimate: {mb_per_token} MB/token")

        # Extract configuration from GPU detection
        config = gpu_config["config"]

        # Calculate optimal context size DYNAMICALLY (like vLLM)
        # NO hardcoded caps! Calculate based on available VRAM.
        if gpu_config["type"] == "dual_p40":
            # Dual P40: Context on GPU1
            # GPU0: Model weights (all layers)
            # GPU1: Context cache (full 24GB available)

            # Get free VRAM on GPU1 (secondary GPU)
            try:
                import pynvml
                pynvml.nvmlInit()
                handle_gpu1 = pynvml.nvmlDeviceGetHandleByIndex(1)  # GPU1 for context
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle_gpu1)
                free_vram_mb = mem_info.free / (1024 * 1024)
                total_vram_mb = mem_info.total / (1024 * 1024)
                pynvml.nvmlShutdown()
                logger.info(f"📊 GPU1 VRAM: {total_vram_mb:.0f}MB total, {free_vram_mb:.0f}MB free")
            except Exception as e:
                logger.warning(f"Could not query GPU1 VRAM: {e}, using conservative estimate")
                free_vram_mb = 20480  # 20GB conservative

            # Safety margin for KoboldCPP overhead
            safety_margin_mb = 2048  # 2GB safety
            available_context_vram_mb = free_vram_mb - safety_margin_mb

            # Calculate max context dynamically
            max_context = int(available_context_vram_mb / mb_per_token)
            context_size = max_context  # NO CAP! Use full available VRAM

            logger.info(f"🎯 Dual P40 Config: {available_context_vram_mb:.0f}MB available → {context_size:,} tokens")

        elif gpu_config["type"] == "rtx":
            # Single GPU: Share VRAM between model and context
            try:
                import pynvml
                pynvml.nvmlInit()
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                free_vram_mb = mem_info.free / (1024 * 1024)
                total_vram_mb = mem_info.total / (1024 * 1024)
                pynvml.nvmlShutdown()
                logger.info(f"📊 GPU VRAM: {total_vram_mb:.0f}MB total, {free_vram_mb:.0f}MB free")
            except Exception as e:
                logger.warning(f"Could not query GPU VRAM: {e}, using conservative estimate")
                free_vram_mb = 20480  # 20GB conservative

            # Model size + safety margin
            model_size_mb = model_size_gb * 1024
            safety_margin_mb = 2048  # 2GB safety

            # Available for context
            available_context_vram_mb = free_vram_mb - model_size_mb - safety_margin_mb

            # Calculate max context dynamically
            max_context = int(available_context_vram_mb / mb_per_token)
            context_size = max(1024, max_context)  # Minimum 1K tokens

            logger.info(f"🎯 RTX Config: {available_context_vram_mb:.0f}MB available → {context_size:,} tokens")

        elif gpu_config["type"] == "amd_rocm":
            # AMD: Conservative estimate (no pynvml support)
            # Use reasonable default based on typical 16-24GB AMD GPUs
            context_size = 32768  # 32K conservative default
            logger.info(f"🎯 AMD ROCm Config: Using conservative {context_size:,} tokens")

        else:
            # CPU fallback
            context_size = 8192  # 8K minimal
            logger.info(f"🎯 CPU Config: Using minimal {context_size:,} tokens")

        logger.info(f"✅ Final Context Size: {context_size:,} tokens (dynamically calculated)")

        # Start server with calculated config
        success = await self.start(
            model_path=model_path,
            context_size=context_size,
            gpu_layers=config["gpu_layers"],
            context_offload=config["context_offload"],
            tensor_split=config["tensor_split"],
            flash_attention=config["flash_attention"],
            quantized_kv=config["quantized_kv"],
            timeout=timeout
        )

        return success, {
            "gpu_config": gpu_config["description"],
            "model_size_gb": model_size_gb,
            "context_size": context_size,
            "gpu_layers": config["gpu_layers"],
            "context_offload": config["context_offload"],
            "tensor_split": config["tensor_split"],
            "flash_attention": config["flash_attention"],
            "quantized_kv": config["quantized_kv"],
        }

    def __del__(self):
        """Cleanup: Stop server on destruction"""
        if self.is_running():
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                pass


# Singleton instance for global access
_koboldcpp_manager: Optional[KoboldCPPProcessManager] = None


def get_koboldcpp_manager(port: int = 5001) -> KoboldCPPProcessManager:
    """
    Get singleton KoboldCPP manager instance

    Args:
        port: Port for KoboldCPP server (default: 5001)

    Returns:
        KoboldCPPProcessManager instance
    """
    global _koboldcpp_manager

    if _koboldcpp_manager is None:
        _koboldcpp_manager = KoboldCPPProcessManager(port=port)

    return _koboldcpp_manager
