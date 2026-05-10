#!/usr/bin/env sh
# perskent installer — https://github.com/Alecell/Perskent
#
# One-liner:
#   curl -fsSL https://raw.githubusercontent.com/Alecell/Perskent/main/install.sh | sh
#
# Detects Python 3.11+, ensures pipx is available, installs perskent in
# an isolated pipx environment (no system-wide pollution), and verifies
# that `pskt` lands on PATH.

set -e

REPO_URL="https://github.com/Alecell/Perskent.git"
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=11

# --- colors --------------------------------------------------------------
red()    { printf '\033[0;31m%s\033[0m\n' "$1"; }
green()  { printf '\033[0;32m%s\033[0m\n' "$1"; }
yellow() { printf '\033[0;33m%s\033[0m\n' "$1"; }
cyan()   { printf '\033[0;36m%s\033[0m\n' "$1"; }

cyan "→ perskent installer"

# --- 1. detect Python 3.11+ ----------------------------------------------
PYTHON_BIN=""
for py in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$py" >/dev/null 2>&1; then
    ver=$("$py" -c 'import sys; print(sys.version_info[0], sys.version_info[1])' 2>/dev/null || echo "")
    if [ -n "$ver" ]; then
      major=$(echo "$ver" | awk '{print $1}')
      minor=$(echo "$ver" | awk '{print $2}')
      if [ "$major" -gt "$PYTHON_MIN_MAJOR" ] \
         || { [ "$major" -eq "$PYTHON_MIN_MAJOR" ] && [ "$minor" -ge "$PYTHON_MIN_MINOR" ]; }
      then
        PYTHON_BIN="$py"
        break
      fi
    fi
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  red "✗ Python ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}+ not found in PATH."
  yellow "  Install it before continuing:"
  echo "    macOS:         brew install python@3.12"
  echo "    Ubuntu/Debian: sudo apt install python3.12 python3.12-venv"
  echo "    Fedora:        sudo dnf install python3.12"
  echo "    Arch:          sudo pacman -S python"
  exit 1
fi
green "✓ Python: $($PYTHON_BIN --version 2>&1)"

# --- 2. ensure pipx ------------------------------------------------------
if ! command -v pipx >/dev/null 2>&1; then
  cyan "→ pipx not found, installing via pip --user..."

  # Ensure $PYTHON_BIN has its own pip (avoids picking up an older system pip
  # that may rely on distutils, removed in 3.12).
  "$PYTHON_BIN" -m ensurepip --upgrade --user >/dev/null 2>&1 || true

  # Try plain install first; fall back to --break-system-packages for distros
  # that enforce PEP 668 on the user site.
  if ! "$PYTHON_BIN" -m pip install --user --upgrade --quiet pipx 2>/dev/null; then
    if ! "$PYTHON_BIN" -m pip install --user --upgrade --quiet --break-system-packages pipx; then
      red "✗ Failed to install pipx."
      yellow "  Try manually:"
      echo "    $PYTHON_BIN -m ensurepip --upgrade --user"
      echo "    $PYTHON_BIN -m pip install --user pipx"
      exit 1
    fi
  fi

  # Add the per-user binary dir to PATH for the remainder of this script.
  USER_BIN="$("$PYTHON_BIN" -c 'import site, os; print(os.path.join(site.getuserbase(), "bin"))' 2>/dev/null || echo "$HOME/.local/bin")"
  if [ -d "$USER_BIN" ]; then
    case ":$PATH:" in
      *":$USER_BIN:"*) ;;
      *) PATH="$USER_BIN:$PATH"; export PATH ;;
    esac
  fi

  if ! command -v pipx >/dev/null 2>&1; then
    red "✗ pipx installed but not in PATH."
    yellow "  Add this to your shell rc:  export PATH=\"$USER_BIN:\$PATH\""
    yellow "  Reopen your terminal and run this script again."
    exit 1
  fi

  # Persist PATH for future shells.
  pipx ensurepath >/dev/null 2>&1 || true
fi
green "✓ pipx: $(pipx --version 2>/dev/null || echo 'available')"

# --- 3. install perskent -------------------------------------------------
cyan "→ Installing perskent (pipx install --force git+${REPO_URL})..."
if ! pipx install --force "git+${REPO_URL}"; then
  red "✗ Failed to install perskent via pipx."
  exit 1
fi

# pipx default bin dir — make sure it's reachable in this session.
PIPX_BIN="$HOME/.local/bin"
if [ -d "$PIPX_BIN" ]; then
  case ":$PATH:" in
    *":$PIPX_BIN:"*) ;;
    *) PATH="$PIPX_BIN:$PATH"; export PATH ;;
  esac
fi

# --- 4. verify -----------------------------------------------------------
if command -v pskt >/dev/null 2>&1; then
  green "✓ $(pskt --version)"
  echo
  cyan "Done. Next steps:"
  echo "  pskt init       # configure your remote registry (URL + token)"
  echo "  pskt --help     # list all commands"
else
  yellow "! perskent was installed but 'pskt' is not in PATH for this session."
  yellow "  Reopen your terminal and run 'pskt --version' to confirm."
fi
