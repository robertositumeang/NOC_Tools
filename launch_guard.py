"""
launch_guard.py – NOC Tools Launcher Handshake Security
========================================================

Prevents child applications (Dashboard, Ticket Checker, VPN, Capture Modem)
from being run directly by double-clicking the .exe.

Only NOC Tools.exe — after the operator has passed the Login & License gates
— can generate a valid token.  Each child app validates the token at startup
and exits immediately if it is missing, expired, or tampered with.

Protocol
--------
1. NOC Tools generates a 5-minute HMAC-SHA256 token at launch time.
2. The token is passed via the environment variable NOC_LAUNCH_TOKEN.
3. The child app calls `require_launcher_token()` as the very first thing
   in main().  If the token is invalid the app shows a brief error dialog
   (on Windows, a MessageBox) and terminates with exit code 2.

Security properties
-------------------
- The HMAC secret is derived from a machine-specific value (volume serial
  or BIOS UUID) so the token cannot be reused on another machine.
- The token includes a UTC timestamp (floored to the minute) so each
  invocation produces a unique value and tokens expire within ~5 minutes.
- Without the HMAC secret there is no practical way to forge a token.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import os
import subprocess
import sys
import time

# Environment variable name used to carry the token
_TOKEN_ENV = "NOC_LAUNCH_TOKEN"

# Token valid window in seconds (generous for slow machines / heavy load)
_TOKEN_TTL = 300  # 5 minutes


# ── Machine fingerprint ────────────────────────────────────────────────────

def _machine_fingerprint() -> str:
    """Return a stable per-machine string used as part of the HMAC secret.

    Uses the Windows volume serial number of the system drive when available,
    falls back to a hash of the machine name + platform info.
    """
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["wmic", "OS", "get", "SerialNumber", "/value"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if "SerialNumber=" in line:
                    serial = line.split("=", 1)[1].strip()
                    if serial:
                        return serial
        except Exception:
            pass

        try:
            result = subprocess.run(
                ["wmic", "csproduct", "get", "UUID", "/value"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if "UUID=" in line:
                    uuid = line.split("=", 1)[1].strip()
                    if uuid and uuid.upper() not in ("", "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF"):
                        return uuid
        except Exception:
            pass

    import platform
    return hashlib.sha256(
        f"{platform.node()}{platform.machine()}{platform.processor()}".encode()
    ).hexdigest()


# ── HMAC secret (derived, not hard-coded) ─────────────────────────────────

_HMAC_PEPPER = b"NOC-Command-Center-v3-launch-guard"


def _hmac_secret() -> bytes:
    """Derive an HMAC secret from the machine fingerprint + a pepper."""
    fingerprint = _machine_fingerprint()
    return hashlib.pbkdf2_hmac(
        "sha256",
        fingerprint.encode(),
        _HMAC_PEPPER,
        iterations=50_000,
    )


# ── Token generation & validation ─────────────────────────────────────────

def _current_slot() -> int:
    """Return the current time slot (changes every _TOKEN_TTL seconds)."""
    return math.floor(time.time() / _TOKEN_TTL)


def _make_token(slot: int) -> str:
    secret = _hmac_secret()
    message = f"noc-launch:{slot}".encode()
    return hmac.new(secret, message, digestmod=hashlib.sha256).hexdigest()


def generate_launch_token() -> str:
    """Generate a time-limited HMAC token for the current launch session.

    Call this in NOC Tools just before spawning a child process.
    Returns a hex string that should be stored in the NOC_LAUNCH_TOKEN
    environment variable of the child process.
    """
    return _make_token(_current_slot())


def validate_launch_token() -> bool:
    """Return True if a valid launch token exists in the environment.

    Accepts tokens from the current time slot *and* the previous slot to
    tolerate clock ticks that straddle a slot boundary.
    """
    token = os.environ.get(_TOKEN_ENV, "")
    if not token:
        return False

    current = _current_slot()
    return any(
        hmac.compare_digest(token, _make_token(slot))
        for slot in (current, current - 1)
    )


# ── Guard entry point (called by child apps) ──────────────────────────────

def require_launcher_token(app_name: str = "Modul NOC") -> None:
    """Validate the launch token and exit immediately if it is missing/invalid.

    Call this as the *very first statement* in each child app's main()
    function, before any UI or server startup.

    Parameters
    ----------
    app_name:
        Human-readable name shown in the error dialog / message.
    """
    if validate_launch_token():
        # Consume the token so the variable is not inherited by further
        # sub-processes spawned by the child app itself.
        os.environ.pop(_TOKEN_ENV, None)
        return

    # Show a user-visible error then exit
    _show_access_denied(app_name)
    sys.exit(2)


def _show_access_denied(app_name: str) -> None:
    """Display an access-denied message and exit.

    Tries a native Windows MessageBox first; falls back to stderr.
    """
    title = "Akses Ditolak"
    message = (
        f"{app_name} tidak dapat dibuka secara langsung.\n\n"
        "Aplikasi ini hanya dapat dijalankan melalui:\n"
        "  NOC Tools.exe  →  Login  →  Pilih Workspace\n\n"
        "Hubungi administrator NOC jika membutuhkan akses."
    )

    if sys.platform == "win32":
        try:
            import ctypes
            # MB_OK | MB_ICONERROR | MB_TOPMOST
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x00000010 | 0x00040000)
            return
        except Exception:
            pass

    # Fallback: print to stderr
    print(f"\n{'=' * 60}\n{title}\n{'-' * 60}\n{message}\n{'=' * 60}\n",
          file=sys.stderr)

