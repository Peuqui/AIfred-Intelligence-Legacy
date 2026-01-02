"""Reflex configuration for AIfred Intelligence"""

import reflex as rx
import os
import socket

# Load .env file for environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, rely on system env vars

# ============================================================
# API URL Configuration
# ============================================================
# The backend URL is auto-detected from the machine's IP address.
# Override with AIFRED_API_URL environment variable if needed.
#
# Examples for .env file:
#   AIFRED_API_URL=https://your-domain.com:8443  # Production with SSL/nginx
#   AIFRED_API_URL=http://192.168.1.100:8002     # Specific IP

def _get_local_ip() -> str:
    """Get the local IP address of this machine."""
    try:
        # Connect to external host to determine local IP (doesn't actually send data)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"

BACKEND_PORT = 8002
_default_api_url = f"http://{_get_local_ip()}:{BACKEND_PORT}"
API_URL = os.getenv("AIFRED_API_URL", _default_api_url)

# Environment mode (affects Reflex optimizations)
is_prod = os.getenv("AIFRED_ENV", "dev") == "prod"

config = rx.Config(
    app_name="aifred",
    backend_host="0.0.0.0",  # Listen on all interfaces
    backend_port=8002,
    frontend_port=3002,
    frontend_host="0.0.0.0",  # Frontend on all interfaces
    # API URL from environment variable
    api_url=API_URL,
    env=rx.Env.PROD if is_prod else rx.Env.DEV,
    # Disable sitemap plugin (not needed)
    disable_plugins=["reflex.plugins.sitemap.SitemapPlugin"],
    # Performance optimizations
    compile_timeout=90,  # Increase compilation timeout (default: 60s)
    # Hide "Built with Reflex" badge
    show_built_with_reflex=False,
    # KaTeX for LaTeX rendering in Markdown (locally hosted)
    stylesheets=[
        "/katex/katex.min.css",
    ],
)
