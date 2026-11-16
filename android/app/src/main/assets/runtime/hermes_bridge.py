#!/usr/bin/env python3
"""
Arkaxhermes feature bridge — JSON-lines API yang berjalan DI DALAM Ubuntu proot.

Tujuan: memberi Arkaxhermes akses terstruktur ke fitur Hermes Agent yang tidak
memiliki subcommand JSON, TANPA mem-fork atau mengubah source upstream.

Prinsip:
  1. CLI asli Hermes diprioritaskan bila tersedia (`hermes …`).
  2. Bila tidak ada, baca/tulis berkas asli di ~/.hermes (config.yaml, .env,
     skills/, MEMORY.md, sessions.db, cron/jobs.json, dll).
  3. Bila keduanya tidak memungkinkan, kembalikan ok=False + `fallback` berisi
     argv untuk dibuka di layar Terminal. TIDAK PERNAH mengarang data.

Pemakaian:
  python3 /opt/arkax/hermes_bridge.py <action> '<json-payload>'
  echo '{"key":"OPENAI_API_KEY","value":"sk-…"}' | python3 /opt/arkax/hermes_bridge.py env.set
  python3 /opt/arkax/hermes_bridge.py --list

Keluaran: satu baris JSON {ok, action, data, source, warnings, fallback, raw}.
"""

from __future__ import annotations

import base64
import datetime as dt
import glob
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).resolve()
# Di dalam proot nilainya /mnt/arkax; env override memudahkan pengujian di host/CI.
SHARED = Path(os.environ.get("ARKAX_SHARED", "/mnt/arkax")).resolve()
SRC = Path(os.environ.get("ARKAX_HERMES_SRC", "/opt/hermes-agent")).resolve()
HERMES = shutil.which("hermes") or "/usr/local/bin/hermes"

ALLOWED_ROOTS = [HOME, SHARED, Path("/opt/arkax"), SRC]
PROVIDERS = [
  {
    "id": "nous",
    "name": "Nous Portal",
    "envKeys": [],
    "note": "OAuth device-code; 300+ model + Tool Gateway",
    "kind": "oauth"
  },
  {
    "id": "fireworks",
    "name": "Fireworks AI",
    "envKeys": [
      "FIREWORKS_API_KEY"
    ],
    "note": "OpenAI-compatible direct model API",
    "kind": "api"
  },
  {
    "id": "openrouter",
    "name": "OpenRouter",
    "envKeys": [
      "OPENROUTER_API_KEY"
    ],
    "note": "Aggregator 200+ model; OAuth PKCE tersedia",
    "kind": "api"
  },
  {
    "id": "moa",
    "name": "Mixture of Agents",
    "envKeys": [],
    "note": "Preset virtual; lihat `hermes moa`",
    "kind": "virtual"
  },
  {
    "id": "novita",
    "name": "NovitaAI",
    "envKeys": [
      "NOVITA_API_KEY"
    ],
    "note": "Model API, Agent Sandbox, GPU Cloud",
    "kind": "api"
  },
  {
    "id": "lmstudio",
    "name": "LM Studio",
    "envKeys": [
      "LM_API_KEY"
    ],
    "note": "Server lokal http://127.0.0.1:1234/v1",
    "kind": "local"
  },
  {
    "id": "anthropic",
    "name": "Anthropic",
    "envKeys": [
      "ANTHROPIC_API_KEY",
      "ANTHROPIC_TOKEN",
      "CLAUDE_CODE_OAUTH_TOKEN"
    ],
    "note": "Claude via API key atau Claude Code",
    "kind": "api"
  },
  {
    "id": "openai-codex",
    "name": "ChatGPT / Codex Subscription",
    "envKeys": [],
    "note": "OAuth eksternal; `hermes auth add openai-codex`",
    "kind": "oauth"
  },
  {
    "id": "openai-api",
    "name": "OpenAI API",
    "envKeys": [
      "OPENAI_API_KEY"
    ],
    "note": "api.openai.com; OPENAI_BASE_URL override",
    "kind": "api"
  },
  {
    "id": "openai",
    "name": "OpenAI (alias)",
    "envKeys": [
      "OPENAI_API_KEY"
    ],
    "note": "Alias lama untuk openai-api",
    "kind": "api"
  },
  {
    "id": "alibaba",
    "name": "Qwen Cloud / DashScope",
    "envKeys": [
      "DASHSCOPE_API_KEY"
    ],
    "note": "Qwen + multi-provider",
    "kind": "api"
  },
  {
    "id": "alibaba-coding-plan",
    "name": "Alibaba Coding Plan",
    "envKeys": [
      "ALIBABA_CODING_PLAN_API_KEY",
      "DASHSCOPE_API_KEY"
    ],
    "note": "Coding Plan endpoint",
    "kind": "api"
  },
  {
    "id": "xai-oauth",
    "name": "xAI Grok OAuth",
    "envKeys": [],
    "note": "SuperGrok / Premium+ OAuth",
    "kind": "oauth"
  },
  {
    "id": "xiaomi",
    "name": "Xiaomi MiMo",
    "envKeys": [
      "XIAOMI_API_KEY"
    ],
    "note": "MiMo-V2.5 / V2",
    "kind": "api"
  },
  {
    "id": "tencent-tokenhub",
    "name": "Tencent TokenHub",
    "envKeys": [
      "TOKENHUB_API_KEY"
    ],
    "note": "Hy4 preview",
    "kind": "api"
  },
  {
    "id": "tencent-tokenplan",
    "name": "Tencent TokenPlan",
    "envKeys": [
      "TOKENPLAN_API_KEY"
    ],
    "note": "Hy4 via Anthropic Messages",
    "kind": "api"
  },
  {
    "id": "nvidia",
    "name": "NVIDIA NIM",
    "envKeys": [
      "NVIDIA_API_KEY"
    ],
    "note": "Nemotron / NIM",
    "kind": "api"
  },
  {
    "id": "huggingface",
    "name": "Hugging Face",
    "envKeys": [
      "HF_TOKEN"
    ],
    "note": "Inference Providers",
    "kind": "api"
  },
  {
    "id": "gemini",
    "name": "Google AI Studio",
    "envKeys": [
      "GOOGLE_API_KEY",
      "GEMINI_API_KEY"
    ],
    "note": "Native Gemini API",
    "kind": "api"
  },
  {
    "id": "vertex",
    "name": "Google Vertex AI",
    "envKeys": [],
    "note": "Service-account JSON / ADC",
    "kind": "sdk"
  },
  {
    "id": "deepseek",
    "name": "DeepSeek",
    "envKeys": [
      "DEEPSEEK_API_KEY"
    ],
    "note": "V3, R1, coder",
    "kind": "api"
  },
  {
    "id": "xai",
    "name": "xAI",
    "envKeys": [
      "XAI_API_KEY"
    ],
    "note": "Grok direct API + x_search",
    "kind": "api"
  },
  {
    "id": "zai",
    "name": "Z.AI / GLM",
    "envKeys": [
      "GLM_API_KEY",
      "ZAI_API_KEY",
      "Z_AI_API_KEY"
    ],
    "note": "Zhipu direct API",
    "kind": "api"
  },
  {
    "id": "kimi-coding",
    "name": "Kimi / Kimi Coding Plan",
    "envKeys": [
      "KIMI_API_KEY",
      "KIMI_CODING_API_KEY"
    ],
    "note": "api.kimi.com & Moonshot",
    "kind": "api"
  },
  {
    "id": "kimi-coding-cn",
    "name": "Kimi / Moonshot (China)",
    "envKeys": [
      "KIMI_CN_API_KEY"
    ],
    "note": "Domestic direct API",
    "kind": "api"
  },
  {
    "id": "stepfun",
    "name": "StepFun Step Plan",
    "envKeys": [
      "STEPFUN_API_KEY"
    ],
    "note": "Agent / coding models",
    "kind": "api"
  },
  {
    "id": "minimax",
    "name": "MiniMax",
    "envKeys": [
      "MINIMAX_API_KEY"
    ],
    "note": "Global direct API",
    "kind": "api"
  },
  {
    "id": "minimax-oauth",
    "name": "MiniMax (OAuth)",
    "envKeys": [],
    "note": "Coding Plan OAuth",
    "kind": "oauth"
  },
  {
    "id": "minimax-cn",
    "name": "MiniMax (China)",
    "envKeys": [
      "MINIMAX_CN_API_KEY"
    ],
    "note": "Domestic direct API",
    "kind": "api"
  },
  {
    "id": "ollama-cloud",
    "name": "Ollama Cloud",
    "envKeys": [
      "OLLAMA_API_KEY"
    ],
    "note": "ollama.com hosted models",
    "kind": "api"
  },
  {
    "id": "ollama",
    "name": "Ollama Local",
    "envKeys": [
      "OLLAMA_BASE_URL"
    ],
    "note": "Alias `custom` untuk endpoint lokal",
    "kind": "local"
  },
  {
    "id": "custom",
    "name": "Endpoint kustom",
    "envKeys": [
      "OPENAI_BASE_URL"
    ],
    "note": "OpenAI-compatible URL + CUSTOM_API_KEY",
    "kind": "local"
  },
  {
    "id": "arcee",
    "name": "Arcee AI",
    "envKeys": [
      "ARCEEAI_API_KEY"
    ],
    "note": "Trinity models",
    "kind": "api"
  },
  {
    "id": "gmi",
    "name": "GMI Cloud",
    "envKeys": [
      "GMI_API_KEY"
    ],
    "note": "Multi-model direct API",
    "kind": "api"
  },
  {
    "id": "kilocode",
    "name": "Kilo Code",
    "envKeys": [
      "KILOCODE_API_KEY"
    ],
    "note": "Kilo Gateway API",
    "kind": "api"
  },
  {
    "id": "opencode-zen",
    "name": "OpenCode Zen",
    "envKeys": [
      "OPENCODE_ZEN_API_KEY"
    ],
    "note": "Curated models, pay-as-you-go",
    "kind": "api"
  },
  {
    "id": "opencode-go",
    "name": "OpenCode Go",
    "envKeys": [
      "OPENCODE_GO_API_KEY"
    ],
    "note": "Open models subscription",
    "kind": "api"
  },
  {
    "id": "bedrock",
    "name": "AWS Bedrock",
    "envKeys": [
      "AWS_ACCESS_KEY_ID"
    ],
    "note": "IAM / AWS SDK; BEDROCK_BASE_URL",
    "kind": "sdk"
  },
  {
    "id": "azure-foundry",
    "name": "Azure Foundry",
    "envKeys": [
      "AZURE_FOUNDRY_API_KEY"
    ],
    "note": "OpenAI/Anthropic-style deployment",
    "kind": "api"
  },
  {
    "id": "ai-gateway",
    "name": "Vercel AI Gateway",
    "envKeys": [
      "AI_GATEWAY_API_KEY"
    ],
    "note": "Multi-model aggregator",
    "kind": "api"
  },
  {
    "id": "qwen-oauth",
    "name": "Qwen OAuth (Portal)",
    "envKeys": [],
    "note": "Reuses local Qwen CLI login",
    "kind": "oauth"
  },
  {
    "id": "qwen",
    "name": "Qwen (alias)",
    "envKeys": [
      "DASHSCOPE_API_KEY"
    ],
    "note": "Alias untuk alibaba",
    "kind": "api"
  },
  {
    "id": "copilot",
    "name": "GitHub Copilot / ACP",
    "envKeys": [
      "COPILOT_GITHUB_TOKEN",
      "GITHUB_TOKEN"
    ],
    "note": "Melalui `hermes acp` / plugin",
    "kind": "acp"
  }
]

