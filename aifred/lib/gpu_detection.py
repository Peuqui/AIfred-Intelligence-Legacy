"""
GPU Detection and Compatibility Checking

Detects GPU compute capability and provides backend compatibility info.
Prevents users from trying to use incompatible backends with their GPU.
"""

from typing import Optional, List, Dict, Any, TypedDict
from dataclasses import dataclass, field
from . import nvidia_smi


class GPUDict(TypedDict):
    """Type for parsed GPU info from nvidia-smi"""
    name: str
    vram_mb: int
    compute_cap: float


class BackendRequirement(TypedDict):
    """Type for backend requirements"""
    min_compute_capability: float
    requires_tensor_cores: bool
    requires_fast_fp16: bool
    description: str


class KnownIssue(TypedDict):
    """Type for known GPU issues"""
    fp16_ratio: str
    issue: str
    recommendation: str


@dataclass
class GPUInfo:
    """GPU information and capabilities"""
    name: str
    compute_capability: float
    vram_mb: int
    has_tensor_cores: bool
    supports_fast_fp16: bool
    recommended_backends: List[str]
    unsupported_backends: List[str]
    warnings: List[str]
    # Multi-GPU info
    gpu_count: int = 1
    total_vram_mb: int = 0
    all_gpu_names: List[str] = field(default_factory=list)
    all_gpu_vram_mb: List[int] = field(default_factory=list)


