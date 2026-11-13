# scripts/

Small tools that support the loop. None of them decide anything: they record
state, validate transitions, and report. Adjudication stays with the human or
the commanding agent.

## round_engine.py — round state tracker (LangGraph + SQLite)

Validates transitions of the per-campaign round state machine, persists state
through a LangGraph `SqliteSaver` checkpointer, and separates campaigns by
`thread_id`.

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

./venv/bin/python round_engine.py --db state.db transition \
    --campaign demo --round 5 --to DISPATCH --note "brief dispatched"
./venv/bin/python round_engine.py --db state.db transition --campaign demo --round 5 --to EXECUTING
./venv/bin/python round_engine.py --db state.db status --campaign demo --round 5
./venv/bin/python round_engine.py --db state.db list --campaign demo
./venv/bin/python round_engine.py --db state.db check-termination --campaign demo --round 5 --receipts receipts.json
```

Transitions are rejected unless legal for the current state (e.g. `IDLE` only
accepts `DISPATCH`); a rejected transition leaves the stored state untouched.

## explore_ledger.py — append-only exploration tree

Each node is one JSONL line carrying `node_id, parent, status, card, exit_ref,
prev_hash`. Appending is monotonic: writing a node never rewrites history, and
`verify` walks the hash chain to prove the tree has not been edited underneath.

```bash
python3 explore_ledger.py --file tree.jsonl root --name "map name"
python3 explore_ledger.py --file tree.jsonl append --node e-01 --parent root --status done --card cards/e-01.md
python3 explore_ledger.py --file tree.jsonl append --node e-02 --parent e-01 --status dead_end --exit-ref ref:42
python3 explore_ledger.py --file tree.jsonl tree
python3 explore_ledger.py --file tree.jsonl verify
```

Statuses: `running | done | dead_end | uncertain`.

## exit_pool.py — resource-pool bookkeeping

Tracks generic reusable resources (a proxy slot, a device, a rate budget) by
reference ID only; the tool never stores the resource itself. Allocation is
idempotent per node, so re-running a dispatch cannot double-grant.

```bash
python3 exit_pool.py --file pool.json add --tier L1 --ip-source ref:exit-a --note demo
python3 exit_pool.py --file pool.json alloc --node e-01
python3 exit_pool.py --file pool.json status
python3 exit_pool.py --file pool.json release --node e-01
```

Tiers are `L1..L4`; `--ip-source` takes an opaque reference, never a literal
address, so the pool file is safe to commit.

## drift_scan.py — receipt drift/cleanse scanner (observe-only)

Counts two signals in a receipt payload: *drift* (prose where a tool call was
expected) and *cleanse* (patterns that should never appear in a receipt). It
reports and exits; blocking policy is a separate decision.

```bash
python3 drift_scan.py receipts.json
```
