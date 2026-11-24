# Diagrams

The images in this repo's READMEs. Each `.d2` file is the source for a `-light.png` and a `-dark.png`; the
READMEs pick one with `<picture>`, so they follow your color scheme.

| Source | Shows |
| --- | --- |
| `architecture.d2` | What runs where: laptop, Omnigent on Databricks, the Sandbox host, and the UC and Unity Gateway pieces |
| `one-turn.d2` | One question, end to end, as a sequence diagram |
| `data-model.d2` | What the bundle builds and who reads it |
| `read-only.d2` | The two read-only layers: the playbook and the CEL guardrail |
| `setup.d2` | The seven setup steps and what each one leaves behind |

They were rendered with [D2](https://d2lang.com/) 0.9.0 (dagre layout) and a Databricks color theme, as 2x
PNGs. They're PNGs rather than SVGs because GitHub strips the `<image>` tags D2 uses for icons. The sources
set no colors; they tag each shape with a role (`source`, `compute`, `store`, `serve`, `govern`, `group`)
and reference icons as `${ICONS}/databricks/<name>.svg`. To render them with plain `d2`, drop the `class:`
and `icon:` lines, or define those classes yourself.
