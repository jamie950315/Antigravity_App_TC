# Antigravity_App_TC

Traditional Chinese (`zh-TW`) localization toolkit for the Google Antigravity macOS desktop application (`/Applications/Antigravity.app`, v2.x architecture).

## Architecture Overview

Unlike Claude Desktop (which ships i18n JSON resources and Vite web assets inside `app.asar`), Google Antigravity 2.x uses a two-layer architecture:

1. **Electron Main & Preload Process (`Contents/Resources/app.asar`)**:
   - `dist/main.js`, `dist/menu.js`, `dist/tray.js`, `dist/updater.js`, `dist/ipcHandlers.js`, `dist/ideInstall/wizardHtml.js`, `dist/provisionSplash.js`: Control native macOS application menus, system tray, auto-updater state machine (`MenuUpdateStep`), dock menu, file dialogs, and onboarding splash windows.
   - `dist/preload.js`: Runs inside every `BrowserWindow` with direct DOM access (`document`, `MutationObserver`) and exposes `window.electronAPI` via `contextBridge`.
2. **Embedded Web UI (`Contents/Resources/bin/language_server`)**:
   - The React 19 + Tailwind CSS + Radix UI + Lexical + Monaco + xterm.js frontend (`main.js`, ~9.9 MB) is stored inside an embedded ZIP archive appended to the signed `language_server` Go binary and served over `https://127.0.0.1:<port>/`.
   - Modifying `language_server` directly would invalidate Google's code signature on the Go binary. Instead, `lib/zhtw.py` decompresses the embedded `main.js` in memory (via `zlib`) for offline string extraction and coverage analysis (`zhtw.py missing`), while `lib/inject.js` is injected into `dist/preload.js` to translate the live DOM and native right-click context menus (`electronAPI.showContextMenu`).

## Key Files

```
Antigravity_App_TC/
├── deploy.sh                # One-command deploy / check / undo pipeline
├── lib/
│   ├── zhtw.py              # CLI: inject, strip, patch-main, stats, missing, merge, unpack-pattern, verify-unpacked, fuse-integrity
│   ├── icu.py               # ICU MessageFormat & placeholder parser/validator/expander
│   └── inject.js            # DOM MutationObserver + rAF batching + coalesced multi-text-node translator
└── data/
    ├── translations.json    # Master EN -> zh-TW dictionary (exact strings + {var} templates)
    └── entitlements.plist   # macOS entitlements for optional ad-hoc re-signing (--resign)
```

## Critical Guardrails

- **Never corrupt AI responses, user prompts, or code editors**: `lib/inject.js` skips `.md-divider-spacing` (`CustomMarkdown` root for AI responses, thinking blocks, and artifacts), `.markdown-frontmatter`, `[data-testid="user-input-step"]`, `[data-testid="planner-response-text"]`, `[data-testid="pending-user-messages"]`, `[data-testid="side-question-question"]`, `[data-testid="side-question-answer"]`, `[contenteditable="true"]`, `[data-lexical-editor]`, `.monaco-editor`, `.cm-editor`, `.xterm`, `[data-testid="terminal-surface"]`, `[data-testid="setup-script-output"]`, `[data-testid="sidecar-logs-content"]`, `pre`, `code`, `textarea`, and `input`.
- **Keep reasoning effort levels in English**: `Low`, `Medium`, `High`, `Extra`, and `Max` are excluded from translation and guarded in `[data-testid^="model-selector-"]`.
- **Preserve `MenuUpdateStep` state machine**: In `dist/updater.js`, `updateActions` is keyed by `MenuUpdateStep.*`. Always patch `MenuUpdateStep` enum values in `dist/updater.js` rather than mutating the menu label in `dist/menu.js` alone, or clicking "Check for Updates" becomes a no-op.
- **Preserve `app.asar.unpacked`**: Always pass `--unpack-dir "$(python3 lib/zhtw.py unpack-pattern ...)"` when running `asar pack` and verify with `python3 lib/zhtw.py verify-unpacked` so unpacked native/MCP modules (`node_modules/chrome-devtools-mcp`, `node_modules/ws`) keep working.
- **Preserve Google LLC code signature when `EnableEmbeddedAsarIntegrityValidation` is disabled**: In Antigravity 2.23.0, the `@electron/fuses` wire has `EnableEmbeddedAsarIntegrityValidation = 0`. `deploy.sh` checks `zhtw.py fuse-integrity` and leaves `Info.plist` and the `Developer ID Application: Google LLC (EQHXZ8M8AV)` signature untouched unless the fuse is enabled in a future release or `--resign` is explicitly passed.

## Translation Style Rules (Taiwan Traditional Chinese `zh-TW`)

| English | Correct (`zh-TW`) | Avoid (`zh-CN`) |
|---|---|---|
| Settings | 設定 | 設置 |
| File / Files | 檔案 | 文件 |
| Folder / Directory | 資料夾 / 目錄 | 文件夾 |
| Server | 伺服器 | 服務器 |
| Account | 帳號 | 帳戶 |
| Default | 預設 | 默認 |
| Connection / Connect | 連線 | 連接 |
| Log / Logs | 記錄 | 日誌 |
| Copy / Paste / Cut / Undo | 複製 / 貼上 / 剪下 / 復原 | 拷貝 / 粘貼 / 剪切 / 撤銷 |
| Permission | 權限 | 許可權 |
| Terminal | 終端機 | 終端 |
| Workspace | 工作區 | 工作空間 |
| Extension / Plugin | 擴充功能 / 外掛 | 擴展 / 插件 |
| Code | 程式碼 | 代碼 |

- Use formal 「您」 for "you/your".
- Keep brand names and technical terms in original English (`Antigravity`, `Agent`, `MCP`, `Git`, `GitHub`, `WSL`, `SSH`, `Worktree`, `PR`, `Commit`, `Branch`, `Token`, `API`, `URL`, `CLI`, `IDE`, `Chrome`, `DevTools`, `Sandbox`, `Sidecar`, `Subagent`).
- Do not add single lowercase common words (such as `and`, `or`, `in`, `around`) to `data/translations.json`.

## Common Commands

```bash
# Check current app status, dictionary stats, and Web UI coverage
./deploy.sh --check

# Deploy localization to /Applications/Antigravity.app
./deploy.sh

# Patch without stopping/relaunching (or test against a staged bundle via ANTIGRAVITY_APP=...)
ANTIGRAVITY_APP=/path/to/Antigravity.app ./deploy.sh --no-launch

# Restore original unpatched app.asar
./deploy.sh --undo

# Extract untranslated UI strings from a new Antigravity release
python3 lib/zhtw.py missing --json > /tmp/missing.json

# Validate and merge new translations into data/translations.json
python3 lib/zhtw.py merge /tmp/new_translations.json
```
