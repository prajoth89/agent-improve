#!/usr/bin/env python3
"""
agent-improve: Agent-agnostic self-improvement CLI.
Works with any agent harness on this machine.

Store: ~/AGENT_IMPROVEMENT/improve.db (SQLite)
Usage: agent-improve <command> [options]
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

STORE_DIR = Path.home() / "AGENT_IMPROVEMENT"
DB_PATH = STORE_DIR / "improve.db"
SKILLS_DIR = STORE_DIR / "skills"
SESSIONS_DIR = STORE_DIR / "sessions"

SCORE_MATRIX = {
    ("LOW", "POOR"): 1, ("LOW", "ADEQUATE"): 1,
    ("LOW", "GOOD"): 2, ("LOW", "EXCELLENT"): 2,
    ("MEDIUM", "POOR"): 1, ("MEDIUM", "ADEQUATE"): 2,
    ("MEDIUM", "GOOD"): 3, ("MEDIUM", "EXCELLENT"): 4,
    ("HIGH", "POOR"): 2, ("HIGH", "ADEQUATE"): 3,
    ("HIGH", "GOOD"): 4, ("HIGH", "EXCELLENT"): 5,
}


def get_db():
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_DIR.mkdir(exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS self_evals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            harness TEXT NOT NULL,
            task TEXT,
            ambition TEXT,
            quality TEXT,
            score INTEGER,
            note TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mistakes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            harness TEXT NOT NULL,
            category TEXT,
            description TEXT,
            trigger_words TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            harness TEXT NOT NULL,
            name TEXT NOT NULL,
            file_path TEXT,
            description TEXT
        )
    """)
    conn.commit()
    return conn


def cmd_eval(args):
    """Record a self-evaluation score."""
    conn = get_db()
    ts = datetime.now(timezone.utc).isoformat()
    harness = args.harness or os.environ.get("AGENT_HARNESS", "unknown")

    if args.auto:
        # Auto mode: just record session end without scoring
        conn.execute(
            "INSERT INTO self_evals (ts, harness, task, note) VALUES (?,?,?,?)",
            (ts, harness, "session-end", "auto-recorded")
        )
        conn.commit()
        print(f"[agent-improve] session end recorded for {harness}")
        return

    ambition = (args.ambition or "MEDIUM").upper()
    quality = (args.quality or "GOOD").upper()
    score = args.score or SCORE_MATRIX.get((ambition, quality), 3)

    conn.execute(
        "INSERT INTO self_evals (ts, harness, task, ambition, quality, score, note) VALUES (?,?,?,?,?,?,?)",
        (ts, harness, args.task or "", ambition, quality, score, args.note or "")
    )
    conn.commit()

    # Check for inflation (4+ consecutive scores >= 4)
    rows = conn.execute(
        "SELECT score FROM self_evals WHERE harness=? AND score IS NOT NULL ORDER BY id DESC LIMIT 5",
        (harness,)
    ).fetchall()
    scores = [r["score"] for r in rows]
    inflation_warning = ""
    if len(scores) >= 4 and all(s >= 4 for s in scores[:4]):
        inflation_warning = "\nNOTE: 4 consecutive high scores -- verify ambition is not being inflated"

    print(f"""
Self-Eval recorded
  Harness:   {harness}
  Task:      {args.task or '(none)'}
  Ambition:  {ambition}
  Quality:   {quality}
  Score:     {score}/5{inflation_warning}
""")


def cmd_mistake(args):
    """Log a mistake for pattern analysis."""
    conn = get_db()
    ts = datetime.now(timezone.utc).isoformat()
    harness = args.harness or os.environ.get("AGENT_HARNESS", "unknown")

    conn.execute(
        "INSERT INTO mistakes (ts, harness, category, description, trigger_words) VALUES (?,?,?,?,?)",
        (ts, harness, args.category or "uncategorized", args.desc or "", args.trigger or "")
    )
    conn.commit()
    print(f"[agent-improve] mistake logged: {args.category} | {args.desc or ''}")


def cmd_skill(args):
    """Register a captured skill."""
    conn = get_db()
    ts = datetime.now(timezone.utc).isoformat()
    harness = args.harness or os.environ.get("AGENT_HARNESS", "unknown")

    file_path = args.file or ""
    if file_path and not os.path.isabs(file_path):
        file_path = str(Path.cwd() / file_path)

    conn.execute(
        "INSERT INTO skills (ts, harness, name, file_path, description) VALUES (?,?,?,?,?)",
        (ts, harness, args.name, file_path, args.description or "")
    )
    conn.commit()

    # If a file path given, copy to shared skills dir
    if file_path and Path(file_path).exists():
        dest = SKILLS_DIR / f"{args.name}.md"
        dest.write_text(Path(file_path).read_text())
        print(f"[agent-improve] skill '{args.name}' registered and copied to {dest}")
    else:
        print(f"[agent-improve] skill '{args.name}' registered (no file copy)")