class GPUDetector:
    """
    Detect GPU capabilities and provide backend compatibility information

    Usage:
        detector = GPUDetector()
        gpu_info = detector.detect()
        if gpu_info:
            print(f"GPU: {gpu_info.name}")
            print(f"Compute Capability: {gpu_info.compute_capability}")
            print(f"Recommended Backends: {gpu_info.recommended_backends}")
    """

    # Compute Capability → Architecture mapping
    ARCH_MAP = {
        (3, 0): "Kepler",
        (3, 5): "Kepler",
        (5, 0): "Maxwell",
        (5, 2): "Maxwell",
        (6, 0): "Pascal",
        (6, 1): "Pascal",  # Tesla P40, P100
        (7, 0): "Volta",   # V100
        (7, 5): "Turing",  # RTX 2080, T4
        (8, 0): "Ampere",  # A100
        (8, 6): "Ampere",  # RTX 3090, A40
        (8, 9): "Ada Lovelace",  # RTX 4090
        (9, 0): "Hopper",  # H100
    }

    # Backend requirements
    BACKEND_REQUIREMENTS: Dict[str, BackendRequirement] = {
        "ollama": {
            "min_compute_capability": 3.5,
            "requires_tensor_cores": False,
            "requires_fast_fp16": False,
            "description": "GGUF models (INT8/Q4/Q8), universal compatibility"
        },
        "llamacpp": {
            "min_compute_capability": 3.5,
            "requires_tensor_cores": False,
            "requires_fast_fp16": False,
            "description": "llama.cpp + llama-swap (GGUF), universal compatibility"
        },
        "vllm": {
            "min_compute_capability": 7.0,
            "requires_tensor_cores": False,
            "requires_fast_fp16": True,
            "description": "AWQ/GPTQ models, requires Volta+ (7.0+)"
        },
        "tabbyapi": {
            "min_compute_capability": 7.0,
            "requires_tensor_cores": False,
            "requires_fast_fp16": True,
            "description": "ExLlamaV2/V3 (EXL2), requires fast FP16"
        }
    }

    # Known problematic GPUs
    KNOWN_ISSUES: Dict[str, Dict[str, Any]] = {
        "Tesla P40": {
            "fp16_ratio": "1:64",
            "issue": "Extremely slow FP16 performance",
            "recommendation": "Use Ollama or llama.cpp (GGUF) only"
        },
        "Tesla P100": {
            "fp16_ratio": "1:2",
            "issue": "Moderate FP16 performance",
            "recommendation": "Ollama/llama.cpp recommended, vLLM possible but slower"
        },
        "Tesla K80": {
            "compute_capability": 3.7,
            "issue": "Too old for modern inference frameworks",
            "recommendation": "Upgrade GPU"
        }
    }

    def __init__(self):
        self.gpu_info: Optional[GPUInfo] = None

    def detect(self) -> Optional[GPUInfo]:
        """
        Detect GPU and return GPUInfo

        For multi-GPU systems, detects the GPU with the LOWEST compute capability
        to ensure backend compatibility across all GPUs.

        Returns:
            GPUInfo if GPU detected, None otherwise
        """
        try:
            rows = nvidia_smi.query("name,memory.total,compute_cap")
            if not rows:
                return None

            # For multi-GPU: Find GPU with LOWEST compute capability
            # This ensures backend compatibility across all GPUs
            gpu_list: List[GPUDict] = []
            for row in rows:
                try:
                    gpu_list.append({
                        "name": row["name"],
                        "vram_mb": int(row["memory.total"]),
                        "compute_cap": float(row["compute_cap"])
                    })
                except (ValueError, KeyError):
                    continue

            if not gpu_list:
                return None

            # Sort by compute capability and take the lowest
            # (ensures backends work on ALL GPUs, not just the best one)
            gpu_list.sort(key=lambda x: x["compute_cap"])
            selected_gpu = gpu_list[0]

            gpu_name = selected_gpu["name"]
            vram_mb = selected_gpu["vram_mb"]
            compute_cap = selected_gpu["compute_cap"]
            gpu_count = len(gpu_list)
            total_vram_mb = sum(g["vram_mb"] for g in gpu_list)

            # Log multi-GPU detection
            if len(gpu_list) > 1:
                gpu_names = [f"{g['name']} ({g['compute_cap']})" for g in gpu_list]
                print(f"🎮 Multi-GPU detected: {', '.join(gpu_names)}")
                print(f"🎯 Using lowest compute capability: {gpu_name} ({compute_cap}) for compatibility check")

            # Determine capabilities
            has_tensor_cores = compute_cap >= 7.0
            supports_fast_fp16 = self._check_fast_fp16(gpu_name, compute_cap)

            # Determine backend compatibility
            recommended, unsupported, warnings = self._analyze_compatibility(
                gpu_name, compute_cap, has_tensor_cores, supports_fast_fp16
            )

            self.gpu_info = GPUInfo(
                name=gpu_name,
                compute_capability=compute_cap,
                vram_mb=vram_mb,
                has_tensor_cores=has_tensor_cores,
                supports_fast_fp16=supports_fast_fp16,
                recommended_backends=recommended,
                unsupported_backends=unsupported,
                warnings=warnings,
                gpu_count=gpu_count,
                total_vram_mb=total_vram_mb,
                all_gpu_names=[g["name"] for g in gpu_list],
                all_gpu_vram_mb=[g["vram_mb"] for g in gpu_list],
            )

            return self.gpu_info

        except (ValueError, KeyError):
            return None

    def _check_fast_fp16(self, gpu_name: str, compute_cap: float) -> bool:
        """
        Check if GPU has fast FP16 performance

        Pascal (6.x) has very slow FP16 (1:64 ratio for later Pascal like P40)
        Volta+ (7.0+) has fast FP16
        """
        # Known slow FP16 GPUs
        if "P40" in gpu_name or "P4" in gpu_name:
            return False

        # Pascal generation (6.x) generally has slow FP16
        if 6.0 <= compute_cap < 7.0:
            # P100 is exception (6.0) - has decent FP16
            if "P100" in gpu_name:
                return True
            return False

        # Volta+ (7.0+) has fast FP16
        return compute_cap >= 7.0

    def _analyze_compatibility(
        self,
        gpu_name: str,
        compute_cap: float,
        has_tensor_cores: bool,
        supports_fast_fp16: bool
    ) -> tuple[List[str], List[str], List[str]]:
        """
        Analyze which backends are compatible

        Returns:
            (recommended_backends, unsupported_backends, warnings)
        """
        recommended = []
        unsupported = []
        warnings = []

        # Check each backend
        for backend, reqs in self.BACKEND_REQUIREMENTS.items():
            min_cap = reqs["min_compute_capability"]
            needs_tc = reqs["requires_tensor_cores"]
            needs_fp16 = reqs["requires_fast_fp16"]

            # Check requirements
            cap_ok = compute_cap >= min_cap
            tc_ok = not needs_tc or has_tensor_cores
            fp16_ok = not needs_fp16 or supports_fast_fp16

            if cap_ok and tc_ok and fp16_ok:
                recommended.append(backend)
            else:
                unsupported.append(backend)

                # Generate specific warning
                reasons = []
                if not cap_ok:
                    reasons.append(f"requires compute capability {min_cap}+ (you have {compute_cap})")
                if not tc_ok:
                    reasons.append("requires Tensor Cores")
                if not fp16_ok:
                    reasons.append("requires fast FP16 (your GPU has slow FP16)")

                warning = f"{backend}: " + ", ".join(reasons)
                warnings.append(warning)

        # Add known issue warnings
        for known_gpu, issue_info in self.KNOWN_ISSUES.items():
            if known_gpu in gpu_name:
                warnings.append(f"{gpu_name}: {str(issue_info['issue'])}")
                warnings.append(f"Recommendation: {str(issue_info['recommendation'])}")

        return recommended, unsupported, warnings

    def is_backend_compatible(self, backend: str) -> bool:
        """
        Check if a specific backend is compatible

        Args:
            backend: "ollama", "vllm", "tabbyapi"

        Returns:
            True if compatible, False otherwise
        """
        if not self.gpu_info:
            self.detect()

        if not self.gpu_info:
            # No GPU detected or detection failed - allow all backends
            return True

        return backend.lower() in self.gpu_info.recommended_backends

    def get_compatibility_message(self, backend: str) -> Optional[str]:
        """
        Get user-friendly compatibility message for a backend

        Args:
            backend: "ollama", "vllm", "tabbyapi"

        Returns:
            Warning message if incompatible, None if compatible
        """
        if not self.gpu_info:
            self.detect()

        if not self.gpu_info:
            return None

        backend = backend.lower()

        if backend in self.gpu_info.unsupported_backends:
            # Find relevant warning
            for warning in self.gpu_info.warnings:
                if warning.startswith(f"{backend}:"):
                    return warning

            # Generic warning
            reqs: BackendRequirement | None = self.BACKEND_REQUIREMENTS.get(backend)
            desc = reqs.get('description', '') if reqs else ''
            return (
                f"⚠️ {backend} may not work properly on {self.gpu_info.name}\n"
                f"   (Compute Capability: {self.gpu_info.compute_capability})\n"
                f"   {desc}"
            )

        return None


# Global instance
_detector = GPUDetector()


def detect_gpu() -> Optional[GPUInfo]:
    """Convenience function to detect GPU"""
    return _detector.detect()


def is_backend_compatible(backend: str) -> bool:
    """Convenience function to check backend compatibility"""
    return _detector.is_backend_compatible(backend)


def get_compatibility_message(backend: str) -> Optional[str]:
    """Convenience function to get compatibility message"""
    return _detector.get_compatibility_message(backend)
