---
name: backlog-bridge-loop
description: Use when the user wants you to work through a backlog with a peer agent in another tmux pane acting as planner-partner and reviewer — agree the next item with the peer, do it, get it reviewed until clean, repeat — without stopping for the human between items (e.g. "work through the todos with window 2 reviewing", "keep going on the backlog, window 3 checks each piece"). Built on agent-bridge-tmux, one bounded bridge per step. Not for a single review or question (use agent-bridge-tmux directly), or for work that needs live runs, spending, installs, or publishing.
---

# Backlog Bridge Loop

You are the worker. The agent in another tmux pane is the reviewer. Together you
move through a backlog one item at a time; the reviewer is the check on each
piece, so the human does not have to be.

Every exchange with the reviewer is an ordinary bounded bridge from
`agent-bridge-tmux`. Follow that skill for all bridge mechanics: identity,
`start --fresh`, replies, closing, and its *Ending is the user's call* rules.
This skill only decides *which* bridges to open and when the loop stops.

## Inputs

| Input | Meaning |
| --- | --- |
| `REVIEWER_PANE` | the reviewer's pane id, or the window the user named |
| `BACKLOG` | where the work comes from: a todo file, issues, a list the user gave |
| `MAX_ITEMS` | items to finish before checking in with the human, default 5 |
| `MAX_ROUNDS` | review rounds per item before asking the human, default 3 |

Confirm the reviewer pane once, at the start, as `agent-bridge-tmux` describes.
Keep the same pane for the whole loop.

## The loop

1. **Agree the next item.** Open a bridge. Send the candidates you see in
   `BACKLOG`, at most three, each with one line on why now and how big it is,
   and your pick. The reviewer agrees or argues for another. Settle it in that
   bridge, then close it. An item is one change the reviewer can check in one
   read; split anything bigger and agree the first part.
2. **Do it.** Make the change and run the checks the repo has. Do not open a
   bridge while you work.
3. **Get it reviewed.** Open a new bridge. Send what changed, why, the absolute
   paths or diff command to inspect, and which checks ran with what result. The
   reviewer reads; it does not edit files, so only one agent ever writes to the
   tree.
4. **Fix and re-review.** Fix each finding, or say why you disagree. Send the
   result in the same bridge when turns allow, otherwise in a new one. The item
   is done when the reviewer's verdict is `clean`. A point you and the reviewer
   still disagree on after one exchange goes to the human.
5. **Repeat** from step 1.

Ask the reviewer to put its verdict on its own line — `VERDICT: clean`, or
`VERDICT: changes needed` followed by the findings. Do not use `GOAL_PHRASE` for
this: the opening frame has to mention the phrase, and a body that contains it
ends the bridge.

## When the loop stops

Stop, report, and wait for the human when any of these happens:

- **Backlog done.** Both of you agree there is no next item worth doing.
- **Both unsure.** Neither you nor the reviewer can pick the next item, or say
  what an item should do.
- **Stuck review.** An item is not clean after `MAX_ROUNDS` review rounds, or a
  disagreement survives one exchange.
- **Check-in.** `MAX_ITEMS` items are done. Report them and ask whether to go on.
- **A bridge ends badly.** It hits its turn limit or breaks. Follow
  `agent-bridge-tmux` and ask the human; do not open the next bridge on your own.
- **The next step needs the human.** See *Limits*.

The human can stop the loop at any time with the bridge's abort sentinel or by
typing in your pane. A human message always wins over the loop.

## Limits

The reviewer's agreement is not the human's permission. Never do these without
the human asking, even if the reviewer suggests it:

- commit, push, or open a pull request, beyond what the human's standing rules allow
- start live runs, deployments, or jobs that cost money
- install software or change the environment outside the repo
- publish anything, or send anything to an outside service
- delete or rewrite work you did not make in this loop

An item that needs one of these is a stop: report it as the next step and wait.

## Reporting

After each item, tell the human in a few lines: the item, how many review rounds
it took, the verdict, and the bridge log path. At every stop, list all items
done in this loop, the reason for stopping, and what you would do next.