TOOLSETS = [
  "bot_room",
  "browser",
  "catalog",
  "clarify",
  "code_execution",
  "coding",
  "computer_use",
  "connections",
  "context_engine",
  "cronjob",
  "debugging",
  "delegation",
  "desktop_ui",
  "discord",
  "discord_admin",
  "feishu_doc",
  "feishu_drive",
  "file",
  "hermes-acp",
  "hermes-api-server",
  "hermes-bluebubbles",
  "hermes-cli",
  "hermes-cron",
  "hermes-dingtalk",
  "hermes-discord",
  "hermes-email",
  "hermes-feishu",
  "hermes-gateway",
  "hermes-matrix",
  "hermes-mattermost",
  "hermes-qqbot",
  "hermes-signal",
  "hermes-slack",
  "hermes-sms",
  "hermes-telegram",
  "hermes-webhook",
  "hermes-wecom",
  "hermes-wecom-callback",
  "hermes-weixin",
  "hermes-whatsapp",
  "image_gen",
  "kanban",
  "memory",
  "onboarding",
  "project",
  "safe",
  "search",
  "session_search",
  "skills",
  "terminal",
  "todo",
  "tts",
  "video",
  "video_gen",
  "vision",
  "web",
  "x_search",
  "stt"
]
CONFIG_ONLY_TOOLSETS = {"stt"}
CONFIGURABLE_TOOLSETS = [
    "web","browser","terminal","file","code_execution","vision","video","image_gen",
    "video_gen","x_search","tts","stt","skills","todo","kanban","memory","context_engine",
    "session_search","connections","clarify","delegation","cronjob","discord","discord_admin",
    "computer_use",
]

def config_get(key: str):
    """Baca config.yaml lewat CLI resmi (bukan parser YAML sendiri)."""
    r = hermes("config", "get", key, "--json", timeout=25)
    if r["ok"]:
        try:
            return json.loads(r["stdout"])
        except Exception:
            return r["stdout"].strip()
    return None


def config_set(key: str, value, force=False):
    argv = ["config", "set"]
    if force:
        argv.append("--force")
    argv += [key, str(value)]
    return hermes(*argv)


def json_literal(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def auth_blob() -> str:
    for name in ("auth.json", "auth_store.json"):
        try:
            return (HOME / name).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
    return ""


def state_db():
    p = HOME / "state.db"
    return p if p.exists() else find_session_db()

def out(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False, default=str))
    sys.stdout.flush()


def result(action, data=None, source="bridge", warnings=None, fallback=None,
           raw=None, ok=True):
    return {
        "ok": ok, "action": action, "data": data, "source": source,
        "warnings": warnings or [], "fallback": fallback, "raw": raw,
    }


def run_cli(argv, timeout=90, stdin_text=None):
    """Jalankan argv (bukan string shell) dengan environment Hermes."""
    env = os.environ.copy()
    env["HERMES_HOME"] = str(HOME)
    env.setdefault("LANG", "C.UTF-8")
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout,
            cwd=str(HOME), env=env, input=stdin_text,
        )
        return {"ok": proc.returncode == 0, "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(), "exit": proc.returncode}
    except FileNotFoundError as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc), "exit": 127}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "timeout", "exit": 124}
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "stdout": "", "stderr": repr(exc), "exit": 1}


def hermes(*args, timeout=90):
    return run_cli([HERMES, *[str(a) for a in args]], timeout=timeout)


