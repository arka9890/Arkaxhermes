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
SHARED = Path("/mnt/arkax")
SRC = Path("/opt/hermes-agent")
HERMES = shutil.which("hermes") or "/usr/local/bin/hermes"

ALLOWED_ROOTS = [HOME, SHARED, Path("/opt/arkax"), SRC]
PROVIDERS = [
    ("nous", "Nous Portal", "NOUS_API_KEY", "300+ model + Tool Gateway, OAuth"),
    ("anthropic", "Anthropic", "ANTHROPIC_API_KEY", "Claude family, prompt caching"),
    ("openai", "OpenAI", "OPENAI_API_KEY", "GPT family, responses API"),
    ("openrouter", "OpenRouter", "OPENROUTER_API_KEY", "200+ model, satu kunci"),
    ("gemini", "Google AI", "GOOGLE_API_KEY", "Gemini family"),
    ("deepseek", "DeepSeek", "DEEPSEEK_API_KEY", "DeepSeek V3 / R1"),
    ("xai", "xAI (Grok)", "XAI_API_KEY", "x_search, Grok"),
    ("groq", "Groq", "GROQ_API_KEY", "Inferensi cepat"),
    ("mistral", "Mistral", "MISTRAL_API_KEY", "Mistral / Codestral"),
    ("bedrock", "AWS Bedrock", "AWS_ACCESS_KEY_ID", "Bedrock, fast mode Mantle"),
    ("azure-foundry", "Azure AI Foundry", "AZURE_API_KEY", "Azure OpenAI"),
    ("zai", "Z.ai", "ZAI_API_KEY", "GLM family"),
    ("kimi-coding", "Kimi", "KIMI_API_KEY", "Kimi coding"),
    ("minimax", "MiniMax", "MINIMAX_API_KEY", "MiniMax family"),
    ("qwen-oauth", "Qwen", "QWEN_API_KEY", "Qwen OAuth"),
    ("novita", "Novita AI", "NOVITA_API_KEY", "Hosted open models"),
    ("huggingface", "Hugging Face", "HF_TOKEN", "Inference endpoints"),
    ("nvidia", "NVIDIA NIM", "NVIDIA_API_KEY", "NIM endpoints"),
    ("ollama", "Ollama Local", "OLLAMA_BASE_URL", "Model lokal di endpoint"),
    ("lmstudio", "LM Studio", "LMSTUDIO_BASE_URL", "Model lokal (OpenAI-compatible)"),
    ("copilot", "GitHub Copilot", "GITHUB_TOKEN", "Copilot / ACP"),
    ("custom", "Endpoint kustom", "OPENAI_BASE_URL", "OpenAI-compatible URL"),
]
TOOLSETS = [
    "web", "search", "terminal", "file", "browser", "vision", "image_gen",
    "skills", "tts", "todo", "memory", "session_search", "cronjob",
    "code_execution", "delegation", "clarify", "messaging", "discord",
    "discord_admin", "debugging", "safe",
]


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
    for p in sorted(HOME.rglob("*.db")):
        try:
            con = sqlite3.connect("file:%s?mode=ro" % p, uri=True, timeout=2)
            names = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            con.close()
            if any(("session" in n or "message" in n) for n in names):
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
        "envKeys": sorted(env.keys()), "sessionDb": str(db) if db else None,
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
    r = hermes("config", "get", key)
    if r["ok"]:
        return result("config.get", {"key": key, "value": r["stdout"]}, "hermes-cli", raw=r)
    cfg = HOME / "config.yaml"
    value = None
    if cfg.exists():
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.match(r"^\s*%s\s*:" % re.escape(key.split(".")[-1]), line):
                value = line.split(":", 1)[1].strip()
                break
    return result("config.get", {"key": key, "value": value}, "config.yaml",
                  warnings=[] if value is not None else ["kunci tidak ditemukan; gunakan hermes config get"],
                  fallback={"argv": [HERMES, "config", "get", key]})


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
    cfg = hermes("config", "get", "provider", timeout=20)
    active = cfg["stdout"].strip() if cfg["ok"] else ""
    return result("providers.list", [{
        "id": pid, "name": name, "envKey": envkey, "note": note,
        "configured": bool(env.get(envkey)), "active": active == pid,
    } for pid, name, envkey, note in PROVIDERS], "bridge+filesystem")


