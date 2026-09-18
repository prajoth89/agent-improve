#!/usr/bin/env bash
# agent-improve-session-end.sh
# Drop this in each harness's Stop/SessionEnd hook.
# Records session end to the shared improvement store.
# No output to stdout (fail-open: errors are silenced).

HARNESS="${AGENT_HARNESS:-${1:-unknown}}"
agent-improve eval --harness "$HARNESS" --auto 2>/dev/null || true
