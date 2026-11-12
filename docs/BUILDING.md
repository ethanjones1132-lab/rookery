# How Rookery was built

Rookery was built in a short, hard-deadline sprint (Nov 7–10, 2026) by a small
crew of AI coding agents directed by Ethan Jones, a producer and VST author. The
project is as much a study in **review-gated agent work** as it is a DAW.

## The shape of the work

- **One source of truth.** The agent and the Desktop page edit the same
  `project.json`. Every write validates, snapshots history and broadcasts a diff;
  no side path is allowed to invent state.
- **Small, owned slices.** Work was split into self-contained briefs (engine,
  renderer, Flock, page, sampling, export). Each worker got its own git worktree
  and branch, plus the contract in `docs/contract.md` and the catalog rules
  enforced by `tools/audit.py`.
- **Red tests before green.** Acceptance tests were written against the written
  API first. A slice was not merged because it "looked done"; it was merged when
  the suite, the catalog audit and a second reviewer agreed.

## The review gate

Every worker branch was reviewed before merge. The reviewer re-ran the tests,
read the diff against the contract, and checked the things tests miss: validation
messages, determinism claims, disclosure language and the Desktop SDK boundary.
Fixes went back to the worker or were made on the branch, then re-verified. The
catalog rules in `tools/audit.py` were executable, not prose.

## Test discipline

- `pytest tests/engine tests/acceptance` is the gate: schema, exact length,
  determinism across processes, seam, clipping, undo, API and tool round-trips.
- Audio claims come with a check report, never an adjective.
- A cross-platform CI matrix (Ubuntu, macOS, Windows; Python 3.11, plus 3.14 on
  Ubuntu) runs the same command and `tools/audit.py`.
- The two known `xfail` song-content items are explicit, not hidden.

The full crew board and agent transcripts are development history; this file is
the part worth keeping in a public tree.