def act_model_set(p):
    cmds = []
    if p.get("provider"):
        cmds.append(("config", "set", "provider", p["provider"]))
    if p.get("model"):
        cmds.append(("config", "set", "model", p["model"]))
    if not cmds:
        return result("model.set", ok=False, warnings=["provider atau model wajib diisi"])
    results = [hermes(*c) for c in cmds]
    return result("model.set", {"commands": [" ".join(c) for c in cmds],
                                "ok": all(r["ok"] for r in results)},
                  "hermes-cli", raw=results,
                  warnings=["Sebagian rilis memakai `hermes model` interaktif; gunakan /model di Chat bila config.set gagal"])


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
    return cli_or_fallback("skills.install", ["skills", "install", name],
                           hint="hermes skills install / Skills Hub (agentskills.io)")


def act_skills_nudges(p):
    r = hermes("config", "get", "memory.nudge", timeout=20)
    return result("skills.nudges", {"enabled": r["ok"] and "true" in r["stdout"].lower(),
                                    "raw": r["stdout"]}, "hermes-cli")


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
    return result("memory.providers", {"plugins": data,
                                       "honcho": "honcho" in str(data).lower()},
                  "hermes-cli", warnings=[] if r["ok"] else ["hermes plugins list tidak tersedia; jalankan hermes plugins install honcho"])


def act_sessions_list(p):
    db = find_session_db()
    if not db:
        return result("sessions.list", [], "none",
                      warnings=["session store SQLite belum ditemukan"],
                      fallback={"argv": [HERMES, "sessions", "list"], "hint": "Buka Terminal"})
    limit = int(p.get("limit", 100))
    queries = [
        "SELECT * FROM sessions ORDER BY rowid DESC LIMIT ?",
        "SELECT * FROM session ORDER BY rowid DESC LIMIT ?",
    ]
    for sql in queries:
        try:
            rows = db_query(db, sql, (limit,))
            return result("sessions.list", rows, "sqlite:%s" % db.name)
        except Exception:
            continue
    return cli_or_fallback("sessions.list", ["sessions", "list", "--json"], parse_json=True)


def act_sessions_search(p):
    q = p.get("query", "").strip()
    if not q:
        return result("sessions.search", [], "bridge", warnings=["query kosong"])
    db = find_session_db()
    if not db:
        return result("sessions.search", [], "none",
                      warnings=["session store belum ada"],
                      fallback={"argv": [HERMES, "sessions", "search", q]})
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=3)
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    finally:
        con.close()
    for fts in [t for t in tables if "fts" in t.lower()]:
        try:
            rows = db_query(db, "SELECT * FROM %s WHERE %s MATCH ? LIMIT 50" % (fts, fts), (q,))
            return result("sessions.search", rows, "fts5:%s" % fts)
        except Exception:
            continue
    for t in [t for t in tables if "message" in t.lower()]:
        try:
            rows = db_query(db, "SELECT * FROM %s WHERE content LIKE ? LIMIT 50" % t, ("%%%s%%" % q,))
            return result("sessions.search", rows, "like:%s" % t)
        except Exception:
            continue
    return cli_or_fallback("sessions.search", ["sessions", "search", q, "--json"], parse_json=True)


def act_sessions_read(p):
    sid = p.get("id", "")
    return cli_or_fallback("sessions.read", ["sessions", "show", sid, "--json"], parse_json=True,
                           hint="hermes --resume <id>")


def act_sessions_delete(p):
    sid = p.get("id", "")
    if not sid:
        return result("sessions.delete", ok=False, warnings=["id wajib diisi"])
    return cli_or_fallback("sessions.delete", ["sessions", "delete", sid], hint="hermes sessions delete")


