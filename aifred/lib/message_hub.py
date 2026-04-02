"""Message Hub — Background worker management for channel listeners.

Manages the lifecycle of channel workers (IMAP listener, Discord bot, etc.).
Workers are registered as async coroutines and run as asyncio tasks.
Started during global init (on_load) to survive Granian worker respawns.

Workers auto-restart on crash with exponential backoff (max 5 retries).
"""

import asyncio
import sys
from dataclasses import dataclass
from typing import Callable, Coroutine

from .logging_utils import log_message


def _hub_log(msg: str, level: str = "info") -> None:
    """Log to both debug-log file AND stdout (→ journalctl)."""
    log_message(msg, level)
    print(f"[MessageHub] {msg}", file=sys.stderr, flush=True)

# Auto-restart limits
_MAX_RESTART_ATTEMPTS = 5
_INITIAL_BACKOFF_SECONDS = 5
_MAX_BACKOFF_SECONDS = 300  # 5 minutes


@dataclass
class _Worker:
    """Internal bookkeeping for a registered worker."""

    name: str
    factory: Callable[[], Coroutine]  # async def that runs until cancelled
    task: asyncio.Task | None = None
    restart_count: int = 0


class MessageHub:
    """Central registry and lifecycle manager for channel workers."""

    def __init__(self) -> None:
        self._workers: dict[str, _Worker] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, name: str, factory: Callable[[], Coroutine]) -> None:
        """Register a worker coroutine factory.

        *factory* is called (without arguments) when the hub starts.
        The returned coroutine is wrapped in an asyncio.Task.
        The coroutine should run indefinitely and handle its own errors;
        it will be cancelled on shutdown.
        """
        if name in self._workers:
            _hub_log(f"Message Hub: worker '{name}' already registered, replacing", "warning")
        self._workers[name] = _Worker(name=name, factory=factory)
        _hub_log(f"Message Hub: registered worker '{name}'")

    def unregister(self, name: str) -> None:
        """Remove a worker (stops it first if running)."""
        worker = self._workers.pop(name, None)
        if worker and worker.task and not worker.task.done():
            worker.task.cancel()
            _hub_log(f"Message Hub: unregistered + cancelled worker '{name}'")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start_all(self) -> None:
        """Start all registered workers as background tasks."""
        for worker in self._workers.values():
            if worker.task and not worker.task.done():
                continue  # already running
            worker.task = asyncio.create_task(
                self._run_worker(worker),
                name=f"message_hub:{worker.name}",
            )
        started = [w.name for w in self._workers.values() if w.task]
        if started:
            _hub_log(f"Message Hub: started workers: {', '.join(started)}")
        else:
            _hub_log("Message Hub: no workers registered")

    async def stop_all(self) -> None:
        """Cancel all running worker tasks and wait for them to finish."""
        tasks_to_cancel: list[asyncio.Task] = []
        for worker in self._workers.values():
            if worker.task and not worker.task.done():
                worker.task.cancel()
                tasks_to_cancel.append(worker.task)
                _hub_log(f"Message Hub: cancelling worker '{worker.name}'")

        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
            _hub_log("Message Hub: all workers stopped")

        # Clear task references
        for worker in self._workers.values():
            worker.task = None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_running(self, name: str) -> bool:
        """Check whether a specific worker is currently running."""
        worker = self._workers.get(name)
        return worker is not None and worker.task is not None and not worker.task.done()

    def status(self) -> dict[str, bool]:
        """Return running status for all registered workers."""
        return {name: self.is_running(name) for name in self._workers}

    def health(self) -> dict[str, dict[str, object]]:
        """Return detailed health info for all workers."""
        return {
            name: {
                "running": self.is_running(name),
                "restart_count": w.restart_count,
            }
            for name, w in self._workers.items()
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run_worker(self, worker: _Worker) -> None:
        """Wrapper with auto-restart on crash (exponential backoff)."""
        while True:
            try:
                worker.restart_count = 0  # Reset on successful start
                await worker.factory()
                # factory returned normally — don't restart
                _hub_log(f"Message Hub: worker '{worker.name}' exited normally")
                return
            except asyncio.CancelledError:
                _hub_log(f"Message Hub: worker '{worker.name}' stopped")
                return
            except Exception as exc:
                worker.restart_count += 1
                if worker.restart_count > _MAX_RESTART_ATTEMPTS:
                    error_msg = (
                        f"CRITICAL: worker '{worker.name}' crashed {worker.restart_count} times, "
                        f"permanently dead. Last error: {exc}"
                    )
                    _hub_log(f"Message Hub: {error_msg}", "error")
                    # Write notification so the UI can show it
                    from .message_processor import write_hub_notification
                    write_hub_notification(
                        session_id="",
                        session_title=f"Worker '{worker.name}' crashed",
                        channel=worker.name,
                        sender="system",
                        status="error",
                    )
                    return

                backoff = min(
                    _INITIAL_BACKOFF_SECONDS * (2 ** (worker.restart_count - 1)),
                    _MAX_BACKOFF_SECONDS,
                )
                _hub_log(
                    f"Message Hub: worker '{worker.name}' crashed ({worker.restart_count}/{_MAX_RESTART_ATTEMPTS}): "
                    f"{exc} — restarting in {backoff}s",
                    "error",
                )
                await asyncio.sleep(backoff)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
message_hub = MessageHub()


def register_channel_workers(hub: MessageHub | None = None) -> None:
    """Register all configured channel listeners with the hub.

    Auto-discovers channel plugins and registers those that are
    both configured (credentials present) and enabled in settings.
    """
    hub = hub or message_hub

    from .settings import load_settings
    from .plugin_registry import all_channels

    settings = load_settings() or {}
    channel_toggles = settings.get("channel_toggles", {})

    for name, plugin in all_channels().items():
        if hub.is_running(name):
            continue  # already running, don't re-register
        toggles = channel_toggles.get(name, {})
        plugin_on = toggles.get("monitor", False)
        listener_on = plugin_on if plugin.always_reply else toggles.get("listener", False)
        if plugin.is_configured() and plugin_on and listener_on:
            hub.register(name, plugin.listener_loop)
        else:
            _hub_log(f"Message Hub: channel '{name}' skipped "
                     f"(configured={plugin.is_configured()}, enabled={plugin_on}, listener={listener_on})")