def cli_supported(*args):
    probe = hermes(*args, "--help", timeout=20)
    return probe["exit"] not in (127, 2) and "unknown" not in probe["stderr"].lower()


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def atomic_write(path: Path, text: str, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def write_json(path: Path, data, mode=0o600):
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", mode)


def safe_path(raw: str, for_write=False) -> Path:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = HOME / p
    target = p.resolve()
    if not any(str(target) == str(r) or str(target).startswith(str(r) + os.sep)
               for r in ALLOWED_ROOTS):
        raise ValueError("path di luar root yang diizinkan: %s" % raw)
    if for_write and str(target).startswith(str(SRC)):
        raise ValueError("source Hermes bersifat read-only")
    return target


def read_env() -> dict:
    path = HOME / ".env"
    data = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def write_env(updates: dict, deletes=None) -> dict:
    path = HOME / ".env"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
    seen, new_lines = set(), []
    deletes = set(deletes or [])
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in deletes:
                continue
            if key in updates:
                new_lines.append("%s=%s" % (key, str(updates[key]).replace("\n", " ")))
                seen.add(key)
                continue
        new_lines.append(line)
    for key, value in updates.items():
        if key not in seen:
            new_lines.append("%s=%s" % (key, str(value).replace("\n", " ")))
    atomic_write(path, "\n".join(new_lines).rstrip() + "\n", 0o600)
    return {"keys": sorted(read_env().keys())}


def parse_frontmatter(text: str) -> dict:
    meta = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            for line in text[3:end].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta



def find_session_db():
    """state.db adalah satu-satunya session store resmi Hermes v0.23.1."""
    preferred = HOME / "state.db"
    if preferred.exists():
        return preferred
    for p in sorted(HOME.rglob("*.db")):
        try:
            con = sqlite3.connect("file:%s?mode=ro" % p, uri=True, timeout=2)
            names = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            con.close()
            if "sessions" in names and "messages" in names:
                return p
        except Exception:
            continue
    return None

def db_query(db: Path, sql: str, params=()):
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=3)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def service_states():
    states = {}
    for name in ("gateway", "cron", "dashboard", "webhook"):
        pid_file = HOME / "run" / ("%s.pid" % name)
        running = False
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text().strip()), 0)
                running = True
            except Exception:
                pass
        states[name] = "running" if running else "stopped"
    return states


def cli_or_fallback(action, argv, parse_json=False, hint=None):
    r = hermes(*argv)
    if r["ok"]:
        data = r["stdout"]
        if parse_json:
            try:
                data = json.loads(data)
            except Exception:
                pass
        return result(action, data=data, source="hermes-cli", raw=r)
    return result(action, data=None, source="hermes-cli", ok=False,
                  warnings=[r["stderr"] or "CLI mengembalikan error"],
                  fallback={"argv": [HERMES, *argv], "hint": hint or "Buka Terminal"},
                  raw=r)


# --------------------------------------------------------------------------
# Aksi
# --------------------------------------------------------------------------

def act_status(p):
    env = read_env()
    db = find_session_db()
    skills = list((HOME / "skills").rglob("SKILL.md")) + list((HOME / "skills").glob("*.md"))
    version = hermes("--version", timeout=25)["stdout"]
    return result("status", {
        "hermesHome": str(HOME), "hermesVersion": version or "unknown",
        "python": sys.version.split()[0], "arch": os.uname().machine,
        "envKeys": sorted(env.keys()), "sessionDb": str(state_db() or ""),
        "skills": len(skills), "memory": (HOME / "MEMORY.md").exists(),
        "userProfile": (HOME / "USER.md").exists(),
        "services": service_states(),
        "config": (HOME / "config.yaml").exists(),
        "diskFreeMb": int(shutil.disk_usage(HOME).free / (1024 * 1024)),
    })



def act_config_get(p):
    key = p.get("key", "")
    if not key:
        return result("config.get", ok=False, warnings=["key wajib diisi"])
    value = config_get(key)
    if value is not None:
        return result("config.get", {"key": key, "value": value}, "hermes-cli")
    cfg = HOME / "config.yaml"
    fallback = None
    if cfg.exists():
        leaf = key.split(".")[-1]
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.match(r"^\s*%s\s*:" % re.escape(leaf), line):
                fallback = line.split(":", 1)[1].strip()
                break
    return result("config.get", {"key": key, "value": fallback}, "config.yaml",
                  warnings=[] if fallback is not None else ["kunci tidak disetel"],
                  fallback={"argv": [HERMES, "config", "get", key, "--json"]})

def act_config_set(p):
    key, value = p.get("key"), p.get("value")
    if not key or value is None:
        return result("config.set", ok=False, warnings=["key dan value wajib diisi"])
    return cli_or_fallback("config.set", ["config", "set", key, str(value)],
                           hint="hermes config set")


def act_env_set(p):
    key, value = p.get("key"), p.get("value")
    if not key or not re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", str(key)):
        return result("env.set", ok=False, warnings=["nama variabel env tidak valid"])
    if value is None or value == "":
        return result("env.set", write_env({}, deletes=[key]), "filesystem")
    return result("env.set", write_env({key: value}), "filesystem")


def act_env_list(p):
    env = read_env()
    return result("env.list", [{"key": k, "masked": "••••" + v[-4:] if len(v) > 4 else "••••"}
                               for k, v in sorted(env.items())], "filesystem")



def act_providers(p):
    env = read_env()
    active = str(config_get("model.provider") or "").strip().strip('"')
    blob = auth_blob()
    return result("providers.list", [{
        "id": item["id"], "name": item["name"],
        "envKey": (item["envKeys"][0] if item["envKeys"] else ""),
        "envKeys": item["envKeys"], "note": item["note"], "kind": item["kind"],
        "configured": any(env.get(k) for k in item["envKeys"]) or
                      (item["kind"] in ("oauth", "sdk", "acp") and item["id"] in blob),
        "active": active == item["id"],
        "models": item["note"], "latency": "—",
    } for item in PROVIDERS], "hermes-cli+filesystem")

def act_model_set(p):
    alias = {"openai": "openai-api", "qwen": "alibaba", "glm": "zai", "grok": "xai",
             "aws": "bedrock", "hf": "huggingface", "nim": "nvidia"}
    provider = alias.get(p.get("provider", ""), p.get("provider", ""))
    model = p.get("model", "")
    if not provider and not model:
        return result("model.set", ok=False, warnings=["provider atau model wajib diisi"])
    results, commands = [], []
    # Kunci resmi: model.provider dan model.default (bukan `provider`/`model` polos).
    if provider:
        commands.append(("config", "set", "model.provider", provider))
    if model:
        commands.append(("config", "set", "model.default", model))
    for argv in commands:
        results.append(hermes(*argv))
    return result("model.set", {"commands": [" ".join(c) for c in commands],
                                "ok": all(r["ok"] for r in results)},
                  "hermes-cli", raw=results,
                  warnings=["`hermes model` adalah picker interaktif; gunakan TUI bila perlu daftar model live"])

def act_skills_list(p):
    items = []
    root = HOME / "skills"
    if root.exists():
        for f in sorted(root.rglob("*.md")):
            text = f.read_text(encoding="utf-8", errors="replace")
            meta = parse_frontmatter(text)
            items.append({
                "name": meta.get("name", f.stem), "path": str(f),
                "description": meta.get("description", ""),
                "size": f.stat().st_size,
                "modified": dt.datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
            })
    return result("skills.list", items, "filesystem",
                  warnings=[] if items else ["belum ada skill; Hermes akan membuatnya setelah tugas kompleks"])


def act_skills_read(p):
    path = safe_path(p.get("path", ""))
    return result("skills.read", {"path": str(path), "content": path.read_text(encoding="utf-8", errors="replace")}, "filesystem")


def act_skills_write(p):
    path = safe_path(p.get("path", ""), for_write=True)
    atomic_write(path, p.get("content", ""), 0o644)
    return result("skills.write", {"path": str(path)}, "filesystem")


def act_skills_delete(p):
    path = safe_path(p.get("path", ""), for_write=True)
    backup = HOME / "backups" / (path.name + "." + dt.datetime.now().strftime("%Y%m%d%H%M%S") + ".bak")
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup)
    path.unlink()
    return result("skills.delete", {"deleted": str(path), "backup": str(backup)}, "filesystem")


def act_skills_install(p):
    name = p.get("name", "")
    if not name:
        return result("skills.install", ok=False, warnings=["name wajib diisi"])
    return cli_or_fallback("skills.install", ["skills", "install", name, "--yes"],
                           hint="hermes skills install / Skills Hub (agentskills.io)")



