#!/usr/bin/env python3
"""Generate GitHub-profile-safe SVG assets from public GitHub signals."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import textwrap
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets"
STATE_PATH = ASSETS_DIR / "ecosystem-state.json"
HERO_PATH = ASSETS_DIR / "ai-ecosystem.svg"
PROJECTS_PATH = ASSETS_DIR / "project-matrix.svg"
SKILLS_PATH = ASSETS_DIR / "skill-map.svg"
GITHUB_API = "https://api.github.com"


def request_json(url: str, token: str | None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "davidvuy-profile-os",
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
        {
            "name": repo["name"],
            "language": repo.get("language") or "Unknown",
            "stars": int(repo.get("stargazers_count") or 0),
            "forks": int(repo.get("forks_count") or 0),
            "open_issues": int(repo.get("open_issues_count") or 0),
            "pushed_at": repo.get("pushed_at") or "",
            "archived": bool(repo.get("archived")),
        }
        for repo in repos_raw
        if not repo.get("fork")
    ][:30]

    events = [
        {
            "type": event.get("type", "UnknownEvent"),
            "repo": (event.get("repo") or {}).get("name", "").split("/")[-1],
            "created_at": event.get("created_at"),
        }
        for event in events_raw[:80]
    ]

    workflow_successes = 0
    workflow_failures = 0
    for repo in repos[:6]:
        try:
            runs = request_json(
                f"{GITHUB_API}/repos/{owner}/{repo['name']}/actions/runs?per_page=10",
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
        "repos": repos,
        "events": events,
        "workflow": {"successes": workflow_successes, "failures": workflow_failures},
    }


def offline_signals(owner: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "owner": owner,
        "generated_at": now,
        "repos": [
            {"name": "ai-app-care-os", "language": "TypeScript", "stars": 6, "forks": 1, "open_issues": 0, "pushed_at": now, "archived": False},
            {"name": "profile-os", "language": "Python", "stars": 4, "forks": 0, "open_issues": 0, "pushed_at": now, "archived": False},
            {"name": "launch-engine", "language": "JavaScript", "stars": 3, "forks": 0, "open_issues": 2, "pushed_at": now, "archived": False},
            {"name": "visual-systems", "language": "CSS", "stars": 2, "forks": 0, "open_issues": 0, "pushed_at": now, "archived": False},
        ],
        "events": [{"type": "PushEvent", "repo": "profile-os", "created_at": now} for _ in range(18)],
        "workflow": {"successes": 5, "failures": 0},
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

    activity = min(100, push_events * 5 + len(events) + stars)
    pressure = min(100, total_issues * 6 + failures * 10 + issue_events * 3)
    health = max(0, min(100, 78 + workflow["successes"] * 2 + push_events - pressure // 3))
    mood = "shipping" if activity >= 75 else "building" if health >= 80 else "repairing"
    if failures > 4 or pressure > 55:
        mood = "stabilizing"

    language_counts: dict[str, int] = {}
    for repo in repos:
        language = repo["language"] or "Unknown"
        language_counts[language] = language_counts.get(language, 0) + 1
    top_languages = sorted(language_counts, key=language_counts.get, reverse=True)[:5]

    return {
        "mood": mood,
        "activity": activity,
        "pressure": pressure,
        "health": health,
        "top_languages": top_languages,
        "narrative": (
            f"{signals['owner']} is {mood}: {len(repos)} public repos, "
            f"{push_events} recent push events, {total_issues} open issue signals, "
            f"{workflow['successes']} successful workflow pulses."
        ),
    }


def try_openai_narrative(signals: dict[str, Any], state: dict[str, Any]) -> str | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "input": [
            {"role": "system", "content": "Write one compact GitHub profile diagnosis. No markdown. Max 22 words."},
            {"role": "user", "content": json.dumps({"signals": signals, "state": state}, ensure_ascii=True)[:12000]},
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None
    texts = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                texts.append(content.get("text", ""))
    return " ".join(texts).strip()[:170] or None


def language_color(language: str) -> str:
    return {
        "TypeScript": "#38bdf8",
        "JavaScript": "#facc15",
        "Python": "#22c55e",
        "CSS": "#fb7185",
        "HTML": "#f97316",
        "Dart": "#06b6d4",
        "Swift": "#f472b6",
        "Java": "#f59e0b",
        "Unknown": "#94a3b8",
    }.get(language, "#a78bfa")


def display_name(owner: str) -> str:
    return "David Vuy" if owner.lower() == "davidvuy" else owner


def wrapped_text(text: str, x: int, y: int, width_chars: int, class_name: str, line_height: int = 24) -> str:
    lines = textwrap.wrap(text, width=width_chars)[:2]
    tspans = "".join(
        f'<tspan x="{x}" dy="{0 if index == 0 else line_height}">{html.escape(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    return f'<text x="{x}" y="{y}" class="{class_name}">{tspans}</text>'


def render_bars(values: list[int], x: int, y: int, width: int, height: int, color: str) -> str:
    if not values:
        return ""
    step = width / len(values)
    parts = []
    for index, value in enumerate(values):
        bar_height = max(4, height * min(100, value) / 100)
        parts.append(
            f'<rect class="bar" x="{x + index * step:.1f}" y="{y + height - bar_height:.1f}" '
            f'width="{max(3, step - 4):.1f}" height="{bar_height:.1f}" fill="{color}" opacity="{0.38 + (index % 4) * 0.12:.2f}"/>'
        )
    return "\n".join(parts)


def render_hero(signals: dict[str, Any], state: dict[str, Any]) -> str:
    owner = html.escape(signals["owner"])
    name = html.escape(display_name(signals["owner"]))
    generated = signals["generated_at"][:16].replace("T", " ")
    repos = signals["repos"]
    events = signals["events"]
    top_languages = ", ".join(state["top_languages"]) or "Unknown"
    status_color = "#22c55e" if state["health"] >= 82 else "#f59e0b" if state["health"] >= 62 else "#fb7185"

    event_values = [
        88 if event["type"] == "PushEvent" else 54 if "Issue" in event["type"] else 34
        for event in events[:42]
    ]
    event_values.extend([14] * (42 - len(event_values)))

    terminal_lines = [
        f"$ scan github://{owner}",
        f"mode={state['mood']} health={state['health']} activity={state['activity']}",
        f"languages={top_languages}",
        "loop=idea -> prototype -> verify -> ship",
    ]
    terminal = "\n".join(
        f'<text x="76" y="{302 + i * 27}" class="mono">{html.escape(line)}</text>'
        for i, line in enumerate(terminal_lines)
    )

    repo_rows = []
    for index, repo in enumerate(repos[:7]):
        y = 302 + index * 26
        language = repo["language"] or "Unknown"
        heat = max(10, min(116, 24 + repo["open_issues"] * 10 + repo["stars"] * 5))
        repo_rows.append(
            f'<text x="706" y="{y}" class="repo-name">{html.escape(repo["name"][:28])}</text>'
            f'<rect x="1018" y="{y - 12}" width="{heat}" height="8" fill="{language_color(language)}" opacity=".78"/>'
            f'<text x="1150" y="{y}" text-anchor="end" class="repo-meta">{html.escape(language)}</text>'
        )

    narrative = wrapped_text(state["narrative"], 72, 528, 76, "small", line_height=18)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="560" viewBox="0 0 1200 560" role="img" aria-labelledby="title desc">
  <title id="title">Profile OS for {name}</title>
  <desc id="desc">{html.escape(state["narrative"])}</desc>
  <style>
    :root {{ color-scheme: dark; }}
    .bg {{ fill: #08090d; }}
    .grid {{ stroke: #1f2937; stroke-width: 1; opacity: .48; }}
    .panel {{ fill: #10141c; stroke: #253044; stroke-width: 1; }}
    .panel-hot {{ fill: #141116; stroke: #f59e0b; stroke-width: 1; }}
    .eyebrow {{ font: 700 13px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #2dd4bf; letter-spacing: 0; }}
    .title {{ font: 800 58px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #f8fafc; letter-spacing: 0; }}
    .subtitle {{ font: 600 19px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #cbd5e1; }}
    .small {{ font: 600 14px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #94a3b8; }}
    .mono {{ font: 650 16px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #d1fae5; }}
    .metric {{ font: 800 34px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #f8fafc; }}
    .label {{ font: 700 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #64748b; }}
    .repo-name {{ font: 650 15px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #e5e7eb; }}
    .repo-meta {{ font: 650 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #94a3b8; }}
    .scan {{ fill: #2dd4bf; opacity: .15; animation: scan 5s linear infinite; }}
    .bar {{ animation: barPulse 4s ease-in-out infinite; }}
    .pulse {{ animation: pulse 2.8s ease-in-out infinite; }}
    @keyframes scan {{ 0% {{ transform: translateX(-260px); }} 100% {{ transform: translateX(1220px); }} }}
    @keyframes barPulse {{ 0%, 100% {{ opacity: .42; }} 50% {{ opacity: .95; }} }}
    @keyframes pulse {{ 0%, 100% {{ opacity: .55; }} 50% {{ opacity: 1; }} }}
    @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
  </style>
  <defs>
    <linearGradient id="edge" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#2dd4bf"/>
      <stop offset=".52" stop-color="#f59e0b"/>
      <stop offset="1" stop-color="#fb7185"/>
    </linearGradient>
  </defs>
  <rect class="bg" width="1200" height="560"/>
  {"".join(f'<line class="grid" x1="{x}" y1="0" x2="{x}" y2="560"/>' for x in range(40, 1200, 40))}
  {"".join(f'<line class="grid" x1="0" y1="{y}" x2="1200" y2="{y}"/>' for y in range(30, 560, 30))}
  <rect x="26" y="26" width="1148" height="508" rx="8" fill="none" stroke="url(#edge)" stroke-width="2"/>
  <rect class="scan" x="0" y="26" width="180" height="508"/>
  <text x="70" y="78" class="eyebrow">PROFILE_OS / PUBLIC SIGNAL BOARD / {generated} UTC</text>
  <text x="68" y="148" class="title">{name}</text>
  <text x="72" y="185" class="subtitle">AI-native prototypes, automation systems, and launchable product slices.</text>
  <rect x="70" y="220" width="550" height="190" rx="8" class="panel"/>
  <text x="94" y="258" class="eyebrow">TERMINAL SNAPSHOT</text>
  {terminal}
  <rect x="656" y="220" width="474" height="190" rx="8" class="panel"/>
  <text x="680" y="258" class="eyebrow">REPOSITORY STREAM</text>
  {"".join(repo_rows)}
  <g transform="translate(72 438)">
    <rect x="0" y="0" width="144" height="66" rx="8" class="panel"/>
    <text x="18" y="22" class="label">HEALTH</text>
    <text x="18" y="54" class="metric">{state["health"]}</text>
    <rect x="166" y="0" width="144" height="66" rx="8" class="panel"/>
    <text x="184" y="22" class="label">ACTIVITY</text>
    <text x="184" y="54" class="metric">{state["activity"]}</text>
    <rect x="332" y="0" width="144" height="66" rx="8" class="panel-hot"/>
    <text x="350" y="22" class="label">PRESSURE</text>
    <text x="350" y="54" class="metric">{state["pressure"]}</text>
    <circle cx="522" cy="33" r="8" fill="{status_color}" class="pulse"/>
    <text x="542" y="39" class="small">mode: {html.escape(state["mood"])}</text>
  </g>
  <g transform="translate(682 438)">
    <text x="0" y="0" class="eyebrow">RECENT EVENT DENSITY</text>
    {render_bars(event_values, 0, 18, 430, 62, "#2dd4bf")}
  </g>
  {narrative}
</svg>
'''


def render_project_matrix(signals: dict[str, Any]) -> str:
    repos = signals["repos"][:9]
    rows_count = max(1, (len(repos) + 2) // 3)
    height = 134 + rows_count * 102
    rows = []
    for index, repo in enumerate(repos):
        col = index % 3
        row = index // 3
        x = 54 + col * 372
        y = 102 + row * 102
        language = repo["language"] or "Unknown"
        heat = min(100, 74 + repo["stars"] * 8 + repo["forks"] * 5 - repo["open_issues"] * 4)
        rows.append(
            f'<g class="card" style="animation-delay:{index * -0.35}s">'
            f'<rect x="{x}" y="{y}" width="332" height="88" rx="8" class="card-bg"/>'
            f'<rect x="{x}" y="{y}" width="5" height="88" fill="{language_color(language)}"/>'
            f'<text x="{x + 22}" y="{y + 31}" class="repo">{html.escape(repo["name"][:30])}</text>'
            f'<text x="{x + 22}" y="{y + 58}" class="meta">{html.escape(language)} / stars {repo["stars"]} / issues {repo["open_issues"]}</text>'
            f'<rect x="{x + 214}" y="{y + 62}" width="86" height="6" fill="#1f2937"/>'
            f'<rect x="{x + 214}" y="{y + 62}" width="{max(8, min(86, heat * 0.86)):.1f}" height="6" fill="{language_color(language)}"/>'
            "</g>"
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}" role="img" aria-label="Project matrix">
  <style>
    :root {{ color-scheme: dark; }}
    .bg {{ fill: #08090d; }}
    .grid {{ stroke: #1f2937; opacity: .45; }}
    .title {{ font: 800 34px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #f8fafc; }}
    .sub {{ font: 600 15px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #94a3b8; }}
    .repo {{ font: 750 18px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #e5e7eb; }}
    .meta {{ font: 600 13px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #94a3b8; }}
    .card-bg {{ fill: #10141c; stroke: #253044; }}
    .card {{ animation: lift 4s ease-in-out infinite; }}
    @keyframes lift {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-4px); }} }}
    @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
  </style>
  <rect class="bg" width="1200" height="{height}"/>
  {"".join(f'<line class="grid" x1="{x}" y1="0" x2="{x}" y2="{height}"/>' for x in range(42, 1200, 42))}
  {"".join(f'<line class="grid" x1="0" y1="{y}" x2="1200" y2="{y}"/>' for y in range(34, height, 34))}
  <text x="54" y="58" class="title">Project Matrix</text>
  <text x="54" y="86" class="sub">Recent public repositories rendered as a no-click portfolio layer.</text>
  {"".join(rows)}
</svg>
'''


def render_skill_map(state: dict[str, Any]) -> str:
    languages = state["top_languages"] or ["Python", "TypeScript", "Automation"]
    language_text = " / ".join(languages[:5])
    lanes = [
        ("Prototype", 92, "#2dd4bf"),
        ("Automate", 86, "#f59e0b"),
        ("Interface", 78, "#38bdf8"),
        ("Launch", 72, "#fb7185"),
    ]
    lane_svg = []
    for index, (label, score, color) in enumerate(lanes):
        y = 104 + index * 46
        lane_svg.append(
            f'<text x="72" y="{y + 8}" class="label">{label}</text>'
            f'<rect x="232" y="{y - 10}" width="820" height="16" rx="8" class="track"/>'
            f'<rect x="232" y="{y - 10}" width="{score * 8.2:.1f}" height="16" rx="8" fill="{color}" class="fill"/>'
            f'<text x="1080" y="{y + 8}" text-anchor="end" class="score">{score}</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="290" viewBox="0 0 1200 290" role="img" aria-label="Builder skill map">
  <style>
    :root {{ color-scheme: dark; }}
    .bg {{ fill: #08090d; }}
    .title {{ font: 800 34px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #f8fafc; }}
    .sub {{ font: 600 15px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #94a3b8; }}
    .label {{ font: 750 18px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #e5e7eb; }}
    .score {{ font: 800 20px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #f8fafc; }}
    .track {{ fill: #111827; stroke: #253044; }}
    .fill {{ animation: breathe 3.2s ease-in-out infinite; transform-origin: left; }}
    @keyframes breathe {{ 0%, 100% {{ opacity: .68; }} 50% {{ opacity: 1; }} }}
    @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
  </style>
  <rect class="bg" width="1200" height="290"/>
  <rect x="34" y="30" width="1132" height="230" rx="8" fill="#10141c" stroke="#253044"/>
  <text x="72" y="76" class="title">Builder Skill Map</text>
  <text x="72" y="102" class="sub">Current language signal: {html.escape(language_text)}</text>
  {"".join(lane_svg)}
</svg>
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Use bundled sample signals")
    parser.add_argument("--owner", default=os.getenv("GITHUB_OWNER") or os.getenv("GITHUB_REPOSITORY_OWNER") or "davidvuy")
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
    HERO_PATH.write_text(render_hero(signals, state), encoding="utf-8")
    PROJECTS_PATH.write_text(render_project_matrix(signals), encoding="utf-8")
    SKILLS_PATH.write_text(render_skill_map(state), encoding="utf-8")

    print(
        textwrap.dedent(
            f"""\
            Generated {HERO_PATH}
            Generated {PROJECTS_PATH}
            Generated {SKILLS_PATH}
            mood={state['mood']} health={state['health']} activity={state['activity']} pressure={state['pressure']}
            """
        ).strip()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
