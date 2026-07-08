<h1 align="center">David's self-aware GitHub ecosystem</h1>

<p align="center">
  A profile that rewrites its visual mood from live GitHub signals: commits,
  issues, repository health, and workflow results.
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/ai-ecosystem.svg">
    <img alt="AI ecosystem generated from David's GitHub activity" src="assets/ai-ecosystem.svg" width="100%">
  </picture>
</p>

## What this is

This profile is built as a small autonomous system rather than a static README.
Every run gathers recent GitHub activity, classifies the developer ecosystem,
and renders a pure SVG scene that GitHub can display without JavaScript.

- Calm, healthy activity becomes a bright living landscape.
- Heavy fixes, failed workflows, or stale projects make the world darker,
  stormier, and more glitchy.
- The terminal and creature animations are pure SVG/CSS, so they work inside a
  GitHub profile README.

## How it updates

The workflow in `.github/workflows/ai-ecosystem.yml` runs on a schedule,
on demand, and after profile changes. It writes:

- `assets/ai-ecosystem.svg` - the generated visual profile world
- `assets/ecosystem-state.json` - the structured state used by the renderer

Optional AI mode:

Add an `OPENAI_API_KEY` repository secret to let the script ask an LLM for a
short profile diagnosis. Without that secret, the script uses a deterministic
local classifier so the profile stays free and reliable.

## Local preview

```bash
python3 scripts/generate_ai_ecosystem.py --offline
open assets/ai-ecosystem.svg
```