def act_skills_nudges(p):
    value = config_get("memory.nudge_interval")
    r = hermes("memory", "status", timeout=20)
    return result("skills.nudges", {"enabled": value not in (0, "0", None),
                                    "nudgeInterval": value, "raw": r["stdout"]}, "hermes-cli")

def act_memory_get(p):
    which = p.get("file", "MEMORY.md")
    if which not in ("MEMORY.md", "USER.md", "SOUL.md", "AGENTS.md"):
        return result("memory.get", ok=False, warnings=["berkas memori tidak dikenal"])
    path = HOME / which
    return result("memory.get", {"file": which, "content": path.read_text(encoding="utf-8", errors="replace")
                                 if path.exists() else "", "exists": path.exists()}, "filesystem")


def act_memory_set(p):
    which = p.get("file", "MEMORY.md")
    if which not in ("MEMORY.md", "USER.md", "SOUL.md", "AGENTS.md"):
        return result("memory.set", ok=False, warnings=["berkas memori tidak dikenal"])
    path = HOME / which
    if path.exists():
        shutil.copy2(path, HOME / "backups" / (which + ".bak"))
    atomic_write(path, p.get("content", ""), 0o600)
    return result("memory.set", {"file": which, "bytes": path.stat().st_size}, "filesystem")


def act_memory_append(p):
    which = p.get("file", "MEMORY.md")
    if which not in ("MEMORY.md", "USER.md", "SOUL.md", "AGENTS.md"):
        return result("memory.append", ok=False, warnings=["berkas memori tidak dikenal"])
    path = HOME / which
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n" + p.get("text", "").rstrip() + "\n")
    return result("memory.append", {"file": which}, "filesystem")


def act_memory_clear(p):
    if not p.get("confirm"):
        return result("memory.clear", ok=False, warnings=["butuh confirm:true"])
    which = p.get("file", "MEMORY.md")
    path = HOME / which
    stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    if path.exists():
        shutil.copy2(path, HOME / "backups" / ("%s.%s.bak" % (which, stamp)))
        atomic_write(path, "", 0o600)
    return result("memory.clear", {"file": which, "backup": stamp}, "filesystem")



def act_memory_providers(p):
    r = hermes("plugins", "list", "--json", timeout=30)
    data = r["stdout"]
    try:
        data = json.loads(data)
    except Exception:
        pass
    status = hermes("memory", "status", timeout=20)
    return result("memory.providers", {"plugins": data,
                                       "honcho": "honcho" in str(data).lower(),
                                       "status": status["stdout"]}, "hermes-cli",
                  warnings=[] if r["ok"] else ["hermes plugins list tidak tersedia"])


def act_sessions_list(p):
    db = state_db()
    limit = int(p.get("limit", 100))
    if db:
        try:
            rows = db_query(db, """
                SELECT id, COALESCE(title, display_name, id) AS title, source, model,
                       COALESCE(last_activity_at, started_at) AS ts,
                       message_count, COALESCE(input_tokens,0)+COALESCE(output_tokens,0) AS tokens
                FROM sessions WHERE archived = 0 OR archived IS NULL
                ORDER BY ts DESC LIMIT ?
            """, (limit,))
            items = []
            for r in rows:
                ts = r.get("ts") or 0
                try:
                    age = (dt.datetime.now().timestamp() - float(ts)) / 86400
                    when = "Hari ini" if age < 1 else "7 hari terakhir" if age < 7 else "Arsip"
                except Exception:
                    when = "-"
                items.append({"id": r["id"], "title": r["title"], "when": when,
                              "model": r.get("model") or "-", "tokens": r.get("tokens") or 0,
                              "messages": r.get("message_count") or 0})
            return result("sessions.list", items, "sqlite:state.db")
        except Exception as exc:
            return result("sessions.list", ok=False, warnings=["state.db: %s" % exc],
                          fallback={"argv": [HERMES, "sessions", "list", "--limit", str(limit)]})
    r = hermes("sessions", "list", "--limit", str(limit), timeout=30)
    lines = [l.strip() for l in r["stdout"].splitlines() if l.strip()]
    return result("sessions.list", [{"id": str(i), "title": l, "when": "-", "model": "-", "tokens": 0}
                                    for i, l in enumerate(lines[:limit])], "hermes-cli",
                  warnings=["state.db belum ada; menampilkan `hermes sessions list` sebagai teks"], raw=r)


def act_sessions_search(p):
    q = p.get("query", "").strip()
    if not q:
        return result("sessions.search", [], "bridge", warnings=["query kosong"])
    db = state_db()
    if not db:
        return result("sessions.search", [], "none",
                      warnings=["state.db belum ada; FTS5 belum bisa dipakai"],
                      fallback={"argv": [HERMES, "sessions", "list", "--limit", "50"]})
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=3)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%fts%'")]
    finally:
        con.close()
    for fts in [t for t in tables if not t.endswith(("_data","_idx","_docsize","_config","_content"))]:
        try:
            rows = db_query(db, """
                SELECT m.session_id AS id, COALESCE(s.title, s.display_name, m.session_id) AS title,
                       substr(m.content, 1, 240) AS snippet, m.role, m.timestamp
                FROM %s f JOIN messages m ON m.id = f.rowid
                JOIN sessions s ON s.id = m.session_id
                WHERE %s MATCH ? LIMIT 50
            """ % (fts, fts), (q,))
            return result("sessions.search", rows, "fts5:%s" % fts)
        except Exception:
            continue
    try:
        rows = db_query(db, """
            SELECT m.session_id AS id, COALESCE(s.title, m.session_id) AS title,
                   substr(m.content, 1, 240) AS snippet, m.role, m.timestamp
            FROM messages m LEFT JOIN sessions s ON s.id = m.session_id
            WHERE m.content LIKE ? AND m.active = 1 LIMIT 50
        """, ("%%%s%%" % q,))
        return result("sessions.search", rows, "like:messages",
                      warnings=["FTS5 belum terindeks; memakai LIKE"])
    except Exception as exc:
        return result("sessions.search", ok=False, warnings=[str(exc)],
                      fallback={"argv": [HERMES, "sessions", "list", "--limit", "50"]})


def act_sessions_read(p):
    sid = p.get("id", "")
    db = state_db()
    if not db:
        return result("sessions.read", ok=False, warnings=["state.db belum ada"],
                      fallback={"argv": [HERMES, "sessions", "export", "--session-id", sid, "--format", "md"]})
    try:
        rows = db_query(db, """
            SELECT role, content, timestamp FROM messages
            WHERE session_id = ? AND (active = 1 OR active IS NULL)
            ORDER BY id LIMIT 500
        """, (sid,))
        return result("sessions.read", {"id": sid, "messages": rows}, "sqlite:state.db")
    except Exception as exc:
        return result("sessions.read", ok=False, warnings=[str(exc)],
                      fallback={"argv": [HERMES, "sessions", "export", "--session-id", sid, "--format", "md"]})


def act_sessions_delete(p):
    sid = p.get("id", "")
    if not sid:
        return result("sessions.delete", ok=False, warnings=["id wajib diisi"])
    return cli_or_fallback("sessions.delete", ["sessions", "delete", "--yes", sid])


def act_sessions_stats(p):
    db = state_db()
    if not db:
        r = hermes("sessions", "stats", timeout=25)
        return result("sessions.stats", {"raw": r["stdout"]}, "hermes-cli",
                      warnings=[] if r["ok"] else ["state.db belum ada"], raw=r)
    stats = {}
    for table, label in (("sessions", "sessions"), ("messages", "messages")):
        try:
            stats[label] = db_query(db, "SELECT COUNT(*) AS n FROM %s" % table)[0]["n"]
        except Exception:
            stats[label] = 0
    try:
        stats["tokens"] = db_query(db, "SELECT COALESCE(SUM(input_tokens+output_tokens),0) AS n FROM sessions")[0]["n"]
    except Exception:
        stats["tokens"] = 0
    return result("sessions.stats", stats, "sqlite:state.db")

