#!/usr/bin/env python3
"""
llama-swap Autoscan - Automatic model discovery and configuration

Scans for new GGUF models (Ollama blobs, HuggingFace cache, ~/models/)
and automatically:
1. Creates symlinks for Ollama blobs with descriptive filenames
2. Adds new model entries to llama-swap-config.yaml
3. Creates preliminary VRAM cache entries

Designed to run as ExecStartPre before llama-swap service starts.
"""

import json
import re
import socket
import subprocess
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODELS_DIR = Path.home() / "models"

OLLAMA_PATHS = [
    Path("/usr/share/ollama/.ollama/models"),   # System-Service
    Path.home() / ".ollama" / "models",         # User-Installation
]

LLAMASWAP_CONFIG = Path.home() / ".config" / "llama-swap" / "config.yaml"
# Persists models that failed the compatibility test — not re-tested on subsequent runs.
# Delete an entry manually to re-test after a llama.cpp update.
AUTOSCAN_SKIP_FILE = LLAMASWAP_CONFIG.parent / "autoscan-skip.json"

# VRAM cache lives in the AIfred data directory
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
VRAM_CACHE_FILE = PROJECT_ROOT / "data" / "model_vram_cache.json"

LLAMA_SERVER_BIN = Path.home() / "llama.cpp" / "build" / "bin" / "llama-server"
DEFAULT_TTL = 300
DEFAULT_NGL = 99
DEFAULT_FLAGS = "--flash-attn on -ctk q8_0 -ctv q8_0 -np 1 -t 4 --mlock"
DEFAULT_CONTEXT = 32768  # Fallback if GGUF metadata unreadable

# No size filter - even tiny LLMs (135M edge models) should be loadable


# ---------------------------------------------------------------------------
# Ollama manifest scanning
# ---------------------------------------------------------------------------

def find_ollama_base() -> Optional[Path]:
    """Find the active Ollama models directory."""
    for path in OLLAMA_PATHS:
        manifest_dir = path / "manifests" / "registry.ollama.ai" / "library"
        if manifest_dir.exists():
            return path
    return None


def is_embedding_model(manifest_data: dict) -> bool:
    """
    Check if a model is an embedding model (not usable for text generation).

    Detection: Embedding models have no 'params' layer in their manifest.
    All LLMs and VLMs have params (temperature, top_p, etc.),
    embedding models don't need inference parameters.
    """
    has_params = any(
        layer.get("mediaType") == "application/vnd.ollama.image.params"
        for layer in manifest_data.get("layers", [])
    )
    return not has_params


def build_symlink_name(model_name: str, tag: str, config_data: dict) -> str:
    """
    Build a descriptive GGUF filename from Ollama model name, tag, and config.

    Strategy:
    - Start with model_name + tag as the basis
    - Append file_type (quantization) if not already in the tag
    - Title-case and use hyphens as separators

    Examples:
        qwen3, 8b, Q4_K_M           → Qwen3-8B-Q4_K_M.gguf
        qwen3, 14b-q8_0, Q8_0       → Qwen3-14B-Q8_0.gguf
        qwen3-coder, 30b, Q4_K_M    → Qwen3-Coder-30B-Q4_K_M.gguf
        deepseek-ocr, 3b, F16       → DeepSeek-OCR-3B-F16.gguf
    """
    file_type = config_data.get("file_type", "")

    # Combine model name and tag
    # model_name: "qwen3-coder", tag: "30b" → "qwen3-coder-30b"
    raw = f"{model_name}-{tag}"

    # Check if quant info is already in the tag (case-insensitive)
    has_quant = False
    if file_type:
        has_quant = file_type.lower().replace("_", "") in raw.lower().replace("_", "")

    # Append quant if missing
    if file_type and not has_quant:
        raw = f"{raw}-{file_type}"

    # Known abbreviations that should always be uppercase
    UPPERCASE_WORDS = {"vl", "ocr", "rl", "a3b", "moe"}

    # Title-case each segment separated by hyphens
    # But preserve: uppercase sequences (Q4_K_M, OCR, VL, A3B), numbers, version strings (2507)
    parts = raw.split("-")
    formatted_parts = []
    for part in parts:
        # Already uppercase (Q4_K_M, OCR, VL, F16) or contains underscore → uppercase
        if part.isupper() or "_" in part:
            formatted_parts.append(part.upper())
        # Known abbreviations → uppercase
        elif part.lower() in UPPERCASE_WORDS:
            formatted_parts.append(part.upper())
        # Pure number or size like "8b", "30b", "1.7b" → uppercase
        elif re.match(r'^\d+\.?\d*[bB]$', part):
            formatted_parts.append(part.upper())
        # Version string like "2507" → keep as-is
        elif part.isdigit():
            formatted_parts.append(part)
        # Quant notation like "q8_0", "q4" → uppercase
        elif re.match(r'^[qQ]\d+', part):
            formatted_parts.append(part.upper())
        # Normal word → capitalize first letter
        else:
            formatted_parts.append(part.capitalize())

    filename = "-".join(formatted_parts)

    # Clean up: remove duplicate quant patterns that may appear
    # e.g., "Q4_K_M-Q4_K_M" from tag already containing it
    # (shouldn't happen with has_quant check, but safety net)

    return f"{filename}.gguf"


