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

Each harness needs one hook that calls `agent-improve` when a session ends. The hook is
fail-open -- if `agent-improve` is not installed or fails, the harness exits normally.

**Before wiring any harness:** install the CLI once:

```bash
cp agent_improve.py ~/.local/bin/agent-improve
chmod +x ~/.local/bin/agent-improve
agent-improve report  # confirm it works
```

---

### Claude Code

Claude Code fires a `Stop` hook every time a session ends. Add one entry to the `Stop` array
in `~/.claude/settings.json`.

**Step 1** -- Open the file:
```bash
open ~/.claude/settings.json
```

**Step 2** -- Find the `"hooks"` key. If it does not exist, add it. Locate or create the `"Stop"` array inside it.

**Step 3** -- Add this object to the `"Stop"` array (add a comma after the previous entry if one exists):
```json
{
  "hooks": [{
    "type": "command",
    "command": "AGENT_HARNESS=claude-code agent-improve eval --auto 2>/dev/null || true",
    "timeout": 5
  }]
}
```

**Step 4** -- Save the file. No restart needed -- Claude Code reads hooks on the next session start.

**Verify:** Start and end a Claude Code session, then run `agent-improve report --days 1`. You should see `claude-code` in the harness list.

---

### Codex

Codex reads hooks from `~/.codex/hooks.json`. The file may not exist yet.

**Step 1** -- Open or create the file:
```bash
# If the file does not exist:
echo '{}' > ~/.codex/hooks.json

open ~/.codex/hooks.json
```

**Step 2** -- Add or merge the `session_end` key:
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

If `session_end` already exists, append the object to the existing array.

**Step 3** -- Save the file. No restart needed.

**Verify:** Run a Codex session, then `agent-improve report --days 1`. You should see `codex`.

---

### Copilot CLI

Copilot CLI is invoked via `relay.mjs` (the delegate relay script). Add one line after the
relay exits.

**Step 1** -- Open your relay wrapper or the script where you call `relay.mjs`:
```bash
# Example wrapper at ~/bin/copilot-task.sh
```

**Step 2** -- Add the hook immediately after the `node relay.mjs` call:
```bash
node ~/.hermes/skills/autonomous-ai-agents/copilot-delegate/scripts/relay.mjs \
  --brief /tmp/brief.txt \
  --cd /path/to/repo \
  --allow-all-tools

# Record session end (fail-open)
AGENT_HARNESS=copilot-cli agent-improve eval --auto 2>/dev/null || true
```

**Step 3** -- Save the file.

**Verify:** Run `copilot-byok` or dispatch a relay task, then `agent-improve report --days 1`.

---

### Hermes

Hermes does not have a per-session Stop hook in the same way, but it has a cron scheduler.
Wire a weekly report delivery instead.

**Step 1** -- Create the report script:
```bash
cat > ~/.hermes/scripts/agent-improve-weekly.sh << 'EOF'
#!/usr/bin/env bash
agent-improve report --days 7
EOF
chmod +x ~/.hermes/scripts/agent-improve-weekly.sh
```

**Step 2** -- Register the cron job:
```bash
hermes cron add "every monday 9am" "Weekly agent self-improvement report" \
  --script agent-improve-weekly.sh \
  --no-agent
```

**Step 3** -- Confirm the job was created:
```bash
hermes cron list
```

You should see the Monday 9am job in the list. It will deliver the report to your configured
Hermes notification channel.

---

### Any other harness

Use the included `agent-improve-session-end.sh` as a generic hook.

**Step 1** -- Copy it to PATH:
```bash
cp agent-improve-session-end.sh ~/.local/bin/
chmod +x ~/.local/bin/agent-improve-session-end.sh
```

**Step 2** -- In your harness's exit or stop hook, add one line:
```bash
bash ~/.local/bin/agent-improve-session-end.sh my-harness-name
```

Replace `my-harness-name` with a short identifier for the harness (e.g. `cursor`, `aider`,
`opencode`). This name appears in reports.

**Step 3** -- Test it:
```bash
bash ~/.local/bin/agent-improve-session-end.sh test-harness
agent-improve report --days 1
# Should show: test-harness  n=1
```

---

### Quick-check all harnesses

After wiring, run one session on each harness and then:

```bash
agent-improve report --days 1
```

Expected output lists every harness you wired with `n >= 1`. Any harness missing from the
list did not fire its hook correctly -- recheck the hook file for that harness.

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
