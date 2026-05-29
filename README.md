# perskent

CLI for managing AI code-agent packages (skills, agents, commands) via your own private Git repository — no central registry, no third-party host.

You point `pskt` at your own repo (a private GitHub repo works fine), and the CLI handles installation, updates, versioning, and publishing of your packages to the chosen code-agent's directory at the chosen scope (global or per-project).

**Supported code-agents:** [Claude Code](https://claude.com/claude-code), [opencode](https://opencode.ai), [Qwen Code](https://github.com/QwenLM/qwen-code), [OpenAI Codex CLI](https://github.com/openai/codex), [Cursor](https://cursor.com). You pick which one each scope targets at `pskt init` time — see [Code-agents](#code-agents) below.

## Installation

One-liner (Linux / macOS, requires Python 3.11+):

```bash
curl -fsSL https://raw.githubusercontent.com/Alecell/Perskent/main/install.sh | sh
```

The script detects `python3.11+`, ensures `pipx` is available on your system, and installs `perskent` into an isolated environment. The `pskt` and `perskent` commands become available on your `PATH`.

Direct install via pipx:

```bash
pipx install git+https://github.com/Alecell/Perskent.git
```

Upgrade later:

```bash
pipx upgrade perskent
```

## Quick start

```bash
pskt init                         # registry URL + token, and which code-agent each scope targets
pskt find remote                  # list packages available in the registry
pskt install my-agent root        # install in the global dir of the chosen code-agent
pskt install my-skill project     # install in the project dir of the chosen code-agent
pskt install                      # or run without args for an interactive picker
pskt code-agent opencode root     # later: switch the root scope to a different code-agent
```

## Commands

| Command | Description |
|---|---|
| `pskt init` | Configure remote registry URL and clone it into `~/.pskt/` |
| `pskt doctor` | Diagnostics (Python, git, paths, token, reachability) |
| `pskt status` | Consolidated view: workspace state, registry packages, installations (outdated/orphaned) |
| `pskt sync` | `git pull` on the local workspace |
| `pskt find remote` | List packages available in the registry |
| `pskt find local` | List installed packages (root + project) |
| `pskt show <name>` | Show details of a package |
| `pskt search <term>` | Search by name or description |
| `pskt install [<name>] [<root\|project>] [--force]` | Install a package (interactive picker if args omitted) |
| `pskt remove [<name>] [<root\|project>]` | Uninstall a package (interactive picker if args omitted) |
| `pskt update [<name>] [<root\|project>]` | Upgrade a package, preserving files marked in `[update].preserve` (interactive picker if args omitted) |
| `pskt add [<name>] [<root\|project>]` | Bring an artifact already in the code-agent's directory into the workspace (reverse of `install`); generates a manifest and registers it as installed |
| `pskt push [<name>]` `[<root\|project>]` `[-m <msg>]` | Publish a package. Without a scope: a package edited directly in `~/.pskt/`. With a scope: an installation edited in place (see [Publishing edits made in place](#publishing-edits-made-in-place)) |
| `pskt destroy <name> [-y]` | Permanently delete a package from the registry (workspace + remote). Does not affect installed copies. |
| `pskt code-agent [<tool>] [<root\|project>]` | Show or change which code-agent each scope targets. Without args, shows the current config. |

For any command that accepts `<name>`: if packages with the same name exist in multiple kinds, use the qualified name — `agents/my-thing`, `skills/my-thing`, `commands/my-thing`.

## Interactive prompts

`push`, `install`, `remove`, `update`, and `add` accept their arguments interactively when omitted — arrow keys + enter:

```bash
pskt push          # picker for workspace packages (edited in ~/.pskt/)
pskt push root     # picker for root installations with local edits to publish
pskt push project  # picker for project installations with local edits to publish
pskt install       # picker for registry packages → scope picker
pskt remove        # scope picker → picker for packages installed in that scope
pskt update        # scope picker → picker for packages installed in that scope
pskt add           # scope picker → picker for un-registered artifacts in that scope
```

Example output:

```
? Scope?
  ❯ root
    project

? Which package to update in root?
  ❯ agents/my-agent    v1.0.0
    skills/helper      v0.3.0
    commands/init      v0.2.0
```

Partial arguments still work — `pskt install foo` only prompts for the missing scope; `pskt update agents/foo root` runs non-interactively.

For `remove` and `update`, scope must be provided (either as a positional argument or via the picker). This prevents silent updates of the wrong installation when a package is installed in both `root` and `project`.

## Concepts

### Remote registry vs local workspace

- **Remote registry** — your private Git repository (e.g. `your-user/my-registry`) that stores versioned packages.
- **Local workspace** — clone of the registry at `~/.pskt/`. This is where you **edit** packages; `pskt push` syncs them to the remote.
- **Installation** — copies files from the local workspace into the directory consumed by the chosen code-agent (not a symlink; code-agents read physical files).

### Scopes (root vs project)

- **`root`** — installs into the chosen code-agent's global directory (e.g. `~/.claude/`, `~/.config/opencode/`), available across all projects.
- **`project`** — installs into the chosen code-agent's project-local directory (e.g. `./.claude/`, `./.opencode/`), this project only.

The two scopes can target different code-agents. `pskt find local` shows both scopes simultaneously when run from inside a project, with the code-agent of each scope labelled.

### Code-agents

`pskt init` asks which code-agent each scope targets and persists the choice. CLIs found on `PATH` are offered first as defaults.

| Code-agent | Root install dir | Project install dir |
|---|---|---|
| `claude` (Claude Code) | `~/.claude/` | `./.claude/` |
| `opencode` | `~/.config/opencode/` | `./.opencode/` |
| `qwen` (Qwen Code) | `~/.qwen/` | `./.qwen/` |
| `codex` (OpenAI Codex CLI) | `~/.codex/` | `./.codex/` |
| `cursor` (Cursor) | `~/.cursor/` | `./.cursor/` |

Switch later with `pskt code-agent <tool> [root|project]`. Without arguments, `pskt code-agent` prints the current configuration.

**Per-code-agent supported kinds.** perskent only orchestrates files — it does not edit the code-agent's `settings.json` / `config.toml`. Some code-agents accept a given kind only inline in their config, not as a standalone file; in those cases `pskt install` refuses the kind with a clear message:

| Kind     | claude | opencode | qwen | codex                  | cursor |
|----------|:------:|:--------:|:----:|:----------------------:|:------:|
| `agent`    |   ✓    |    ✓     |  ✓   | ✗ (inline in `config.toml`) | ✓ (`.cursor/agents/`) |
| `skill`    |   ✓    |    ✓     |  ✓   | ✓ (installed into `~/.agents/skills/`, by Codex convention) | ✓ (`.cursor/skills/`) |
| `command`  |   ✓    |    ✓     |  ✓   | ✗ (no file-based slash commands)   | ✓ (`.cursor/commands/`) |

The file content (frontmatter format, etc.) is the package author's responsibility — perskent never reads or rewrites the files it copies, so a package written for one code-agent's frontmatter conventions may not work on another without adjustments.

### Registry layout

```
<your-registry>/
├── agents/
│   └── my-agent/
│       ├── manifest.toml
│       ├── agents/my-agent.md           → <code-agent-dir>/agents/my-agent.md
│       └── agent-memory/my-agent/...    → <code-agent-dir>/agent-memory/my-agent/...
├── skills/
│   └── my-skill/
│       ├── manifest.toml
│       └── skills/my-skill/SKILL.md     → <code-agent-dir>/skills/my-skill/SKILL.md
└── commands/
    └── my-cmd/
        ├── manifest.toml
        └── commands/my-cmd.md           → <code-agent-dir>/commands/my-cmd.md
```

The parent folder (`agents`, `skills`, `commands`) signals the package **kind**. Each package's contents (except `manifest.toml`) are mirrored **1:1** into the code-agent's directory for the chosen scope — no renaming, no imposed layout convention. The author decides the structure inside the package.

## Publishing edits made in place

Packages often evolve while you _use_ them — you tweak a skill's `SKILL.md` directly inside `~/.claude/skills/...` as you discover what works. `pskt push <scope>` publishes those in-place edits without you having to copy anything back by hand:

```bash
pskt push project              # picker of project installations with local edits
pskt push root                 # same, for the global scope
pskt push skills/my-skill root # target a specific installation
```

It mirrors the installation back into the workspace (`~/.pskt/`), runs the normal bump → commit → push flow, and updates the install record to the freshly published version. Two safeguards:

- **Files matching `[update].preserve` are never published.** User-runtime data (agent memory, notes) stays local — only the package template is pushed.
- The picker only lists installations that actually differ from the workspace, so there's nothing to scroll past when a package is already in sync.

This is the reverse direction of `pskt update` (which pulls the registry's version _down_ into an installation). See the [data-flow overview](#remote-registry-vs-local-workspace): `update` is registry → installation, `push <scope>` is installation → workspace → registry.

## Manifest

```toml
[package]
name = "my-agent"
version = "1.0.0"
description = "..."
author = "you"

# Optional. Without this section, the default is to overwrite everything on update.
[update]
preserve = [
  "agent-memory/my-agent/MEMORY.md",   # exact file
  "agent-memory/my-agent/notes/",      # whole folder (recursive, trailing /)
]
```

### About `[update].preserve`

On `pskt update`, files whose paths match a `preserve` pattern are **not overwritten** if they already exist in the destination. This protects user-accumulated data (agent memory, notes, etc.) across versions.

| Scenario | Without `preserve` | With `preserve` |
|---|---|---|
| First install | File is created | File is created (initial template) |
| Update, file exists in destination | Overwritten | **Left untouched** |
| Update, new version added a file | Created | Created |
| Update, new version removed a file | Removed from destination | **Left untouched** |

## Authentication

- **HTTPS**: token (GitHub PAT) stored in the OS keyring when available, or in `~/.config/pskt/token` with `chmod 600` as a fallback (WSL2, headless servers, containers).
- **SSH**: delegated to `ssh-agent` / your SSH key — no token managed by the CLI.

The choice is automatic based on the URL form provided to `pskt init`.

## Shell completions

perskent ships tab completion for bash, zsh, fish, and PowerShell (via Typer).

Install it for your current shell:

```bash
pskt --install-completion
```

The output prints which rc file was modified. Reload your shell (or `source` the rc file) and tab completion kicks in:

```bash
pskt <TAB>             # lists commands (init, doctor, status, install, ...)
pskt --<TAB>           # lists global flags
pskt install --<TAB>   # lists flags for the install subcommand
```

To preview the completion script without installing it:

```bash
pskt --show-completion
```

Both commands also accept an explicit shell: `pskt --install-completion bash`, `pskt --show-completion zsh`, etc.

Note: completion of dynamic values (package names from the registry) is not wired up — completion covers commands and flags only.

## Requirements

- Python 3.11+ on `PATH`
- `git` installed
- A remote Git repository (private or public) you control, to serve as your registry

## Releases

Versions are published as [GitHub Releases](https://github.com/Alecell/Perskent/releases). Each release lists the changes and the install command.

## License

MIT
