# deadlock-build-modeling

## What this is

A tool that tells a Deadlock player **what to buy, in what order, and where to
put their ability points** -- for their hero and their archetype, before a match
and during one. `README.md` has the commands; `CONTEXT.md` is the glossary and
the terms in it are the ones to use.

**Who it is for.** A player who has picked their hero and wants the build a
strong player would run. Not an analyst: the output is a build to follow, in the
order it is bought, with the evidence attached so it can be argued with. The
two shapes are a whole build before the match and a next purchase during one.

**What it deliberately is not.** Not an item win-rate table and not a pick-rate
table — both already exist and are one lookup away, which is why sequence and
timing are the questions worth answering. Not a claim about what an item
*causes*: this project built the causal version, and `docs/DIAGNOSIS.md`
records why it was discarded. And not a ranking of items in the abstract; every
answer is conditioned on a hero and an archetype, because averaged advice
serves neither build.

Four things about the project decide most arguments before they start:

- **It imitates, it does not explain.** The model says what strong players do,
  never that an item causes a win. The causal version was built and discarded;
  `docs/DIAGNOSIS.md` records why, and late-game net worth being an outcome
  rather than a control is the short version. Do not reintroduce a win-rate
  objective.
- **Every number must trace to a table row with a count.** That is what `why`
  is for, and it is why the model is a backoff frequency table rather than a
  network. A recommendation nobody can check by hand is the failure this
  project was rebuilt to avoid.
- **The gate is per-item, not aggregate.** An item bought by at least 70% of an
  archetype's players must appear in the build generated for them
  (`scripts/generate_builds.py`, which exits non-zero when one does not). The
  previous model passed five aggregate gates and still produced unusable
  builds.
- **Two numbers from two different runs are not a comparison.** Cluster
  separation falls when k rises, a hero that did not split reports the
  separation of a rejected candidate, and held-out accuracy depends on the run
  configuration. Rerun both sides in one run, or say nothing.

## Agent skills

### Issue tracker

Issues live as GitHub issues in `quinn-zilly/deadlock-build-modeling`, managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
