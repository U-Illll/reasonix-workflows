# reasonix-workflows

The workflow playbooks behind my day-to-day agent work, published as
reusable process documentation: how to plan a task, how to run a
discuss-then-execute loop with independent critics, and how to run a
plan → decompose → critic → decide → revise → verify build loop.

Everything here is **process**, not payload. The documents describe roles,
state machines, gates and checklists, plus small tools that track loop state.
Engagement-specific targets, credentials, hosts and evidence are not part of
this repository.

## Contents

```
modes/
  standard-mode-one/          五步法 + dispatch axes + tool cheat-sheet
  standard-mode-two/          discuss/execute loop (reverse-engineering shaped)
    roles.md                  commander / advisors / execution bodies
    round.md                  round state machine, five gates, explore-tree protocol
    domains.md                execution domains and tool surfaces
  standard-mode-three/        large forward-engineering build loop
    roles.md                  commander / decomposer / critic pool / verifier
    round.md                  P0-P6 machine, terminations, persistence
    domains.md                phase-by-phase toolchain per domain
templates/                    task brief, advisor prompt, adjudication,
                              review, receipt schema, explore card
scripts/
  round_engine.py             LangGraph round-state tracker (SQLite checkpointer)
  drift_scan.py               receipt drift/cleanse rule scanner (observe-only)
  explore_ledger.py           append-only exploration-tree ledger with hash chain
  exit_pool.py                generic resource-pool bookkeeping for explore nodes
  requirements.txt
```

## The three modes at a glance

| Mode | Shape | When |
|---|---|---|
| One | five-step linear task loop with a dispatch axis and a verification gate | ordinary multi-step engineering tasks |
| Two | commander ↔ silent execution ↔ two independent critics ↔ adjudicate, per round | hard, partially-unknown problems (incident analysis, crypto/protocol work, binary forensics) |
| Three | plan → decompose → six-critic pool → decide → revise → verify, with a DAG scheduler | building something large where critique must be orthogonal |

Mode Two's distinguishing feature is **separation of the discuss layer from the
execution layer**: the executing agent returns structured receipts only, and two
stateless critics (safety/environment vs algorithm/data) attack the receipt
before the commander commits to exactly one direction.

## Scripts

`round_engine.py` tracks *where a round is*, not what to do next: it validates
transitions, persists state in SQLite through a LangGraph checkpointer, and
suggests terminations. Adjudication stays with the human/commander.

```bash
python scripts/round_engine.py --db state.db transition --campaign demo --round 5 --to DISPATCH
python scripts/round_engine.py --db state.db status --campaign demo --round 5
```

`explore_ledger.py` maintains the exploration tree as an append-only JSONL with
a hash chain, so a dead-end card can never be silently rewritten:

```bash
python scripts/explore_ledger.py --file tree.jsonl root --name map
python scripts/explore_ledger.py --file tree.jsonl append --node e-01 --parent root --status dead_end --exit-ref ref:42
python scripts/explore_ledger.py --file tree.jsonl tree
python scripts/explore_ledger.py --file tree.jsonl verify
```

`drift_scan.py` scores receipts for drift (prose instead of tool calls) and
cleanse (leaked sensitive patterns). It observes only; it does not block.

## Deploying as agent skills

Each `modes/*/SKILL.md` keeps the front-matter shape used by the Reasonix skill
loader (`name`, `description`). Copy a mode directory into your skills path and
it becomes invocable; the sub-modules are routed from the framework skill.

## License

MIT.