def scan_ollama_manifests(ollama_base: Path) -> list[dict]:
    """
    Scan all Ollama manifests and return model info.

    Returns list of dicts with keys:
        model_name, tag, blob_path, blob_size, config_data, symlink_name
    """
    manifest_base = ollama_base / "manifests" / "registry.ollama.ai" / "library"
    blobs_base = ollama_base / "blobs"

    # Collect best entry per blob inline (longest symlink name wins)
    best_per_blob: dict[str, dict] = {}
    skipped = 0

    for model_dir in sorted(manifest_base.iterdir()):
        if not model_dir.is_dir():
            continue

        model_name = model_dir.name

        for tag_file in sorted(model_dir.iterdir()):
            if not tag_file.is_file():
                continue

            tag = tag_file.name

            try:
                manifest = json.loads(tag_file.read_text())
            except (json.JSONDecodeError, OSError):
                print(f"  ! Error reading manifest: {model_name}:{tag}")
                continue

            # Find GGUF blob layer
            blob_digest = None
            blob_size = 0
            config_digest = None

            for layer in manifest.get("layers", []):
                media_type = layer.get("mediaType", "")
                if media_type == "application/vnd.ollama.image.model":
                    blob_digest = layer["digest"]
                    blob_size = layer.get("size", 0)
                elif media_type == "application/vnd.docker.container.image.v1+json":
                    config_digest = layer.get("digest") or manifest.get("config", {}).get("digest")

            # Config digest might be in manifest.config instead of layers
            if not config_digest:
                config_digest = manifest.get("config", {}).get("digest")

            if not blob_digest:
                continue

            # Read config blob for metadata
            config_data: dict = {}
            if config_digest:
                config_blob_path = blobs_base / config_digest.replace(":", "-")
                if config_blob_path.exists():
                    try:
                        config_data = json.loads(config_blob_path.read_text())
                    except (json.JSONDecodeError, OSError):
                        pass

            # Filter embedding models
            if is_embedding_model(manifest):
                print(f"  ~ Skip:    {model_name}:{tag} (embedding model)")
                continue

            # Resolve blob path
            blob_path = blobs_base / blob_digest.replace(":", "-")
            if not blob_path.exists():
                print(f"  ! Blob missing: {model_name}:{tag} → {blob_digest[:24]}...")
                continue

            symlink_name = build_symlink_name(model_name, tag, config_data)

            entry = {
                "model_name": model_name,
                "tag": tag,
                "ollama_id": f"{model_name}:{tag}",
                "blob_digest": blob_digest,
                "blob_path": blob_path,
                "blob_size": blob_size,
                "config_data": config_data,
                "symlink_name": symlink_name,
            }

            # Multiple Ollama tags can point to the same blob - keep longest name
            existing = best_per_blob.get(blob_digest)
            if existing is None or len(symlink_name) > len(existing["symlink_name"]):
                if existing is not None:
                    skipped += 1
                best_per_blob[blob_digest] = entry
            else:
                skipped += 1

    if skipped:
        print(f"  ~ {skipped} shorter tag(s) skipped (same blob, less descriptive name)")

    return list(best_per_blob.values())


