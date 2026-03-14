#!/usr/bin/env python3
"""
Phantom 👻 — Hidden App Launcher for Linux Mint

A stealthy terminal tool that hides desktop applications from the system menu,
search, taskbar, and Alt+F2 runner, while providing a private launcher to
access them silently.

Usage:
    phantom                  Launch the Phantom UI
    phantom --change-password  Change the master password

Requirements:
    Python 3.10+ (stdlib only, zero external dependencies)
    Linux Mint / Cinnamon desktop environment
"""

from __future__ import annotations

import hashlib
import json
import getpass
import os
import shlex
import shutil
import signal
import subprocess
import sys
import termios
import time
import tty
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

PHANTOM_DIR = Path.home() / ".phantom"
HIDDEN_DIR = PHANTOM_DIR / "hidden"
CONFIG_FILE = PHANTOM_DIR / "config.json"

SYSTEM_APPS_DIR = Path("/usr/share/applications")
LOCAL_APPS_DIR = Path.home() / ".local" / "share" / "applications"

MAX_PASSWORD_ATTEMPTS = 3

VERSION = "1.0.0"

# ANSI escape codes
ESC = "\033"
CLEAR_SCREEN = f"{ESC}[2J{ESC}[H"
CURSOR_HOME = f"{ESC}[H"
CLEAR_LINE = f"{ESC}[K"
BOLD = f"{ESC}[1m"
DIM = f"{ESC}[2m"
RESET = f"{ESC}[0m"
REVERSE = f"{ESC}[7m"
CYAN = f"{ESC}[36m"
GREEN = f"{ESC}[32m"
RED = f"{ESC}[31m"
YELLOW = f"{ESC}[33m"
MAGENTA = f"{ESC}[35m"
WHITE = f"{ESC}[97m"
BG_DARK = f"{ESC}[48;5;235m"
HIDE_CURSOR = f"{ESC}[?25l"
SHOW_CURSOR = f"{ESC}[?25h"


# ──────────────────────────────────────────────────────────────────────────────
# Custom Exceptions
# ──────────────────────────────────────────────────────────────────────────────


class PhantomAuthError(Exception):
    """Raised when authentication fails."""
    pass


class PhantomConfigError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


class PhantomAppError(Exception):
    """Raised when there is an error with app operations (hide/unhide/launch)."""
    pass


# ──────────────────────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class DesktopApp:
    """Represents a parsed .desktop application entry."""
    name: str
    exec_cmd: str
    icon: str
    filename: str
    source_path: Path
    is_hidden: bool = False

    def display_label(self) -> str:
        """Return a formatted label for the terminal UI."""
        icon_part = f"  {DIM}({self.icon}){RESET}" if self.icon else ""
        return f"{self.name}{icon_part}"


PHANTOM_PATH_COMMENT_PREFIX = "# PHANTOM_ORIGINAL_PATH="


@dataclass
class Config:
    """Phantom configuration stored in config.json."""
    password_hash: str
    version: str = VERSION
    hidden_apps: dict[str, str] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# Terminal I/O Helpers
# ──────────────────────────────────────────────────────────────────────────────


