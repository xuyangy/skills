# skills

Personal agent skills. Each folder under `skills/` is one self-contained skill:
its `SKILL.md` is what the agent reads, and any `README.md` beside it is for you.

| Skill | What it does |
| --- | --- |
| [agent-bridge-tmux](skills/agent-bridge-tmux/) | Bounded two-way exchange with an agent in another tmux pane: ask it, have it review, or debate, with turn limits and a stop button. |
| [backlog-bridge-loop](skills/backlog-bridge-loop/) | Work through a backlog with a peer agent in another tmux pane: agree the next item, do it, get it reviewed until clean, repeat. Needs agent-bridge-tmux. |

## Install

Link the skills you want into your agent's skills folder, for example for
Claude Code:

```bash
ln -s "$PWD/skills/agent-bridge-tmux" ~/.claude/skills/agent-bridge-tmux
ln -s "$PWD/skills/backlog-bridge-loop" ~/.claude/skills/backlog-bridge-loop
```
