#!/usr/bin/env python3
"""Antigravity_App_TC — Traditional Chinese (zh-TW) localization toolkit for Google Antigravity."""

import glob
import json
import os
import re
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import icu  # noqa: E402

TRANS_FILE = os.path.join(ROOT, "data", "translations.json")
INJECT_TEMPLATE = os.path.join(ROOT, "lib", "inject.js")

START_MARK = "/*__AGZHTW_START__*/"
END_MARK = "/*__AGZHTW_END__*/"

DEFAULT_APP = "/Applications/Antigravity.app"

# Placeholder regex for template strings such as "{count}Running" or "{x1} items"
_PH_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")

# Effort levels that must remain in English in the model selector UI
EFFORT_LEVELS = {"Low", "Medium", "High", "Extra", "Max"}


def load_translations() -> dict[str, str]:
    with open(TRANS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def save_translations(d: dict[str, str]):
    ordered = dict(sorted(d.items(), key=lambda kv: kv[0]))
    with open(TRANS_FILE, "w", encoding="utf-8") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _template_to_regex(en_pat: str, zh_pat: str):
    """Compile a '{var}' template pair into (prefix_key, js_regex_literal, js_replacement)."""
    en_parts = re.split(r"(\{[a-zA-Z0-9_]+\})", en_pat)
    ph_order = []
    regex_parts = []
    literal_len = 0

    for part in en_parts:
        if not part:
            continue
        m = _PH_RE.fullmatch(part)
        if m:
            ph_order.append(m.group(1))
            regex_parts.append("(.+?)")
        else:
            literal_len += len(part.strip())
            escaped = re.sub(r"([.*+?^${}()|[\]\\\/])", r"\\\1", part)
            regex_parts.append(escaped)

    if not ph_order or literal_len < 2:
        return None

    # Build JS replacement string ($1, $2, ...)
    zh_rep = zh_pat
    for idx, name in enumerate(ph_order, 1):
        zh_rep = zh_rep.replace(f"{{{name}}}", f"${idx}")

    # If there are still unresolved placeholders in zh_rep, skip
    if _PH_RE.search(zh_rep):
        return None

    first_part = en_parts[0]
    prefix = first_part[:3] if (first_part and not _PH_RE.match(first_part) and len(first_part) >= 3) else None
    js_re = f"/^{''.join(regex_parts)}$/"
    return prefix, js_re, zh_rep


def build_runtime_payload(trans: dict[str, str]) -> tuple[dict[str, str], str]:
    """Split translations into exact lookup table T and bucketed regex expression P."""
    exact: dict[str, str] = {}
    template_pairs: list[tuple[str, str]] = []

    for en, zh in trans.items():
        if not en or not zh or en == zh or en in EFFORT_LEVELS:
            continue
        if ", plural," in en or ", select," in en or ", selectordinal," in en:
            for ep, zp in icu.expand_plural_to_templates(en, zh):
                if _PH_RE.search(ep):
                    template_pairs.append((ep, zp))
                elif ep != zp:
                    exact[ep] = zp
        elif _PH_RE.search(en):
            template_pairs.append((en, zh))
            # Also add exact entry in case the literal placeholder string itself appears
            exact[en] = zh
        else:
            exact[en] = zh

    buckets: dict[str, list[tuple[str, str]]] = {}
    fallback: list[tuple[str, str]] = []
    seen_re = set()

    # Sort longer literal templates first so specific patterns match before general ones
    template_pairs.sort(key=lambda pair: len(_PH_RE.sub("", pair[0])), reverse=True)

    for ep, zp in template_pairs:
        compiled = _template_to_regex(ep, zp)
        if not compiled:
            continue
        prefix, js_re, zh_rep = compiled
        if js_re in seen_re:
            continue
        seen_re.add(js_re)
        if prefix:
            buckets.setdefault(prefix, []).append((js_re, zh_rep))
        else:
            fallback.append((js_re, zh_rep))

    bucket_entries = []
    for k, items in sorted(buckets.items()):
        arr = ",".join(f"[{r},{json.dumps(rep, ensure_ascii=False)}]" for r, rep in items)
        bucket_entries.append(f"{json.dumps(k, ensure_ascii=False)}:[{arr}]")

    fb_arr = ",".join(f"[{r},{json.dumps(rep, ensure_ascii=False)}]" for r, rep in fallback)
    patterns_js = "{b:{" + ",".join(bucket_entries) + "},f:[" + fb_arr + "]}"
    return exact, patterns_js


def build_inject_js(trans: dict[str, str]) -> str:
    with open(INJECT_TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    exact, patterns_js = build_runtime_payload(trans)
    code = tpl.replace("__TRANSLATIONS__", json.dumps(exact, ensure_ascii=False, separators=(",", ":")))
    code = code.replace("__PATTERNS__", patterns_js)
    return f"\n{START_MARK}\n{code.strip()}\n{END_MARK}\n"


def _resolve_preload_targets(args: list[str]) -> list[str]:
    targets = []
    for arg in args:
        if os.path.isdir(arg):
            candidate = os.path.join(arg, "dist", "preload.js")
            if os.path.isfile(candidate):
                targets.append(candidate)
            else:
                for p in glob.glob(os.path.join(arg, "**", "preload.js"), recursive=True):
                    if "node_modules" not in p:
                        targets.append(p)
        elif os.path.isfile(arg):
            targets.append(arg)
    return targets


_CTX_MENU_ORIG = "showContextMenu: (items) => electron_1.ipcRenderer.invoke('window:show-context-menu', items),"
_CTX_MENU_HOOK = (
    "showContextMenu: (items) => electron_1.ipcRenderer.invoke("
    "'window:show-context-menu', globalThis.__agzhtw_menu ? globalThis.__agzhtw_menu(items) : items),"
)


def strip_content(content: str) -> str:
    while START_MARK in content and END_MARK in content:
        s = content.index(START_MARK)
        e = content.index(END_MARK) + len(END_MARK)
        while s > 0 and content[s - 1] == "\n":
            s -= 1
        content = content[:s] + content[e:]
    content = content.replace(_CTX_MENU_HOOK, _CTX_MENU_ORIG)
    return content


def cmd_inject(args: list[str]):
    targets = _resolve_preload_targets(args)
    if not targets:
        print("Error: no preload.js target found", file=sys.stderr)
        sys.exit(1)
    trans = load_translations()
    snippet = build_inject_js(trans)
    for path in targets:
        with open(path, encoding="utf-8") as f:
            content = strip_content(f.read())
        if _CTX_MENU_ORIG in content:
            content = content.replace(_CTX_MENU_ORIG, _CTX_MENU_HOOK, 1)
        content = content.rstrip() + snippet
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  Injected: {os.path.basename(path)} ({len(trans)} dictionary entries)")


def cmd_strip(args: list[str]):
    targets = _resolve_preload_targets(args)
    for path in targets:
        with open(path, encoding="utf-8") as f:
            orig = f.read()
        cleaned = strip_content(orig)
        if cleaned != orig:
            with open(path, "w", encoding="utf-8") as f:
                f.write(cleaned)
            print(f"  Stripped: {os.path.basename(path)}")


def cmd_patch_main(args: list[str]):
    """Patch Electron main-process JS files (menu, updater, tray, main, ipcHandlers, wizardHtml, provisionSplash)."""
    if not args:
        print("Usage: zhtw.py patch-main <extracted_app_dir>", file=sys.stderr)
        sys.exit(1)
    app_dir = args[0]
    dist_dir = os.path.join(app_dir, "dist") if os.path.isdir(os.path.join(app_dir, "dist")) else app_dir
    trans = load_translations()

    patched_files = 0

    # 1. dist/updater.js: Patch MenuUpdateStep enum values & dialog messages so updateActions lookup stays intact
    updater_path = os.path.join(dist_dir, "updater.js")
    if os.path.isfile(updater_path):
        with open(updater_path, encoding="utf-8") as f:
            src = orig = f.read()
        updater_replacements = [
            ('MenuUpdateStep["CheckForUpdates"] = "Check for Updates";', 'MenuUpdateStep["CheckForUpdates"] = "檢查更新";'),
            ('MenuUpdateStep["CheckingForUpdates"] = "Checking for Updates...";', 'MenuUpdateStep["CheckingForUpdates"] = "正在檢查更新...";'),
            ('MenuUpdateStep["DownloadingUpdate"] = "Downloading Update...";', 'MenuUpdateStep["DownloadingUpdate"] = "正在下載更新...";'),
            ('MenuUpdateStep["RestartToUpdate"] = "Restart to Update";', 'MenuUpdateStep["RestartToUpdate"] = "重新啟動以更新";'),
            ("title: 'Check for Updates',", "title: '檢查更新',"),
            ("message: 'No updates available',", "message: '目前已是最新版本',"),
        ]
        for old, new in updater_replacements:
            src = src.replace(old, new)
        if src != orig:
            with open(updater_path, "w", encoding="utf-8") as f:
                f.write(src)
            patched_files += 1
            print("  Patched: dist/updater.js")

    # 2. dist/menu.js: Translate native macOS application menu items before Menu.setApplicationMenu(menu)
    menu_path = os.path.join(dist_dir, "menu.js")
    if os.path.isfile(menu_path):
        with open(menu_path, encoding="utf-8") as f:
            src = orig = f.read()
        menu_dict = {
            "About Antigravity": "關於 Antigravity",
            "Settings...": "設定...",
            "Services": "服務",
            "Hide Antigravity": "隱藏 Antigravity",
            "Hide Others": "隱藏其他",
            "Show All": "顯示全部",
            "Quit Antigravity": "結束 Antigravity",
            "Quit": "結束 Antigravity",
            "File": "檔案",
            "New Window": "新增視窗",
            "Close Window": "關閉視窗",
            "Edit": "編輯",
            "Undo": "復原",
            "Redo": "重做",
            "Cut": "剪下",
            "Copy": "複製",
            "Paste": "貼上",
            "Paste and Match Style": "貼上並符合樣式",
            "Delete": "刪除",
            "Select All": "全選",
            "Substitutions": "替換",
            "Show Substitutions": "顯示替換",
            "Smart Copy/Paste": "智慧型複製/貼上",
            "Smart Quotes": "智慧型引號",
            "Smart Dashes": "智慧型破折號",
            "Smart Links": "智慧型連結",
            "Data Detectors": "資料偵測器",
            "Text Replacement": "文字替換",
            "Transformations": "轉換",
            "Make Upper Case": "轉為大寫",
            "Make Lower Case": "轉為小寫",
            "Capitalize": "首字大寫",
            "Speech": "語音",
            "Start Speaking": "開始朗讀",
            "Stop Speaking": "停止朗讀",
            "View": "檢視",
            "Reload": "重新載入",
            "Force Reload": "強制重新載入",
            "Toggle Developer Tools": "切換開發人員工具",
            "Actual Size": "實際大小",
            "Zoom In": "放大",
            "Zoom Out": "縮小",
            "Toggle Full Screen": "切換全螢幕",
            "Window": "視窗",
            "Minimize": "最小化",
            "Zoom": "縮放",
            "Bring All to Front": "將此程式所有視窗移至最前",
            "Help": "說明",
            "Open Legacy Antigravity IDE": "開啟舊版 Antigravity IDE",
            "Restart Language Server": "重新啟動 Language Server",
            "Diagnostic Tools": "診斷工具",
            "Open Logs Folder": "開啟記錄資料夾",
            "Clear Supercomplete Cache": "清除 Supercomplete 快取",
            "Report Issue": "回報問題",
            "Reset Onboarding": "重設引導流程",
        }
        for k, v in trans.items():
            if len(k) < 40 and "\n" not in k and "{" not in k:
                menu_dict.setdefault(k, v)
        menu_hook = (
            f"{START_MARK}\n"
            f"    const __agMenuMap = {json.dumps(menu_dict, ensure_ascii=False)};\n"
            "    const __agTranslateMenu = (m) => {\n"
            "        if (!m || !m.items) return;\n"
            "        for (const item of m.items) {\n"
            "            if (item.label && __agMenuMap[item.label]) item.label = __agMenuMap[item.label];\n"
            "            if (item.submenu) __agTranslateMenu(item.submenu);\n"
            "        }\n"
            "    };\n"
            "    __agTranslateMenu(menu);\n"
            f"    {END_MARK}\n"
            "    electron_1.Menu.setApplicationMenu(menu);"
        )
        src = strip_content(src)
        if "electron_1.Menu.setApplicationMenu(menu);" in src:
            src = src.replace("electron_1.Menu.setApplicationMenu(menu);", menu_hook, 1)
        if src != orig:
            with open(menu_path, "w", encoding="utf-8") as f:
                f.write(src)
            patched_files += 1
            print("  Patched: dist/menu.js")

    # 3. dist/tray.js: Patch dynamic agent count
    tray_path = os.path.join(dist_dir, "tray.js")
    if os.path.isfile(tray_path):
        with open(tray_path, encoding="utf-8") as f:
            src = orig = f.read()
        old_tray_block = (
            "            countItem.label =\n"
            "                (count > 0 ? `${count}` : 'No') +\n"
            "                    ' agent' +\n"
            "                    (count === 1 ? '' : 's') +\n"
            "                    ' running';"
        )
        new_tray_block = (
            "            countItem.label = count > 0 ? `${count} 個 Agent 運作中` : '無正在運作的 Agent';"
        )
        src = src.replace(old_tray_block, new_tray_block)
        if src != orig:
            with open(tray_path, "w", encoding="utf-8") as f:
                f.write(src)
            patched_files += 1
            print("  Patched: dist/tray.js")

    # 4. dist/main.js: Patch dock menu, tray init, quit confirmation, and startup error dialogs
    main_path = os.path.join(dist_dir, "main.js")
    if os.path.isfile(main_path):
        with open(main_path, encoding="utf-8") as f:
            src = orig = f.read()
        main_replacements = [
            ("label: 'New Window',", "label: '新增視窗',"),
            ("runningAgents: 'No agent(s) running',", "runningAgents: '無正在運作的 Agent',"),
            ("showWindow: 'Show Antigravity',", "showWindow: '顯示 Antigravity',"),
            ("quit: 'Quit',", "quit: '結束 Antigravity',"),
            ("title: 'Confirm Quit',", "title: '確認結束',"),
            ("message: 'Are you sure you want to quit?',", "message: '確定要結束 Antigravity 嗎？',"),
            (
                "detail: 'There may be agents or background tasks running.',",
                "detail: '目前可能仍有 Agent 或背景任務正在執行。',",
            ),
            ("buttons: ['Cancel', 'Quit'],", "buttons: ['取消', '結束'],"),
            ("title: 'Startup Error',", "title: '啟動錯誤',"),
            ("buttons: ['Close'],", "buttons: ['關閉'],"),
            ("title: 'WSL Error',", "title: 'WSL 錯誤',"),
            ("buttons: ['OK'],", "buttons: ['確定'],"),
        ]
        for old, new in main_replacements:
            src = src.replace(old, new)
        if src != orig:
            with open(main_path, "w", encoding="utf-8") as f:
                f.write(src)
            patched_files += 1
            print("  Patched: dist/main.js")

    # 5. dist/ipcHandlers.js: Patch native open dialog titles & WSL path messages
    ipc_path = os.path.join(dist_dir, "ipcHandlers.js")
    if os.path.isfile(ipc_path):
        with open(ipc_path, encoding="utf-8") as f:
            src = orig = f.read()
        ipc_replacements = [
            ("title: 'Open workspace',", "title: '開啟工作區',"),
            ("title: 'Open workspaces',", "title: '開啟工作區',"),
            ("showErrorBox('Cannot open folder',", "showErrorBox('無法開啟資料夾',"),
            ("message: 'Folder is on the Windows filesystem',", "message: '資料夾位於 Windows 檔案系統中',"),
        ]
        for old, new in ipc_replacements:
            src = src.replace(old, new)
        if src != orig:
            with open(ipc_path, "w", encoding="utf-8") as f:
                f.write(src)
            patched_files += 1
            print("  Patched: dist/ipcHandlers.js")

    # 6. dist/ideInstall/wizardHtml.js & dist/provisionSplash.js
    wizard_path = os.path.join(dist_dir, "ideInstall", "wizardHtml.js")
    if os.path.isfile(wizard_path):
        with open(wizard_path, encoding="utf-8") as f:
            src = orig = f.read()
        wizard_replacements = [
            ("<title>Welcome to Antigravity</title>", "<title>歡迎使用 Antigravity</title>"),
            (">Setting up…</div>", ">正在設定…</div>"),
            ("<h1>Welcome to the new Antigravity!</h1>", "<h1>歡迎使用全新 Antigravity！</h1>"),
            (
                "<p>Antigravity has been redesigned to put agents first with new capabilities. If you'd still like a code editor, you can download it as a separate app named <b>Antigravity IDE</b>.</p>",
                "<p>Antigravity 已重新設計為以 Agent 為核心的全新體驗。如果您仍需要使用程式碼編輯器，可以將其下載為名為 <b>Antigravity IDE</b> 的獨立應用程式。</p>",
            ),
            ("<span>Download the Antigravity IDE</span>", "<span>下載 Antigravity IDE</span>"),
            (">Explore the new Antigravity</button>", ">探索全新 Antigravity</button>"),
        ]
        for old, new in wizard_replacements:
            src = src.replace(old, new)
        if src != orig:
            with open(wizard_path, "w", encoding="utf-8") as f:
                f.write(src)
            patched_files += 1
            print("  Patched: dist/ideInstall/wizardHtml.js")

    splash_path = os.path.join(dist_dir, "provisionSplash.js")
    if os.path.isfile(splash_path):
        with open(splash_path, encoding="utf-8") as f:
            src = orig = f.read()
        splash_replacements = [
            ("<div>Setting up WSL: ${escapeHtml(distro)}</div>", "<div>正在設定 WSL：${escapeHtml(distro)}</div>"),
        ]
        for old, new in splash_replacements:
            src = src.replace(old, new)
        if src != orig:
            with open(splash_path, "w", encoding="utf-8") as f:
                f.write(src)
            patched_files += 1
            print("  Patched: dist/provisionSplash.js")

    print(f"  Main-process patching complete ({patched_files} files updated)")


def cmd_stats():
    trans = load_translations()
    exact_count = 0
    template_count = 0
    icu_errors = []

    for en, zh in trans.items():
        if _PH_RE.search(en) or ", plural," in en or ", select," in en:
            template_count += 1
            errs = icu.validate_pair(en, zh)
            if errs:
                icu_errors.append((en, errs))
        else:
            exact_count += 1

    print(f"Total translations: {len(trans)}")
    print(f"  Exact UI strings: {exact_count}")
    print(f"  Template/ICU:     {template_count}")
    if icu_errors:
        print(f"  ICU/Placeholder warnings ({len(icu_errors)}):")
        for k, errs in icu_errors[:10]:
            print(f"    - {k!r}: {', '.join(errs)}")
    else:
        print("  ICU/Placeholder validation: 100% passed")


def _extract_web_bundle_from_language_server(ls_path: str) -> str | None:
    """Decompress the embedded main.js frontend bundle directly from the tail of language_server."""
    if not os.path.isfile(ls_path):
        return None
    size = os.path.getsize(ls_path)
    tail_size = min(size, 32 * 1024 * 1024)
    with open(ls_path, "rb") as f:
        f.seek(size - tail_size)
        data = f.read(tail_size)
    pos = 0
    while True:
        idx = data.find(b"PK\x03\x04", pos)
        if idx == -1:
            break
        if idx + 30 <= len(data):
            _, _, _, method, _, _, _, comp_size, _, name_len, extra_len = struct.unpack(
                "<4sHHHHHIIIHH", data[idx : idx + 30]
            )
            name = data[idx + 30 : idx + 30 + name_len].decode("utf-8", "replace")
            if name == "main.js" and comp_size > 100000:
                data_start = idx + 30 + name_len + extra_len
                comp_data = data[data_start : data_start + comp_size]
                if method == 8:
                    return zlib.decompress(comp_data, -15).decode("utf-8", "replace")
                elif method == 0:
                    return comp_data.decode("utf-8", "replace")
        pos = idx + 4
    return None


def _extract_ui_strings_from_web_js(js: str) -> set[str]:
    found = set()
    for m in re.finditer(r'children:\s*"([^"\\\n]{2,120})"', js):
        found.add(m.group(1))
    for m in re.finditer(r"children:\s*'([^'\\\n]{2,120})'", js):
        found.add(m.group(1))
    for m in re.finditer(
        r'(?:label|title|placeholder|description|tooltip|aria-label|header|emptyText|confirmText|cancelText):\s*"([^"\\\n]{2,120})"',
        js,
    ):
        found.add(m.group(1))
    for m in re.finditer(
        r"(?:label|title|placeholder|description|tooltip|aria-label|header|emptyText|confirmText|cancelText):\s*'([^'\\\n]{2,120})'",
        js,
    ):
        found.add(m.group(1))

    clean = set()
    for s in found:
        s = s.strip()
        if len(s) < 2 or len(s) > 100:
            continue
        if not re.search(r"[A-Za-z]{2,}", s):
            continue
        if s in EFFORT_LEVELS:
            continue
        if s.startswith(("http", "/", ".", "--", "var(", "rgb", "hsl", "data-", "moz-", "webkit-", "vscode-", "antigravity://")):
            continue
        if re.match(r"^[a-z0-9_.:/-]+$", s):
            continue
        if re.search(r"[{}[\]()=>;$\\]", s) and not _PH_RE.search(s):
            continue
        if any(
            x in s
            for x in (
                "px",
                "rem",
                "vh",
                "vw",
                "flex-",
                "grid-",
                "text-",
                "bg-",
                "border-",
                "items-",
                "justify-",
                "cursor-",
                "opacity-",
            )
        ):
            continue
        if not s[0].isupper():
            continue
        clean.add(s)
    return clean


def cmd_missing(args: list[str]):
    as_json = "--json" in args
    pos_args = [a for a in args if a != "--json"]
    app_path = pos_args[0] if pos_args else os.environ.get("ANTIGRAVITY_APP", DEFAULT_APP)

    ls_path = os.path.join(app_path, "Contents", "Resources", "bin", "language_server")
    js = _extract_web_bundle_from_language_server(ls_path)
    if not js:
        print(f"Error: could not read embedded web bundle from {ls_path}", file=sys.stderr)
        sys.exit(1)

    ui_strings = _extract_ui_strings_from_web_js(js)
    trans = load_translations()

    translated = []
    untranslated = []
    for s in sorted(ui_strings):
        base_colon = s[:-1].strip() if s.endswith(":") else None
        base_dots = s[:-3].strip() if s.endswith("...") else None
        if s in trans or (base_colon and base_colon in trans) or (base_dots and base_dots in trans):
            translated.append(s)
        else:
            untranslated.append(s)

    if as_json:
        print(json.dumps(untranslated, ensure_ascii=False, indent=2))
    else:
        total = len(ui_strings)
        cov = (len(translated) / total * 100.0) if total else 100.0
        print(f"Web UI candidates scanned: {total}")
        print(f"Covered by dictionary:     {len(translated)} ({cov:.1f}%)")
        print(f"Remaining candidates:      {len(untranslated)}")
        for s in untranslated[:30]:
            print(f"  - {s}")
        if len(untranslated) > 30:
            print(f"  ... and {len(untranslated) - 30} more (use --json to dump all)")


def cmd_merge(args: list[str]):
    if not args:
        print("Usage: zhtw.py merge <new_translations.json>", file=sys.stderr)
        sys.exit(1)
    with open(args[0], encoding="utf-8") as f:
        incoming = json.load(f)
    trans = load_translations()
    added = 0
    updated = 0
    skipped = 0
    for en, zh in incoming.items():
        if not isinstance(en, str) or not isinstance(zh, str) or not en.strip() or not zh.strip():
            skipped += 1
            continue
        if en in EFFORT_LEVELS or en == zh:
            skipped += 1
            continue
        if _PH_RE.search(en) or ", plural," in en:
            errs = icu.validate_pair(en, zh)
            if errs:
                print(f"  Skipping invalid ICU pair {en!r}: {errs}", file=sys.stderr)
                skipped += 1
                continue
        if en not in trans:
            added += 1
        elif trans[en] != zh:
            updated += 1
        trans[en] = zh
    save_translations(trans)
    print(f"Merged into data/translations.json: +{added} added, ~{updated} updated, {skipped} skipped (total: {len(trans)})")


def _read_asar_header_and_base(asar_path: str) -> tuple[dict, int]:
    with open(asar_path, "rb") as f:
        header_data = f.read(16)
        if len(header_data) < 16:
            raise ValueError(f"Invalid asar file: {asar_path}")
        _, header_size, _, json_len = struct.unpack("<IIII", header_data)
        raw_json = f.read(json_len).rstrip(b"\x00").decode("utf-8")
        return json.loads(raw_json), 8 + header_size


def _read_asar_header(asar_path: str) -> dict:
    hdr, _ = _read_asar_header_and_base(asar_path)
    return hdr


def cmd_is_patched(args: list[str]):
    """Check in O(1) whether dist/preload.js inside app.asar contains the localization marker."""
    asar_path = args[0] if args else os.path.join(os.environ.get("ANTIGRAVITY_APP", DEFAULT_APP), "Contents", "Resources", "app.asar")
    if not os.path.isfile(asar_path):
        sys.exit(1)
    try:
        hdr, base = _read_asar_header_and_base(asar_path)
        preload_meta = hdr.get("files", {}).get("dist", {}).get("files", {}).get("preload.js")
        if not preload_meta or "offset" not in preload_meta:
            sys.exit(1)
        offset = int(preload_meta["offset"])
        size = int(preload_meta["size"])
        with open(asar_path, "rb") as f:
            f.seek(base + offset)
            content = f.read(size)
        if START_MARK.encode("utf-8") in content:
            sys.exit(0)
    except Exception:
        pass
    sys.exit(1)


def cmd_unpack_pattern(args: list[str]):
    """Print the --unpack-dir pattern needed to preserve unpacked directories in app.asar."""
    if not args:
        print("Usage: zhtw.py unpack-pattern <app.asar>", file=sys.stderr)
        sys.exit(1)
    header = _read_asar_header(args[0])
    dirs = set()

    def walk(node, prefix=""):
        files = node.get("files", {})
        for name, meta in files.items():
            rel = f"{prefix}/{name}" if prefix else name
            if meta.get("unpacked"):
                parts = rel.split("/")
                top = "/".join(parts[:2]) if len(parts) >= 2 and parts[0] == "node_modules" else parts[0]
                dirs.add(top)
            elif "files" in meta:
                walk(meta, rel)

    walk(header)
    patterns = sorted(dirs)
    if not patterns:
        return
    if len(patterns) == 1:
        print(patterns[0])
    else:
        print("{" + ",".join(patterns) + "}")


def cmd_verify_unpacked(args: list[str]):
    """Verify that every file under app.asar.unpacked is marked unpacked:true in app.asar."""
    if len(args) < 2:
        print("Usage: zhtw.py verify-unpacked <app.asar> <app.asar.unpacked>", file=sys.stderr)
        sys.exit(1)
    asar_path, unpacked_dir = args[0], args[1]
    if not os.path.isdir(unpacked_dir):
        print("  No app.asar.unpacked directory present; skipping check")
        return

    header = _read_asar_header(asar_path)
    missing = []
    checked = 0

    for root_dir, _, filenames in os.walk(unpacked_dir):
        for fname in filenames:
            full = os.path.join(root_dir, fname)
            rel = os.path.relpath(full, unpacked_dir)
            parts = rel.split(os.sep)
            cur = header
            ok = False
            for p in parts:
                cur = cur.get("files", {}).get(p)
                if not cur:
                    break
                if cur.get("unpacked"):
                    ok = True
            checked += 1
            if not ok:
                missing.append(rel)

    if missing:
        print(f"Error: {len(missing)} unpacked files are missing unpacked:true in {asar_path}:", file=sys.stderr)
        for m in missing[:10]:
            print(f"  - {m}", file=sys.stderr)
        sys.exit(1)
    print(f"  Verified app.asar.unpacked integrity ({checked} unpacked files marked correctly)")


def cmd_fuse_integrity(args: list[str]):
    """Check whether EnableEmbeddedAsarIntegrityValidation is enabled in Electron Framework."""
    import mmap

    app_path = args[0] if args else os.environ.get("ANTIGRAVITY_APP", DEFAULT_APP)
    ef_path = os.path.join(
        app_path,
        "Contents",
        "Frameworks",
        "Electron Framework.framework",
        "Versions",
        "A",
        "Electron Framework",
    )
    if not os.path.isfile(ef_path):
        print("0")
        return
    sentinel = b"dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX"
    with open(ef_path, "rb") as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            idx = mm.find(sentinel)
            if idx == -1 or idx + len(sentinel) + 6 > len(mm):
                print("0")
                return
            wire_len = mm[idx + len(sentinel) + 1]
            wire = mm[idx + len(sentinel) + 2 : idx + len(sentinel) + 2 + wire_len].decode("ascii", "replace")
    # Fuse index 4 is EnableEmbeddedAsarIntegrityValidation ('1' = enabled, '0' = disabled)
    enabled = len(wire) > 4 and wire[4] == "1"
    print("1" if enabled else "0")


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: zhtw.py <inject|strip|patch-main|stats|missing|merge|is-patched|unpack-pattern|verify-unpacked|fuse-integrity> [args...]",
            file=sys.stderr,
        )
        sys.exit(1)
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    if cmd == "inject":
        cmd_inject(rest)
    elif cmd == "strip":
        cmd_strip(rest)
    elif cmd == "patch-main":
        cmd_patch_main(rest)
    elif cmd == "stats":
        cmd_stats()
    elif cmd == "missing":
        cmd_missing(rest)
    elif cmd == "merge":
        cmd_merge(rest)
    elif cmd == "is-patched":
        cmd_is_patched(rest)
    elif cmd == "unpack-pattern":
        cmd_unpack_pattern(rest)
    elif cmd == "verify-unpacked":
        cmd_verify_unpacked(rest)
    elif cmd == "fuse-integrity":
        cmd_fuse_integrity(rest)
    else:
        print(f"Unknown subcommand: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
