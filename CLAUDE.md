# deadlock-build-modeling

A tool that tells a Deadlock player what to buy, in what order, and where to
put ability points, for their hero and archetype, before and during a match.
`README.md` has the commands. `CONTEXT.md` defines the project's terms; use
them.

## Rules

- **Imitate strong players.** The model predicts what good players buy, not
  what wins. Keep win rate out of every objective and score: late-game net
  worth is a result of winning, not a cause. `docs/DIAGNOSIS.md` explains why
  the earlier win-rate model was dropped.
- **Every number traces to a table row with a count.** The model is a backoff
  table of counts so a person can check any recommendation by hand, and the
  `why` command prints the rows behind one. Keep it that way.
- **Check builds item by item.** Every item bought by at least 70% of a
  cell's players must appear in that cell's generated build.
  `scripts/generate_builds.py` checks this and exits non-zero on a miss. The
  earlier model passed five aggregate checks and still made unusable builds.
- **Compare numbers only within one run.** Rerun both sides together before
  comparing. Separation falls as k rises, a hero with no split reports the
  separation of its rejected split, and held-out accuracy depends on the run's
  sample and settings.

## Agent skills

- **Issues** are GitHub issues in `quinn-zilly/deadlock-build-modeling`,
  managed with `gh`. See `docs/agents/issue-tracker.md`.
- **Triage labels** use the five standard names. See
  `docs/agents/triage-labels.md`.
- **Domain docs**: one `CONTEXT.md` and `docs/adr/` at the repo root. See
  `docs/agents/domain.md`.
