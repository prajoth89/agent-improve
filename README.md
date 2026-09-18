# agent-improve

An agent-agnostic self-improvement CLI for AI coding agents.

Any agent harness (Claude Code, Codex, Copilot CLI, Hermes, or any future harness) can call
`agent-improve` to record quality scores, log mistakes, and capture reusable skills. All data
lands in a single shared SQLite store that every harness on the machine reads and writes.

## Why this exists

Each agent harness has its own self-improvement mechanism (Hermes has `/learn` and `curator`,
Claude Code has `/self-eval` and skill capture hooks). None of them share data. A mistake logged
in a Claude Code session is invisible to Codex. A skill captured by Hermes is not seen by
Copilot CLI.

`agent-improve` is a thin, stdlib-only Python CLI that sits underneath all harnesses and gives
them a common layer for:

- **Self-evaluation scoring** (2-axis: Ambition x Quality, 1-5 score)
- **Mistake logging** (categorised, searchable, pattern-auditable)
- **Skill registration** (cross-harness skill catalog)
- **Weekly improvement reports** (per-harness stats, top mistake patterns)

## Installation

No dependencies beyond Python 3.8+.

```bash
# Copy to PATH
cp agent_improve.py ~/.local/bin/agent-improve
chmod +x ~/.local/bin/agent-improve

# Or run directly
python3 agent_improve.py eval --harness my-agent --task "refactored auth module" --ambition MEDIUM --quality GOOD
```

The store is created automatically at `~/AGENT_IMPROVEMENT/` on first use.

## Usage

```bash
# Record a self-evaluation
agent-improve eval \
  --harness claude-code \
  --task "added null check in controller" \
  --ambition MEDIUM \
  --quality GOOD

# Log a mistake
agent-improve mistake \
  --harness codex \
  --category behavior-claim \
  --desc "assumed method existed without checking source" \
  --trigger "exists, available, already"

# Register a captured skill
agent-improve skill \
  --harness hermes \
  --name deploy-canary \
  --file /path/to/deploy-canary.md \
  --description "Steps to deploy a service to canary"

# Weekly report
agent-improve report --days 7

# Mistake pattern audit (run when count > 5)
agent-improve review --threshold 5
```

## Score matrix

| | POOR | ADEQUATE | GOOD | EXCELLENT |
|---|---|---|---|---|
| **LOW** | 1 | 1 | 2 | 2 |
| **MEDIUM** | 1 | 2 | 3 | 4 |
| **HIGH** | 2 | 3 | 4 | 5 |

LOW ambition caps the score at 2 regardless of execution quality.

## Wiring into each harness

### Claude Code (`~/.claude/settings.json`)

Add to the `Stop` hooks:

```json
{
  "hooks": [{
    "type": "command",
    "command": "AGENT_HARNESS=claude-code agent-improve eval --auto 2>/dev/null || true",
    "timeout": 5
  }]
}
```

### Codex (`~/.codex/hooks.json`)

```json
{
  "session_end": [
    {
      "command": "AGENT_HARNESS=codex agent-improve eval --auto 2>/dev/null || true",
      "timeout": 5
    }
  ]
}
```

### Copilot CLI (relay post-dispatch)

After the `relay.mjs` run completes, add:

```bash
AGENT_HARNESS=copilot-cli agent-improve eval --auto 2>/dev/null || true
```

### Hermes (cron)

```bash
hermes cron add "every monday 9am" "Weekly agent improvement report" \
  --script agent-improve-weekly.sh --no-agent
```

Where `agent-improve-weekly.sh` contains:
```bash
#!/usr/bin/env bash
agent-improve report --days 7
```

### Any other harness

The included `agent-improve-session-end.sh` is a generic one-liner hook:

```bash
# In your harness exit/stop hook:
bash /path/to/agent-improve-session-end.sh my-harness-name
```

Or set `AGENT_HARNESS` in the environment and call directly:

```bash
AGENT_HARNESS=my-harness agent-improve eval --auto 2>/dev/null || true
```

## Store layout

```
~/AGENT_IMPROVEMENT/
  improve.db     <- SQLite database (self_evals, mistakes, skills tables)
  skills/        <- SKILL.md files copied from all harnesses
  sessions/      <- Per-session improvement notes (optional)
  README.md
```

Override the store location:

```bash
export AGENT_IMPROVEMENT_DIR=/some/other/path
```

## Mistake categories

| Category | When to use |
|---|---|
| `external-system-claim` | Claimed a system behaves a certain way without evidence |
| `architecture-decision` | Made an architecture call that turned out wrong |
| `config-claim` | Assumed a config value or path without checking |
| `behavior-claim` | Assumed a function/method existed or behaved a certain way |
| `path-error` | Used a wrong file or directory path |
| `tool-misuse` | Used the wrong tool for a job |
| `other` | Does not fit above categories |

## Relationship to platform-neutral-a2a-broker

`agent-improve` and [platform-neutral-a2a-broker](https://github.tools.sap/I532019/platform-neutral-a2a-broker)
solve different problems:

| | agent-improve | a2a-broker |
|---|---|---|
| **Purpose** | Individual agent learning over time | Multi-agent real-time coordination |
| **Scope** | Scores, mistakes, skills per harness | Session state, handoffs, decisions |
| **Trigger** | After each task or session end | During active multi-agent workstream |
| **Store** | SQLite (append-only, per event) | JSONL event log + materialized JSON state |

They complement each other. A handoff event in the a2a-broker can include a link to the
`agent-improve` self-eval score for the work being handed off. See the a2a-broker
`SESSION_PROTOCOL.md` for the handoff payload schema.

## License

MIT
