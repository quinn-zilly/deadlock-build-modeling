# Why the generated builds were wrong

The build planner produced builds a Deadlock player judged clearly wrong. This
records the diagnosis, because the aggregate metrics never caught it: the gate
passed at +0.0169 AUC and the recommender beat its popularity floor by 14.7 SE
while the builds were unusable.

## The evidence

For Wraith, high-rank winning players buy:

| Item | % of winning high-rank Wraiths |
|---|---|
| Quicksilver Reload | 99.8% |
| Monster Rounds | 93.0% |
| Rapid Rounds | 80.9% |
| Extra Spirit | 79.6% |
| Surge of Power | 72.6% |

The planner recommended **none** of them. It chose Golden Goose Egg, Split
Shot, Infuser and Escalating Exposure instead. Every item in its global top 10
had a pick rate between 1% and 10%.

## Root cause: selection on early purchase

Not the cost confound, which within-tier centring had already handled
(corr(advantage, cost) = 0.00; corr with net-worth-at-buy only 0.11).

The problem is that **buying a rarely-bought item early means the player was
already ahead**:

| Item | Cost | Bought in first 20 min by | Median buy time |
|---|---|---|---|
| Split Shot | 1600 | **1.3%** | 694s |
| Quicksilver Reload | 1600 | **23.1%** | 411s |
| Infuser | 6400 | 1.0% | 1083s |
| Monster Rounds | 800 | 21.2% | 174s |

Split Shot and Quicksilver Reload cost exactly the same, so tier centring
treats them as comparable — but their early-buy populations are completely
different. Conditioning on "bought this within 20 minutes" is a collider: for a
staple everyone buys it selects nobody, and for a rare item it selects players
with an economic lead.

## A second, independent flaw

The paired design excludes any item held by *both* lane sides. A near-universal
staple is therefore measured only in the rare lanes where one side skipped it,
and the global table dilutes hero-specific staples across all 38 heroes.

Measured per-hero, the effect these methods missed is large:

    Quicksilver Reload, Wraith:  buyers 51.2% win, non-buyers 41.4%  (+9.8 pts)

The signal was always there. The method could not see it.

## What did not fix it

Centring within (cost, pick-rate) cells. It removed the correlation
(corr(adj, pick_rate) = -0.007) but made the staples *worse*: Quicksilver
Reload fell from rank 45 to 76. Residualising away a correlation does not
address a selection mechanism.

## What looks promising

Per-hero buyer-vs-non-buyer lift, stratified by net-worth quintile.
Unstratified it reproduces the wealth confound (corr with cost 0.62), since
buying anything requires souls. Stratifying halves that to 0.36 and surfaces
plausible Wraith items: Ricochet (27% pick), Dispel Magic (37%), Rapid Rounds
(78%), Mercurial Magnum (16%).

This is a direction, not a finished method. The remaining 0.36 correlation with
cost still needs work.

## The lesson worth keeping

Every aggregate check passed while the output was wrong. The AUC gate, the
replication guard, the popularity floor, the shuffled-label and antisymmetry
tests — all green. It took a player looking at a build to find the flaw.

Validate item models against what strong players actually buy, before trusting
any aggregate metric.