def read_key() -> str:
    """Read a single keypress from stdin using raw terminal mode.

    Returns:
        A string representing the key pressed. Arrow keys are returned as
        'UP', 'DOWN', 'LEFT', 'RIGHT'. Regular keys as their character.
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == ESC[0]:  # Escape sequence
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                arrow_map = {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}
                return arrow_map.get(ch3, "")
            return "ESC"
        if ch == "\r" or ch == "\n":
            return "ENTER"
        if ch == "\x03":  # Ctrl+C
            return "CTRL_C"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ""  # Unreachable, but satisfies type checker


def clear_screen(soft: bool = False) -> None:
    """Clear the terminal screen.

    Args:
        soft: If True, only move cursor to home (no flicker).
              If False, full clear + move to home.
    """
    if soft:
        sys.stdout.write(CURSOR_HOME)
    else:
        sys.stdout.write(CLEAR_SCREEN)
    sys.stdout.flush()


def _print_line(text: str = "") -> None:
    """Print a line followed by a clear-to-end-of-line escape.

    This ensures that when overwriting in-place (soft redraw),
    leftover characters from a previous longer line are erased.

    Args:
        text: The text to print.
    """
    sys.stdout.write(f"{text}{CLEAR_LINE}\n")


def print_header(subtitle: str = "", soft: bool = False) -> None:
    """Print the Phantom header banner.

    Args:
        subtitle: Optional subtitle text displayed below the logo.
        soft: If True, use cursor-home instead of full clear (no flicker).
    """
    clear_screen(soft=soft)
    _print_line()
    _print_line(f"{CYAN}{BOLD}  ██████╗ ██╗  ██╗ █████╗ ███╗   ██╗████████╗ ██████╗ ███╗   ███╗")
    _print_line(f"  ██╔══██╗██║  ██║██╔══██╗████╗  ██║╚══██╔══╝██╔═══██╗████╗ ████║")
    _print_line(f"  ██████╔╝███████║███████║██╔██╗ ██║   ██║   ██║   ██║██╔████╔██║")
    _print_line(f"  ██╔═══╝ ██╔══██║██╔══██║██║╚██╗██║   ██║   ██║   ██║██║╚██╔╝██║")
    _print_line(f"  ██║     ██║  ██║██║  ██║██║ ╚████║   ██║   ╚██████╔╝██║ ╚═╝ ██║")
    _print_line(f"  ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝ ╚═╝     ╚═╝")
    _print_line(f"{RESET}")
    _print_line(f"  {DIM}👻  Hidden App Launcher  •  v{VERSION}{RESET}")
    if subtitle:
        _print_line(f"  {YELLOW}{subtitle}{RESET}")
    else:
        _print_line()
    _print_line(f"  {DIM}{'─' * 60}{RESET}")
    _print_line()


def print_status(message: str, style: str = DIM) -> None:
    """Print a styled status message.

    Args:
        message: The message to display.
        style: ANSI style code to apply.
    """
    _print_line(f"  {style}{message}{RESET}")


def read_password(prompt: str = "  🔒 Master Password: ") -> str:
    """Read a password from the user without echoing.

    Args:
        prompt: The prompt string displayed to the user.

    Returns:
        The password string entered.
    """
    return getpass.getpass(prompt)


# ──────────────────────────────────────────────────────────────────────────────
# Password / Config Management
# ──────────────────────────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    """Hash a password using SHA-256.

    Args:
        password: The plaintext password.

    Returns:
        Hex digest of the SHA-256 hash.
    """
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def load_config() -> Optional[Config]:
    """Load the Phantom config from disk.

    Returns:
        A Config object if the file exists, otherwise None.

    Raises:
        PhantomConfigError: If the config file is corrupt.
    """
    if not CONFIG_FILE.exists():
        return None
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return Config(
            password_hash=data["password_hash"],
            version=data.get("version", VERSION),
            hidden_apps=data.get("hidden_apps", {}),
        )
    except (json.JSONDecodeError, KeyError) as exc:
        raise PhantomConfigError(f"Corrupt config file: {exc}") from exc


def save_config(config: Config) -> None:
    """Save the Phantom config to disk.

    Args:
        config: The Config object to persist.
    """
    PHANTOM_DIR.mkdir(parents=True, exist_ok=True)
    HIDDEN_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "password_hash": config.password_hash,
        "version": config.version,
        "hidden_apps": config.hidden_apps,
    }
    CONFIG_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def setup_password(recovered_hidden_apps: Optional[dict[str, str]] = None) -> Config:
    """Run first-time password setup.

    Args:
        recovered_hidden_apps: Optional dict of filename→original_path recovered
            from stashed .desktop files. Preserved into the new config.

    Returns:
        A new Config with the hashed password.

    Raises:
        PhantomAuthError: If the passwords don't match.
    """
    print_header("First-Time Setup")
    print_status("Create a master password to protect your hidden apps.\n", WHITE)

    pw1 = read_password("  🔑 New password: ")
    pw2 = read_password("  🔑 Confirm password: ")

    if pw1 != pw2:
        raise PhantomAuthError("Passwords do not match.")
    if len(pw1) < 4:
        raise PhantomAuthError("Password must be at least 4 characters.")

    config = Config(
        password_hash=hash_password(pw1),
        hidden_apps=recovered_hidden_apps or {},
    )
    save_config(config)
    print()
    print_status("✅  Password set. You can now use Phantom!", GREEN)
    print()
    return config


def change_password() -> None:
    """Change the master password interactively.

    Raises:
        PhantomAuthError: If the old password is wrong or new passwords don't match.
        PhantomConfigError: If no config exists yet.
    """
    config = load_config()
    if config is None:
        raise PhantomConfigError("No password configured yet. Run 'phantom' first.")

    print_header("Change Password")

    old_pw = read_password("  🔒 Current password: ")
    if hash_password(old_pw) != config.password_hash:
        raise PhantomAuthError("Current password is incorrect.")

    new_pw1 = read_password("  🔑 New password: ")
    new_pw2 = read_password("  🔑 Confirm new password: ")

    if new_pw1 != new_pw2:
        raise PhantomAuthError("New passwords do not match.")
    if len(new_pw1) < 4:
        raise PhantomAuthError("Password must be at least 4 characters.")

    config.password_hash = hash_password(new_pw1)
    save_config(config)
    print()
    print_status("✅  Password changed successfully!", GREEN)
    print()


def authenticate(config: Config) -> None:
    """Authenticate the user against the stored password hash.

    Args:
        config: The loaded Config object.

    Raises:
        PhantomAuthError: If authentication fails after MAX_PASSWORD_ATTEMPTS.
    """
    for attempt in range(1, MAX_PASSWORD_ATTEMPTS + 1):
        pw = read_password()
        if hash_password(pw) == config.password_hash:
            return
        remaining = MAX_PASSWORD_ATTEMPTS - attempt
        if remaining > 0:
            print_status(
                f"❌  Wrong password. {remaining} attempt{'s' if remaining != 1 else ''} remaining.",
                RED,
            )
        else:
            print_status("🚫  Too many failed attempts. Exiting.", RED)
            print()
            raise PhantomAuthError("Authentication failed after 3 attempts.")


# ──────────────────────────────────────────────────────────────────────────────
# Desktop File Parsing
# ──────────────────────────────────────────────────────────────────────────────


def parse_desktop_file(path: Path) -> Optional[DesktopApp]:
    """Parse a .desktop file and extract app metadata.

    Args:
        path: Path to the .desktop file.

    Returns:
        A DesktopApp if the file is a valid application, otherwise None.
    """
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except (PermissionError, OSError):
        return None

    name = ""
    exec_cmd = ""
    icon = ""
    app_type = ""
    no_display = False
    hidden = False
    in_desktop_entry = False

    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "[Desktop Entry]":
            in_desktop_entry = True
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_desktop_entry = False
            continue
        if not in_desktop_entry:
            continue

        if "=" not in stripped:
            continue

        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()

        if key == "Name" and not name:  # Take first Name= (default locale)
            name = value
        elif key == "Exec":
            exec_cmd = value
        elif key == "Icon":
            icon = value
        elif key == "Type":
            app_type = value
        elif key == "NoDisplay":
            no_display = value.lower() == "true"
        elif key == "Hidden":
            hidden = value.lower() == "true"

    if app_type != "Application" or not name or not exec_cmd:
        return None
    if no_display or hidden:
        return None

    return DesktopApp(
        name=name,
        exec_cmd=exec_cmd,
        icon=icon,
        filename=path.name,
        source_path=path,
    )


def clean_exec_cmd(exec_cmd: str) -> list[str]:
    """Clean an Exec= value from a .desktop file for subprocess execution.

    Strips field codes (%u, %U, %f, %F, %d, %D, %n, %N, %i, %c, %k, %v, %m)
    and returns a list of arguments suitable for subprocess.

    Args:
        exec_cmd: Raw Exec= value from a .desktop file.

    Returns:
        A list of command arguments.
    """
    field_codes = {
        "%u", "%U", "%f", "%F", "%d", "%D",
        "%n", "%N", "%i", "%c", "%k", "%v", "%m",
    }

    try:
        parts = shlex.split(exec_cmd)
    except ValueError:
        # Fallback for malformed Exec lines
        parts = exec_cmd.split()

    cleaned = [p for p in parts if p not in field_codes]
    return cleaned


# ──────────────────────────────────────────────────────────────────────────────
# App Discovery
# ──────────────────────────────────────────────────────────────────────────────


def discover_installed_apps() -> list[DesktopApp]:
    """Discover all visible installed applications.

    Scans both system and local .desktop file directories. If an app exists
    in both locations, the local version takes priority.

    Returns:
        A sorted list of DesktopApp objects for installed apps.
    """
    apps: dict[str, DesktopApp] = {}

    # System apps first (lower priority)
    if SYSTEM_APPS_DIR.is_dir():
        for desktop_file in sorted(SYSTEM_APPS_DIR.glob("*.desktop")):
            app = parse_desktop_file(desktop_file)
            if app:
                apps[app.filename] = app

    # Local apps override system apps (higher priority)
    if LOCAL_APPS_DIR.is_dir():
        for desktop_file in sorted(LOCAL_APPS_DIR.glob("*.desktop")):
            app = parse_desktop_file(desktop_file)
            if app:
                apps[app.filename] = app

    return sorted(apps.values(), key=lambda a: a.name.lower())


def discover_hidden_apps() -> list[DesktopApp]:
    """Discover all hidden (stashed) applications in Phantom's hidden dir.

    Returns:
        A sorted list of DesktopApp objects for hidden apps.
    """
    apps: list[DesktopApp] = []
    if not HIDDEN_DIR.is_dir():
        return apps

    for desktop_file in sorted(HIDDEN_DIR.glob("*.desktop")):
        app = parse_desktop_file_hidden(desktop_file)
        if app:
            apps.append(app)

    return sorted(apps, key=lambda a: a.name.lower())


def parse_desktop_file_hidden(path: Path) -> Optional[DesktopApp]:
    """Parse a .desktop file from the hidden directory.

    Unlike parse_desktop_file, this doesn't filter by NoDisplay/Hidden since
    the file is already stashed by us.

    Args:
        path: Path to the .desktop file in the hidden directory.

    Returns:
        A DesktopApp if parseable, otherwise None.
    """
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except (PermissionError, OSError):
        return None

    name = ""
    exec_cmd = ""
    icon = ""
    app_type = ""
    in_desktop_entry = False

    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "[Desktop Entry]":
            in_desktop_entry = True
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_desktop_entry = False
            continue
        if not in_desktop_entry:
            continue

        if "=" not in stripped:
            continue

        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()

        if key == "Name" and not name:
            name = value
        elif key == "Exec":
            exec_cmd = value
        elif key == "Icon":
            icon = value
        elif key == "Type":
            app_type = value

    if app_type != "Application" or not name or not exec_cmd:
        return None

    return DesktopApp(
        name=name,
        exec_cmd=exec_cmd,
        icon=icon,
        filename=path.name,
        source_path=path,
        is_hidden=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# App Hiding / Unhiding
# ──────────────────────────────────────────────────────────────────────────────


def _prepend_path_comment(desktop_file: Path, original_path: str) -> None:
    """Prepend a PHANTOM_ORIGINAL_PATH comment to a stashed .desktop file.

    Args:
        desktop_file: Path to the stashed .desktop file.
        original_path: The original absolute path of the .desktop file.
    """
    content = desktop_file.read_text(encoding="utf-8", errors="replace")
    comment_line = f"{PHANTOM_PATH_COMMENT_PREFIX}{original_path}\n"
    # Don't add duplicate comments
    if content.startswith(PHANTOM_PATH_COMMENT_PREFIX):
        # Replace existing comment line
        lines = content.splitlines(keepends=True)
        lines[0] = comment_line
        desktop_file.write_text("".join(lines), encoding="utf-8")
    else:
        desktop_file.write_text(comment_line + content, encoding="utf-8")


def _strip_path_comment(desktop_file: Path) -> None:
    """Remove the PHANTOM_ORIGINAL_PATH comment from a .desktop file.

    Called before restoring a file to its original location so the comment
    doesn't pollute the restored file.

    Args:
        desktop_file: Path to the stashed .desktop file.
    """
    content = desktop_file.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines(keepends=True)
    if lines and lines[0].startswith(PHANTOM_PATH_COMMENT_PREFIX):
        desktop_file.write_text("".join(lines[1:]), encoding="utf-8")


def recover_hidden_apps_metadata() -> dict[str, str]:
    """Scan ~/.phantom/hidden/ and recover original paths from stashed files.

    Reads the ``# PHANTOM_ORIGINAL_PATH=`` comment at the top of each stashed
    .desktop file to reconstruct the filename→original_path mapping.

    This is used when config.json is missing (e.g. user deleted it to reset
    their password) so hidden app metadata is not lost.

    Returns:
        A dict mapping .desktop filenames to their original absolute paths.
    """
    recovered: dict[str, str] = {}
    if not HIDDEN_DIR.is_dir():
        return recovered

    for desktop_file in sorted(HIDDEN_DIR.glob("*.desktop")):
        try:
            with desktop_file.open("r", encoding="utf-8", errors="replace") as f:
                first_line = f.readline().strip()
            if first_line.startswith(PHANTOM_PATH_COMMENT_PREFIX):
                original_path = first_line[len(PHANTOM_PATH_COMMENT_PREFIX):]
                if original_path:
                    recovered[desktop_file.name] = original_path
        except (PermissionError, OSError):
            continue

    return recovered


def refresh_desktop_database() -> None:
    """Run update-desktop-database to refresh the system's app index.

    Attempts to update both the system-wide and user-local databases.
    Failures are silently ignored (system db requires root).
    """
    # Update local database (user has permission)
    LOCAL_APPS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["update-desktop-database", str(LOCAL_APPS_DIR)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Attempt system database (will silently fail without root)
    try:
        subprocess.run(
            ["update-desktop-database", str(SYSTEM_APPS_DIR)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError):
        pass


def hide_app(app: DesktopApp) -> bool:
    """Hide an application by moving its .desktop file to the Phantom stash.

    If the app has both system and local .desktop files, the local one is
    moved and the system one is overridden with a NoDisplay=true stub.

    Args:
        app: The DesktopApp to hide.

    Returns:
        True if the app was hidden, False if it was already hidden.

    Raises:
        PhantomAppError: If the operation fails.
    """
    dest = HIDDEN_DIR / app.filename

    # Already hidden?
    if dest.exists():
        return False

    HIDDEN_DIR.mkdir(parents=True, exist_ok=True)

    source = app.source_path
    is_system_file = source.parent == SYSTEM_APPS_DIR
    local_path = LOCAL_APPS_DIR / app.filename

    try:
        if is_system_file:
            # Can't delete system file without root — create a local override
            # with NoDisplay=true AND stash the original to hidden/
            shutil.copy2(source, dest)

            # Create a local .desktop that hides it from the menu
            LOCAL_APPS_DIR.mkdir(parents=True, exist_ok=True)
            override_content = (
                "[Desktop Entry]\n"
                f"Name={app.name}\n"
                "Type=Application\n"
                "NoDisplay=true\n"
                "Hidden=true\n"
            )
            local_path.write_text(override_content, encoding="utf-8")
        else:
            # Local file — move it to hidden
            shutil.move(str(source), str(dest))

            # If a system .desktop with the same name exists, the system app
            # would re-emerge in the menu. Create a NoDisplay override.
            system_path = SYSTEM_APPS_DIR / app.filename
            if system_path.exists():
                LOCAL_APPS_DIR.mkdir(parents=True, exist_ok=True)
                override_content = (
                    "[Desktop Entry]\n"
                    f"Name={app.name}\n"
                    "Type=Application\n"
                    "NoDisplay=true\n"
                    "Hidden=true\n"
                )
                local_path.write_text(override_content, encoding="utf-8")

        # Prepend original-path comment to stashed file for recovery
        _prepend_path_comment(dest, str(source))

        # Record in config.json
        config = load_config()
        if config is not None:
            config.hidden_apps[app.filename] = str(source)
            save_config(config)

        refresh_desktop_database()
        return True
    except (PermissionError, OSError) as exc:
        raise PhantomAppError(f"Failed to hide '{app.name}': {exc}") from exc


def unhide_app(app: DesktopApp) -> bool:
    """Unhide an application by restoring its .desktop file.

    Args:
        app: The DesktopApp to unhide (must be in the hidden directory).

    Returns:
        True if the app was unhidden, False if it wasn't hidden.

    Raises:
        PhantomAppError: If the operation fails.
    """
    stashed = HIDDEN_DIR / app.filename

    if not stashed.exists():
        return False

    local_path = LOCAL_APPS_DIR / app.filename
    system_path = SYSTEM_APPS_DIR / app.filename

    try:
        # Determine the original source path to decide restore strategy.
        # Priority: config.json > embedded comment > fallback heuristic
        original_path_str = None
        config = load_config()
        if config is not None:
            original_path_str = config.hidden_apps.get(app.filename)

        if not original_path_str:
            # Try reading from the embedded comment
            try:
                first_line = stashed.read_text(encoding="utf-8", errors="replace").splitlines()[0]
                if first_line.startswith(PHANTOM_PATH_COMMENT_PREFIX):
                    original_path_str = first_line[len(PHANTOM_PATH_COMMENT_PREFIX):]
            except (IndexError, OSError):
                pass

        original_was_system = False
        original_was_local = False
        if original_path_str:
            original_source = Path(original_path_str)
            original_was_system = original_source.parent == SYSTEM_APPS_DIR
            original_was_local = original_source.parent == LOCAL_APPS_DIR

        if original_was_system or (not original_was_local and system_path.exists()):
            # Originally a system app — we copied it to stash and created
            # a local NoDisplay override. Remove override + delete stash.
            if local_path.exists():
                local_path.unlink()
            stashed.unlink()
        elif original_was_local:
            # Originally a local file — move it back.
            # If we created a NoDisplay override (because a system counterpart
            # exists), remove it first so our restored file takes its place.
            if local_path.exists() and system_path.exists():
                local_path.unlink()
            LOCAL_APPS_DIR.mkdir(parents=True, exist_ok=True)
            _strip_path_comment(stashed)
            shutil.move(str(stashed), str(local_path))
        else:
            # Fallback: no original path info. Use heuristic.
            if system_path.exists():
                # Likely a system app — remove override + delete stash
                if local_path.exists():
                    local_path.unlink()
                stashed.unlink()
            else:
                # Assume local
                LOCAL_APPS_DIR.mkdir(parents=True, exist_ok=True)
                _strip_path_comment(stashed)
                shutil.move(str(stashed), str(local_path))

        # Remove from config.json
        if config is not None and app.filename in config.hidden_apps:
            del config.hidden_apps[app.filename]
            save_config(config)

        refresh_desktop_database()
        return True
    except (PermissionError, OSError) as exc:
        raise PhantomAppError(f"Failed to unhide '{app.name}': {exc}") from exc


# ──────────────────────────────────────────────────────────────────────────────
# App Launching
# ──────────────────────────────────────────────────────────────────────────────


def launch_app(app: DesktopApp) -> None:
    """Launch an app silently in the background.

    Parses the Exec= field, strips field codes, and starts the process
    with all output suppressed so the terminal stays clean.

    Args:
        app: The DesktopApp to launch.

    Raises:
        PhantomAppError: If the app binary cannot be found or executed.
    """
    cmd = clean_exec_cmd(app.exec_cmd)
    if not cmd:
        raise PhantomAppError(f"Empty command for '{app.name}'.")

    try:
        devnull = subprocess.DEVNULL
        subprocess.Popen(
            cmd,
            stdout=devnull,
            stderr=devnull,
            stdin=devnull,
            start_new_session=True,
            # Don't inherit our environment changes
        )
    except FileNotFoundError:
        raise PhantomAppError(f"Binary not found: {cmd[0]}")
    except OSError as exc:
        raise PhantomAppError(f"Failed to launch '{app.name}': {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# UI: Main Launcher View
# ──────────────────────────────────────────────────────────────────────────────


def render_list(
    items: list[DesktopApp],
    selected: int,
    title: str,
) -> None:
    """Render a scrollable list of apps with the selected item highlighted.

    All output uses _print_line to clear trailing characters on soft redraws.

    Args:
        items: The list of DesktopApp objects to display.
        selected: Index of the currently selected item.
        title: Title displayed above the list.
    """
    _print_line(f"  {BOLD}{WHITE}{title}{RESET}")
    _print_line(f"  {DIM}{'─' * 50}{RESET}")

    if not items:
        _print_line(f"  {DIM}(empty){RESET}")
        _print_line()
        return

    # Determine visible window (show max 15 items at a time)
    max_visible = 15
    total = len(items)

    if total <= max_visible:
        start = 0
        end = total
    else:
        half = max_visible // 2
        start = max(0, selected - half)
        end = start + max_visible
        if end > total:
            end = total
            start = max(0, end - max_visible)

    if start > 0:
        _print_line(f"  {DIM}  ▲ {start} more above{RESET}")
    else:
        _print_line()  # Placeholder line to keep layout stable

    for i in range(start, end):
        app = items[i]
        prefix = "  ▸ " if i == selected else "    "
        if i == selected:
            _print_line(f"  {REVERSE}{CYAN}{prefix}{app.display_label()}{RESET}")
        else:
            _print_line(f"  {DIM}{prefix}{app.display_label()}{RESET}")

    if end < total:
        _print_line(f"  {DIM}  ▼ {total - end} more below{RESET}")
    else:
        _print_line()  # Placeholder line to keep layout stable

    _print_line()


def launcher_view() -> None:
    """Main launcher view showing hidden apps for selection and launch.

    Uses render→read→update loop with cursor-home soft redraws for
    flicker-free navigation.

    Controls:
        ↑/↓ — Navigate the list
        Enter — Launch the selected app
        m — Enter manage mode
        q — Quit
    """
    selected = 0
    need_full_redraw = True  # First render is always a full clear

    while True:
        hidden_apps = discover_hidden_apps()

        if not hidden_apps:
            # Empty state — no hidden apps yet
            print_header("Launcher", soft=not need_full_redraw)
            print_status("↑↓ Navigate  •  Enter Launch  •  m Manage  •  q Quit\n", DIM)
            print_status("No hidden apps yet. Press  m  to enter Manage Mode.", YELLOW)
            _print_line()
            sys.stdout.flush()
            need_full_redraw = True

            sys.stdout.write(HIDE_CURSOR)
            sys.stdout.flush()
            try:
                key = read_key()
            finally:
                sys.stdout.write(SHOW_CURSOR)
                sys.stdout.flush()

            if key in ("q", "Q", "CTRL_C"):
                return
            if key in ("m", "M"):
                manage_view()
                need_full_redraw = True
            continue

        # Clamp selection
        if selected >= len(hidden_apps):
            selected = max(0, len(hidden_apps) - 1)

        # ── Render once ──
        print_header("Launcher", soft=not need_full_redraw)
        print_status("↑↓ Navigate  •  Enter Launch  •  m Manage  •  q Quit\n", DIM)
        render_list(hidden_apps, selected, "🔒 Hidden Apps")
        sys.stdout.flush()
        need_full_redraw = False

        # ── Read one keypress ──
        sys.stdout.write(HIDE_CURSOR)
        sys.stdout.flush()
        try:
            key = read_key()
        finally:
            sys.stdout.write(SHOW_CURSOR)
            sys.stdout.flush()

        # ── Update state ──
        if key == "UP":
            selected = (selected - 1) % len(hidden_apps)
        elif key == "DOWN":
            selected = (selected + 1) % len(hidden_apps)
        elif key == "ENTER":
            app = hidden_apps[selected]
            try:
                launch_app(app)
                print_header("Launcher")
                print_status(f"🚀  Launched: {app.name}", GREEN)
                _print_line()
                sys.stdout.flush()
                time.sleep(1)
            except PhantomAppError as exc:
                print_header("Launcher")
                print_status(f"❌  {exc}", RED)
                _print_line()
                sys.stdout.flush()
                time.sleep(2)
            need_full_redraw = True
        elif key in ("m", "M"):
            manage_view()
            need_full_redraw = True  # Full redraw after returning from manage
        elif key in ("q", "Q", "CTRL_C"):
            return


# ──────────────────────────────────────────────────────────────────────────────
# UI: Manage View (Hide / Unhide)
# ──────────────────────────────────────────────────────────────────────────────


def manage_view() -> None:
    """Manage mode UI with two panels: Hidden apps and Installed apps.

    Uses render→read→update loop with cursor-home soft redraws for
    flicker-free navigation.

    Controls:
        ←/→ — Switch panel focus
        ↑/↓ — Navigate within the focused panel
        h — Hide the selected installed app
        u — Unhide the selected hidden app
        q — Go back to launcher
    """
    focus = 0  # 0 = hidden panel (left), 1 = installed panel (right)
    sel_hidden = 0
    sel_installed = 0
    status_msg = ""
    status_style = DIM
    need_full_redraw = True  # First render is always a full clear

    while True:
        hidden_apps = discover_hidden_apps()
        installed_apps = discover_installed_apps()

        # Filter out apps that are already hidden from the installed list
        hidden_filenames = {a.filename for a in hidden_apps}
        installed_apps = [a for a in installed_apps if a.filename not in hidden_filenames]

        # Clamp selections
        if sel_hidden >= len(hidden_apps):
            sel_hidden = max(0, len(hidden_apps) - 1)
        if sel_installed >= len(installed_apps):
            sel_installed = max(0, len(installed_apps) - 1)

        # ── Render once ──
        print_header("Manage Mode", soft=not need_full_redraw)
        print_status("←→ Switch Panel  •  ↑↓ Navigate  •  h Hide  •  u Unhide  •  q Back\n", DIM)

        if status_msg:
            print_status(status_msg, status_style)
        else:
            _print_line()  # Placeholder to keep layout stable
        _print_line()

        hidden_title = f"{'▸ ' if focus == 0 else '  '}🔒 Hidden Apps ({len(hidden_apps)})"
        installed_title = f"{'▸ ' if focus == 1 else '  '}📦 Installed Apps ({len(installed_apps)})"

        render_list(
            hidden_apps,
            sel_hidden if focus == 0 else -1,
            hidden_title,
        )

        render_list(
            installed_apps,
            sel_installed if focus == 1 else -1,
            installed_title,
        )
        sys.stdout.flush()
        need_full_redraw = False

        # ── Read one keypress ──
        sys.stdout.write(HIDE_CURSOR)
        sys.stdout.flush()
        try:
            key = read_key()
        finally:
            sys.stdout.write(SHOW_CURSOR)
            sys.stdout.flush()

        # ── Update state ──
        status_msg = ""

        if key in ("q", "Q", "CTRL_C"):
            return
        elif key == "LEFT":
            focus = 0
        elif key == "RIGHT":
            focus = 1
        elif key == "UP":
            if focus == 0 and hidden_apps:
                sel_hidden = (sel_hidden - 1) % len(hidden_apps)
            elif focus == 1 and installed_apps:
                sel_installed = (sel_installed - 1) % len(installed_apps)
        elif key == "DOWN":
            if focus == 0 and hidden_apps:
                sel_hidden = (sel_hidden + 1) % len(hidden_apps)
            elif focus == 1 and installed_apps:
                sel_installed = (sel_installed + 1) % len(installed_apps)
        elif key in ("h", "H"):
            if focus == 1 and installed_apps:
                app = installed_apps[sel_installed]
                try:
                    if hide_app(app):
                        status_msg = f"✅  Hidden: {app.name}"
                        status_style = GREEN
                    else:
                        status_msg = f"⚠️  Already hidden: {app.name}"
                        status_style = YELLOW
                except PhantomAppError as exc:
                    status_msg = f"❌  {exc}"
                    status_style = RED
                need_full_redraw = True  # List contents changed
            elif focus == 0:
                status_msg = "💡  Switch to Installed panel (→) to hide an app"
                status_style = YELLOW
        elif key in ("u", "U"):
            if focus == 0 and hidden_apps:
                app = hidden_apps[sel_hidden]
                try:
                    if unhide_app(app):
                        status_msg = f"✅  Unhidden: {app.name}"
                        status_style = GREEN
                    else:
                        status_msg = f"⚠️  Not hidden: {app.name}"
                        status_style = YELLOW
                except PhantomAppError as exc:
                    status_msg = f"❌  {exc}"
                    status_style = RED
                need_full_redraw = True  # List contents changed
            elif focus == 1:
                status_msg = "💡  Switch to Hidden panel (←) to unhide an app"
                status_style = YELLOW


# ──────────────────────────────────────────────────────────────────────────────
# Main Entry Point
# ──────────────────────────────────────────────────────────────────────────────


def check_root() -> None:
    """Check if running as root and warn/exit if so.

    Raises:
        SystemExit: If the effective user ID is 0 (root).
    """
    if os.geteuid() == 0:
        print(f"\n  {RED}{BOLD}⚠️  Do not run Phantom as root!{RESET}")
        print(f"  {DIM}Running as root could damage your system application database.{RESET}")
        print(f"  {DIM}Please run as a normal user.{RESET}\n")
        sys.exit(1)


def main() -> None:
    """Main entry point for the Phantom application."""
    # Handle Ctrl+C gracefully
    def signal_handler(sig: int, frame) -> None:
        """Handle interrupt signal cleanly."""
        sys.stdout.write(SHOW_CURSOR)
        sys.stdout.flush()
        print(f"\n\n  {DIM}👻  Phantom vanished.{RESET}\n")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Root check
    check_root()

    # Handle --change-password flag
    if len(sys.argv) > 1 and sys.argv[1] == "--change-password":
        try:
            change_password()
        except (PhantomAuthError, PhantomConfigError) as exc:
            print(f"\n  {RED}❌  {exc}{RESET}\n")
            sys.exit(1)
        sys.exit(0)

    # Load or create config
    try:
        config = load_config()
    except PhantomConfigError as exc:
        print(f"\n  {RED}❌  {exc}{RESET}\n")
        sys.exit(1)

    if config is None:
        # Attempt to recover hidden-app metadata before asking for new password
        recovered = recover_hidden_apps_metadata()
        if recovered:
            print_header("Recovery")
            print_status(
                f"🔍  Found {len(recovered)} hidden app(s) with recovery data.",
                GREEN,
            )
            print_status("Your hidden apps will be preserved.\n", DIM)

        # First-time / password-reset setup
        try:
            config = setup_password(recovered_hidden_apps=recovered or None)
        except PhantomAuthError as exc:
            print(f"\n  {RED}❌  {exc}{RESET}\n")
            sys.exit(1)

    # Authentication
    print_header("Authentication")
    assert config is not None
    try:
        authenticate(config)
    except PhantomAuthError as exc:
        print(f"\n  {RED}❌  {exc}{RESET}\n")
        sys.exit(1)

    # Launch the main UI
    try:
        launcher_view()
    finally:
        sys.stdout.write(SHOW_CURSOR)
        sys.stdout.flush()

    clear_screen()
    print(f"\n  {DIM}👻  Phantom vanished. Your secrets are safe.{RESET}\n")


if __name__ == "__main__":
    main()
