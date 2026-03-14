# Phantom 👻

> A stealthy hidden app launcher for Linux Mint. Hide apps from Cinnamon's menu, search, taskbar, and Alt+F2 runner — then launch them privately from Phantom's terminal UI.

---

## Features

- 🔒 **Master password protection** — SHA-256 hashed, stored locally
- 👻 **True app hiding** — moves `.desktop` files out of the system index
- 🚀 **Silent launch** — runs hidden apps directly via their binary with suppressed output
- ⌨️ **Full keyboard navigation** — arrow keys, no mouse needed
- 📦 **Manage mode** — browse installed apps, hide/unhide with a keystroke
- 🐍 **Zero dependencies** — pure Python 3.10+ stdlib, no pip install needed
- 📄 **Single file** — the entire tool is one `phantom.py` script

---

## Installation

```bash
git clone https://github.com/ManuPanghal-DEV/Phantom.git
cd Phantom
chmod +x install.sh
./install.sh
```

The installer will:
1. Verify Python 3.10+ is available
2. Create `~/.phantom/` and `~/.phantom/hidden/` directories
3. Copy `phantom.py` to `/usr/local/bin/phantom` (requires `sudo`)

---

## Usage

### Launch Phantom

```bash
phantom
```

On first run, you'll be asked to create a master password.

### Change Password

```bash
phantom --change-password
```

---

## Controls

### Launcher View (after login)

| Key     | Action                    |
|---------|---------------------------|
| `↑` `↓` | Navigate hidden apps list |
| `Enter` | Launch selected app       |
| `m`     | Enter Manage Mode         |
| `q`     | Quit                      |

### Manage Mode

| Key     | Action                         |
|---------|--------------------------------|
| `←` `→` | Switch between panels          |
| `↑` `↓` | Navigate within panel          |
| `h`     | Hide selected installed app    |
| `u`     | Unhide selected hidden app     |
| `q`     | Back to launcher               |

---

## How It Works

### Hiding an App

1. The app's `.desktop` file is moved from `/usr/share/applications/` or `~/.local/share/applications/` into `~/.phantom/hidden/`
2. For system-level apps (owned by root), Phantom creates a local override with `NoDisplay=true` instead of trying to delete the system file
3. `update-desktop-database` is run to refresh Cinnamon's app index
4. The app disappears from the menu, search, taskbar, and Alt+F2

### Launching a Hidden App

1. Phantom reads the `Exec=` field from the stashed `.desktop` file
2. Field codes (`%u`, `%f`, etc.) are stripped
3. The binary is launched directly via `subprocess.Popen` with all I/O suppressed
4. The app runs in a new session — closing Phantom won't kill it

### Unhiding an App

1. The `.desktop` file is moved back to its original location
2. Any local `NoDisplay=true` overrides are removed
3. `update-desktop-database` is run to refresh the index
4. The app reappears in the system menu

---

## File Structure

```
~/.phantom/
├── config.json       # Password hash + hidden_apps metadata
└── hidden/           # Stashed .desktop files (with recovery comments)
```

---

## Security Notes

- Passwords are hashed with SHA-256 before storage (never stored in plaintext)
- Three wrong password attempts will lock you out and exit
- Phantom refuses to run as root to prevent accidental system damage
- Hidden apps are only hidden from the desktop environment — the binaries remain on disk

---

## Requirements

- **Linux **  any distro using Cinnamon/GNOME with `.desktop` file standards
- **Python 3.10+** (pre-installed on Linux Mint 21+)
- Terminal with ANSI escape code support (virtually every modern terminal)

---

## Troubleshooting

**App still shows in menu after hiding:**
Run `update-desktop-database ~/.local/share/applications/` manually, then restart Cinnamon (`cinnamon --replace &`).

**Phantom says "Binary not found":**
The app's `Exec=` path might be relative. Check the stashed `.desktop` file in `~/.phantom/hidden/` and verify the binary exists.

**Forgot your password:**
Delete `~/.phantom/config.json` and run `phantom` again. Phantom will auto-scan `~/.phantom/hidden/`, recover each app's original path from embedded comments, and preserve all hidden app metadata when you set a new password. No apps are lost.

---

## License

MIT — do whatever you want with it. 👻
