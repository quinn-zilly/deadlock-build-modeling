# Why the generated builds were wrong

The first version of this project scored items by how much buying them
raised the chance of winning, and built plans from those scores. A Deadlock
player looked at its builds and judged them clearly wrong. Every automated
check had passed: the AUC gate at +0.0169, and the recommender beat its
popularity baseline by 14.7 standard errors.

This file records what went wrong. After it, the project stopped trying to
measure what wins and switched to imitating what strong players buy.

## What the builds got wrong

For Wraith, high-rank players who won bought:

| Item | % of winning high-rank Wraiths |
|---|---|
| Quicksilver Reload | 99.8% |
| Monster Rounds | 93.0% |
| Rapid Rounds | 80.9% |
| Extra Spirit | 79.6% |
| Surge of Power | 72.6% |

The planner recommended none of them. It chose Golden Goose Egg, Split Shot,
Infuser, and Escalating Exposure. Every item in its overall top 10 was bought
by between 1% and 10% of players.

## Cause: buying a rare item early means you were already ahead

Item cost wasn't the problem. Comparing items only against others of the same
tier had already removed it (correlation with cost 0.00, with net worth at the
time of purchase only 0.11).

The problem was that the model looked at items bought in the first 20
minutes, and a player who buys an unusual item early is usually already
winning:

| Item | Cost | Bought in first 20 min by | Median buy time |
|---|---|---|---|
| Split Shot | 1600 | 1.3% | 694s |
| Quicksilver Reload | 1600 | 23.1% | 411s |
| Infuser | 6400 | 1.0% | 1083s |
| Monster Rounds | 800 | 21.2% | 174s |

Split Shot and Quicksilver Reload cost the same, so the model treated them as
comparable. But almost everyone buys Quicksilver Reload early, so "bought it
early" tells you nothing about the player. Few buy Split Shot early, and those
who do are the ones with a lead in souls. The model credited the item with
the lead.

## A second, separate flaw

The model compared the two sides of each lane and skipped any item both sides
held. An item nearly everyone buys was therefore measured only in the rare
lanes where one side skipped it. And one table covered all 38 heroes, which
washed out each hero's own staples.

Measured per hero, the effect was there all along:

    Quicksilver Reload, Wraith:  buyers 51.2% win, non-buyers 41.4%  (+9.8 points)

## What didn't fix it

Adjusting scores within groups of similar cost and pick rate. That removed the
correlation with pick rate (-0.007) but ranked the staples even lower:
Quicksilver Reload fell from 45th to 76th. Adjusting away a correlation
doesn't fix a selection effect.

## What looked promising at the time

Comparing buyers with non-buyers per hero, within net-worth quintiles. Without
the quintiles it just measures wealth (correlation with cost 0.62), since
buying anything takes souls. With them the correlation halved to 0.36 and the
top Wraith items looked sensible: Ricochet (27% pick rate), Dispel Magic
(37%), Rapid Rounds (78%), Mercurial Magnum (16%).

This was never finished. The project dropped the win-rate approach instead,
partly because late-game net worth turned out to be mostly a result of
winning rather than something to control for.

## The lesson

Every aggregate check passed while the output was wrong: the AUC gate, the
replication check, the popularity baseline, the shuffled-label test, and the
antisymmetry test. It took a player reading a build to find the problem.

So check a model's output against what strong players actually buy, item by
item, before trusting any aggregate score. That is why the staple gate exists.
