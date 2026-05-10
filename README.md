# perskent

CLI para gerenciar skills, agents e commands do [Claude Code](https://claude.com/claude-code) via um repositório Git privado seu — sem registry central, sem dependência de host de terceiros.

Você aponta o `pskt` pro seu próprio repo (pode ser privado no GitHub), e a CLI cuida de instalação, atualização, versionamento e publicação dos seus pacotes para o `.claude/` do scope que escolher (global ou por projeto).

## Instalação

One-liner (Linux / macOS, requer Python 3.11+):

```bash
curl -fsSL https://raw.githubusercontent.com/Alecell/Perskent/main/install.sh | sh
```

O script detecta `python3.11+`, garante `pipx` no sistema, e instala o `perskent` em um ambiente isolado. Comandos `pskt` e `perskent` ficam disponíveis no `PATH`.

Alternativa direta via pipx:

```bash
pipx install git+https://github.com/Alecell/Perskent.git
```

Atualizar depois:

```bash
pipx upgrade perskent
```

## Quick start

```bash
pskt init                         # configura o registry remoto (URL do seu repo + token)
pskt find remote                  # lista pacotes disponíveis no registry
pskt install my-agent root        # instala em ~/.claude/ (global)
pskt install my-skill project     # instala em ./.claude/ (este projeto)
```

## Comandos

| Comando | Descrição |
|---|---|
| `pskt init` | Configura URL do registry remoto e clona em `~/.pskt/` |
| `pskt doctor` | Diagnóstico (Python, git, paths, token, conectividade) |
| `pskt sync` | `git pull` no workspace local |
| `pskt find remote` | Lista pacotes disponíveis no registry |
| `pskt find local` | Lista pacotes instalados (root + project) |
| `pskt show <name>` | Detalhes de um pacote |
| `pskt search <termo>` | Busca por nome/descrição |
| `pskt install <name> [root\|project] [--force]` | Instala um pacote |
| `pskt remove <name> <root\|project>` | Desinstala um pacote |
| `pskt update <name>` | Atualiza um pacote preservando arquivos marcados em `[update].preserve` |
| `pskt push <name> [-m <msg>]` | Faz bump + commit + push de um pacote editado localmente |

Em qualquer comando que receba `<name>`, se houver pacotes com o mesmo nome em kinds diferentes, use o nome qualificado: `agents/my-thing`, `skills/my-thing`, `commands/my-thing`.

## Conceitos

### Registry remoto vs workspace local

- **Registry remoto** — repositório Git privado seu (ex.: `seu-usuario/meu-registry`) que guarda os pacotes versionados.
- **Workspace local** — clone do registry em `~/.pskt/`. É aqui que você **edita** os pacotes; `pskt push` sincroniza com o remoto.
- **Instalação** — cópia de arquivos do workspace local para o `.claude/` consumido pelo Claude Code (não é symlink; o Claude Code lê arquivos físicos).

### Scopes (root vs project)

- **`root`** — instala em `~/.claude/`, disponível em todos os projetos.
- **`project`** — instala em `./.claude/` (relativo ao diretório atual), apenas neste projeto.

`pskt find local` mostra os dois scopes simultaneamente quando você está num projeto.

### Estrutura do registry

```
<seu-registry>/
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

A pasta-mãe (`agents`, `skills`, `commands`) sinaliza o **tipo** do pacote. O conteúdo de cada pacote (exceto `manifest.toml`) é replicado **1:1** dentro do `.claude/` do scope escolhido — sem renomeação, sem convenção de layout imposta. O autor decide a estrutura dentro do pacote.

## Manifest

```toml
[package]
name = "my-agent"
version = "1.0.0"
description = "..."
author = "alecell"

# Opcional. Sem essa seção, default = sobrescreve tudo em update.
[update]
preserve = [
  "agent-memory/my-agent/MEMORY.md",   # arquivo exato
  "agent-memory/my-agent/notes/",      # pasta inteira (recursivo, termina em /)
]
```

### Sobre `[update].preserve`

Em `pskt update`, arquivos cujos paths batem com algum pattern em `preserve` **não são sobrescritos** se já existem no destino. Isso protege dados acumulados pelo user (memória do agent, anotações, etc) entre versões.

| Situação | Sem `preserve` | Com `preserve` |
|---|---|---|
| Primeiro install | Cria o arquivo | Cria o arquivo (template inicial) |
| Update, arquivo existe no destino | Sobrescreve | **Mantém o que está lá** |
| Update, versão nova adicionou arquivo | Cria | Cria |
| Update, versão nova removeu arquivo | Remove do destino | **Mantém o que está lá** |

## Autenticação

- **HTTPS**: token (PAT do GitHub) salvo no keyring do OS quando disponível, ou em arquivo `~/.config/pskt/token` com `chmod 600` como fallback (WSL2, headless servers, containers).
- **SSH**: delegado ao `ssh-agent` / chave SSH do sistema — sem token gerenciado pela CLI.

A escolha é automática pela forma da URL informada no `pskt init`.

## Requirements

- Python 3.11+ no `PATH`
- `git` instalado
- Um repositório Git remoto (privado ou público) que você controle, para servir como seu registry

## Releases

Versões publicadas em [GitHub Releases](https://github.com/Alecell/Perskent/releases). Cada release lista as mudanças e o comando de instalação.

## License

MIT
