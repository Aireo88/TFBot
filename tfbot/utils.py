"""Utility helpers for TFBot."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Set, Tuple

import discord

logger = logging.getLogger("tfbot.utils")


def int_from_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid integer for %s=%s. Falling back to %s.", name, raw, default)
        return default


def float_from_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid float for %s=%s. Falling back to %s.", name, raw, default)
        return default


def path_from_env(name: str) -> Optional[Path]:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    return Path(value).expanduser()


def parse_channel_ids(raw: str) -> Set[int]:
    ids: Set[int] = set()
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.add(int(chunk))
        except ValueError:
            logger.warning("Ignoring invalid channel id %s", chunk)
    return ids


def get_channel_id(env_name: str, default: int = 0, test_mode: Optional[bool] = None) -> int:
    """
    Get channel ID with backward compatibility and live/test mode support.
    
    Behavior:
    - If test_mode is None (TFBOT_TEST not defined): Use current format (backward compatible)
    - If test_mode=True (TFBOT_TEST=YES): Use _TEST suffixed channels
    - If test_mode=False (TFBOT_TEST=NO): Use _LIVE suffixed channels
    
    NO FALLBACK between modes - if channel not set in active mode, returns default (0).
    Core channels still error on launch if missing (handled by caller).
    
    Args:
        env_name: Base name (e.g., "TFBOT_CHANNEL_ID")
        default: Default value if not found (typically 0 to disable)
        test_mode: None = backward compat (current format), False = LIVE, True = TEST
    
    Returns:
        Channel ID from appropriate variant, or default if not set
    """
    if test_mode is None:
        # Backward compatibility: Use current format (no suffix)
        return int_from_env(env_name, default)
    elif test_mode:
        # TEST mode: Use _TEST suffix
        return int_from_env(f"{env_name}_TEST", default)
    else:
        # LIVE mode: Use _LIVE suffix
        return int_from_env(f"{env_name}_LIVE", default)


def get_setting(env_name: str, default: str = "", test_mode: Optional[bool] = None) -> str:
    """
    Get setting with backward compatibility and live/test mode support.
    
    Behavior:
    - If test_mode is None (TFBOT_TEST not defined): Use current format (backward compatible)
    - If test_mode=True (TFBOT_TEST=YES): Use _TEST suffixed settings, fallback to base name
    - If test_mode=False (TFBOT_TEST=NO): Use _LIVE suffixed settings, fallback to base name
    
    Falls back to base name if mode-specific variant is not found (allows gradual migration).
    
    Args:
        env_name: Base name (e.g., "TFBOT_NAME")
        default: Default value if not found
        test_mode: None = backward compat (current format), False = LIVE, True = TEST
    
    Returns:
        Setting value from appropriate variant, or default if not set
    """
    if test_mode is None:
        # Backward compatibility: Use current format (no suffix)
        return os.getenv(env_name, default).strip()
    elif test_mode:
        # TEST mode: Use _TEST suffix, fallback to base name
        return os.getenv(f"{env_name}_TEST", os.getenv(env_name, default)).strip()
    else:
        # LIVE mode: Use _LIVE suffix, fallback to base name
        return os.getenv(f"{env_name}_LIVE", os.getenv(env_name, default)).strip()


def normalize_pose_name(pose: Optional[str]) -> Optional[str]:
    if pose is None:
        return None
    stripped = pose.strip()
    if not stripped:
        return None
    return stripped.lower()


def is_admin(member: discord.abc.User) -> bool:
    if isinstance(member, discord.Member):
        if member.guild_permissions.administrator:
            return True
        roles: Iterable[discord.Role] = getattr(member, "roles", [])
        return any(role.name.lower() == "admin" for role in roles)
    return False


def member_profile_name(member: discord.Member) -> str:
    """Return the user's profile name, ignoring any server nickname."""
    global_name = getattr(member, "global_name", None)
    if isinstance(global_name, str) and global_name.strip():
        return global_name.strip()
    return member.name


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "float_from_env",
    "get_channel_id",
    "get_setting",
    "int_from_env",
    "is_admin",
    "member_profile_name",
    "normalize_pose_name",
    "parse_channel_ids",
    "path_from_env",
    "utc_now",
]
