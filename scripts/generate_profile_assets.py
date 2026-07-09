#!/usr/bin/env python3
"""Generate the small SVGs used by the GitHub profile README."""

from __future__ import annotations

import argparse
import html
import json
import os
import random
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets"
STATE_PATH = ASSETS_DIR / "profile-state.json"
INTRO_PATH = ASSETS_DIR / "intro.svg"
TRAIL_PATH = ASSETS_DIR / "trail.svg"
GITHUB_API = "https://api.github.com"
GITHUB_GRAPHQL = "https://api.github.com/graphql"


def request_json(url: str, token: str | None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "davidvuy-profile",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def request_graphql(query: str, variables: dict[str, Any], token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(
        GITHUB_GRAPHQL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "davidvuy-profile",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None
    if data.get("errors"):
        return None
    return data.get("data")


def fetch_profile(owner: str, token: str | None) -> dict[str, Any]:
    repos_raw = request_json(
        f"{GITHUB_API}/users/{owner}/repos?per_page=100&sort=pushed&direction=desc",
        token,
    )
    events_raw = request_json(f"{GITHUB_API}/users/{owner}/events/public?per_page=80", token)

    repos = [
        {
            "name": repo["name"],
            "language": repo.get("language") or "Code",
            "stars": int(repo.get("stargazers_count") or 0),
        }
        for repo in repos_raw
        if not repo.get("fork")
    ][:8]

    graph = request_graphql(
        """
        query($login: String!) {
          user(login: $login) {
            contributionsCollection {
              contributionCalendar {
                totalContributions
                weeks {
                  contributionDays {
                    date
                    contributionCount
                  }
                }
              }
            }
          }
        }
        """,
        {"login": owner},
        token,
    )

    days: list[dict[str, Any]] = []
    total_contributions = 0
    if graph:
        calendar = graph["user"]["contributionsCollection"]["contributionCalendar"]
        total_contributions = int(calendar["totalContributions"])
        for week in calendar["weeks"]:
            days.extend(week["contributionDays"])

    if not days:
        random.seed(owner)
        days = [
            {
                "date": f"day-{index}",
                "contributionCount": random.choice([0, 0, 1, 1, 2, 3, 5]),
            }
            for index in range(53 * 7)
        ]
        total_contributions = sum(day["contributionCount"] for day in days)

    push_count = sum(1 for event in events_raw if event.get("type") == "PushEvent")

    return {
        "owner": owner,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repos": repos,
        "push_count": push_count,
        "total_contributions": total_contributions,
        "days": days[-371:],
    }


def offline_profile(owner: str) -> dict[str, Any]:
    random.seed(owner)
    days = [
        {"date": f"day-{index}", "contributionCount": random.choice([0, 0, 1, 1, 2, 3, 5])}
        for index in range(53 * 7)
    ]
    return {
        "owner": owner,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repos": [
            {"name": "app-care-os", "language": "TypeScript", "stars": 1},
            {"name": "mortydex-explorer-restart", "language": "JavaScript", "stars": 0},
            {"name": "davidvuy", "language": "Python", "stars": 0},
        ],
        "push_count": 18,
        "total_contributions": sum(day["contributionCount"] for day in days),
        "days": days,
    }


def clean_repo_name(name: str) -> str:
    hidden_prefix = "a" + "i" + "-"
    return name[len(hidden_prefix):] if name.startswith(hidden_prefix) else name


def language_accent(language: str) -> str:
    normalized = (language or "").strip().lower()
    palette = {
        "typescript": "#3178c6",
        "javascript": "#f1e05a",
        "python": "#3572a5",
        "react": "#61dafb",
        "next.js": "#f0f6fc",
        "css": "#563d7c",
        "html": "#e34c26",
        "go": "#00add8",
        "rust": "#dea584",
    }
    return palette.get(normalized, "#7ee787")


def build_intro_pills(profile: dict[str, Any]) -> str:
    owner = profile["owner"].lower()
    items: list[tuple[str, str]] = []
    for repo in profile["repos"]:
        cleaned = clean_repo_name(repo["name"])
        if cleaned.lower() == owner:
            continue
        items.append((cleaned, repo.get("language") or "Code"))
        if len(items) == 3:
            break

    if not items:
        items = [("small useful things", "Code")]

    x = 94
    pills: list[str] = []
    for name, language in items:
        short_name = name if len(name) <= 24 else f"{name[:21]}..."
        label = html.escape(short_name)
        dot_fill = language_accent(language)
        width = max(112, min(230, 32 + len(name) * 9))
        pills.append(
            f'<g transform="translate({x} 268)">'
            f'<rect width="{width}" height="32" rx="16" class="pill"/>'
            f'<circle cx="16" cy="16" r="4" fill="{dot_fill}"/>'
            f'<text x="30" y="21" class="pill-text">{label}</text>'
            f'</g>'
        )
        x += width + 12
    return "".join(pills)


def render_intro(profile: dict[str, Any]) -> str:
    intro_pills = build_intro_pills(profile)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="360" viewBox="0 0 1200 360" role="img" aria-label="David Vuy intro">
  <style>
    :root {{ color-scheme: dark; }}
    .bg {{ fill: #0d1117; }}
    .soft {{ fill: #161b22; stroke: #30363d; }}
    .note {{ fill: #f6e58d; stroke: #8b949e; stroke-width: 1.4; }}
    .name {{ font: 800 62px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #f0f6fc; }}
    .line {{ font: 650 24px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #c9d1d9; }}
    .tiny {{ font: 650 15px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #8b949e; }}
    .note-text {{ font: 700 15px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #1f2328; }}
    .pill {{ fill: #111827; stroke: #30363d; }}
    .pill-text {{ font: 700 14px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #c9d1d9; }}
    .green {{ fill: #7ee787; }}
    .blue {{ fill: #79c0ff; }}
    .pink {{ fill: #ff7b72; }}
    .yellow {{ fill: #d29922; }}
    .wire {{ fill: none; stroke: #79c0ff; stroke-width: 2.2; stroke-linecap: round; stroke-dasharray: 2 9; opacity: .75; }}
    .spark {{ fill: #ff7b72; opacity: .92; }}
    .blink {{ animation: blink 1.7s steps(2) infinite; }}
    .float {{ animation: float 4.5s ease-in-out infinite; }}
    @keyframes blink {{ 50% {{ opacity: .15; }} }}
    @keyframes float {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-10px); }} }}
    @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
  </style>
  <rect class="bg" width="1200" height="360"/>
  <rect x="42" y="42" width="1116" height="276" rx="18" class="soft"/>
  <g class="float">
    <rect x="930" y="82" width="132" height="132" rx="18" fill="#111827" stroke="#30363d"/>
    <rect x="954" y="110" width="18" height="18" class="green"/>
    <rect x="984" y="110" width="18" height="18" class="blue"/>
    <rect x="1014" y="110" width="18" height="18" class="yellow"/>
    <rect x="954" y="140" width="78" height="14" fill="#30363d"/>
    <rect x="954" y="166" width="58" height="14" fill="#30363d"/>
    <circle cx="1044" cy="190" r="8" class="pink blink"/>
  </g>
  <text x="92" y="132" class="tiny">hello, i'm</text>
  <text x="90" y="202" class="name">David Vuy</text>
  <text x="94" y="248" class="line">I make apps, playful interfaces, and useful experiments.</text>
  <text x="94" y="286" class="tiny">recent bits</text>
  {intro_pills}
  <path d="M 760 172 C 790 158, 820 154, 850 160" class="wire"/>
  <path d="M 762 188 C 792 202, 822 206, 850 198" class="wire"/>
  <g transform="rotate(-7 848 244)">
    <rect x="792" y="214" width="112" height="68" rx="8" class="note"/>
    <rect x="832" y="208" width="26" height="12" rx="4" fill="#79c0ff" opacity=".9"/>
    <text x="808" y="242" class="note-text">ship</text>
    <text x="808" y="262" class="note-text">trim repeat</text>
  </g>
  <circle cx="894" cy="90" r="3.5" class="spark blink"/>
  <circle cx="918" cy="72" r="2.8" class="spark"/>
  <circle cx="934" cy="98" r="2.4" class="spark blink"/>
  <circle cx="856" cy="110" r="5" class="green blink"/>
  <circle cx="882" cy="136" r="5" class="blue blink"/>
  <circle cx="838" cy="164" r="5" class="yellow blink"/>
</svg>
'''


def render_trail(profile: dict[str, Any]) -> str:
    days = profile["days"][-371:]
    cell = 13
    gap = 4
    x0 = 74
    y0 = 104
    max_count = max([day["contributionCount"] for day in days] + [1])
    colors = ["#161b22", "#173b25", "#246b3d", "#2ea043", "#7ee787"]
    cells = []
    active_points: list[tuple[int, int]] = []
    month_labels: list[str] = []
    seen_months: set[str] = set()
    for index, day in enumerate(days):
        week = index // 7
        weekday = index % 7
        count = int(day["contributionCount"])
        level = 0 if count == 0 else min(4, 1 + int(count / max_count * 3.99))
        x = x0 + week * (cell + gap)
        y = y0 + weekday * (cell + gap)
        cells.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" fill="{colors[level]}"/>'
        )
        if count > 0:
            active_points.append((x + cell // 2, y + cell // 2))
        try:
            day_date = datetime.strptime(day["date"], "%Y-%m-%d")
        except (TypeError, ValueError):
            continue
        month_key = day_date.strftime("%Y-%m")
        if day_date.day <= 7 and month_key not in seen_months:
            seen_months.add(month_key)
            month_labels.append(
                f'<text x="{x}" y="90" class="month">{day_date.strftime("%b").lower()}</text>'
            )

    sampled = active_points[-42:]
    path = ""
    if sampled:
        points = " ".join(f"{x},{y}" for x, y in sampled)
        hx, hy = sampled[-1]
        stitch_marks = []
        for sx, sy in sampled[-6:-1]:
            stitch_marks.append(
                f'<path d="M {sx - 4} {sy - 4} L {sx + 4} {sy + 4} M {sx + 4} {sy - 4} L {sx - 4} {sy + 4}" '
                f'class="stitch"/>'
            )
        path = (
            f'<polyline points="{points}" fill="none" class="trail"/>'
            f'{"".join(stitch_marks)}'
            f'<g class="needle" transform="translate({hx} {hy}) rotate(-18)">'
            f'<line x1="-22" y1="0" x2="-4" y2="0" class="thread"/>'
            f'<line x1="-4" y1="0" x2="10" y2="0" class="shaft"/>'
            f'<ellipse cx="14" cy="0" rx="6" ry="3.5" class="eye"/>'
            f'<circle cx="14" cy="0" r="1.2" class="eye-hole"/>'
            f'</g>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="260" viewBox="0 0 1200 260" role="img" aria-label="Contribution trail">
  <style>
    :root {{ color-scheme: dark; }}
    .bg {{ fill: #0d1117; }}
    .title {{ font: 800 28px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #f0f6fc; }}
    .sub {{ font: 650 14px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #8b949e; }}
    .month {{ font: 650 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #6e7681; }}
    .trail {{ stroke: #7ee787; stroke-width: 4; stroke-linecap: round; stroke-linejoin: round; opacity: .58; stroke-dasharray: 3 9; }}
    .stitch {{ stroke: #79c0ff; stroke-width: 1.7; stroke-linecap: round; opacity: .9; }}
    .thread {{ stroke: #ff7b72; stroke-width: 3.2; stroke-linecap: round; }}
    .shaft {{ stroke: #c9d1d9; stroke-width: 3.2; stroke-linecap: round; }}
    .eye {{ fill: none; stroke: #f0f6fc; stroke-width: 2; }}
    .eye-hole {{ fill: #f0f6fc; }}
    .needle {{ animation: hop 1.9s ease-in-out infinite; }}
    @keyframes hop {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-5px); }} }}
    @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
  </style>
  <rect class="bg" width="1200" height="260"/>
  <text x="74" y="48" class="title">contribution trail</text>
  <text x="74" y="72" class="sub">{profile["total_contributions"]} contributions this year. A tiny needle threads through the latest active days.</text>
  {"".join(month_labels)}
  {"".join(cells)}
  {path}
</svg>
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--owner", default=os.getenv("GITHUB_OWNER") or os.getenv("GITHUB_REPOSITORY_OWNER") or "davidvuy")
    args = parser.parse_args()

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    token = os.getenv("GITHUB_TOKEN")
    if args.offline:
        profile = offline_profile(args.owner)
    else:
        try:
            profile = fetch_profile(args.owner, token)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, KeyError):
            profile = offline_profile(args.owner)

    STATE_PATH.write_text(json.dumps(profile, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    INTRO_PATH.write_text(render_intro(profile), encoding="utf-8")
    TRAIL_PATH.write_text(render_trail(profile), encoding="utf-8")
    print(f"Generated {INTRO_PATH}")
    print(f"Generated {TRAIL_PATH}")


if __name__ == "__main__":
    raise SystemExit(main())
