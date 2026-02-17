"""
GGUF Model Discovery and Metadata Utilities

Finds GGUF models on the filesystem and extracts metadata
for llama.cpp backend integration.
"""

import struct
import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class GGUFModelInfo:
    """GGUF model metadata"""
    def __init__(
        self,
        path: Path,
        name: str,
        size_gb: float,
        quantization: str,
        native_context: Optional[int] = None,
        architecture: Optional[str] = None
    ):
        self.path = path
        self.name = name
        self.size_gb = size_gb
        self.quantization = quantization
        self.native_context = native_context
        self.architecture = architecture

    def __repr__(self):
        return f"GGUFModelInfo(name='{self.name}', size={self.size_gb:.1f}GB, quant={self.quantization})"


def is_gguf_file(file_path: Path) -> bool:
    """
    Check if file is GGUF format by reading magic bytes

    Args:
        file_path: Path to potential GGUF file

    Returns:
        True if file starts with 'GGUF' magic bytes
    """
    try:
        with open(file_path, 'rb') as f:
            magic = f.read(4)
            return magic == b'GGUF'
    except (IOError, OSError):
        return False


def get_gguf_layer_count(gguf_path: Path) -> Optional[int]:
    """
    Extract layer count (block_count) from GGUF model metadata.

    GGUF files store layer count as metadata keys like:
    - llama.block_count (Llama/Qwen models)
    - mistral.block_count (Mistral models)

    Args:
        gguf_path: Path to GGUF model file

    Returns:
        Number of transformer layers, or None if not found

    Example:
        >>> get_gguf_layer_count(Path("/models/qwen-30b-q4.gguf"))
        48
    """
    if not gguf_path.exists():
        logger.warning(f"GGUF file not found: {gguf_path}")
        return None

    try:
        import gguf

        with open(gguf_path, "rb") as f:
            try:
                reader = gguf.GGUFReader(f)

                # Try common architecture-specific keys
                layer_keys = [
                    'llama.block_count',        # Llama, Qwen, Yi
                    'mistral.block_count',      # Mistral
                    'gpt2.block_count',         # GPT2
                    'phi.block_count',          # Phi
                    'gemma.block_count',        # Gemma
                    'qwen2.block_count',        # Qwen2
                    'qwen3moe.block_count',     # Qwen3 MoE
                    'block_count',              # Generic fallback
                ]

                for field in reader.fields.values():
                    for key in layer_keys:
                        if field.name == key:
                            value_array = field.parts[-1]
                            layer_count = int(value_array[0]) if len(value_array) > 0 else None
                            if layer_count:
                                logger.info(f"✅ Layer count from GGUF metadata ({key}): {layer_count}")
                                return layer_count

                logger.warning("No block_count key found in GGUF metadata")
                return None

            except Exception as e:
                logger.error(f"Error parsing GGUF metadata: {e}")
                return None

    except ImportError:
        logger.warning("gguf-py library not installed")
        return None
    except Exception as e:
        logger.error(f"Error reading GGUF file {gguf_path}: {e}")
        return None


def get_gguf_native_context(gguf_path: Path) -> Optional[int]:
    """
    Extract native context length from GGUF model metadata using gguf-py library.

    GGUF files store native context as metadata keys like:
    - llama.context_length (Llama/Qwen models)
    - mistral.context_length (Mistral models)
    - gpt2.context_length (GPT2 models)

    Args:
        gguf_path: Path to GGUF model file

    Returns:
        Native context length in tokens, or None if not found

    Example:
        >>> get_gguf_native_context(Path("/models/qwen-7b-q4.gguf"))
        32768
    """
    if not gguf_path.exists():
        logger.warning(f"GGUF file not found: {gguf_path}")
        return None

    try:
        # Try importing gguf-py library
        import gguf

        with open(gguf_path, "rb") as f:
            try:
                # Load GGUF metadata
                reader = gguf.GGUFReader(f)

                # Search for ANY key that ends with 'context_length' or contains 'max_position_embeddings'
                # This is more robust than hardcoding all possible architecture names
                for field in reader.fields.values():
                    field_name = field.name.lower()

                    # Match patterns: *.context_length or *max_position_embeddings
                    if field_name.endswith('.context_length') or field_name == 'context_length' or \
                       'max_position_embeddings' in field_name:
                        try:
                            # Extract value from memmap array
                            # field.parts is a list where parts[-1] is a memmap with the actual value
                            # For uint32 values: parts[-1] is memmap([value], dtype=uint32)
                            value_array = field.parts[-1]
                            context = int(value_array[0]) if len(value_array) > 0 else None
                            if context and context > 0:
                                logger.info(f"✅ Native context from GGUF metadata ({field.name}): {context:,} tokens")
                                return context
                        except (IndexError, ValueError, TypeError) as e:
                            logger.debug(f"Failed to parse {field.name}: {e}")
                            continue

                # Log available keys for debugging
                all_keys = [f.name for f in reader.fields.values()]
                context_related_keys = [k for k in all_keys if 'context' in k.lower() or 'length' in k.lower()]
                logger.warning("No context_length key found in GGUF metadata")
                logger.warning(f"Available context-related keys: {context_related_keys}")
                logger.debug(f"All metadata keys (first 30): {all_keys[:30]}")
                return None

            except Exception as e:
                logger.error(f"Error parsing GGUF metadata: {e}")
                return None

    except ImportError:
        logger.warning("gguf-py library not installed - cannot read native context")
        logger.info("Install with: pip install gguf")
        return None
    except Exception as e:
        logger.error(f"Error reading GGUF file {gguf_path}: {e}")
        return None