def act_sessions_stats(p):
    db = find_session_db()
    if not db:
        return result("sessions.stats", {"sessions": 0, "messages": 0, "tokens": 0}, "none",
                      warnings=["data statistik belum tersedia"])
    stats = {}
    for table, label in (("sessions", "sessions"), ("messages", "messages")):
        try:
            stats[label] = db_query(db, "SELECT COUNT(*) AS n FROM %s" % table)[0]["n"]
        except Exception:
            stats[label] = 0
    return result("sessions.stats", stats, "sqlite")


def act_cron_list(p):
    jobs_file = HOME / "cron" / "jobs.json"
    if jobs_file.exists():
        data = read_json(jobs_file, {})
        jobs = data.get("jobs", data) if isinstance(data, dict) else data
        return result("cron.list", jobs, "jobs.json")
    return cli_or_fallback("cron.list", ["cron", "list", "--json"], parse_json=True)


def act_cron_create(p):
    schedule, prompt = p.get("schedule"), p.get("prompt")
    if not schedule or not prompt:
        return result("cron.create", ok=False, warnings=["schedule dan prompt wajib diisi"])
    argv = ["cron", "create", schedule, prompt]
    for skill in p.get("skills", []) or ([p["skill"]] if p.get("skill") else []):
        argv += ["--skill", skill]
    if p.get("name"):
        argv += ["--name", p["name"]]
    if p.get("model"):
        argv += ["--model", p["model"]]
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
    return cli_or_fallback("cron.delivery", ["send", p.get("platform", ""), p.get("message", "")])


def act_tools_list(p):
    pref = read_json(HOME / "arkax-toolsets.json", {"enabled": TOOLSETS})
    r = hermes("tools", "--json", timeout=30)
    data = r["stdout"]
    try:
        data = json.loads(data)
    except Exception:
        data = None
    return result("tools.list", {
        "toolsets": [{"name": t, "enabled": t in pref.get("enabled", TOOLSETS)} for t in TOOLSETS],
        "upstream": data,
    }, "bridge", warnings=[] if r["ok"] else ["hermes tools --json tidak tersedia; memakai daftar bawaan"])


def act_tools_set(p):
    enabled = p.get("toolsets") or p.get("enabled") or []
    write_json(HOME / "arkax-toolsets.json", {"enabled": enabled}, 0o600)
    r = hermes("config", "set", "toolsets", ",".join(enabled))
    return result("tools.set", {"enabled": enabled, "cliOk": r["ok"]}, "filesystem+hermes-cli",
                  warnings=[] if r["ok"] else ["config.set gagal; toolset akan dikirim lewat --toolsets pada chat"],
                  raw=r)


def act_tools_backend(p):
    backend = p.get("backend", "local")
    return cli_or_fallback("tools.backend", ["config", "set", "terminal.backend", backend],
                           hint="terminal.backend: local|docker|ssh|modal|daytona|vercel_sandbox")


def act_mcp_list(p):
    for name in ("mcp.json", "mcp_servers.json"):
        path = HOME / name
        if path.exists():
            return result("mcp.list", read_json(path, {}), "filesystem:%s" % name)
    return cli_or_fallback("mcp.list", ["mcp", "list", "--json"], parse_json=True)


def act_mcp_add(p):
    name = p.get("name", "")
    if not name:
        return result("mcp.add", ok=False, warnings=["name wajib diisi"])
    if cli_supported("mcp", "add"):
        argv = ["mcp", "add", name]
        if p.get("command"):
            argv += ["--command", p["command"]]
        if p.get("url"):
            argv += ["--url", p["url"]]
        r = cli_or_fallback("mcp.add", argv)
        if r["ok"]:
            return r
    path = HOME / "mcp.json"
    data = read_json(path, {"servers": {}})
    data.setdefault("servers", {})[name] = {
        "transport": p.get("transport", "stdio"),
        "command": p.get("command"), "args": p.get("args", []),
        "url": p.get("url"), "env": p.get("env", {}),
        "enabled": True,
    }
    write_json(path, data)
    return result("mcp.add", {"name": name}, "filesystem:mcp.json",
                  warnings=["Ditulis ke ~/.hermes/mcp.json; pastikan rilis Hermes membaca berkas ini atau jalankan `hermes mcp add` di Terminal"],
                  fallback={"argv": [HERMES, "mcp", "list"]})


