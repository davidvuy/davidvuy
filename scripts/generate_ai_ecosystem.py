#!/usr/bin/env python3
"""Generate a GitHub-profile-safe animated SVG from recent GitHub signals."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import random
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets"
STATE_PATH = ASSETS_DIR / "ecosystem-state.json"
SVG_PATH = ASSETS_DIR / "ai-ecosystem.svg"
GITHUB_API = "https://api.github.com"


@dataclass(frozen=True)
class RepoSignal:
    name: str
    language: str
    stars: int
    forks: int
    open_issues: int
    pushed_at: str
    archived: bool


def request_json(url: str, token: str | None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "self-aware-github-ecosystem",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_github_signals(owner: str, token: str | None) -> dict[str, Any]:
    repos_raw = request_json(
        f"{GITHUB_API}/users/{owner}/repos?per_page=100&sort=pushed&direction=desc",
        token,
    )
    events_raw = request_json(f"{GITHUB_API}/users/{owner}/events/public?per_page=100", token)

    repos = [
        RepoSignal(
            name=repo["name"],
            language=repo.get("language") or "Unknown",
            stars=int(repo.get("stargazers_count") or 0),
            forks=int(repo.get("forks_count") or 0),
            open_issues=int(repo.get("open_issues_count") or 0),
            pushed_at=repo.get("pushed_at") or "",
            archived=bool(repo.get("archived")),
        )
        for repo in repos_raw
        if not repo.get("fork")
    ][:24]

    recent_events = [
        {
            "type": event.get("type", "UnknownEvent"),
            "repo": (event.get("repo") or {}).get("name", "").split("/")[-1],
            "created_at": event.get("created_at"),
        }
        for event in events_raw[:60]
    ]

    workflow_failures = 0
    workflow_successes = 0
    for repo in repos[:6]:
        try:
            runs = request_json(
                f"{GITHUB_API}/repos/{owner}/{repo.name}/actions/runs?per_page=10",
                token,
            )
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            continue
        for run in runs.get("workflow_runs", []):
            conclusion = run.get("conclusion")
            if conclusion == "success":
                workflow_successes += 1
            elif conclusion in {"failure", "timed_out", "cancelled", "action_required"}:
                workflow_failures += 1

    return {
        "owner": owner,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repos": [repo.__dict__ for repo in repos],
        "events": recent_events,
        "workflow": {
            "successes": workflow_successes,
            "failures": workflow_failures,
        },
    }


def offline_signals(owner: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "owner": owner,
        "generated_at": now,
        "repos": [
            {
                "name": "ai-profile-ecosystem",
                "language": "Python",
                "stars": 12,
                "forks": 1,
                "open_issues": 1,
                "pushed_at": now,
                "archived": False,
            },
            {
                "name": "github-identity-lab",
                "language": "TypeScript",
                "stars": 8,
                "forks": 0,
                "open_issues": 0,
                "pushed_at": now,
                "archived": False,
            },
            {
                "name": "visual-systems",
                "language": "CSS",
                "stars": 5,
                "forks": 0,
                "open_issues": 0,
                "pushed_at": now,
                "archived": False,
            },
        ],
        "events": [
            {"type": "PushEvent", "repo": "ai-profile-ecosystem", "created_at": now},
            {"type": "IssuesEvent", "repo": "github-identity-lab", "created_at": now},
        ],
        "workflow": {"successes": 4, "failures": 0},
    }


def classify_state(signals: dict[str, Any]) -> dict[str, Any]:
    repos = signals["repos"]
    events = signals["events"]
    workflow = signals["workflow"]

    push_events = sum(1 for event in events if event["type"] == "PushEvent")
    issue_events = sum(1 for event in events if "Issue" in event["type"])
    total_issues = sum(repo["open_issues"] for repo in repos)
    stars = sum(repo["stars"] for repo in repos)
    failures = workflow["failures"]

    activity = min(100, push_events * 8 + len(events) * 2 + stars // 2)
    pressure = min(100, total_issues * 7 + failures * 18 + issue_events * 5)
    health = max(0, min(100, 72 + workflow["successes"] * 3 + push_events * 2 - pressure // 2))

    if failures > 0 or pressure >= 65:
        mood = "stormy"
        weather = "digital rain"
        palette = ["#111827", "#7f1d1d", "#f97316", "#fef3c7"]
    elif activity >= 70:
        mood = "productive"
        weather = "electric sunrise"
        palette = ["#07111f", "#0f766e", "#22c55e", "#bae6fd"]
    elif health >= 82:
        mood = "calm"
        weather = "clear orbit"
        palette = ["#0f172a", "#2563eb", "#14b8a6", "#e0f2fe"]
    else:
        mood = "focused"
        weather = "soft static"
        palette = ["#18181b", "#4f46e5", "#06b6d4", "#f8fafc"]

    dominant_languages: dict[str, int] = {}
    for repo in repos:
        language = repo["language"] or "Unknown"
        dominant_languages[language] = dominant_languages.get(language, 0) + 1

    top_languages = sorted(dominant_languages, key=dominant_languages.get, reverse=True)[:5]
    narrative = (
        f"{signals['owner']} is in a {mood} cycle: {len(repos)} public project signals, "
        f"{push_events} recent pushes, {total_issues} open issue markers, "
        f"and {workflow['successes']} healthy workflow pulses."
    )

    return {
        "mood": mood,
        "weather": weather,
        "palette": palette,
        "activity": activity,
        "pressure": pressure,
        "health": health,
        "top_languages": top_languages,
        "narrative": narrative,
    }


def try_openai_narrative(signals: dict[str, Any], state: dict[str, Any]) -> str | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "input": [
            {
                "role": "system",
                "content": (
                    "Write one compact GitHub profile ecosystem diagnosis. "
                    "No hype, no markdown, max 24 words."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"signals": signals, "state": state}, ensure_ascii=True)[:12000],
            },
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None

    texts: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                texts.append(content.get("text", ""))
    narrative = " ".join(texts).strip()
    return narrative[:180] or None


def repo_orbs(repos: list[dict[str, Any]], palette: list[str]) -> str:
    if not repos:
        return ""
    parts: list[str] = []
    radius = 168
    center_x = 730
    center_y = 300
    for index, repo in enumerate(repos[:12]):
        angle = (math.tau / max(1, min(len(repos), 12))) * index
        orbit = radius - (index % 3) * 38
        x = center_x + math.cos(angle) * orbit
        y = center_y + math.sin(angle) * orbit * 0.58
        size = 6 + min(18, repo["stars"] + repo["forks"] + 2)
        color = palette[1 + index % 2]
        label = html.escape(repo["name"][:22])
        label_x = x + size + 8
        anchor = "start"
        if x > 900:
            label_x = x - size - 8
            anchor = "end"
        parts.append(
            f'<g class="repo repo-{index}" style="animation-delay:{index * -0.7:.1f}s">'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{size}" fill="{color}" opacity="0.82"/>'
            f'<text x="{label_x:.1f}" y="{y + 4:.1f}" text-anchor="{anchor}" class="repo-label">{label}</text>'
            "</g>"
        )
    return "\n".join(parts)


def svg_wrapped_text(text: str, x: int, y: int, width: int, class_name: str) -> str:
    max_chars = max(24, width // 16)
    lines = textwrap.wrap(text, width=max_chars)[:2]
    tspans = "\n".join(
        f'<tspan x="{x}" dy="{0 if index == 0 else 26}">{html.escape(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    return f'<text x="{x}" y="{y}" class="{class_name}">{tspans}</text>'


def render_svg(signals: dict[str, Any], state: dict[str, Any]) -> str:
    owner = html.escape(signals["owner"])
    generated = signals["generated_at"][:16].replace("T", " ")
    palette = state["palette"]
    repos = signals["repos"]
    events = signals["events"]
    top_languages = ", ".join(state["top_languages"]) or "Unknown"
    narrative = html.escape(state["narrative"])

    random.seed(f"{signals['owner']}:{signals['generated_at'][:10]}:{state['mood']}")
    stars = "\n".join(
        f'<circle class="star" cx="{random.randint(20, 1160)}" cy="{random.randint(20, 420)}" r="{random.choice([1, 1.5, 2])}" />'
        for _ in range(70)
    )
    rain = "\n".join(
        f'<line class="rain" x1="{x}" y1="-20" x2="{x - 18}" y2="60" style="animation-delay:{i * -0.13:.2f}s" />'
        for i, x in enumerate(range(40, 1180, 46))
    )
    petals = "\n".join(
        f'<circle class="petal" cx="{80 + i * 46}" cy="{460 + (i % 4) * 14}" r="{4 + (i % 3)}" />'
        for i in range(23)
    )

    glitch_class = "glitchy" if state["mood"] == "stormy" else ""
    creature_mood = {
        "stormy": ("#f97316", "M510 375 q30 -36 60 0", "M632 375 q30 36 60 0"),
        "productive": ("#22c55e", "M510 383 q30 28 60 0", "M632 383 q30 28 60 0"),
        "calm": ("#38bdf8", "M510 380 q30 12 60 0", "M632 380 q30 12 60 0"),
        "focused": ("#a78bfa", "M510 380 h60", "M632 380 h60"),
    }[state["mood"]]

    terminal_lines = [
        f"$ ecosystem scan --owner {owner}",
        f"mood={state['mood']} weather={state['weather']}",
        f"health={state['health']} activity={state['activity']} pressure={state['pressure']}",
        f"languages={top_languages}",
    ]
    terminal = "\n".join(
        f'<text x="64" y="{158 + index * 30}" class="term line-{index}">{html.escape(line)}</text>'
        for index, line in enumerate(terminal_lines)
    )
    narrative_text = svg_wrapped_text(state["narrative"], 50, 552, 1080, "subtitle")

    display_owner = "David Vuy" if signals["owner"].lower() == "davidvuy" else owner

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-labelledby="title desc">
  <title id="title">Profile OS for {display_owner}</title>
  <desc id="desc">{narrative}</desc>
  <style>
    :root {{
      color-scheme: dark;
    }}
    .bg {{ fill: url(#sky); }}
    .star {{ fill: {palette[3]}; opacity: .55; animation: twinkle 4s ease-in-out infinite; }}
    .horizon {{ fill: url(#ground); }}
    .grid {{ stroke: {palette[2]}; stroke-width: 1; opacity: .18; }}
    .title {{ font: 700 42px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #f8fafc; letter-spacing: 0; }}
    .subtitle {{ font: 500 18px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #cbd5e1; }}
    .metric {{ font: 700 24px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #f8fafc; }}
    .metric-label {{ font: 600 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #a5b4fc; text-transform: uppercase; }}
    .term {{ font: 600 18px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #d1fae5; opacity: .92; animation: pulseText 12s ease-in-out infinite; }}
    .line-1 {{ animation-delay: .8s; }}
    .line-2 {{ animation-delay: 1.6s; }}
    .line-3 {{ animation-delay: 2.4s; }}
    .terminal {{ fill: rgba(2, 6, 23, .68); stroke: {palette[2]}; stroke-width: 1.5; }}
    .creature {{ transform-origin: 600px 378px; animation: breathe 3.4s ease-in-out infinite; }}
    .eye {{ fill: #020617; animation: blink 5s infinite; transform-origin: center; }}
    .repo {{ animation: floatRepo 5s ease-in-out infinite; }}
    .repo-label {{ font: 600 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #e2e8f0; opacity: .8; }}
    .rain {{ stroke: #93c5fd; stroke-width: 2; opacity: .0; animation: rainFall 1.2s linear infinite; }}
    .petal {{ fill: {palette[2]}; opacity: .42; animation: bloom 4.8s ease-in-out infinite; }}
    .glitchy {{ animation: glitch 1.7s steps(2) infinite; }}
    @keyframes twinkle {{ 0%, 100% {{ opacity: .25; }} 50% {{ opacity: .9; }} }}
    @keyframes breathe {{ 0%, 100% {{ transform: scale(1); }} 50% {{ transform: scale(1.025); }} }}
    @keyframes blink {{ 0%, 94%, 100% {{ transform: scaleY(1); }} 96% {{ transform: scaleY(.08); }} }}
    @keyframes floatRepo {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-10px); }} }}
    @keyframes rainFall {{ 0% {{ transform: translateY(-100px); opacity: .0; }} 12% {{ opacity: .55; }} 100% {{ transform: translateY(700px); opacity: 0; }} }}
    @keyframes bloom {{ 0%, 100% {{ transform: translateY(0) scale(.9); }} 50% {{ transform: translateY(-18px) scale(1.25); }} }}
    @keyframes pulseText {{ 0%, 100% {{ opacity: .72; }} 50% {{ opacity: 1; }} }}
    @keyframes glitch {{ 0%, 100% {{ transform: translate(0, 0); filter: none; }} 20% {{ transform: translate(3px, -1px); filter: hue-rotate(25deg); }} 40% {{ transform: translate(-2px, 2px); }} }}
    @media (prefers-reduced-motion: reduce) {{
      * {{ animation: none !important; }}
    }}
  </style>
  <defs>
    <linearGradient id="sky" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0" stop-color="{palette[0]}"/>
      <stop offset=".55" stop-color="{palette[1]}"/>
      <stop offset="1" stop-color="#020617"/>
    </linearGradient>
    <linearGradient id="ground" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="{palette[2]}" stop-opacity=".42"/>
      <stop offset="1" stop-color="#020617"/>
    </linearGradient>
    <filter id="glow">
      <feGaussianBlur stdDeviation="4" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>
  <rect class="bg" width="1200" height="630"/>
  <g class="{glitch_class}">
    {stars}
    {'<g>' + rain + '</g>' if state["mood"] == "stormy" else petals}
    <path class="horizon" d="M0 472 C180 430 270 510 420 468 C575 424 690 488 828 452 C975 412 1065 455 1200 426 L1200 630 L0 630 Z"/>
    <g opacity=".8">
      {"".join(f'<line class="grid" x1="{x}" y1="500" x2="600" y2="630"/>' for x in range(0, 1220, 80))}
      {"".join(f'<line class="grid" x1="0" y1="{y}" x2="1200" y2="{y}"/>' for y in range(500, 631, 26))}
    </g>
    <text x="48" y="62" class="title">{display_owner} // Profile OS</text>
    <text x="50" y="92" class="subtitle">A living GitHub front page generated {generated} UTC</text>

    <rect x="42" y="122" width="418" height="172" rx="8" class="terminal"/>
    {terminal}

    <g transform="translate(48 330)">
      <text class="metric-label" x="0" y="0">Health</text>
      <text class="metric" x="0" y="34">{state["health"]}</text>
      <text class="metric-label" x="130" y="0">Activity</text>
      <text class="metric" x="130" y="34">{state["activity"]}</text>
      <text class="metric-label" x="286" y="0">Pressure</text>
      <text class="metric" x="286" y="34">{state["pressure"]}</text>
    </g>

    <g class="creature" filter="url(#glow)">
      <ellipse cx="600" cy="388" rx="118" ry="78" fill="{creature_mood[0]}" opacity=".92"/>
      <ellipse cx="558" cy="360" rx="20" ry="24" class="eye"/>
      <ellipse cx="646" cy="360" rx="20" ry="24" class="eye"/>
      <path d="{creature_mood[1]}" stroke="#020617" stroke-width="7" stroke-linecap="round" fill="none"/>
      <path d="{creature_mood[2]}" stroke="#020617" stroke-width="7" stroke-linecap="round" fill="none"/>
      <path d="M515 310 q-48 -56 -88 -8" stroke="{palette[3]}" stroke-width="8" stroke-linecap="round" fill="none"/>
      <path d="M685 310 q48 -56 88 -8" stroke="{palette[3]}" stroke-width="8" stroke-linecap="round" fill="none"/>
    </g>

    <g>
      {repo_orbs(repos, palette)}
    </g>

    {narrative_text}
    <text x="50" y="612" class="subtitle">Repos {len(repos)} | Recent events {len(events)} | Weather {html.escape(state["weather"])}</text>
  </g>
</svg>
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Use bundled sample signals")
    parser.add_argument("--owner", default=os.getenv("GITHUB_OWNER") or os.getenv("GITHUB_REPOSITORY_OWNER") or "David")
    args = parser.parse_args()

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    token = os.getenv("GITHUB_TOKEN")
    if args.offline:
        signals = offline_signals(args.owner)
    else:
        try:
            signals = fetch_github_signals(args.owner, token)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, KeyError) as error:
            print(f"Falling back to offline signals: {error}", file=sys.stderr)
            signals = offline_signals(args.owner)

    state = classify_state(signals)
    ai_narrative = try_openai_narrative(signals, state)
    if ai_narrative:
        state["narrative"] = ai_narrative

    STATE_PATH.write_text(
        json.dumps({"signals": signals, "state": state}, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    SVG_PATH.write_text(render_svg(signals, state), encoding="utf-8")

    print(
        textwrap.dedent(
            f"""\
            Generated {SVG_PATH}
            mood={state['mood']} health={state['health']} activity={state['activity']} pressure={state['pressure']}
            """
        ).strip()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
