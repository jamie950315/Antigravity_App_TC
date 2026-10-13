#!/usr/bin/env bash
# Antigravity_App_TC — Traditional Chinese (zh-TW) Localization Deployer for Google Antigravity
#
# Usage:
#   ./deploy.sh              Patch Antigravity.app and relaunch
#   ./deploy.sh --no-launch  Patch without launching (or stopping if custom ANTIGRAVITY_APP)
#   ./deploy.sh --check      Show version, patch status, dictionary stats, and UI coverage
#   ./deploy.sh --undo       Restore original unpatched app.asar
#   ./deploy.sh --resign     Also update ElectronAsarIntegrity and ad-hoc re-sign bundle

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP="${ANTIGRAVITY_APP:-/Applications/Antigravity.app}"
CONTENTS="$APP/Contents"
RESOURCES="$CONTENTS/Resources"
ASAR="$RESOURCES/app.asar"
ASAR_UNPACKED="$RESOURCES/app.asar.unpacked"
ASAR_BAK="$RESOURCES/app.asar.bak"
ASAR_BAK_VER="$RESOURCES/app.asar.bak.version"
PLIST="$CONTENTS/Info.plist"
PLIST_BAK="$CONTENTS/Info.plist.bak"
ENTITLEMENTS="$SCRIPT_DIR/data/entitlements.plist"
ZHTW="$SCRIPT_DIR/lib/zhtw.py"
WORK="/tmp/antigravity_zhtw_$$"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERR]${NC}   $*" >&2; }

cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

if [ ! -d "$APP" ] || [ ! -f "$ASAR" ]; then
    err "Antigravity.app not found at $APP"
    exit 1
fi

APP_VER=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$PLIST" 2>/dev/null || echo "unknown")

is_patched() {
    python3 "$ZHTW" is-patched "$ASAR" >/dev/null 2>&1
}

find_asar_cmd() {
    if command -v asar >/dev/null 2>&1; then
        echo "asar"
    elif command -v npx >/dev/null 2>&1; then
        echo "npx --yes @electron/asar"
    else
        err "Neither 'asar' nor 'npx' found. Install Node.js or @electron/asar."
        exit 1
    fi
}

compute_asar_header_hash() {
    python3 -c "
import struct, hashlib
with open('$1', 'rb') as f:
    d = f.read(16)
    _, _, _, jl = struct.unpack('<IIII', d)
    hdr = f.read(jl).rstrip(b'\x00')
    print(hashlib.sha256(hdr).hexdigest())
"
}

stop_app() {
    if [ "$APP" != "/Applications/Antigravity.app" ]; then
        return 0
    fi
    if pgrep -f "/Applications/Antigravity.app/Contents/MacOS/Antigravity" >/dev/null 2>&1; then
        info "Stopping running Antigravity..."
        osascript -e 'tell application "Antigravity" to quit' 2>/dev/null || true
        for _ in $(seq 1 15); do
            pgrep -f "/Applications/Antigravity.app/Contents/MacOS/Antigravity" >/dev/null 2>&1 || break
            sleep 0.5
        done
        if pgrep -f "/Applications/Antigravity.app/Contents/MacOS/Antigravity" >/dev/null 2>&1; then
            killall "Antigravity" 2>/dev/null || true
            sleep 1
        fi
        ok "Antigravity stopped"
    fi
}

MODE="deploy"
LAUNCH=true
FORCE_RESIGN=false

for arg in "$@"; do
    case "$arg" in
        --check)     MODE="check" ;;
        --undo|--restore) MODE="undo" ;;
        --no-launch) LAUNCH=false ;;
        --resign)    FORCE_RESIGN=true ;;
        -h|--help)
            sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            err "Unknown option: $arg"
            exit 1
            ;;
    esac
done

if [ "$MODE" = "check" ]; then
    echo -e "${BOLD}Antigravity Traditional Chinese (zh-TW) Status${NC}"
    echo "  Target bundle:    $APP"
    echo "  App version:      $APP_VER"
    if is_patched; then
        echo -e "  Localization:     ${GREEN}Patched (zh-TW active)${NC}"
    else
        echo -e "  Localization:     ${YELLOW}Unpatched (original English)${NC}"
    fi
    if [ -f "$ASAR_BAK" ]; then
        BAK_VER="$(cat "$ASAR_BAK_VER" 2>/dev/null || echo "unknown")"
        echo "  Backup app.asar:  Present (version: $BAK_VER)"
    else
        echo "  Backup app.asar:  None"
    fi
    FUSE_VAL="$(python3 "$ZHTW" fuse-integrity "$APP")"
    if [ "$FUSE_VAL" = "0" ]; then
        echo "  Asar fuse check:  Disabled (original Google signature preserved)"
    else
        echo "  Asar fuse check:  Enabled (requires Info.plist hash + ad-hoc codesign)"
    fi
    echo ""
    python3 "$ZHTW" stats
    echo ""
    python3 "$ZHTW" missing "$APP"
    exit 0
