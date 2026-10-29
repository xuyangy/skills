# skills

Personal agent skills. Each folder under `skills/` is one self-contained skill:
its `SKILL.md` is what the agent reads, and any `README.md` beside it is for you.

| Skill | What it does |
| --- | --- |
| [agent-bridge-tmux](skills/agent-bridge-tmux/) | Bounded two-way exchange with an agent in another tmux pane: ask it, have it review, or debate, with turn limits and a stop button. |
| [backlog-bridge-loop](skills/backlog-bridge-loop/) | Work through a backlog with a peer agent in another tmux pane: agree the next item, do it, get it reviewed until clean, repeat. Needs agent-bridge-tmux. |

## Install

Install with [skills](https://github.com/vercel-labs/skills). It copies the
skills from the latest commit on `main`, for all your projects:

```bash
npx skills add xuyangy/skills -g
```

Check for updates, and update to the latest `main`:

```bash
npx skills check
npx skills update
```

Installed skills are copies, so nothing changes until you update. `main` is
what gets installed: keep unfinished work on a branch.
