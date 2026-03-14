#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Phantom 👻 — Installer Script
#
# Installs the Phantom hidden app launcher for Linux Mint.
#
# Usage:
#   chmod +x install.sh
#   ./install.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

CYAN='\033[36m'
GREEN='\033[32m'
RED='\033[31m'
YELLOW='\033[33m'
DIM='\033[2m'
BOLD='\033[1m'
RESET='\033[0m'

INSTALL_DIR="/usr/local/bin"
INSTALL_PATH="${INSTALL_DIR}/phantom"
PHANTOM_HOME="${HOME}/.phantom"
HIDDEN_DIR="${PHANTOM_HOME}/hidden"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_FILE="${SCRIPT_DIR}/phantom.py"

echo ""
echo -e "${CYAN}${BOLD}  ╔══════════════════════════════════════════════╗${RESET}"
echo -e "${CYAN}${BOLD}  ║     👻  Phantom — Installer                 ║${RESET}"
echo -e "${CYAN}${BOLD}  ╚══════════════════════════════════════════════╝${RESET}"
echo ""

# ── Checks ──────────────────────────────────────────────────────────────────

# Check if running as root
if [ "$(id -u)" -eq 0 ]; then
    echo -e "  ${RED}✗  Do not run the installer as root.${RESET}"
    echo -e "  ${DIM}The installer will use sudo only when needed.${RESET}"
    echo ""
    exit 1
fi

# Check Python 3.10+
if ! command -v python3 &>/dev/null; then
    echo -e "  ${RED}✗  Python 3 is not installed.${RESET}"
    echo -e "  ${DIM}Install it with: sudo apt install python3${RESET}"
    echo ""
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo -e "  ${RED}✗  Python 3.10+ required (found ${PYTHON_VERSION}).${RESET}"
    echo ""
    exit 1
fi

echo -e "  ${GREEN}✓${RESET}  Python ${PYTHON_VERSION} detected"

# Check source file exists
if [ ! -f "$SOURCE_FILE" ]; then
    echo -e "  ${RED}✗  phantom.py not found in ${SCRIPT_DIR}${RESET}"
    echo ""
    exit 1
fi

echo -e "  ${GREEN}✓${RESET}  Source file found"

# ── Install ─────────────────────────────────────────────────────────────────

# Create Phantom directories
mkdir -p "$PHANTOM_HOME"
mkdir -p "$HIDDEN_DIR"
echo -e "  ${GREEN}✓${RESET}  Created ${DIM}~/.phantom/${RESET} directories"

# Copy phantom.py to /usr/local/bin/phantom
echo -e "  ${DIM}  → Installing to ${INSTALL_PATH} (requires sudo)${RESET}"
sudo cp "$SOURCE_FILE" "$INSTALL_PATH"
sudo chmod +x "$INSTALL_PATH"
echo -e "  ${GREEN}✓${RESET}  Installed to ${BOLD}${INSTALL_PATH}${RESET}"

# ── Done ────────────────────────────────────────────────────────────────────

echo ""
echo -e "  ${GREEN}${BOLD}✅  Phantom installed successfully!${RESET}"
echo ""
echo -e "  ${BOLD}Usage:${RESET}"
echo -e "    ${CYAN}phantom${RESET}                    Launch Phantom"
echo -e "    ${CYAN}phantom --change-password${RESET}   Change master password"
echo ""
echo -e "  ${DIM}On first launch, you'll be prompted to set a master password.${RESET}"
echo -e "  ${DIM}Run 'phantom' now to get started! 👻${RESET}"
echo ""
