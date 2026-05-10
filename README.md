# perskent

CLI for managing [Claude Code](https://claude.com/claude-code) skills, agents and commands via your own private Git repository — no central registry, no third-party host.

You point `pskt` at your own repo (a private GitHub repo works fine), and the CLI handles installation, updates, versioning, and publishing of your packages to the `.claude/` of the chosen scope (global or per-project).

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
pskt init                         # configure the remote registry (your repo URL + token)
pskt find remote                  # list packages available in the registry
pskt install my-agent root        # install in ~/.claude/ (global)
pskt install my-skill project     # install in ./.claude/ (this project only)
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
| `pskt install <name> [root\|project] [--force]` | Install a package |
| `pskt remove <name> <root\|project>` | Uninstall a package |
| `pskt update <name>` | Upgrade a package, preserving files marked in `[update].preserve` |
| `pskt push <name> [-m <msg>]` | Bump + commit + push a locally-edited package |
| `pskt destroy <name> [-y]` | Permanently delete a package from the registry (workspace + remote). Does not affect installed copies. |

For any command that accepts `<name>`: if packages with the same name exist in multiple kinds, use the qualified name — `agents/my-thing`, `skills/my-thing`, `commands/my-thing`.

## Concepts

### Remote registry vs local workspace

- **Remote registry** — your private Git repository (e.g. `your-user/my-registry`) that stores versioned packages.
- **Local workspace** — clone of the registry at `~/.pskt/`. This is where you **edit** packages; `pskt push` syncs them to the remote.
- **Installation** — copies files from the local workspace into the `.claude/` consumed by Claude Code (not a symlink; Claude Code reads physical files).

### Scopes (root vs project)

- **`root`** — installs into `~/.claude/`, available across all projects.
- **`project`** — installs into `./.claude/` (relative to the current directory), this project only.

`pskt find local` shows both scopes simultaneously when run from inside a project.

### Registry layout

```
<your-registry>/
├── agents/
│   └── my-agent/
│       ├── manifest.toml
│       ├── agents/my-agent.md           → .claude/agents/my-agent.md
│       └── agent-memory/my-agent/...    → .claude/agent-memory/my-agent/...
├── skills/
│   └── my-skill/
│       ├── manifest.toml
│       └── skills/my-skill/SKILL.md     → .claude/skills/my-skill/SKILL.md
└── commands/
    └── my-cmd/
        ├── manifest.toml
        └── commands/my-cmd.md           → .claude/commands/my-cmd.md
```

The parent folder (`agents`, `skills`, `commands`) signals the package **kind**. Each package's contents (except `manifest.toml`) are mirrored **1:1** into the chosen scope's `.claude/` — no renaming, no imposed layout convention. The author decides the structure inside the package.

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