fi

if [ "$MODE" = "undo" ]; then
    if [ ! -f "$ASAR_BAK" ]; then
        warn "No backup found at $ASAR_BAK — nothing to restore."
        exit 0
    fi
    stop_app
    cp -f "$ASAR_BAK" "$ASAR"
    rm -f "$ASAR_BAK" "$ASAR_BAK_VER"
    if [ -f "$PLIST_BAK" ]; then
        cp -f "$PLIST_BAK" "$PLIST"
        rm -f "$PLIST_BAK"
    fi
    xattr -cr "$APP" 2>/dev/null || true
    ok "Restored original Antigravity v$APP_VER"
    exit 0
fi

# Deploy mode
echo -e "${BOLD}Deploying Traditional Chinese (zh-TW) to Antigravity v$APP_VER${NC}"

if [ "$LAUNCH" = true ]; then
    stop_app
fi

# Refresh backup whenever current app.asar is clean/unpatched (handles official updates automatically)
if ! is_patched; then
    info "Creating clean backup of v$APP_VER app.asar..."
    cp -f "$ASAR" "$ASAR_BAK"
    echo "$APP_VER" > "$ASAR_BAK_VER"
    ok "Saved backup to $ASAR_BAK"
elif [ -f "$ASAR_BAK" ]; then
    info "Restoring clean v$APP_VER app.asar from backup before re-patching..."
    cp -f "$ASAR_BAK" "$ASAR"
else
    warn "app.asar is already patched and no backup exists; using current app.asar as base"
    cp -f "$ASAR" "$ASAR_BAK"
    echo "$APP_VER" > "$ASAR_BAK_VER"
fi

ASAR_CMD="$(find_asar_cmd)"
mkdir -p "$WORK"

info "Extracting app.asar..."
$ASAR_CMD extract "$ASAR" "$WORK/app"

# Strip any prior markers if backup was somehow already patched
python3 "$ZHTW" strip "$WORK/app"

info "Patching Electron main-process menus, tray, updater, and dialogs..."
python3 "$ZHTW" patch-main "$WORK/app"

info "Injecting DOM localization runtime into preload.js..."
python3 "$ZHTW" inject "$WORK/app"

info "Repacking app.asar..."
UNPACK_PATTERN="$(python3 "$ZHTW" unpack-pattern "$ASAR_BAK")"
if [ -n "$UNPACK_PATTERN" ]; then
    $ASAR_CMD pack "$WORK/app" "$WORK/app.asar" --unpack-dir "$UNPACK_PATTERN"
    rm -rf "$WORK/app.asar.unpacked"
else
    $ASAR_CMD pack "$WORK/app" "$WORK/app.asar"
fi
python3 "$ZHTW" verify-unpacked "$WORK/app.asar" "$ASAR_UNPACKED"

cp -f "$WORK/app.asar" "$ASAR"
ok "Updated $ASAR"

FUSE_ENABLED="$(python3 "$ZHTW" fuse-integrity "$APP")"
if [ "$FUSE_ENABLED" = "1" ] || [ "$FORCE_RESIGN" = true ]; then
    info "Updating ElectronAsarIntegrity hash and re-signing bundle..."
    [ ! -f "$PLIST_BAK" ] && cp -f "$PLIST" "$PLIST_BAK"
    NEW_HASH="$(compute_asar_header_hash "$ASAR")"
    /usr/libexec/PlistBuddy -c "Set :ElectronAsarIntegrity:Resources/app.asar:hash $NEW_HASH" "$PLIST" 2>/dev/null || true
    xattr -cr "$APP" 2>/dev/null || true
    codesign --force --sign - "$CONTENTS/Frameworks/Electron Framework.framework" 2>/dev/null || true
    for helper in "Antigravity Helper" "Antigravity Helper (GPU)" "Antigravity Helper (Plugin)" "Antigravity Helper (Renderer)"; do
        if [ -d "$CONTENTS/Frameworks/$helper.app" ]; then
            codesign --force --sign - --entitlements "$ENTITLEMENTS" "$CONTENTS/Frameworks/$helper.app" 2>/dev/null || true
        fi
    done
    codesign --force --sign - --entitlements "$ENTITLEMENTS" "$APP"
    ok "Bundle re-signed (SHA256: ${NEW_HASH:0:16}...)"
else
    info "EnableEmbeddedAsarIntegrityValidation is disabled; preserving original Google LLC code signature"
fi

echo ""
ok "Antigravity v$APP_VER Traditional Chinese localization deployed!"

if [ "$LAUNCH" = true ] && [ "$APP" = "/Applications/Antigravity.app" ]; then
    info "Launching Antigravity..."
    open "$APP"
fi
