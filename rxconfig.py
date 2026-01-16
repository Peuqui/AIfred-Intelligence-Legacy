"""Reflex configuration for AIfred Intelligence"""

import reflex as rx
import os

# Load .env file for environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, rely on system env vars

# ============================================================
# API URL Configuration
# ============================================================
# We use "0.0.0.0" as the hostname because Reflex's frontend JS
# has a SAME_DOMAIN_HOSTNAMES list that includes "0.0.0.0".
# When the browser sees this, it replaces it with window.location.hostname.
#
# This allows the same deployment to work via:
#   - https://narnia.spdns.de:8443 (nginx/external)
#   - https://narnia.spdns.de:443 (nginx/external alt port)
#   - http://192.168.0.252:3002 (direct/local from other machines)
#
# The frontend JS (state.js getBackendURL) does the magic replacement.

# Environment mode (affects Reflex optimizations)
is_prod = os.getenv("AIFRED_ENV", "dev") == "prod"

config = rx.Config(
    app_name="aifred",
    backend_host="0.0.0.0",  # Listen on all interfaces
    backend_port=8002,
    frontend_port=3002,
    frontend_host="0.0.0.0",  # Frontend on all interfaces
    # Use 0.0.0.0 - browser JS will replace with actual hostname
    api_url="http://0.0.0.0:8002",
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
