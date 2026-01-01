"""Reflex configuration for AIfred Intelligence"""

import reflex as rx
import os

# ============================================================
# API URL Configuration
# ============================================================
# Set AIFRED_API_URL environment variable to your backend URL
# Examples:
#   - Local dev: http://localhost:8002 (default)
#   - LAN access: http://192.168.1.100:8002
#   - Production: https://your-domain.com:8443
#
# You can set this in a .env file (which is gitignored)
API_URL = os.getenv("AIFRED_API_URL", "http://localhost:8002")

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
    # KaTeX for LaTeX rendering in Markdown (locally hosted)
    stylesheets=[
        "/katex/katex.min.css",
    ],
)
