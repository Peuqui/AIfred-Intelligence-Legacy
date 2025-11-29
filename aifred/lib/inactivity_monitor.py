"""
Inactivity Monitor for KoboldCPP Auto-Shutdown

Monitors GPU utilization and automatically shuts down KoboldCPP server
after GPUs are idle for a configurable period to save power (~100W idle).

Features:
- GPU utilization monitoring via nvidia-smi
- Background monitoring via asyncio
- Configurable timeout and check interval
- Graceful shutdown using existing Manager API
- No false positives during active inference

Usage:
    monitor = InactivityMonitor(
        manager=koboldcpp_manager,
        timeout_seconds=30,    # Shutdown after 30s of GPU idle
        check_interval=10      # Check GPU every 10 seconds
    )
    await monitor.start_monitoring()

    # Monitor automatically tracks GPU activity
    # No manual record_activity() calls needed!

    # Stop monitoring when done
    await monitor.stop_monitoring()
"""

import asyncio
import subprocess
from typing import Optional, TYPE_CHECKING, List
from aifred.lib.logging_utils import log_message

# Avoid circular imports
if TYPE_CHECKING:
    from aifred.lib.koboldcpp_manager import KoboldCPPProcessManager


class InactivityMonitor:
    """
    Monitors GPU activity and auto-shutdowns KoboldCPP after idle period

    Uses nvidia-smi to check GPU utilization. If ALL GPUs are at 0% for
    the configured timeout period, triggers graceful shutdown.

    This approach eliminates race conditions from timestamp-based tracking
    and correctly handles long-running inference requests.

    Thread-Safety:
        - Uses asyncio (single-threaded execution model)
        - subprocess calls are blocking but run in event loop
        - No threading primitives needed

    No Side Effects:
        - Only calls public Manager APIs (stop(), is_running())
        - Does not modify global state directly
        - Read-only GPU monitoring via nvidia-smi
    """

    def __init__(
        self,
        manager: "KoboldCPPProcessManager",
        timeout_seconds: int = 30,    # 30 seconds for testing (1800 for production)
        check_interval: int = 10      # Check every 10 seconds
    ):
        """
        Initialize GPU-based Inactivity Monitor

        Args:
            manager: KoboldCPPProcessManager instance to monitor
            timeout_seconds: Seconds of GPU idle (0% util) before auto-shutdown
            check_interval: Seconds between GPU utilization checks
        """
        self._manager = manager
        self._timeout = timeout_seconds
        self._check_interval = check_interval

        # GPU idle tracking
        self._idle_checks_needed = max(1, timeout_seconds // check_interval)
        self._consecutive_idle_checks = 0

        # Monitoring state
        self._enabled = False
        self._monitor_task: Optional[asyncio.Task] = None

        # Statistics
        self._total_checks = 0
        self._total_idle_checks = 0
        self._total_active_checks = 0

        log_message(
            f"InactivityMonitor initialized: timeout={timeout_seconds}s "
            f"({self._idle_checks_needed} consecutive checks), interval={check_interval}s"
        )

    def _get_gpu_utilization(self) -> Optional[List[int]]:
        """
        Get current GPU utilization for all GPUs

        Returns:
            List of GPU utilization percentages (0-100) for each GPU
            None if nvidia-smi fails

        Example:
            [0, 0]     # Both GPUs idle
            [95, 92]   # Both GPUs active
            [5, 0]     # GPU 0 has residual activity, GPU 1 idle
        """
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=True
            )

            # Parse output: "0\n0\n" -> [0, 0]
            lines = result.stdout.strip().split('\n')
            utilizations = [int(line.strip()) for line in lines if line.strip()]

            return utilizations

        except subprocess.TimeoutExpired:
            log_message("⚠️ nvidia-smi timeout (5s) - GPU may be unresponsive")
            return None
        except subprocess.CalledProcessError as e:
            log_message(f"❌ nvidia-smi failed: {e}")
            return None
        except (ValueError, IndexError) as e:
            log_message(f"❌ Failed to parse nvidia-smi output: {e}")
            return None

    def _are_all_gpus_idle(self) -> bool:
        """
        Check if ALL GPUs are completely idle (0% utilization)

        Returns:
            True if all GPUs at 0%, False if any GPU active or check failed
        """
        utils = self._get_gpu_utilization()

        if utils is None:
            # nvidia-smi failed - assume active to prevent false shutdown
            return False

        all_idle = all(u == 0 for u in utils)

        return all_idle

    def is_monitoring(self) -> bool:
        """Check if monitoring is currently active"""
        return self._enabled and self._monitor_task is not None

    async def start_monitoring(self) -> None:
        """
        Start background GPU monitoring task

        Spawns an asyncio task that runs the monitoring loop.
        Safe to call multiple times (will not create duplicate tasks).

        The monitoring task will:
        1. Check GPU utilization every `check_interval` seconds
        2. Count consecutive idle checks (all GPUs at 0%)
        3. Shutdown server if idle count >= required threshold
        4. Reset counter if any GPU shows activity
        """
        if self.is_monitoring():
            return

        self._enabled = True
        self._consecutive_idle_checks = 0

        # Create background task
        self._monitor_task = asyncio.create_task(self._monitor_loop())

        log_message(f"🔍 GPU-basiertes Inactivity-Monitoring gestartet (timeout: {self._timeout}s)")

    async def stop_monitoring(self) -> None:
        """
        Stop background monitoring task

        Gracefully cancels the monitoring task.
        Safe to call even if monitoring is not active.
        """
        if not self.is_monitoring():
            return

        self._enabled = False

        # Cancel the monitoring task
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass  # Expected
            self._monitor_task = None

        log_message("⏸️ GPU-Monitoring gestoppt")

    async def _monitor_loop(self) -> None:
        """
        Background GPU monitoring loop (runs in asyncio task)

        This is the core monitoring logic that runs periodically.

        Logic:
        1. Check if server is running (skip if not)
        2. Check GPU utilization via nvidia-smi
        3. If ALL GPUs idle (0%):
           - Increment consecutive_idle_checks counter
           - If counter >= threshold → SHUTDOWN
        4. If ANY GPU active (>0%):
           - Reset counter to 0

        Safety:
        - Wrapped in try/except to handle cancellation
        - Uses existing Manager API (no direct process manipulation)
        - False positive prevention: nvidia-smi failures count as "active"
        """
        try:
            while self._enabled:
                # Sleep first (give server time to process requests)
                await asyncio.sleep(self._check_interval)

                self._total_checks += 1

                # Check if server is even running
                if not self._manager.is_running():
                    continue

                # Check GPU utilization
                all_gpus_idle = self._are_all_gpus_idle()

                if all_gpus_idle:
                    self._consecutive_idle_checks += 1
                    self._total_idle_checks += 1

                    # Check if shutdown threshold reached
                    if self._consecutive_idle_checks >= self._idle_checks_needed:
                        idle_duration = self._consecutive_idle_checks * self._check_interval

                        # Send shutdown message to both log file and debug console
                        log_message(f"🛑 KoboldCPP wird wegen Inaktivität heruntergefahren (GPUs waren {idle_duration}s idle, Timeout: {self._timeout}s)")

                        # Graceful shutdown using Manager API
                        try:
                            await self._manager.stop()
                            log_message("✅ KoboldCPP erfolgreich heruntergefahren")
                        except Exception as e:
                            log_message(f"❌ Auto-Shutdown fehlgeschlagen: {e}")

                        # Stop monitoring after shutdown (will restart when server restarts)
                        self._enabled = False
                        break

                else:
                    # At least one GPU is active - reset idle counter
                    self._consecutive_idle_checks = 0
                    self._total_active_checks += 1

        except asyncio.CancelledError:
            raise
        except Exception as e:
            log_message(f"❌ GPU monitoring loop error: {e}")

    def get_stats(self) -> dict:
        """
        Get monitoring statistics

        Returns:
            Dict with monitoring stats (for debugging/metrics)
        """
        return {
            "enabled": self._enabled,
            "monitoring": self.is_monitoring(),
            "timeout_seconds": self._timeout,
            "check_interval": self._check_interval,
            "idle_checks_needed": self._idle_checks_needed,
            "consecutive_idle_checks": self._consecutive_idle_checks,
            "total_checks": self._total_checks,
            "total_idle_checks": self._total_idle_checks,
            "total_active_checks": self._total_active_checks,
            "current_gpu_utilization": self._get_gpu_utilization()
        }

    def __repr__(self) -> str:
        """String representation for debugging"""
        status = "active" if self.is_monitoring() else "inactive"
        idle_progress = f"{self._consecutive_idle_checks}/{self._idle_checks_needed}"
        return (
            f"InactivityMonitor(status={status}, "
            f"idle_checks={idle_progress}, timeout={self._timeout}s)"
        )