def extract_quantization_from_filename(filename: str) -> str:
    """
    Extract quantization level from GGUF filename

    Examples:
        "Qwen3-30B-Instruct-2507-Q4_K_M.gguf" -> "Q4_K_M"
        "model-IQ4_XS.gguf" -> "IQ4_XS"
        "model.gguf" -> "unknown"

    Args:
        filename: GGUF file name

    Returns:
        Quantization string (Q4_K_M, IQ4_XS, etc.)
    """
    import re

    # Match patterns like Q4_K_M, Q5_K_S, Q8_0, IQ4_XS, etc.
    patterns = [
        r'[IQ]+\d+_[A-Z]+',  # IQ4_XS, IQ3_M
        r'Q\d+_[KO]_[MSL]',  # Q4_K_M, Q5_K_S
        r'Q\d+_\d+',         # Q4_0, Q8_0
    ]

    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            return match.group(0)

    return "unknown"


def parse_gguf_metadata(file_path: Path) -> Dict[str, any]:
    """
    Parse GGUF file metadata (simplified version)

    Full GGUF parsing requires gguf-py library.
    This is a lightweight implementation that extracts basic info.

    Args:
        file_path: Path to GGUF file

    Returns:
        Dict with metadata (context_length, architecture, etc.)
    """
    metadata = {}

    try:
        with open(file_path, 'rb') as f:
            # Read GGUF header
            magic = f.read(4)
            if magic != b'GGUF':
                return metadata

            # Read version (uint32)
            version = struct.unpack('<I', f.read(4))[0]
            metadata['gguf_version'] = version

            # GGUF v3 format (skip detailed parsing for now)
            # Full parsing would require reading key-value pairs
            # For now, we'll use filename-based detection

    except Exception:
        pass

    return metadata


def find_gguf_in_huggingface_cache() -> List[GGUFModelInfo]:
    """
    Find GGUF models in HuggingFace cache

    Searches: ~/.cache/huggingface/hub/models--*/snapshots/*/*.gguf

    Returns:
        List of GGUFModelInfo objects
    """
    models = []
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"

    if not hf_cache.exists():
        return models

    # Search for GGUF files in HF cache
    for model_dir in hf_cache.glob("models--*"):
        for snapshot_dir in (model_dir / "snapshots").glob("*"):
            for gguf_file in snapshot_dir.glob("*.gguf"):
                # Extract model name from directory
                # models--bartowski--Qwen3-30B-Instruct-2507-GGUF
                author_model = model_dir.name.replace("models--", "").replace("--", "/", 1)

                # Get file size
                size_bytes = gguf_file.stat().st_size
                size_gb = size_bytes / (1024**3)

                # Extract quantization
                quantization = extract_quantization_from_filename(gguf_file.name)

                # Create friendly name
                model_name = f"{author_model} ({quantization})"

                models.append(GGUFModelInfo(
                    path=gguf_file,
                    name=model_name,
                    size_gb=size_gb,
                    quantization=quantization
                ))

    return models


def find_gguf_in_custom_directory(directory: Path) -> List[GGUFModelInfo]:
    """
    Find GGUF models in custom directory

    Args:
        directory: Path to search (e.g., ~/models/)

    Returns:
        List of GGUFModelInfo objects
    """
    models = []

    if not directory.exists():
        return models

    # Search recursively for .gguf files
    for gguf_file in directory.rglob("*.gguf"):
        # Get file size
        size_bytes = gguf_file.stat().st_size
        size_gb = size_bytes / (1024**3)

        # Extract quantization
        quantization = extract_quantization_from_filename(gguf_file.name)

        # Use filename as model name
        model_name = gguf_file.stem

        models.append(GGUFModelInfo(
            path=gguf_file,
            name=model_name,
            size_gb=size_gb,
            quantization=quantization
        ))

    return models


