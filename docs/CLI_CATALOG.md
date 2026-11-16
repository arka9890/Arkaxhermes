# Katalog CLI Hermes Agent v0.23.1

Dihasilkan dari `python3 hermes --help` dan `<command> --help` pada source yang dibundel Arkaxhermes.

| Perintah | Keterangan | Subcommand |
| --- | --- | --- |
| `chat` | Interactive chat with the agent |  |
| `model` | Select default model and provider |  |
| `moa` | Configure Mixture of Agents provider/model slots | `list`, `ls`, `configure`, `config`, `delete`, `rm` |
| `fallback` | Manage fallback providers (tried when the primary model fails) | `list`, `ls`, `add`, `remove`, `rm`, `clear` |
| `worktree` | Audit and reclaim accumulated git worktrees and merged branches | `list`, `ls`, `audit`, `prune`, `restore` |
| `browser` | Real-profile browsing helpers (close a browser locking its profile) | `close-profile`, `export-signins` |
| `secrets` | Manage external secret sources (Bitwarden, 1Password) | `bitwarden`, `bw`, `onepassword`, `op`, `1password` |
| `egress` | Manage the iron-proxy egress credential-injection firewall | `install`, `setup`, `start`, `stop`, `restart`, `reload`, `status`, `disable`, `config` |
| `migrate` | Move over from another agent, or migrate retired models and deprecated settings | `xai`, `relay`, `openclaw`, `claude-code`, `codex`, `cursor`, `grok-bot`, `openbot` |
| `codex-runtime` | Manage the optional codex app-server runtime (migrate MCP config) | `migrate` |
| `gateway` | Messaging gateway management | `run`, `ensure`, `attach`, `start`, `stop`, `restart`, `status`, `install`, `uninstall`, `list`, `setup`, `migrate-legacy` |
| `proxy` | Local OpenAI-compatible proxy to OAuth providers | `start`, `status`, `providers` |
| `lsp` | Language Server Protocol management | `status`, `list`, `install`, `install-all`, `restart`, `which` |
| `setup` | Interactive setup wizard |  |
| `whatsapp` | Set up WhatsApp integration |  |
| `whatsapp-cloud` | Set up WhatsApp Business Cloud API integration |  |
| `slack` | Slack integration helpers (manifest generation, etc.) | `manifest` |
| `send` | Send a message to a configured platform (scripts, cron jobs, CI). |  |
| `logout` | Clear authentication for an inference provider |  |
| `auth` | Manage pooled provider credentials | `add`, `list`, `remove`, `reset`, `priority`, `refresh`, `status`, `logout`, `upgrade` |
| `status` | Show status of all components | `list`, `prune` |
| `pause` | Emergency stop: pause cron/kanban dispatch and new gateway turns | `resume` |
| `resume` | Lift the emergency stop set by `hermes pause` |  |
| `cron` | Cron job management | `list`, `create`, `add`, `edit`, `pause`, `resume`, `run`, `cancel`, `remove`, `rm`, `delete`, `status` |
| `webhook` | Manage dynamic webhook subscriptions | `subscribe`, `add`, `list`, `ls`, `remove`, `rm`, `test` |
| `peer` | Bot-to-bot DMs across machines (peer Hermes gateways) | `add`, `set`, `list`, `ls`, `remove`, `rm`, `dm`, `run`, `status`, `stop` |
| `portal` | Set up Nous Portal (login, model pick, Tool Gateway); see also `portal info` | `login`, `info`, `status`, `open`, `tools` |
| `kanban` | Multi-profile collaboration board (tasks, links, comments) |  |
| `project` | Manage projects (named, multi-folder workspaces) | `create`, `list`, `ls`, `show`, `add-folder`, `remove-folder`, `rename`, `set-primary`, `use`, `archive`, `restore`, `bind-board` |
| `hooks` | Inspect and manage shell-script hooks | `list`, `ls`, `test`, `revoke`, `remove`, `rm`, `doctor` |
| `doctor` | Check configuration and dependencies |  |
| `verify` | Detect a project's run recipe and smoke-test it |  |
| `security` | Supply-chain audit (OSV.dev) for venv, plugins, and MCP servers | `audit` |
| `approvals` | Approval-prompt tools (mine history into allowlist proposals) | `suggest`, `test` |
| `dump` | Dump setup summary for support/debugging |  |
| `debug` | Debug tools — upload logs and system info for support | `share`, `delete` |
| `backup` | Back up Hermes home directory to a zip file |  |
| `checkpoints` | Inspect / prune / clear ~/.hermes/checkpoints/ |  |
| `import` | Restore a Hermes backup from a zip file |  |
| `config` | View and edit configuration | `show`, `edit`, `get`, `set`, `unset`, `path`, `env-path`, `check`, `migrate` |
| `skin` | List, switch, and tweak skins | `list`, `use`, `set` |
| `console` | Open the safe Hermes command console |  |
| `pairing` | Manage DM pairing codes for user authorization | `list`, `approve`, `revoke`, `clear-pending` |
| `skills` | Search, install, configure, and manage skills | `trust`, `untrust`, `browse`, `search`, `install`, `inspect`, `list`, `check`, `update`, `audit`, `uninstall`, `reset` |
| `bundles` | Create, list, and manage skill bundles (aliases for multiple skills) | `list`, `show`, `create`, `delete`, `reload` |
| `plugins` | Manage and validate plugins | `install`, `search`, `browse`, `validate`, `update`, `auto-update`, `adopt`, `trust-update-url`, `check-updates`, `remove`, `list`, `enable` |
| `curator` | Background skill maintenance (curator) — status, run, pause, pin | `status`, `usage`, `run`, `pause`, `resume`, `pin`, `unpin`, `lock`, `unlock`, `list-unmanaged`, `adopt`, `restore` |
| `pets` | Browse, install, and select petdex animated pets | `list`, `install`, `select`, `show`, `off`, `scale`, `remove`, `doctor` |
| `clipboard` | Read this machine's clipboard (device-local) | `image` |
| `journey` | (learning, memory-graph) Timeline of learned skills + memories over time | `list`, `delete`, `edit` |
| `memory` | Configure external memory provider | `setup`, `status`, `off`, `reset` |
| `tools` | Configure which tools are enabled per platform | `list`, `disable`, `enable`, `post-setup` |
| `computer-use` | Manage the Computer Use (cua-driver) backend (macOS/Windows/Linux) | `install`, `status`, `doctor`, `permissions`, `screen` |
| `mcp` | Manage MCP server connections | `add`, `remove`, `rm`, `list`, `ls`, `test`, `configure`, `config`, `login`, `reauth`, `picker`, `catalog` |
| `connectors` | Manage hosted app connectors and their accounts | `list`, `ls`, `accounts`, `connect`, `rename`, `disconnect` |
| `sessions` | Manage session history (list, rename, export, prune, delete) | `list`, `export`, `delete`, `prune`, `archive`, `optimize`, `clean-markers`, `optimize-storage`, `repair`, `set-journal-mode`, `repair-routing`, `repair-profiles` |
| `insights` | Show usage insights and analytics |  |
| `usage` | Show account rate-limit windows (the /usage block) without starting a session |  |
| `monitoring` | Inspect gateway monitoring (health & diagnostics export) | `status` |
| `vault` | Manage the local encrypted autofill vault (add/list/rm credentials) | `add`, `list`, `rm`, `sources`, `key` |
| `update` | Update Hermes Agent to the latest version |  |
| `uninstall` | Uninstall Hermes Agent |  |
| `acp` | Run Hermes Agent as an ACP (Agent Client Protocol) server |  |
| `profile` | Manage profiles — multiple isolated Hermes instances | `list`, `use`, `create`, `delete`, `describe`, `show`, `alias`, `rename`, `purge-identity`, `migrate-identity`, `export`, `import` |
| `completion` | Print shell completion script (bash, zsh, or fish) |  |
| `dashboard` | Start the web UI dashboard | `register` |
| `serve` | Start the Hermes backend server (headless; powers the desktop app and remote backends) |  |
| `webapp` | Open the Hermes Desktop workspace in a browser |  |
| `desktop` | (gui)       Build and launch the native desktop app |  |
| `logs` | View and filter Hermes log files |  |
| `prompt-size` | Show a byte breakdown of the system prompt + tool schemas |  |