def act_mcp_remove(p):
    name = p.get("name", "")
    path = HOME / "mcp.json"
    data = read_json(path, {"servers": {}})
    data.setdefault("servers", {}).pop(name, None)
    write_json(path, data)
    return result("mcp.remove", {"name": name}, "filesystem:mcp.json",
                  warnings=["Jalankan `hermes mcp remove %s` bila server juga terdaftar di config.yaml" % name])


def act_plugins_list(p):
    r = hermes("plugins", "list", "--json", timeout=30)
    data = r["stdout"]
    try:
        data = json.loads(data)
    except Exception:
        data = [d.name for d in (HOME / "plugins").glob("*")] if (HOME / "plugins").exists() else []
    return result("plugins.list", data, "hermes-cli" if r["ok"] else "filesystem")


def act_plugins_install(p):
    return cli_or_fallback("plugins.install", ["plugins", "install", p.get("name", "")])


def act_plugins_remove(p):
    return cli_or_fallback("plugins.remove", ["plugins", "remove", p.get("name", "")])


def act_profiles_list(p):
    base = HOME.parent
    names = [d.name for d in base.glob(".hermes*") if d.is_dir()]
    r = hermes("profile", "list", "--json", timeout=25)
    return result("profiles.list", {"directories": names, "upstream": r["stdout"] if r["ok"] else None},
                  "filesystem", warnings=["Gunakan `hermes profile use <name>` untuk isolasi penuh HERMES_HOME"])


def act_profiles_create(p):
    name = re.sub(r"[^a-zA-Z0-9_-]", "", p.get("name", ""))
    if not name:
        return result("profiles.create", ok=False, warnings=["name tidak valid"])
    path = HOME.parent / (".hermes-" + name)
    path.mkdir(parents=True, exist_ok=True)
    for sub in ("skills", "logs", "cron", "plugins", "profiles", "context"):
        (path / sub).mkdir(exist_ok=True)
    (path / ".env").touch(exist_ok=True)
    os.chmod(path / ".env", 0o600)
    return result("profiles.create", {"name": name, "home": str(path)}, "filesystem",
                  warnings=["Jalankan `hermes --profile %s setup` untuk mengaktifkan" % name])


def act_profiles_use(p):
    name = p.get("name", "default")
    atomic_write(HOME / "arkax-active-profile", name + "\n", 0o600)
    return cli_or_fallback("profiles.use", ["profile", "use", name],
                           hint="hermes --profile <name> …")


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
    items = [{"name": f.name, "size": f.stat().st_size}
             for f in sorted((HOME / "hooks").glob("*")) if f.is_file()]
    return result("hooks.list", items, "filesystem")


def act_hooks_set(p):
    name = re.sub(r"[^a-zA-Z0-9_.-]", "", p.get("name", ""))
    if not name:
        return result("hooks.set", ok=False, warnings=["name tidak valid"])
    atomic_write(HOME / "hooks" / name, p.get("content", ""), 0o644)
    return result("hooks.set", {"name": name}, "filesystem")


def act_trajectories_list(p):
    items = []
    for f in sorted(HOME.rglob("*.jsonl")):
        items.append({"path": str(f), "size": f.stat().st_size,
                      "lines": sum(1 for _ in f.open(encoding="utf-8", errors="replace"))})
    return result("trajectories.list", items, "filesystem")


def act_approvals_list(p):
    items = []
    for f in sorted((HOME / "approvals").glob("*.json")):
        items.append(read_json(f, {"id": f.stem}))
    r = hermes("approvals", "list", "--json", timeout=20)
    return result("approvals.list", {"local": items, "upstream": r["stdout"] if r["ok"] else None},
                  "filesystem", warnings=["Antrean approval resmi dikelola proses Hermes yang sedang berjalan"])