def act_sessions_export(p):
    sid = p.get("id", "")
    fmt = p.get("format", "md")
    if fmt not in ("jsonl", "md", "qmd", "html", "trace"):
        fmt = "md"
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = SHARED / "exports" / ("arkax-session-%s-%s.%s" % (sid or "all", stamp, fmt))
    dest.parent.mkdir(parents=True, exist_ok=True)
    argv = ["sessions", "export", "--format", fmt, "--yes"]
    if sid:
        argv += ["--session-id", sid]
    argv.append(str(dest))
    r = hermes(*argv, timeout=180)
    return result("sessions.export", {"path": str(dest), "bytes": dest.stat().st_size if dest.exists() else 0,
                                      "stdout": r["stdout"], "stderr": r["stderr"], "exit": r["exit"]},
                  "hermes-cli", ok=r["ok"], raw=r)


def act_cron_list(p):
    jobs_file = HOME / "cron" / "jobs.json"
    if jobs_file.exists():
        data = read_json(jobs_file, {})
        raw = data.get("jobs", []) if isinstance(data, dict) else data
        jobs = []
        for j in raw if isinstance(raw, list) else []:
            sched = j.get("schedule")
            if isinstance(sched, dict):
                sched = sched.get("display") or sched.get("expr") or "interval"
            jobs.append({
                "id": j.get("id"), "name": j.get("name") or (j.get("prompt") or "")[:48],
                "schedule": sched or j.get("schedule_display") or "-",
                "prompt": j.get("prompt") or j.get("script") or "",
                "enabled": bool(j.get("enabled", True)), "state": j.get("state") or "-",
                "model": j.get("model") or "follow", "deliver": j.get("deliver") or "local",
                "next_run_at": j.get("next_run_at"), "last_status": j.get("last_status"),
            })
        return result("cron.list", jobs, "jobs.json")
    r = hermes("cron", "list", timeout=30)
    lines = [l.strip() for l in r["stdout"].splitlines() if l.strip()]
    return result("cron.list", [{"id": str(i), "name": l, "schedule": "-", "prompt": "",
                                 "enabled": True, "model": "follow"} for i, l in enumerate(lines)],
                  "hermes-cli", warnings=["jobs.json belum ada; menampilkan teks `hermes cron list`"], raw=r)


def act_cron_create(p):
    schedule, prompt = p.get("schedule"), p.get("prompt")
    if not schedule:
        return result("cron.create", ok=False, warnings=["schedule wajib diisi"])
    if p.get("noAgent") and not p.get("script"):
        return result("cron.create", ok=False,
                      warnings=["--no-agent di Hermes v0.23.1 membutuhkan --script; prompt diabaikan"],
                      fallback={"argv": [HERMES, "cron", "create", schedule, "--script", "/mnt/arkax/scripts/watch.sh", "--no-agent"],
                                "hint": "Buka Terminal"})
    argv = ["cron", "create", schedule]
    if prompt:
        argv.append(prompt)
    if p.get("name"):
        argv += ["--name", p["name"]]
    for skill in p.get("skills", []) or ([p["skill"]] if p.get("skill") else []):
        argv += ["--skill", skill]
    if p.get("model"):
        argv += ["--model", p["model"]]
    if p.get("modelProvider"):
        argv += ["--provider", p["modelProvider"]]
    if p.get("reasoningEffort"):
        argv += ["--reasoning-effort", p["reasoningEffort"]]
    if p.get("pin"):
        argv += ["--pin"]
    if p.get("deliver"):
        argv += ["--deliver", p["deliver"]]
    if p.get("repeat"):
        argv += ["--repeat", str(p["repeat"])]
    if p.get("timezone"):
        argv += ["--timezone", p["timezone"]]
    if p.get("workdir"):
        argv += ["--workdir", p["workdir"]]
    if p.get("script"):
        argv += ["--script", p["script"]]
    if p.get("noAgent"):
        argv += ["--no-agent"]
    return cli_or_fallback("cron.create", argv, hint="hermes cron create")

def act_cron_toggle(p):
    jid, enable = p.get("id"), bool(p.get("enabled"))
    if not jid:
        return result("cron.toggle", ok=False, warnings=["id wajib diisi"])
    return cli_or_fallback("cron.toggle", ["cron", "resume" if enable else "pause", jid])


def act_cron_run(p):
    return cli_or_fallback("cron.run", ["cron", "run", p.get("id", "")])


def act_cron_remove(p):
    return cli_or_fallback("cron.remove", ["cron", "remove", p.get("id", "")])



def act_cron_delivery(p):
    target = p.get("platform") or p.get("name") or ""
    message = p.get("message", "")
    if not target or not message:
        return result("cron.delivery", ok=False, warnings=["platform dan message wajib diisi"])
    # `hermes send` memakai -t/--to, BUKAN argumen platform posisional.
    return cli_or_fallback("cron.delivery", ["send", "-t", target, message],
                           hint="hermes send -t <platform> <pesan>")

def act_cron_status(p):
    return cli_or_fallback("cron.status", ["cron", "status"])


def act_cron_tick(p):
    return cli_or_fallback("cron.tick", ["cron", "tick", "--accept-hooks"])


def act_gateway_status(p):
    r = hermes("gateway", "status", timeout=30)
    platforms = []
    for name in ("telegram", "discord", "slack", "whatsapp", "signal", "email"):
        configured = bool(re.search(r"\b%s\b" % re.escape(name), (r["stdout"] or ""), re.I))
        platforms.append({"name": name, "state": "Terhubung" if configured else "Siap",
                          "on": configured, "note": "Status dari `hermes gateway status`"})
    return result("gateway.status", platforms, "hermes-cli", ok=True, raw=r)



def act_tools_list(p):
    pref = read_json(HOME / "arkax-toolsets.json", {"enabled": []})
    r = hermes("tools", "list", "--platform", "cli", timeout=30)
    enabled = set(re.findall(r"[✓✔]\s+enabled\s+([a-z0-9_]+)", r["stdout"] or "", re.I))
    disabled = set(re.findall(r"[✗×x]\s+disabled\s+([a-z0-9_]+)", r["stdout"] or "", re.I))
    toolsets = []
    for t in TOOLSETS:
        if t in enabled:
            on = True
        elif t in disabled:
            on = False
        elif t == "stt":
            on = bool(config_get("stt.enabled"))
        else:
            on = t in pref.get("enabled", []) or t not in CONFIGURABLE_TOOLSETS
        toolsets.append({"name": t, "enabled": on,
                         "configOnly": t in CONFIG_ONLY_TOOLSETS,
                         "configurable": t in CONFIGURABLE_TOOLSETS})
    return result("tools.list", {"toolsets": toolsets, "upstream": r["stdout"]},
                  "hermes-cli+filesystem",
                  warnings=[] if r["ok"] else ["hermes tools list gagal; memakai preferensi lokal"], raw=r)


def act_tools_set(p):
    enabled = p.get("toolsets") or p.get("enabled") or []
    if isinstance(enabled, str):
        enabled = [x.strip() for x in enabled.split(",") if x.strip()]
    enabled = set(enabled)
    write_json(HOME / "arkax-toolsets.json", {"enabled": sorted(enabled)}, 0o600)
    configurable = [t for t in CONFIGURABLE_TOOLSETS if t not in CONFIG_ONLY_TOOLSETS]
    to_enable = [t for t in configurable if t in enabled]
    to_disable = [t for t in configurable if t not in enabled]
    results = []
    if to_disable:
        results.append({"argv": ["hermes", "tools", "disable"] + to_disable,
                        **hermes("tools", "disable", "--platform", "cli", *to_disable)})
    if to_enable:
        results.append({"argv": ["hermes", "tools", "enable"] + to_enable,
                        **hermes("tools", "enable", "--platform", "cli", *to_enable)})
    stt_result = config_set("stt.enabled", "true" if "stt" in enabled else "false")
    skipped = [t for t in enabled if t not in CONFIGURABLE_TOOLSETS]
    return result("tools.set", {"enabled": sorted(enabled), "commands": len(results),
                                "skippedBundles": skipped, "sttOk": stt_result["ok"]},
                  "hermes-cli", raw={"tools": results, "stt": stt_result},
                  warnings=(["Toolset bundle/platform berikut tidak bisa di-toggle lewat `hermes tools`, hanya disimpan sebagai preferensi UI: " + ", ".join(skipped)] if skipped else []) +
                           ["`hermes config set toolsets` tidak dipakai lagi: bentuk resminya adalah daftar per-platform lewat `hermes tools enable/disable`"])