def create_symlinks(ollama_models: list[dict]) -> list[dict]:
    """
    Create symlinks in MODELS_DIR for Ollama models.

    Skips creation if another file/symlink already points to the same blob
    (e.g. a manually created symlink with a more descriptive name).

    Returns list of newly created symlink entries.
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # Build map of existing resolved targets → filenames
    existing_targets: dict[str, str] = {}
    for existing_file in MODELS_DIR.glob("*.gguf"):
        resolved = str(existing_file.resolve())
        existing_targets[resolved] = existing_file.name

    new_symlinks = []

    for model in ollama_models:
        symlink_path = MODELS_DIR / model["symlink_name"]

        if symlink_path.exists() or symlink_path.is_symlink():
            print(f"  = Exists:  {model['symlink_name']}")
            continue

        # Check if another file already points to the same blob
        blob_resolved = str(model["blob_path"].resolve())
        existing_name = existing_targets.get(blob_resolved)
        if existing_name:
            print(f"  = Covered: {model['symlink_name']} (already via {existing_name})")
            continue

        symlink_path.symlink_to(model["blob_path"])
        print(f"  + Symlink: {model['symlink_name']} → {model['blob_path'].name[:24]}...")
        existing_targets[blob_resolved] = model["symlink_name"]
        new_symlinks.append(model)

    return new_symlinks


# ---------------------------------------------------------------------------
# GGUF scanning and delta detection
# ---------------------------------------------------------------------------

def _strip_quant_suffix(stem: str) -> str:
    """
    Strip quantization suffix from a GGUF stem.

    Examples:
        Qwen3VL-8B-Instruct-Q4_K_M  → Qwen3VL-8B-Instruct
        mmproj-Qwen3VL-8B-Instruct-F16 → mmproj-Qwen3VL-8B-Instruct
    """
    return re.sub(r'-(?:BF|[QqFf])\d[0-9_A-Za-z]*$', '', stem, flags=re.IGNORECASE)


def _find_mmproj(model_stem: str, mmproj_files: dict[str, Path]) -> Optional[Path]:
    """
    Match a model stem to a mmproj file by common base name (quantization-stripped).

    Example: model "Qwen3VL-8B-Instruct-Q4_K_M" matches mmproj "Qwen3VL-8B-Instruct-F16"
    because both share the base "qwen3vl-8b-instruct".
    """
    model_base = _strip_quant_suffix(model_stem).lower()
    for mmproj_stem, mmp_path in mmproj_files.items():
        mmproj_base = _strip_quant_suffix(mmproj_stem).lower()
        if model_base == mmproj_base:
            return mmp_path
    return None


def scan_gguf_models() -> list[dict]:
    """
    Scan ~/models/ for all GGUF files.

    Detects mmproj-*.gguf files and pairs them with their corresponding VL model.

    Returns list of dicts with keys: name (stem), path, mmproj_path (Optional[Path])
    """
    if not MODELS_DIR.exists():
        return []

    # Collect mmproj files first: stem-without-prefix → path
    mmproj_files: dict[str, Path] = {}
    for mmp in sorted(MODELS_DIR.glob("mmproj-*.gguf")):
        mmproj_files[mmp.stem[len("mmproj-"):]] = mmp

    models = []
    for gguf_file in sorted(MODELS_DIR.glob("*.gguf")):
        # mmproj files are not standalone models
        if gguf_file.name.startswith("mmproj-"):
            continue

        # Skip split-GGUF parts (only count the first part or single files)
        if re.match(r'.*-\d{5}-of-\d{5}\.gguf$', gguf_file.name):
            if not gguf_file.name.endswith("-00001-of-" + gguf_file.name.split("-of-")[-1]):
                continue

        model_stem = gguf_file.stem
        models.append({
            "name": model_stem,
            "path": gguf_file,
            "mmproj_path": _find_mmproj(model_stem, mmproj_files),
        })

    return models


def parse_existing_yaml_models(config_path: Path) -> set[str]:
    """
    Extract model names from existing llama-swap-config.yaml.

    Simple regex-based parsing to avoid YAML library dependency.
    Returns set of model names (keys under 'models:').
    """
    if not config_path.exists():
        return set()

    content = config_path.read_text()
    # Match lines like "  ModelName:" that are model entries under "models:"
    # They are indented by 2 spaces and followed by a colon
    model_names = set()
    in_models_section = False

    for line in content.splitlines():
        if line.strip() == "models:":
            in_models_section = True
            continue

        if in_models_section:
            # Model entry: exactly 2 spaces indent, then name, then colon
            match = re.match(r'^  ([A-Za-z0-9][A-Za-z0-9._-]*):$', line)
            if match:
                model_names.add(match.group(1))
            # Sub-keys have 4+ spaces, skip those
            # A line with 0 indent means we left the models section
            elif line and not line.startswith(" "):
                break

    return model_names


def find_new_models(all_ggufs: list[dict], existing_models: set[str]) -> list[dict]:
    """Find GGUFs that are not yet in the llama-swap config."""
    new = []
    for gguf in all_ggufs:
        if gguf["name"] not in existing_models:
            new.append(gguf)
    return new


# ---------------------------------------------------------------------------
# GGUF metadata reading
# ---------------------------------------------------------------------------

def get_native_context(gguf_path: Path) -> int:
    """
    Read native context length from GGUF metadata.

    Uses gguf-py library if available, falls back to DEFAULT_CONTEXT.
    """
    try:
        # Resolve symlinks to read the actual file
        real_path = gguf_path.resolve()

        import gguf
        with open(real_path, "rb") as f:
            reader = gguf.GGUFReader(f)
            for field in reader.fields.values():
                field_name = field.name.lower()
                if field_name.endswith('.context_length') or field_name == 'context_length':
                    value_array = field.parts[-1]
                    context = int(value_array[0]) if len(value_array) > 0 else None
                    if context and context > 0:
                        return context
    except ImportError:
        print("  ! gguf-py not installed, using default context")
    except Exception as e:
        print(f"  ! Error reading GGUF metadata: {e}")

    return DEFAULT_CONTEXT


# ---------------------------------------------------------------------------
# YAML generation
# ---------------------------------------------------------------------------

def detect_llama_server_bin(config_path: Path) -> Path:
    """
    Detect llama-server binary path from existing config entries.

    Falls back to LLAMA_SERVER_BIN constant.
    """
    if not config_path.exists():
        return LLAMA_SERVER_BIN

    content = config_path.read_text()
    # Extract first llama-server path from any cmd line
    match = re.search(r'(/\S+/llama-server)\s', content)
    if match:
        return Path(match.group(1))

    return LLAMA_SERVER_BIN


def append_models_to_yaml(
    config_path: Path,
    new_models: list[dict],
    server_bin: Path,
) -> int:
    """
    Append new model entries to llama-swap-config.yaml.

    VL models (with mmproj_path set) get a --mmproj argument in the cmd.

    Returns number of models added.
    """
    if not new_models:
        return 0

    # Read existing content
    if config_path.exists():
        content = config_path.read_text()
        # Ensure trailing newline
        if not content.endswith("\n"):
            content += "\n"
    else:
        content = "models:\n"

    added = 0
    for model in new_models:
        name = model["name"]
        # Use the symlink path itself (not resolved), so the YAML points to ~/models/Name.gguf
        path = model["path"].absolute()
        context = get_native_context(model["path"])
        mmproj = model.get("mmproj_path")

        if mmproj:
            cmd_line = (
                f"{server_bin} --port ${{PORT}} "
                f"--model {path} "
                f"--mmproj {mmproj.absolute()} "
                f"-ngl {DEFAULT_NGL} -c {context} {DEFAULT_FLAGS}"
            )
            print(f"  + Added: {name} (VL, context: {context:,}, mmproj: {mmproj.name})")
        else:
            cmd_line = (
                f"{server_bin} --port ${{PORT}} "
                f"--model {path} "
                f"-ngl {DEFAULT_NGL} -c {context} {DEFAULT_FLAGS}"
            )
            print(f"  + Added: {name} (native context: {context:,})")

        # Append YAML block
        content += f"  {name}:\n"
        content += f"    cmd: {cmd_line}\n"
        content += f"    ttl: {DEFAULT_TTL}\n"

        added += 1

    config_path.write_text(content)
    return added


# ---------------------------------------------------------------------------
# VRAM cache
# ---------------------------------------------------------------------------

def update_vram_cache(new_models: list[dict]) -> int:
    """
    Add preliminary VRAM cache entries for new models.

    Returns number of entries added.
    """
    if not new_models:
        return 0

    # Load existing cache
    cache: dict = {}
    if VRAM_CACHE_FILE.exists():
        try:
            cache = json.loads(VRAM_CACHE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            cache = {}

    added = 0
    for model in new_models:
        name = model["name"]

        if name in cache:
            continue

        context = get_native_context(model["path"])

        cache[name] = {
            "backend": "llamacpp",
            "native_context": context,
            "gpu_model": "",
            "llamacpp_calibrations": [],
        }

        print(f"  + Added: {name}")
        added += 1

    # Save cache
    if added > 0:
        VRAM_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        VRAM_CACHE_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n")

    return added


# ---------------------------------------------------------------------------
# Incompatibility skip list
# ---------------------------------------------------------------------------

def load_skip_list() -> dict[str, str]:
    """Load models that previously failed the compatibility test (name → reason)."""
    if not AUTOSCAN_SKIP_FILE.exists():
        return {}
    try:
        return json.loads(AUTOSCAN_SKIP_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_skip_list(skip: dict[str, str]) -> None:
    """Persist the skip list to disk."""
    AUTOSCAN_SKIP_FILE.write_text(json.dumps(skip, indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Compatibility test
# ---------------------------------------------------------------------------

# How long to wait for llama-server to crash with a startup error.
# Compatible models keep running (serving HTTP), so they always hit this timeout.
# Incompatible models fail within 1-2 s → we catch the error before the timeout.
COMPAT_TEST_TIMEOUT = 6


def _free_port() -> int:
    """Return an available TCP port on localhost."""
    with socket.socket() as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def test_model_compatibility(
    gguf_path: Path,
    server_bin: Path,
    mmproj_path: Optional[Path] = None,
) -> tuple[bool, str]:
    """
    Quick llama-server startup test for a new model.

    Starts llama-server with minimal flags and waits COMPAT_TEST_TIMEOUT seconds.
    - If the process exits within the timeout → reads stdout for known error patterns.
    - If the process is still running after the timeout → model is loading fine (compatible).

    For VL models, pass mmproj_path so llama-server gets the required --mmproj argument.

    Returns:
        (True, "")              — compatible (or test inconclusive)
        (False, "reason str")   — known incompatibility detected
    """
    if not server_bin.exists():
        return True, ""

    port = _free_port()
    cmd = [
        str(server_bin),
        "--port", str(port),
        "--model", str(gguf_path.resolve()),
        # Minimal settings — architecture errors occur before any weight loading
        "-ngl", "99",
        "-c", "512",
        "-np", "1",
    ]
    if mmproj_path:
        cmd += ["--mmproj", str(mmproj_path.resolve())]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except Exception:
        return True, ""  # Can't run the binary — not the model's fault

    try:
        stdout_data, _ = proc.communicate(timeout=COMPAT_TEST_TIMEOUT)
        output = stdout_data.decode('utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        # Still running after timeout → server is up, model is compatible
        proc.kill()
        proc.communicate()
        return True, ""

    # Process exited before timeout — check for known permanent failures
    if "unknown model architecture" in output:
        m = re.search(r"unknown model architecture: '([^']+)'", output)
        arch = m.group(1) if m else "unknown"
        return False, f"unsupported architecture '{arch}'"

    if "key not found in model" in output:
        m = re.search(r"key not found in model: (\S+)", output)
        key = m.group(1) if m else "unknown key"
        # Detect Ollama blobs by resolving the symlink
        hint = ""
        if gguf_path.is_symlink() and ".ollama" in str(gguf_path.resolve()):
            hint = " — Ollama blob missing llama.cpp metadata; download official GGUF from HuggingFace"
        return False, f"missing GGUF metadata key '{key}'{hint}"

    # Other early exits (e.g. port conflict) — don't block the model
    return True, ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== llama-swap Autoscan ===")
    print()

    # Step 1: Scan Ollama and create symlinks
    ollama_base = find_ollama_base()
    if ollama_base:
        print("Scanning Ollama models...")
        ollama_models = scan_ollama_manifests(ollama_base)
        new_symlinks = create_symlinks(ollama_models)
        print(f"  {len(ollama_models)} Ollama models found, {len(new_symlinks)} new symlinks created")
    else:
        print("No Ollama installation found, skipping.")
        ollama_models = []

    print()

    # Step 2: Scan for all GGUFs and find new ones
    print("Scanning ~/models/ for GGUFs...")
    all_ggufs = scan_gguf_models()
    existing = parse_existing_yaml_models(LLAMASWAP_CONFIG)
    skip_list = load_skip_list()

    # Models in the skip list are known-incompatible — treat as already handled
    if skip_list:
        skipped = [m["name"] for m in all_ggufs if m["name"] in skip_list and m["name"] not in existing]
        if skipped:
            print(f"  {len(skipped)} model(s) skipped (known incompatible, remove from {AUTOSCAN_SKIP_FILE.name} to re-test):")
            for name in skipped:
                print(f"    ~ {name}: {skip_list[name]}")

    new_models = find_new_models(all_ggufs, existing | set(skip_list))
    vl_models = [m for m in new_models if m.get("mmproj_path")]
    if vl_models:
        print(f"  {len(vl_models)} VL model(s) detected with mmproj:")
        for m in vl_models:
            print(f"    ◆ {m['name']} + {m['mmproj_path'].name}")  # type: ignore[union-attr]
    print(f"  Found {len(all_ggufs)} GGUFs, {len(new_models)} new")
    print()

    if not new_models:
        print("No new models to add. Done.")
        return

    # Step 3: Compatibility test — only for genuinely new models, result cached in skip list
    server_bin = detect_llama_server_bin(LLAMASWAP_CONFIG)
    print("Testing new models for llama-server compatibility...")
    compatible_models = []
    for model in new_models:
        compat, reason = test_model_compatibility(model["path"], server_bin, model.get("mmproj_path"))
        if compat:
            compatible_models.append(model)
            mmproj = model.get("mmproj_path")
            label = f"VL + {mmproj.name}" if mmproj else "OK"
            print(f"  ✓ {model['name']} ({label})")
        else:
            skip_list[model["name"]] = reason
            save_skip_list(skip_list)
            print(f"  ✗ {model['name']}: {reason} — skipping")
    new_models = compatible_models
    print()

    if not new_models:
        print("No compatible models to add. Done.")
        return

    # Step 4: Add to llama-swap config
    print("Updating llama-swap-config.yaml...")
    yaml_added = append_models_to_yaml(LLAMASWAP_CONFIG, new_models, server_bin)
    print()

    # Step 5: Update VRAM cache
    print("Updating VRAM cache...")
    cache_added = update_vram_cache(new_models)
    print()

    print(f"Done. {yaml_added} model(s) added to config, {cache_added} VRAM cache entries created.")


if __name__ == "__main__":
    main()