def act_approvals_decide(p):
    aid, decision = p.get("id"), p.get("decision")
    if decision not in ("approve", "deny", "always", "never"):
        return result("approvals.decide", ok=False, warnings=["decision tidak valid"])
    write_json(HOME / "approvals" / ("%s.json" % re.sub(r"[^a-zA-Z0-9_-]", "", str(aid))),
               {"id": aid, "decision": decision,
                "at": dt.datetime.now(dt.timezone.utc).isoformat()}, 0o600)
    r = hermes("approvals", decision, str(aid), timeout=20)
    return result("approvals.decide", {"id": aid, "decision": decision, "cliOk": r["ok"]},
                  "filesystem+hermes-cli",
                  warnings=[] if r["ok"] else ["Subcommand approvals tidak tersedia; keputusan dicatat lokal, gunakan tombol approval di TUI/Terminal"],
                  raw=r)


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
    commands = p.get("commands", [])
    results = []
    for c in commands[:25]:
        argv = c if isinstance(c, list) else ["hermes", "chat", "-q", str(c)]
        results.append({"argv": argv, **run_cli([HERMES if a == "hermes" else a for a in argv], timeout=180)})
    return result("batch.run", results, "hermes-cli")


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
    dest = SHARED / "exports" / ("arkax-backup-%s.tar.gz" % stamp)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, "w:gz") as tar:
        tar.add(HOME, arcname=".hermes", recursive=True)
    sha = hashlib.sha256(dest.read_bytes()).hexdigest()
    return result("backup.create", {"path": str(dest), "size": dest.stat().st_size,
                                    "sha256": sha}, "filesystem")


def act_backup_restore(p):
    archive = safe_path(p.get("path", ""))
    with tarfile.open(archive, "r:*") as tar:
        for member in tar.getmembers():
            target = (HOME.parent / member.name).resolve()
            if not str(target).startswith(str(HOME.parent)) or ".." in Path(member.name).parts:
                return result("backup.restore", ok=False, warnings=["arsip berisi path berbahaya"])
        tar.extractall(HOME.parent)
    return result("backup.restore", {"path": str(archive)}, "filesystem")


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


ACTIONS = {
    "status": act_status,
    "config.get": act_config_get, "config.set": act_config_set,
    "env.set": act_env_set, "env.list": act_env_list, "env.delete": lambda p: result("env.delete", write_env({}, deletes=[p.get("key", "")]), "filesystem"),
    "providers.list": act_providers, "model.set": act_model_set,
    "skills.list": act_skills_list, "skills.read": act_skills_read,
    "skills.write": act_skills_write, "skills.delete": act_skills_delete,
    "skills.install": act_skills_install, "skills.nudges": act_skills_nudges,
    "memory.get": act_memory_get, "memory.set": act_memory_set,
    "memory.append": act_memory_append, "memory.clear": act_memory_clear,
    "memory.providers": act_memory_providers,
    "sessions.list": act_sessions_list, "sessions.search": act_sessions_search,
    "sessions.read": act_sessions_read, "sessions.delete": act_sessions_delete,
    "sessions.stats": act_sessions_stats,
    "cron.list": act_cron_list, "cron.create": act_cron_create,
    "cron.toggle": act_cron_toggle, "cron.run": act_cron_run,
    "cron.remove": act_cron_remove, "cron.delivery": act_cron_delivery,
    "tools.list": act_tools_list, "tools.set": act_tools_set,
    "tools.backend": act_tools_backend,
    "mcp.list": act_mcp_list, "mcp.add": act_mcp_add, "mcp.remove": act_mcp_remove,
    "plugins.list": act_plugins_list, "plugins.install": act_plugins_install,
    "plugins.remove": act_plugins_remove,
    "profiles.list": act_profiles_list, "profiles.create": act_profiles_create,
    "profiles.use": act_profiles_use,
    "bots.list": act_bots_list, "bots.set": act_bots_set,
    "hooks.list": act_hooks_list, "hooks.set": act_hooks_set,
    "trajectories.list": act_trajectories_list,
    "approvals.list": act_approvals_list, "approvals.decide": act_approvals_decide,
    "context.list": act_context_list, "context.add": act_context_add,
    "batch.run": act_batch_run,
    "files.list": act_files_list, "files.read": act_files_read,
    "files.write": act_files_write, "files.delete": act_files_delete,
    "backup.create": act_backup_create, "backup.restore": act_backup_restore,
    "export.chat": act_export_chat,
    "doctor": act_doctor, "update": act_update,
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