def act_tools_backend(p):
    backend = p.get("backend", "local")
    return cli_or_fallback("tools.backend", ["config", "set", "terminal.backend", backend],
                           hint="terminal.backend: local|docker|ssh|modal|daytona|vercel_sandbox")



def act_mcp_list(p):
    r = hermes("mcp", "list", timeout=30)
    cfg = config_get("mcp_servers")
    if cfg is None:
        cfg = {}
    return result("mcp.list", {"servers": cfg, "raw": r["stdout"]}, "hermes-cli+config.yaml",
                  warnings=[] if r["ok"] else ["`hermes mcp list` mengembalikan error (platform belum aktif)"], raw=r)


def act_mcp_add(p):
    name = re.sub(r"[^a-zA-Z0-9_.-]", "", p.get("name", ""))
    if not name:
        return result("mcp.add", ok=False, warnings=["name wajib diisi"])
    entry = {"transport": p.get("transport", "stdio"), "enabled": True}
    if p.get("command"):
        entry["command"] = p["command"]
    if p.get("args"):
        args = p["args"] if isinstance(p["args"], list) else str(p["args"]).split()
        entry["args"] = args
    if p.get("url"):
        entry["url"] = p["url"]
    if p.get("env"):
        entry["env"] = p["env"]
    # `hermes mcp add` bisa prompt saat koneksi gagal. Menulis config.yaml lewat
    # `hermes config set --force` adalah jalur non-interaktif yang sama-sama resmi.
    r = config_set("mcp_servers.%s" % name, json_literal(entry), force=True)
    return result("mcp.add", {"name": name, "entry": entry}, "hermes-cli:config.set",
                  ok=r["ok"], raw=r,
                  warnings=[] if r["ok"] else ["Gagal menulis mcp_servers.%s" % name],
                  fallback={"argv": [HERMES, "mcp", "add", name], "hint": "Buka Terminal"})


def act_mcp_remove(p):
    name = re.sub(r"[^a-zA-Z0-9_.-]", "", p.get("name", ""))
    if not name:
        return result("mcp.remove", ok=False, warnings=["name wajib diisi"])
    r = hermes("config", "unset", "mcp_servers.%s" % name, timeout=25)
    return result("mcp.remove", {"name": name}, "hermes-cli:config.unset", ok=r["ok"], raw=r,
                  fallback={"argv": [HERMES, "mcp", "remove", name], "hint": "Buka Terminal"})

def act_plugins_list(p):
    r = hermes("plugins", "list", "--json", timeout=30)
    data = r["stdout"]
    try:
        data = json.loads(data)
    except Exception:
        data = [d.name for d in (HOME / "plugins").glob("*")] if (HOME / "plugins").exists() else []
    return result("plugins.list", data, "hermes-cli" if r["ok"] else "filesystem")


def act_plugins_install(p):
    name = p.get("name", "")
    if not name:
        return result("plugins.install", ok=False, warnings=["name wajib diisi"])
    return cli_or_fallback("plugins.install", ["plugins", "install", name, "--yes-deps"])


def act_plugins_remove(p):
    name = p.get("name", "")
    if not name:
        return result("plugins.remove", ok=False, warnings=["name wajib diisi"])
    # `hermes plugins remove` dapat konfirmasi; kirim 'y' lewat stdin agar non-interaktif.
    r = run_cli([HERMES, "plugins", "remove", name], timeout=90, stdin_text="y\n")
    if r["ok"]:
        return result("plugins.remove", {"name": name}, "hermes-cli", raw=r)
    return result("plugins.remove", ok=False, source="hermes-cli", raw=r,
                  warnings=[r["stderr"] or "plugins remove gagal"],
                  fallback={"argv": [HERMES, "plugins", "remove", name], "hint": "Buka Terminal"})



def act_profiles_list(p):
    r = hermes("profile", "list", timeout=25)
    dirs = [d.name for d in (HOME / "profiles").glob("*") if d.is_dir()] if (HOME / "profiles").exists() else []
    return result("profiles.list", {"directories": dirs, "upstream": r["stdout"]},
                  "hermes-cli+filesystem",
                  warnings=["Gunakan `hermes profile use <name>` atau `hermes --profile <name>` bila didukung rilis ini"])


def act_profiles_create(p):
    name = re.sub(r"[^a-zA-Z0-9_-]", "", p.get("name", ""))
    if not name:
        return result("profiles.create", ok=False, warnings=["name tidak valid"])
    return cli_or_fallback("profiles.create", ["profile", "create", name],
                           hint="hermes profile create <name>")


def act_profiles_use(p):
    name = p.get("name", "default")
    atomic_write(HOME / "arkax-active-profile", name + "\n", 0o600)
    return cli_or_fallback("profiles.use", ["profile", "use", name],
                           hint="hermes profile use <name>")

def act_bots_list(p):
    return result("bots.list", read_json(HOME / "bots.json", {"bots": []}), "filesystem",
                  warnings=["Bot Mode mengikuti konfigurasi gateway/Desktop Hermes"])


def act_bots_set(p):
    path = HOME / "bots.json"
    data = read_json(path, {"bots": []})
    bots = [b for b in data.get("bots", []) if b.get("name") != p.get("name")]
    bots.append(p)
    data["bots"] = bots
    write_json(path, data)
    return result("bots.set", {"bots": len(bots)}, "filesystem")



def act_hooks_list(p):
    r = hermes("hooks", "list", timeout=25)
    allowlist = read_json(HOME / "shell-hooks-allowlist.json", {})
    cfg = config_get("hooks") or {}
    items = []
    if isinstance(cfg, dict):
        for event, entries in cfg.items():
            for e in entries if isinstance(entries, list) else [entries]:
                if isinstance(e, dict):
                    items.append({"name": event, "meta": e.get("command", ""),
                                  "matcher": e.get("matcher", "*"), "tag": "config.yaml"})
    return result("hooks.list", {"hooks": items, "allowlist": allowlist, "raw": r["stdout"]},
                  "hermes-cli+config.yaml", ok=True, raw=r)


def act_hooks_set(p):
    event = re.sub(r"[^a-zA-Z0-9_.-]", "", p.get("event") or p.get("name", ""))
    command = p.get("command") or p.get("content", "")
    if not event or not command:
        return result("hooks.set", ok=False,
                      warnings=["event dan command wajib diisi; hooks Hermes dideklarasi di config.yaml, bukan berkas .py lokal"],
                      fallback={"argv": [HERMES, "hooks", "list"], "hint": "Lihat docs/user-guide/features/hooks.md"})
    entry = [{"matcher": p.get("matcher", "*"), "command": command,
              "timeout": int(p.get("timeout", 60))}]
    r = config_set("hooks.%s" % event, json_literal(entry), force=True)
    return result("hooks.set", {"event": event, "entry": entry}, "hermes-cli:config.set",
                  ok=r["ok"], raw=r,
                  warnings=["Persetujuan pertama kali tetap memakai `hermes hooks doctor` / --accept-hooks"],
                  fallback={"argv": [HERMES, "hooks", "list"]})

def act_trajectories_list(p):
    items = []
    for f in sorted(HOME.rglob("*.jsonl")):
        items.append({"path": str(f), "size": f.stat().st_size,
                      "lines": sum(1 for _ in f.open(encoding="utf-8", errors="replace"))})
    return result("trajectories.list", items, "filesystem")