def cmd_report(args):
    """Print improvement report."""
    conn = get_db()
    days = args.days or 7
    since = f"datetime('now', '-{days} days')"

    print(f"\nAgent Self-Improvement Report (last {days} days)\n{'='*50}")

    # Self-evals by harness
    rows = conn.execute(f"""
        SELECT harness, COUNT(*) as n, AVG(score) as avg, MIN(score) as lo, MAX(score) as hi
        FROM self_evals WHERE score IS NOT NULL AND ts > {since}
        GROUP BY harness ORDER BY n DESC
    """).fetchall()
    print("\nSelf-Evals by harness:")
    if rows:
        for r in rows:
            print(f"  {r['harness']:20s}  n={r['n']:3d}  avg={r['avg']:.1f}  range={r['lo']}-{r['hi']}")
    else:
        print("  (none)")

    # Mistakes by category
    rows = conn.execute(f"""
        SELECT category, COUNT(*) as n, GROUP_CONCAT(DISTINCT harness) as harnesses
        FROM mistakes WHERE ts > {since}
        GROUP BY category ORDER BY n DESC
    """).fetchall()
    print("\nMistakes by category:")
    if rows:
        for r in rows:
            print(f"  {r['category']:30s}  n={r['n']:3d}  harnesses={r['harnesses']}")
    else:
        print("  (none)")

    # Skills captured
    rows = conn.execute(f"""
        SELECT harness, name, ts FROM skills WHERE ts > {since}
        ORDER BY ts DESC LIMIT 10
    """).fetchall()
    print("\nRecently captured skills:")
    if rows:
        for r in rows:
            print(f"  [{r['harness']}] {r['name']}  ({r['ts'][:10]})")
    else:
        print("  (none)")

    print()


def cmd_review(args):
    """Pattern audit: top mistake category, recommended hooks."""
    conn = get_db()
    threshold = args.threshold or 5

    total = conn.execute("SELECT COUNT(*) FROM mistakes").fetchone()[0]
    if total < threshold:
        print(f"[agent-improve] Only {total} mistakes logged (threshold={threshold}). Run again when more data accumulates.")
        return

    rows = conn.execute("""
        SELECT category, COUNT(*) as n, GROUP_CONCAT(description, ' | ') as samples
        FROM mistakes GROUP BY category ORDER BY n DESC LIMIT 5
    """).fetchall()

    print(f"\nMistake Pattern Audit ({total} total incidents)\n{'='*50}")
    for r in rows:
        print(f"\n  Category: {r['category']} ({r['n']} incidents)")
        samples = (r['samples'] or "")[:200]
        print(f"  Samples:  {samples}")

    top = rows[0] if rows else None
    if top:
        print(f"\nTop pattern: {top['category']} ({top['n']} incidents)")
        print("Recommended: add trigger words to UserPromptSubmit hook that match this category's descriptions.")


def main():
    parser = argparse.ArgumentParser(
        description="Agent-agnostic self-improvement CLI. Works with any harness."
    )
    sub = parser.add_subparsers(dest="command")

    # eval
    p = sub.add_parser("eval", help="Record self-evaluation score")
    p.add_argument("--harness", help="Harness name (claude-code, codex, copilot, hermes)")
    p.add_argument("--task", help="One-line task description")
    p.add_argument("--score", type=int, choices=range(1, 6), help="Override score 1-5")
    p.add_argument("--ambition", choices=["LOW","MEDIUM","HIGH"])
    p.add_argument("--quality", choices=["POOR","ADEQUATE","GOOD","EXCELLENT"])
    p.add_argument("--note", help="Justification note")
    p.add_argument("--auto", action="store_true", help="Auto-record session end only")

    # mistake
    p = sub.add_parser("mistake", help="Log a mistake for pattern analysis")
    p.add_argument("--harness")
    p.add_argument("--category", choices=[
        "external-system-claim","architecture-decision",
        "config-claim","behavior-claim","path-error","tool-misuse","other"
    ])
    p.add_argument("--desc", help="Description of the mistake")
    p.add_argument("--trigger", help="Trigger words that would have caught it")

    # skill
    p = sub.add_parser("skill", help="Register a captured skill")
    p.add_argument("--harness")
    p.add_argument("--name", required=True, help="Skill name (kebab-case)")
    p.add_argument("--file", help="Path to SKILL.md or .md file")
    p.add_argument("--description", help="One-line description")

    # report
    p = sub.add_parser("report", help="Print improvement report")
    p.add_argument("--days", type=int, default=7)

    # review
    p = sub.add_parser("review", help="Mistake pattern audit")
    p.add_argument("--threshold", type=int, default=5)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "eval": cmd_eval,
        "mistake": cmd_mistake,
        "skill": cmd_skill,
        "report": cmd_report,
        "review": cmd_review,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
