"""Hyprland window queries and dispatches, over the shared connection."""

import json

from loguru import logger

from fabric_config.utils.hyprland_monitor import get_hyprland_monitors


def hyprland_clients() -> list[dict]:
    try:
        clients = json.loads(get_hyprland_monitors().send_command("j/clients").reply)
    except Exception as e:
        logger.error(f"[Hyprland] fetching clients failed: {e}")
        return []
    return [c for c in clients if c.get("mapped", True)]


def focus_window(address: str):
    # Hyprland 0.56+ (Lua config) rejects the old "focuswindow address:..." form
    get_hyprland_monitors().send_command(
        f"/dispatch hl.dsp.focus({{ window = 'address:{address}' }})"
    )


def close_window(address: str):
    get_hyprland_monitors().send_command(
        f"/dispatch hl.dsp.window.close({{ window = 'address:{address}' }})"
    )


def kill_window(address: str):
    get_hyprland_monitors().send_command(
        f"/dispatch hl.dsp.window.kill({{ window = 'address:{address}' }})"
    )