def act_approvals_list(p):
    r = hermes("approvals", "suggest", "--json", "--days", str(p.get("days", 90)), timeout=40)
    data = r["stdout"]
    try:
        data = json.loads(data)
    except Exception:
        data = []
    local = [read_json(f, {"id": f.stem}) for f in sorted((HOME / "approvals").glob("*.json"))]
    return result("approvals.list", {"suggestions": data, "localDecisions": local,
                                     "upstream": r["stdout"]}, "hermes-cli+filesystem",
                  warnings=["Antrean approval live hanya ada pada proses Hermes/TUI; `hermes approvals` hanya menyarankan allowlist"])


def act_approvals_decide(p):
    aid, decision = p.get("id"), p.get("decision")
    if decision not in ("approve", "deny", "always", "never"):
        return result("approvals.decide", ok=False, warnings=["decision tidak valid"])
    write_json(HOME / "approvals" / ("%s.json" % re.sub(r"[^a-zA-Z0-9_-]", "", str(aid))),
               {"id": aid, "decision": decision,
                "at": dt.datetime.now(dt.timezone.utc).isoformat()}, 0o600)
    # v0.23.1 TIDAK punya `hermes approvals approve|deny`. Jangan mengarang CLI.
    return result("approvals.decide", {"id": aid, "decision": decision, "persistedLocally": True},
                  "filesystem", ok=False,
                  warnings=["Hermes v0.23.1 tidak punya subcommand approval decide; keputusan harus diberikan di TUI/Terminal pada proses yang meminta approval."],
                  fallback={"argv": [HERMES, "--tui"],
                            "hint": "Buka Terminal/TUI, lalu jawab prompt approval yang sedang menunggu"})

def act_context_list(p):
    return result("context.list", read_json(HOME / "context-files.json", {"files": []}), "filesystem")


def act_context_add(p):
    path = HOME / "context-files.json"
    data = read_json(path, {"files": []})
    entry = {"path": p.get("path"), "recursive": bool(p.get("recursive", False))}
    data["files"] = [f for f in data["files"] if f.get("path") != entry["path"]] + [entry]
    write_json(path, data)
    return result("context.add", entry, "filesystem",
                  warnings=["Hermes menyuntikkan AGENTS.md/SOUL.md/.cursorrules otomatis; ini daftar tambahan untuk UI"])



def act_batch_run(p):
    dataset = p.get("dataset")
    if dataset:
        argv = [sys.executable, str(SRC / "batch_runner.py"), "--dataset_file=" + str(dataset),
                "--batch_size=" + str(p.get("batchSize", 4)),
                "--max_turns=" + str(p.get("maxTurns", 10)),
                "--num_workers=" + str(p.get("workers", 2))]
        if p.get("runName"):
            argv.append("--run_name=" + str(p["runName"]))
        r = run_cli(argv, timeout=600)
        return result("batch.run", {"argv": argv, **r}, "batch_runner.py", ok=r["ok"], raw=r)
    commands = p.get("commands", [])
    results = []
    for c in commands[:25]:
        argv = c if isinstance(c, list) else [HERMES, "chat", "-Q", "--oneshot", str(c)]
        results.append({"argv": argv, **run_cli(argv, timeout=180)})
    return result("batch.run", results, "hermes-cli",
                  warnings=["Untuk dataset JSONL + trajektori, kirim `dataset` agar memakai batch_runner.py upstream"])