def find_ollama_gguf_blobs() -> List[GGUFModelInfo]:
    """
    Find GGUF models in Ollama blob storage

    WARNING: Ollama blobs are NOT directly usable as standalone GGUF files!
    This function is for reference only - users should download dedicated GGUFs.

    Ollama uses its own format and requires conversion.

    Returns:
        List of GGUFModelInfo objects (for informational purposes)
    """
    models = []
    ollama_blobs = Path.home() / ".ollama" / "models" / "blobs"

    if not ollama_blobs.exists():
        return models

    # Scan blob directory for GGUF files
    for blob_file in ollama_blobs.glob("sha256-*"):
        # Check if file is GGUF format
        if is_gguf_file(blob_file):
            # Get file size
            size_bytes = blob_file.stat().st_size
            size_gb = size_bytes / (1024**3)

            # Use SHA256 hash as identifier (no friendly name available)
            blob_hash = blob_file.name[:12]  # First 12 chars of SHA256

            models.append(GGUFModelInfo(
                path=blob_file,
                name=f"ollama-blob-{blob_hash}",
                size_gb=size_gb,
                quantization="unknown"
            ))

    return models


def find_all_gguf_models() -> List[GGUFModelInfo]:
    """
    Find all GGUF models on the system

    Searches:
    1. HuggingFace cache (~/.cache/huggingface/)
    2. Custom directory (~/models/)
    3. Ollama blobs (for reference only)

    Returns:
        List of GGUFModelInfo objects sorted by size
    """
    all_models = []

    # 1. HuggingFace cache (primary source)
    all_models.extend(find_gguf_in_huggingface_cache())

    # 2. Custom directory (user downloads)
    custom_dir = Path.home() / "models"
    all_models.extend(find_gguf_in_custom_directory(custom_dir))

    # 3. Ollama blobs (informational only - NOT recommended)
    # Commented out because Ollama blobs require conversion
    # all_models.extend(find_ollama_gguf_blobs())

    # Remove duplicates (same path)
    seen_paths = set()
    unique_models = []
    for model in all_models:
        if model.path not in seen_paths:
            seen_paths.add(model.path)
            unique_models.append(model)

    # Sort by size (largest first)
    unique_models.sort(key=lambda m: m.size_gb, reverse=True)

    return unique_models


def get_model_info_by_name(model_name: str) -> Optional[GGUFModelInfo]:
    """
    Get GGUF model info by name

    Args:
        model_name: Model name (e.g., "bartowski/Qwen3-30B-Instruct-2507-GGUF (Q4_K_M)")

    Returns:
        GGUFModelInfo if found, None otherwise
    """
    all_models = find_all_gguf_models()

    for model in all_models:
        if model.name == model_name:
            return model

    return None


def estimate_vram_usage(model_size_gb: float, context_size: int, quantization: str) -> float:
    """
    Estimate VRAM usage for a GGUF model

    Args:
        model_size_gb: Model size in GB
        context_size: Context window size (e.g., 32768)
        quantization: Quantization level (Q4_K_M, Q8_0, etc.)

    Returns:
        Estimated VRAM usage in MB
    """
    # Model weights VRAM (convert GB to MB)
    model_vram_mb = model_size_gb * 1024

    # Context cache VRAM (depends on quantization)
    # Q4: ~0.15 MB/token
    # Q5: ~0.18 MB/token
    # Q8: ~0.30 MB/token

    mb_per_token = {
        "Q4": 0.15,
        "Q5": 0.18,
        "Q8": 0.30,
        "IQ4": 0.15,
        "IQ3": 0.12,
    }

    # Detect quantization level from string
    quant_level = "Q4"  # Default
    for key in mb_per_token.keys():
        if key in quantization:
            quant_level = key
            break

    context_vram_mb = context_size * mb_per_token[quant_level]

    # Safety margin (512MB for CUDA kernels, etc.)
    safety_margin_mb = 512

    total_vram_mb = model_vram_mb + context_vram_mb + safety_margin_mb

    return total_vram_mb


if __name__ == "__main__":
    # Test GGUF discovery
    print("=" * 60)
    print("GGUF Model Discovery Test")
    print("=" * 60)
    print()

    models = find_all_gguf_models()

    if not models:
        print("❌ No GGUF models found")
        print()
        print("Download models with:")
        print("  huggingface-cli download bartowski/Qwen3-30B-Instruct-2507-GGUF \\")
        print("      Qwen3-30B-Instruct-2507-Q4_K_M.gguf --local-dir ~/models/")
    else:
        print(f"✅ Found {len(models)} GGUF model(s):")
        print()
        for model in models:
            print(f"  📦 {model.name}")
            print(f"     Path: {model.path}")
            print(f"     Size: {model.size_gb:.1f}GB")
            print(f"     Quantization: {model.quantization}")
            print()
