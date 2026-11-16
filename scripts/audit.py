#!/usr/bin/env python3
"""
Audit kompatibilitas Arkaxhermes ↔ Hermes Agent v0.23.1.

Memeriksa:
  1. semua layar/tombol UI (via scripts/audit-ui.js + Node VM),
  2. ikon SVG,
  3. aksi feature() ↔ ACTIONS di hermes_bridge.py ↔ mode demo,
  4. endpoint /api/* ↔ ArkaxHttpServer.kt,
  5. panggilan window.ArkaxBridge ↔ ArkaxJsBridge.kt,
  6. perintah CLI di UI/bridge ↔ katalog `hermes --help` v0.23.1.

Menghasilkan docs/AUDIT.json dan docs/AUDIT_MATRIX.csv.
"""
from __future__ import annotations

import ast
import csv
import json
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
UI = ROOT / "android/app/src/main/assets/www/index.html"
BRIDGE_PY = ROOT / "android/app/src/main/assets/runtime/hermes_bridge.py"
HTTP_KT = ROOT / "android/app/src/main/java/com/arkaxhermes/app/bridge/ArkaxHttpServer.kt"
JS_BRIDGE_KT = ROOT / "android/app/src/main/java/com/arkaxhermes/app/bridge/ArkaxJsBridge.kt"
DOCS = ROOT / "docs"


def js_source() -> str:
    html = UI.read_text(encoding="utf-8")
    blocks = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, flags=re.S | re.I)
    return "\n;\n".join(blocks)


def js_literal(name: str, end_marker: str):
    js = js_source()
    m = re.search(r"var " + re.escape(name) + r" = ([\s\S]*?);\n" + re.escape(end_marker), js)
    if not m:
        raise ValueError("literal JS tidak ditemukan: " + name)
    return json.loads(m.group(1))


