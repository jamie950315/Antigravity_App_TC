# Antigravity_App_TC

Traditional Chinese (`zh-TW`) localization toolkit for the Google Antigravity macOS desktop application (`/Applications/Antigravity.app`).

## Features

- **Full-Stack Localization (Electron Main + Web UI)**:
  - **Main Process (`dist/*.js`)**: Native macOS menu bar (`Antigravity`, `檔案`, `編輯`, `檢視`, `視窗`, `說明`), system tray menu and live agent count, auto-updater state machine (`MenuUpdateStep`), dock menu, native workspace dialogs, quit confirmation, and onboarding/WSL splash screens.
  - **Web UI (`dist/preload.js` DOM Runtime)**: Sidebar, workspace/branch management, Agent Manager, conversation list, model selector, settings pages (`General`, `Agent`, `Browser`, `Notifications`, `Tab`, `Account`), MCP Store, Skills, Plugins, Knowledge Base, and native right-click context menus (`electronAPI.showContextMenu`).
- **Content-Safe DOM Translation**:
  - Strictly excludes `.md-divider-spacing` (`CustomMarkdown` containers for AI responses, thinking blocks, and artifacts), user message bubbles, Lexical prompt editors, Monaco/CodeMirror code editors, and xterm terminals.
  - Preserves reasoning effort levels (`Low`, `Medium`, `High`, `Extra`, `Max`) in English.
  - Automatically coalesces and tracks multi-text-node React leaf elements without removing DOM nodes, keeping React 19 Fiber reconciliation intact.
- **Signature & `app.asar.unpacked` Preservation**:
  - Automatically detects and preserves `app.asar.unpacked` (`node_modules/chrome-devtools-mcp`, `node_modules/ws`) during `asar pack` and verifies header integrity.
  - Detects `@electron/fuses` `EnableEmbeddedAsarIntegrityValidation`: when disabled (default in Antigravity 2.23.0), preserves Google's original `Developer ID Application: Google LLC` signature so macOS TCC permissions and built-in auto-updates continue working; when enabled (or with `--resign`), updates `ElectronAsarIntegrity` in `Info.plist` and re-signs with `data/entitlements.plist`.
- **Offline Coverage Scanner for `language_server`**:
  - Decompresses the embedded frontend bundle (`main.js`) directly from `Contents/Resources/bin/language_server` in memory (`< 0.5s`) to report translation coverage and extract newly added UI strings across Antigravity updates.

## Requirements

- macOS with Google Antigravity installed at `/Applications/Antigravity.app`
- Python 3.10+
- Node.js (`asar` CLI or `npx @electron/asar`)

## Quick Start

```bash
# 1. Check status, dictionary statistics, and UI string coverage
./deploy.sh --check

# 2. Apply Traditional Chinese (zh-TW) localization and relaunch Antigravity
./deploy.sh

# 3. Patch without relaunching
./deploy.sh --no-launch

# 4. Restore original English app.asar
./deploy.sh --undo
```

To target a staged or custom app bundle without touching `/Applications/Antigravity.app`:

```bash
ANTIGRAVITY_APP=/path/to/Antigravity.app ./deploy.sh --no-launch
```

## Updating Translations After an Antigravity Upgrade

When Google Antigravity updates to a new version:

1. Run `./deploy.sh --check` to see how many new UI strings were introduced in the embedded `language_server` bundle.
2. Dump untranslated UI candidates:
   ```bash
   python3 lib/zhtw.py missing --json > /tmp/missing.json
   ```
3. Merge a JSON object of `{ "English": "繁體中文" }` pairs into `data/translations.json`:
   ```bash
   python3 lib/zhtw.py merge /tmp/new_translations.json
   ```
4. Re-run `./deploy.sh` (`deploy.sh` automatically detects that `app.asar` was replaced by an official update and refreshes `app.asar.bak` before patching).