## Browser bawaan: `agent-browser` v0.43.0

Sumber: [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser), Apache-2.0.
Dijalankan Arkaxhermes dengan sesi tetap `arkaxhermes`, stream `9223`, dashboard `4848`,
dan Chrome for Testing 157.0.8103.78 linux-arm64.

| Perintah | Fungsi |
| --- | --- |
| `agent-browser open <url>` | Buka/navigasi halaman |
| `agent-browser back` / `forward` / `reload` | Navigasi riwayat |
| `agent-browser snapshot -i` | Accessibility tree + `@eN` ref |
| `agent-browser click <sel>` / `fill` / `type` / `press` | Interaksi elemen |
| `agent-browser get url` / `title` / `cdp-url` | Info halaman & CDP |
| `agent-browser screenshot <path> --screenshot-format jpeg` | Tangkapan layar |
| `agent-browser tab list` | Daftar tab |
| `agent-browser stream status` | Status WebSocket live viewport |
| `agent-browser stream enable --port 9223` | Aktifkan stream port tetap |
| `agent-browser dashboard start --port 4848` | Dashboard observability |
| `agent-browser close` / `dashboard stop` | Tutup sesi & dashboard |
| `agent-browser skills get core` | Panduan resmi sesuai versi CLI |
| `agent-browser mcp` | MCP server stdio untuk klien lain |

Protokol live frame dan input (mouse/keyboard/touch): [Streaming docs](https://agent-browser.dev/streaming).