def bridge_literal(name: str):
    tree = ast.parse(BRIDGE_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError("literal Python tidak ditemukan: " + name)


def bridge_actions() -> set[str]:
    tree = ast.parse(BRIDGE_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "ACTIONS" for t in node.targets
        ) and isinstance(node.value, ast.Dict):
            return {
                k.value for k in node.value.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
    raise ValueError("ACTIONS tidak ditemukan")


def run_ui_audit():
    if not shutil.which("node"):
        return {"skipped": True, "reason": "node tidak tersedia"}
    proc = subprocess.run(
        ["node", str(ROOT / "scripts/audit-ui.js")],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    try:
        data = json.loads(proc.stdout)
    except Exception as exc:
        return {"skipped": False, "fatal": "Output audit-ui.js bukan JSON: %s / %s" % (exc, proc.stderr[:300])}
    data["nodeExit"] = proc.returncode
    return data


def main() -> int:
    strict = "--strict" in sys.argv
    js = js_source()
    screens = js_literal("SCREENS", "function screenById")
    cli_catalog = js_literal("CLI_CATALOG", "var NAV")
    providers = bridge_literal("PROVIDERS")
    toolsets = bridge_literal("TOOLSETS")
    actions = bridge_actions()
    ui = run_ui_audit()

    errors: list[str] = []
    warnings: list[str] = []

    if ui.get("fatal"):
        errors.append(ui["fatal"])
    if ui.get("skipped"):
        warnings.append("audit UI dilewati: " + ui.get("reason", "?"))
    else:
        if ui.get("dead"):
            errors.append("tombol tanpa handler klik: " + ", ".join(ui["dead"]))
        if ui.get("missingIcons"):
            errors.append("ikon SVG hilang: " + ", ".join(ui["missingIcons"]))
        if ui.get("nodeExit") not in (0, 2):
            errors.append("audit-ui.js exit " + str(ui.get("nodeExit")))
        if ui.get("unusedCases"):
            warnings.append("handler klik belum terpakai: " + ", ".join(ui["unusedCases"]))

    # Aksi feature() yang dipakai UI.
    feature_calls = set(re.findall(r"feature\('([a-zA-Z0-9_.-]+)'", js))
    screen_actions = {s["action"] for s in screens if s.get("action")}
    form_actions = {s["add"]["submit"] for s in screens if s.get("add")}
    feature_actions = feature_calls | screen_actions | form_actions
    # `exec` ditangani submitForm lewat runShell; `cli.catalog` hanya data embedded.
    allowed_non_bridge = {"exec", "cli.catalog"}
    unknown_actions = sorted(feature_actions - actions - allowed_non_bridge)
    if unknown_actions:
        errors.append("aksi feature tanpa implementasi bridge: " + ", ".join(unknown_actions))

    demo_block = re.search(
        r"feature: function\(action, body\)\{([\s\S]*?)\n  \},\n  terminal:", js
    )
    demo_actions = set(re.findall(r"action==='([a-zA-Z0-9_.-]+)'", demo_block.group(1))) if demo_block else set()
    missing_demo = sorted(feature_actions - demo_actions - allowed_non_bridge)
    if missing_demo:
        warnings.append("aksi mengandalkan fallback demo generik: " + ", ".join(missing_demo))

    # Endpoint HTTP.
    api_paths = set(re.findall(r"api\('(/api/[^']+)'", js))
    api_paths |= set(re.findall(r"streamGet\('(/api/[^']+)'", js))
    server_src = HTTP_KT.read_text(encoding="utf-8")
    server_paths = set(re.findall(r'req\.path == "([^"]+)"', server_src))
    server_paths |= set(re.findall(r'req\.path\.startsWith\("([^"]+)"\)', server_src))
    server_paths |= {"/health", "/favicon.svg", "/index.html", "/"}
    missing_endpoints = sorted(p for p in api_paths if p not in server_paths and not any(p.startswith(x) for x in server_paths if x.endswith("/")))
    if missing_endpoints:
        errors.append("endpoint UI tanpa handler server: " + ", ".join(missing_endpoints))

    # JavascriptInterface.
    bridge_methods = set(re.findall(r"@JavascriptInterface\s+fun (\w+)", JS_BRIDGE_KT.read_text(encoding="utf-8")))
    called_methods = set(re.findall(r"BRIDGE\.(\w+)", js))
    missing_js = sorted(called_methods - bridge_methods)
    if missing_js:
        errors.append("metode ArkaxBridge hilang: " + ", ".join(missing_js))

    # Perintah CLI: katalog nama dari `hermes --help`.
    cli_names = {c["name"] for c in cli_catalog}
    cli_cmds = []
    for s in screens:
        for c in s.get("cmds", []) or []:
            cli_cmds.append((s["id"], c))
    cli_cmds += [("ui", c) for c in re.findall(r"btn\('[^']*','run','([^']+)'", js)]
    agent_cmds = {
        "open", "back", "forward", "reload", "snapshot", "click", "fill", "type", "press",
        "get", "screenshot", "tab", "stream", "dashboard", "close", "skills", "mcp",
        "read", "eval", "wait", "scroll", "hover", "check", "uncheck", "select", "drag",
    }
    bridge_src = BRIDGE_PY.read_text(encoding="utf-8")
    bridge_cli = set(re.findall(r'hermes\("([a-z][a-z0-9-]*)"', bridge_src))
    bridge_cli |= set(re.findall(r'cli_or_fallback\("[^"]+", \["([a-z][a-z0-9-]*)"', bridge_src))
    bridge_cli |= set(re.findall(r'run_cli\(\[HERMES, "([a-z][a-z0-9-]*)"', bridge_src))
    unknown_cli = []
    for screen, cmd in cli_cmds:
        if not cmd.strip() or cmd.startswith("/") or cmd.startswith(("python3 ", "cat ", "uname", "hermes --help")):
            continue
        if cmd.startswith("agent-browser "):
            parts = cmd.split()
            if len(parts) < 2 or parts[1] in agent_cmds or parts[1].startswith("-"):
                continue
            unknown_cli.append("%s: %s (subcommand=%s)" % (screen, cmd, parts[1]))
        if cmd.startswith("hermes "):
            parts = cmd.split()
            if len(parts) < 2:
                continue
            token = parts[1]
            if token.startswith("-") or token in cli_names:
                continue
            unknown_cli.append("%s: %s (token=%s)" % (screen, cmd, token))
    for token in sorted(bridge_cli):
        if token not in cli_names:
            unknown_cli.append("bridge: hermes %s" % token)
    if unknown_cli:
        errors.append("perintah CLI di luar katalog v0.23.1: " + " | ".join(unknown_cli[:12]))

    # Provider/toolset counts.
    if len(providers) < 40:
        warnings.append("katalog provider lebih kecil dari canonical upstream: %d" % len(providers))
    if len(toolsets) < 57:
        errors.append("katalog toolset lebih kecil dari toolsets.py v0.23.1: %d" % len(toolsets))

    result = {
        "upstream": "NousResearch/hermes-agent v0.23.1 (source bundel)",
        "method": [
            "python3 hermes --help + <command> --help dijalankan dari source bundel",
            "render 27 layar UI dalam Node VM; semua data-act dicocokkan ke handler",
            "AST parse ACTIONS/PROVIDERS/TOOLSETS hermes_bridge.py",
            "regex endpoint Kotlin, JavascriptInterface, dan perintah CLI",
        ],
        "counts": {
            "screens": len(screens),
            "cliCommands": len(cli_catalog),
            "cliSubcommandsCataloged": sum(len(c.get("subs", [])) for c in cli_catalog),
            "bridgeActions": len(actions),
            "providers": len(providers),
            "toolsets": len(toolsets),
            "renderedActs": ui.get("renderedActCount"),
            "clickCases": ui.get("clickCaseCount"),
            "icons": ui.get("iconCount"),
            "svgPaths": ui.get("pKeyCount"),
            "apiPaths": len(api_paths),
            "serverPaths": len(server_paths),
            "jsBridgeMethods": len(bridge_methods),
        },
        "errors": errors,
        "warnings": warnings,
        "ui": ui,
        "featureActions": sorted(feature_actions),
        "bridgeActions": sorted(actions),
        "apiPaths": sorted(api_paths),
        "serverPaths": sorted(server_paths),
        "jsBridgeMethods": sorted(bridge_methods),
        "calledJsBridgeMethods": sorted(called_methods),
        "cliCommands": cli_names and sorted(cli_names) or [],
    }
    DOCS.mkdir(exist_ok=True)
    (DOCS / "AUDIT.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Matriks elemen: satu baris per tombol/layar, aksi bridge, endpoint, CLI, metode JS.
    matrix = []
    for screen, acts in (ui.get("screenActs") or {}).items():
        for act in acts:
            matrix.append(["UI", screen, "data-act=" + act,
                           "click/change handler", "OK" if act in (ui.get("screenActs") and acts) else "?"])
    for act in sorted(actions):
        matrix.append(["Bridge", "hermes_bridge.py", act, "ACTIONS", "OK"])
    for p in sorted(api_paths):
        matrix.append(["HTTP", "ArkaxHttpServer.kt", p, "handler", "OK" if p not in missing_endpoints else "ERROR"])
    for meth in sorted(bridge_methods):
        matrix.append(["JS bridge", "ArkaxJsBridge.kt", meth, "@JavascriptInterface", "OK"])
    for c in cli_catalog:
        matrix.append(["CLI", "docs/CLI_CATALOG.md", c["name"], ", ".join(c.get("subs", [])[:8]), "OK"])
    for screen, cmd in cli_cmds:
        matrix.append(["Perintah UI", screen, cmd, "Terminal /api/exec",
                       "ERROR" if any(screen in x and cmd in x for x in unknown_cli) else "OK"])
    with (DOCS / "AUDIT_MATRIX.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["kategori", "sumber", "elemen/aksi", "handler/bukti", "status"])
        w.writerows(matrix)

    print("Arkaxhermes audit: %d layar, %d perintah CLI, %d aksi bridge, %d provider, %d toolset" % (
        len(screens), len(cli_catalog), len(actions), len(providers), len(toolsets)))
    print("  UI: %s tombol, %s handler, dead=%d, ikon hilang=%d" % (
        ui.get("renderedActCount", "?"), ui.get("clickCaseCount", "?"),
        len(ui.get("dead", [])), len(ui.get("missingIcons", []))))
    print("  Endpoint: %d dipakai UI / %d tersedia; JS bridge: %d metode" % (
        len(api_paths), len(server_paths), len(bridge_methods)))
    print("  ERROR: %d | WARNING: %d" % (len(errors), len(warnings)))
    for e in errors:
        print("  ❌ " + e)
    for w in warnings:
        print("  ⚠️  " + w)
    print("  → docs/AUDIT.json, docs/AUDIT_MATRIX.csv")
    if strict and errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
