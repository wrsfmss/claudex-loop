# claudex-cos: Hermes chief-of-staff / PA plugin

Makes a Hermes agent act as a chief of staff and personal assistant on top of this
repository's skills. It triages every task by autonomy tier and sends non-trivial work
through [`claudex-route`](../../../skills/claudex-route/SKILL.md) or
[`claudex-loop`](../../../skills/claudex-loop/SKILL.md) instead of improvising.

## Tools

| Tool | Purpose |
|---|---|
| `claudex_cos_brief` | Returns the operating doctrine (voice, autonomy tiers, routing rules). |
| `claudex_cos_triage` | Classifies a task: tier `act` / `ask` / `never`, route `self` / `claudex-route` / `claudex-loop` / `decline`. No side effects. |
| `claudex_cos_delegate` | Launches a Hermes subagent under the doctrine. `ask` tasks need `approved=true` after the principal says yes; `never` tasks are refused. |

Triage is keyword-based and deliberately conservative. Treat it as a first filter, not a
substitute for judgement.

## Install

```bash
mkdir -p "${HERMES_HOME:-$HOME/.hermes}/plugins"
cp -R integrations/hermes/claudex-cos "${HERMES_HOME:-$HOME/.hermes}/plugins/claudex-cos"
```

Enable `claudex-cos` under `plugins.enabled` in the Hermes config, then restart Hermes.
Install the `claudex-route` and `claudex-loop` skills separately for the routes to work.

## Personalise without editing the repo

The packaged doctrine is generic. To use your own (name, employer, tool routing, label IDs),
write it to `${HERMES_HOME:-~/.hermes}/claudex-cos/doctrine.md`; it replaces the packaged
one. Keep personal details there, not in this public repository.

## Test

```bash
python3 -m unittest tests.test_hermes_cos
```
