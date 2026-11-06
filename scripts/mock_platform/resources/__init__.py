"""Shared locations for packaged resources, static UI and project data."""

from pathlib import Path

RESOURCE_ROOT = Path(__file__).resolve().parent
PLATFORM_ROOT = RESOURCE_ROOT.parent
PROJECT_ROOT = PLATFORM_ROOT.parents[1]
WEB_ROOT = PLATFORM_ROOT / "web"