def act_files_list(p):
    root = safe_path(p.get("path", str(HOME)))
    if not root.is_dir():
        return result("files.list", ok=False, warnings=["bukan direktori"])
    items = []
    for f in sorted(root.iterdir()):
        st = f.stat()
        items.append({"name": f.name, "path": str(f), "dir": f.is_dir(),
                      "size": 0 if f.is_dir() else st.st_size,
                      "modified": dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
    return result("files.list", items, "filesystem")


def act_files_read(p):
    path = safe_path(p.get("path", ""))
    raw = path.read_bytes()
    try:
        return result("files.read", {"path": str(path), "text": raw.decode("utf-8")}, "filesystem")
    except UnicodeDecodeError:
        return result("files.read", {"path": str(path),
                                     "base64": base64.b64encode(raw).decode("ascii"),
                                     "binary": True}, "filesystem")


def act_files_write(p):
    path = safe_path(p.get("path", ""), for_write=True)
    if p.get("base64"):
        data = base64.b64decode(p["base64"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    else:
        atomic_write(path, p.get("content", ""), 0o644)
    return result("files.write", {"path": str(path), "bytes": path.stat().st_size}, "filesystem")


def act_files_delete(p):
    path = safe_path(p.get("path", ""), for_write=True)
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return result("files.delete", {"path": str(path)}, "filesystem")



def act_backup_create(p):
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = SHARED / "exports" / ("arkax-backup-%s.zip" % stamp)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Format resmi Hermes adalah ZIP, bukan tar.gz. `-q` MENGABAIKAN -o dan
    # menulis state-snapshots/, jadi default di sini adalah backup penuh ke -o.
    argv = ["backup", "-o", str(dest)]
    if p.get("quick"):
        argv += ["-q", "-l", "arkax"]
    r = hermes(*argv, timeout=240)
    sha = hashlib.sha256(dest.read_bytes()).hexdigest() if dest.exists() else ""
    quick = bool(p.get("quick"))
    return result("backup.create", {"path": str(dest), "size": dest.stat().st_size if dest.exists() else 0,
                                    "sha256": sha, "format": "zip", "quick": quick,
                                    "note": "quick menulis ~/state-snapshots, bukan -o" if quick else ""},
                  "hermes-cli", ok=r["ok"] and (quick or dest.exists()), raw=r,
                  warnings=(["`-q` menulis snapshot ke ~/state-snapshots dan mengabaikan -o"] if quick else []) +
                           ([] if r["ok"] else ["`hermes backup` gagal"]),
                  fallback={"argv": [HERMES, "backup", "-o", str(dest)]})


def act_backup_restore(p):
    archive = safe_path(p.get("path", ""))
    if archive.suffix.lower() != ".zip":
        return result("backup.restore", ok=False,
                      warnings=["Hermes v0.23.1 memakai backup ZIP; gunakan `hermes import <file.zip>`"],
                      fallback={"argv": [HERMES, "import", "--force", str(archive)]})
    r = hermes("import", "--force", str(archive), timeout=300)
    return result("backup.restore", {"path": str(archive)}, "hermes-cli", ok=r["ok"], raw=r)

def act_backups_list(p):
    items = []
    for f in sorted((SHARED / "exports").glob("arkax-backup-*")) if (SHARED / "exports").exists() else []:
        if f.is_file():
            items.append({"name": f.name, "path": str(f), "size": f.stat().st_size,
                          "modified": dt.datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")})
    return result("backups.list", items, "filesystem")


def act_files_mkdir(p):
    path = safe_path(p.get("path", ""), for_write=True)
    path.mkdir(parents=True, exist_ok=True)
    return result("files.mkdir", {"path": str(path)}, "filesystem")


def act_export_chat(p):
    fmt = p.get("format", "md")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = SHARED / "exports" / ("arkax-chat-%s.%s" % (stamp, "json" if fmt == "json" else "md"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    messages = p.get("messages", [])
    if fmt == "json":
        dest.write_text(json.dumps({"title": p.get("title", "Arkaxhermes"),
                                    "messages": messages}, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        lines = ["# %s" % p.get("title", "Arkaxhermes"), ""]
        for m in messages:
            lines += ["## %s" % ("Anda" if m.get("role") == "user" else "Hermes Agent"),
                      "", str(m.get("content", "")), ""]
        dest.write_text("\n".join(lines), encoding="utf-8")
    return result("export.chat", {"path": str(dest), "bytes": dest.stat().st_size}, "filesystem")


def act_doctor(p):
    r = hermes("doctor", timeout=120)
    local = {
        "python": sys.version.split()[0], "hermesHome": str(HOME),
        "envKeys": sorted(read_env().keys()), "sessionDb": str(find_session_db() or ""),
        "services": service_states(),
    }
    return result("doctor", {"local": local, "upstream": r["stdout"],
                             "upstreamStderr": r["stderr"], "exit": r["exit"]}, "hermes-cli")


def act_update(p):
    return cli_or_fallback("update", ["update"], hint="hermes update (atau build ulang APK dengan tag baru)")



AB_BIN = "/usr/local/bin/agent-browser"
AB_SESSION = "arkaxhermes"


def ab(*args, timeout=120):
    """Wrapper agent-browser Arkaxhermes (sudah --json + session + Chrome)."""
    return run_cli([AB_BIN] + [str(a) for a in args], timeout=timeout)


def ab_json(raw, key=None):
    for line in reversed((raw or "").splitlines()):
        line = line.strip()
        if not line.startswith("{") or not line.endswith("}"):
            continue
        try:
            obj = json.loads(line)
            return obj.get(key) if key else obj
        except Exception:
            continue
    return None


def act_browser_status(p):
    stream = ab("stream", "status", timeout=30)
    url = ab("get", "url", timeout=30)
    title = ab("get", "title", timeout=30)
    cdp = ab("get", "cdp-url", timeout=30)
    return result("browser.status", {
        "session": AB_SESSION,
        "streamPort": 9223,
        "streamUrl": "ws://127.0.0.1:9223/?pacing=ack&maxFps=8",
        "dashboardUrl": "http://127.0.0.1:4848",
        "stream": ab_json(stream["stdout"]),
        "url": (ab_json(url["stdout"], "data") or {}).get("url", ""),
        "title": (ab_json(title["stdout"], "data") or {}).get("title", ""),
        "cdpUrl": (ab_json(cdp["stdout"], "data") or {}).get("cdpUrl", ""),
        "raw": {"stream": stream["stdout"], "url": url["stdout"], "cdp": cdp["stdout"]},
    }, "agent-browser")


def act_browser_command(p):
    argv = p.get("argv") or []
    if isinstance(argv, str):
        argv = argv.split()
    if not argv:
        return result("browser.command", ok=False, warnings=["argv wajib diisi"])
    r = ab(*argv)
    return result("browser.command", {"argv": argv, "parsed": ab_json(r["stdout"])},
                  "agent-browser", ok=r["ok"], raw=r,
                  fallback={"argv": [AB_BIN] + argv, "hint": "Buka Terminal"})


def act_browser_start(p):
    dash = ab("dashboard", "start", "--port", "4848", timeout=60)
    opening = ab("open", "about:blank", timeout=120)
    return result("browser.start", {
        "dashboardUrl": "http://127.0.0.1:4848",
        "streamUrl": "ws://127.0.0.1:9223/?pacing=ack&maxFps=8",
        "dashboard": dash["stdout"], "open": opening["stdout"]
    }, "agent-browser", ok=dash["ok"] and opening["ok"])


def act_browser_stop(p):
    closing = ab("close", timeout=60)
    dash = ab("dashboard", "stop", timeout=60)
    return result("browser.stop", {"close": closing["stdout"], "dashboard": dash["stdout"]},
                  "agent-browser", ok=True)


def act_browser_snapshot(p):
    r = ab("snapshot", "-i", timeout=60)
    return result("browser.snapshot", {"text": r["stdout"]}, "agent-browser", ok=r["ok"], raw=r)


def act_browser_screenshot(p):
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = "/mnt/arkax/exports/browser-%s.jpg" % stamp
    r = ab("screenshot", path, "--screenshot-format", "jpeg", "--screenshot-quality", "80", timeout=120)
    return result("browser.screenshot", {"path": path, "stdout": r["stdout"]},
                  "agent-browser", ok=r["ok"], raw=r)


def act_browser_dashboard(p):
    return result("browser.dashboard", {"url": "http://127.0.0.1:4848"}, "agent-browser")

ACTIONS = {
    "status": act_status,
    "config.get": act_config_get,
    "config.set": act_config_set,
    "env.set": act_env_set,
    "env.list": act_env_list,
    "env.delete": lambda p: result("env.delete", write_env({}, deletes=[p.get("key", "")]), "filesystem"),
    "providers.list": act_providers,
    "model.set": act_model_set,
    "skills.list": act_skills_list,
    "skills.read": act_skills_read,
    "skills.write": act_skills_write,
    "skills.delete": act_skills_delete,
    "skills.install": act_skills_install,
    "skills.nudges": act_skills_nudges,
    "memory.get": act_memory_get,
    "memory.set": act_memory_set,
    "memory.append": act_memory_append,
    "memory.clear": act_memory_clear,
    "memory.providers": act_memory_providers,
    "sessions.list": act_sessions_list,
    "sessions.search": act_sessions_search,
    "sessions.read": act_sessions_read,
    "sessions.delete": act_sessions_delete,
    "sessions.stats": act_sessions_stats,
    "sessions.export": act_sessions_export,
    "cron.list": act_cron_list,
    "cron.create": act_cron_create,
    "cron.toggle": act_cron_toggle,
    "cron.run": act_cron_run,
    "cron.remove": act_cron_remove,
    "cron.delivery": act_cron_delivery,
    "cron.status": act_cron_status,
    "cron.tick": act_cron_tick,
    "gateway.status": act_gateway_status,
    "tools.list": act_tools_list,
    "tools.set": act_tools_set,
    "tools.backend": act_tools_backend,
    "mcp.list": act_mcp_list,
    "mcp.add": act_mcp_add,
    "mcp.remove": act_mcp_remove,
    "plugins.list": act_plugins_list,
    "plugins.install": act_plugins_install,
    "plugins.remove": act_plugins_remove,
    "profiles.list": act_profiles_list,
    "profiles.create": act_profiles_create,
    "profiles.use": act_profiles_use,
    "bots.list": act_bots_list,
    "bots.set": act_bots_set,
    "hooks.list": act_hooks_list,
    "hooks.set": act_hooks_set,
    "trajectories.list": act_trajectories_list,
    "approvals.list": act_approvals_list,
    "approvals.decide": act_approvals_decide,
    "context.list": act_context_list,
    "context.add": act_context_add,
    "batch.run": act_batch_run,
    "files.list": act_files_list,
    "files.read": act_files_read,
    "files.write": act_files_write,
    "files.delete": act_files_delete,
    "files.mkdir": act_files_mkdir,
    "backup.create": act_backup_create,
    "backup.restore": act_backup_restore,
    "backups.list": act_backups_list,
    "export.chat": act_export_chat,
    "doctor": act_doctor,
    "update": act_update,
    "browser.status": act_browser_status,
    "browser.command": act_browser_command,
    "browser.start": act_browser_start,
    "browser.stop": act_browser_stop,
    "browser.snapshot": act_browser_snapshot,
    "browser.screenshot": act_browser_screenshot,
    "browser.dashboard": act_browser_dashboard,
}

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "--list"):
        print(json.dumps({"actions": sorted(ACTIONS), "hermesHome": str(HOME),
                          "hermesBin": HERMES}, indent=2))
        return 0
    action = sys.argv[1]
    raw_payload = sys.argv[2] if len(sys.argv) > 2 else (sys.stdin.read() if not sys.stdin.isatty() else "")
    try:
        payload = json.loads(raw_payload) if raw_payload.strip() else {}
    except json.JSONDecodeError as exc:
        out(result(action, ok=False, warnings=["payload bukan JSON: %s" % exc]))
        return 2
    handler = ACTIONS.get(action)
    if handler is None:
        out(result(action, ok=False, warnings=["aksi tidak dikenal"],
                   fallback={"argv": [HERMES, *action.split(".")],
                             "hint": "Buka Terminal dan jalankan perintah Hermes langsung"}))
        return 3
    try:
        out(handler(payload))
    except Exception as exc:
        out(result(action, ok=False, warnings=["%s: %s" % (type(exc).__name__, exc)],
                   fallback={"argv": [HERMES, "--help"], "hint": "Lihat /api/logs"}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
