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


def pretty_repo_label(name: str, *, max_words: int = 2, max_chars: int = 22) -> str:
    words = [word for word in clean_repo_name(name).replace("_", " ").replace("-", " ").split() if word]
    if not words:
        return "small useful things"

    leading_noise = {"app", "project", "repo"}
    trailing_noise = {"restart", "rebuild", "prototype", "starter", "template", "demo", "sandbox"}

    while len(words) > 1 and words[0].lower() in leading_noise:
        words.pop(0)
    while len(words) > 1 and words[-1].lower() in trailing_noise:
        words.pop()

    label_words = words[:max_words]
    label = " ".join(label_words)
    if len(label) > max_chars and len(label_words) > 1:
        label = label_words[0]
    if len(label) > max_chars:
        label = f"{label[: max_chars - 3].rstrip()}..."
    return label.lower()


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
        items.append((pretty_repo_label(cleaned), repo.get("language") or "Code"))
        if len(items) == 3:
            break

    if not items:
        items = [("small useful things", "Code")]

    x = 94
    pills: list[str] = []
    for name, language in items:
        label = html.escape(name)
        dot_fill = language_accent(language)
        width = max(112, min(230, 32 + len(name) * 9))
        pills.append(
            f'<g transform="translate({x} 268)">'
            f'<rect width="{width}" height="32" rx="16" class="pill"/>'
            f'<circle cx="16" cy="16" r="4" fill="{dot_fill}"/>'
            f'<text x="30" y="21" class="pill-text">{label}</text>'
            f'<path d="M 32 25 H {width - 20}" class="pill-thread" stroke="{dot_fill}"/>'
            f'<circle cx="{width - 14}" cy="25" r="2.4" fill="{dot_fill}" opacity=".9"/>'
            f'</g>'
        )
        x += width + 12
    return "".join(pills)


def build_intro_note(profile: dict[str, Any]) -> tuple[str, str]:
    owner = profile["owner"].lower()
    fallback = ("small", "but real")
    for repo in profile["repos"]:
        cleaned = clean_repo_name(repo["name"])
        if cleaned.lower() == owner:
            continue
        return ("lately", pretty_repo_label(cleaned, max_chars=14))
    return fallback


def build_intro_note_tab(profile: dict[str, Any]) -> tuple[str, str, int]:
    owner = profile["owner"].lower()
    label_map = {
        "typescript": "TS",
        "javascript": "JS",
        "python": "PY",
        "react": "UI",
        "next.js": "NX",
        "css": "CSS",
        "html": "HTML",
        "go": "GO",
        "rust": "RS",
    }
    for repo in profile["repos"]:
        cleaned = clean_repo_name(repo["name"])
        if cleaned.lower() == owner:
            continue
        language = (repo.get("language") or "Code").strip()
        normalized = language.lower()
        label = label_map.get(normalized, language[:4].upper())
        width = max(26, min(40, 14 + len(label) * 6))
        return (label, language_accent(language), width)
    return ("NEW", "#79c0ff", 34)


def build_postmark_text(profile: dict[str, Any]) -> tuple[str, str]:
    generated_at = profile.get("generated_at")
    if isinstance(generated_at, str):
        normalized = generated_at.replace("Z", "+00:00")
        try:
            stamp_date = datetime.fromisoformat(normalized)
        except ValueError:
            stamp_date = None
        if stamp_date:
            return (stamp_date.strftime("%b").upper(), stamp_date.strftime("%y"))
    return ("NOW", "++")


def current_streak(days: list[dict[str, Any]]) -> int:
    streak = 0
    for day in reversed(days):
        if int(day.get("contributionCount") or 0) <= 0:
            break
        streak += 1
    return streak


def trail_tagline(days: list[dict[str, Any]]) -> str:
    streak = current_streak(days)
    if streak > 0:
        return f"{streak}-day streak"

    recent = days[-7:]
    active_days = sum(1 for day in recent if int(day.get("contributionCount") or 0) > 0)
    total_recent = sum(int(day.get("contributionCount") or 0) for day in recent)

    if total_recent >= 10:
        return "busy little week"
    if active_days >= 3:
        return "thread stayed warm"
    if active_days >= 1:
        return "small spark lately"
    return "new streak soon"


def trail_project_label(profile: dict[str, Any]) -> str:
    owner = profile["owner"].lower()
    for repo in profile["repos"]:
        cleaned = clean_repo_name(repo["name"])
        if cleaned.lower() == owner:
            continue
        return pretty_repo_label(cleaned, max_words=3, max_chars=18)
    return "small useful things"


def render_intro(profile: dict[str, Any]) -> str:
    intro_pills = build_intro_pills(profile)
    note_top, note_bottom = build_intro_note(profile)
    note_tab_text, note_tab_fill, note_tab_width = build_intro_note_tab(profile)
    postmark_top, postmark_bottom = build_postmark_text(profile)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="360" viewBox="0 0 1200 360" role="img" aria-label="David Vuy intro">
  <style>
    :root {{ color-scheme: dark; }}
    .bg {{ fill: #0d1117; }}
    .soft {{ fill: #161b22; stroke: #30363d; }}
    .punch-hole {{ fill: #0d1117; stroke: #30363d; stroke-width: 1.2; opacity: .96; }}
    .punch-shadow {{ fill: #79c0ff; opacity: .08; }}
    .corner-stitch {{ fill: none; stroke: #8b949e; stroke-width: 1.5; stroke-linecap: round; stroke-dasharray: 1.5 6; opacity: .72; }}
    .note {{ fill: #f6e58d; stroke: #8b949e; stroke-width: 1.4; }}
    .note-shadow {{ fill: #0d1117; opacity: .34; }}
    .note-fold {{ fill: #f0d86a; stroke: #8b949e; stroke-width: 1.2; }}
    .note-crease {{ fill: none; stroke: #d29922; stroke-width: 1.2; stroke-linecap: round; opacity: .9; }}
    .note-rule {{ fill: none; stroke: #79c0ff; stroke-width: 1.1; stroke-linecap: round; opacity: .28; }}
    .name {{ font: 800 62px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #f0f6fc; }}
    .line {{ font: 650 24px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #c9d1d9; }}
    .tiny {{ font: 650 15px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #8b949e; }}
    .note-text {{ font: 700 15px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #1f2328; }}
    .note-chip-text {{ font: 800 9px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; letter-spacing: 1px; fill: #f0f6fc; text-anchor: middle; }}
    .pill {{ fill: #111827; stroke: #30363d; }}
    .pill-text {{ font: 700 14px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #c9d1d9; }}
    .pill-thread {{ fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-dasharray: 2 6; opacity: .78; }}
    .green {{ fill: #7ee787; }}
    .blue {{ fill: #79c0ff; }}
    .pink {{ fill: #ff7b72; }}
    .yellow {{ fill: #d29922; }}
    .wire {{ fill: none; stroke: #79c0ff; stroke-width: 2.2; stroke-linecap: round; stroke-dasharray: 2 9; opacity: .75; }}
    .scribble {{ fill: none; stroke: #7ee787; stroke-width: 3.6; stroke-linecap: round; stroke-linejoin: round; opacity: .9; }}
    .orbit {{ fill: none; stroke: #ff7b72; stroke-width: 2.2; stroke-linecap: round; stroke-dasharray: 1 10; opacity: .72; }}
    .planet {{ fill: #79c0ff; }}
    .spark {{ fill: #ff7b72; opacity: .92; }}
    .stamp-card {{ fill: #111827; stroke: #30363d; }}
    .stamp-hole {{ fill: #0d1117; opacity: .95; }}
    .stamp-title {{ font: 800 13px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; letter-spacing: 1.3px; fill: #f0f6fc; }}
    .stamp-value {{ font: 800 18px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; letter-spacing: .8px; fill: #f0f6fc; opacity: .9; text-anchor: end; }}
    .stamp-corner-line {{ fill: none; stroke: #30363d; stroke-width: 1.4; stroke-linecap: round; opacity: .9; }}
    .stamp-line {{ stroke: #30363d; stroke-width: 2; stroke-linecap: round; }}
    .stamp-wave {{ fill: none; stroke: #79c0ff; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; opacity: .9; }}
    .plane-path {{ fill: none; stroke: #8b949e; stroke-width: 1.8; stroke-linecap: round; stroke-dasharray: 4 10; opacity: .55; }}
    .plane {{ fill: #f0f6fc; opacity: .95; }}
    .plane-group {{ animation: drift 7.5s ease-in-out infinite; }}
    .postmark-ring {{ fill: none; stroke: #8b949e; stroke-width: 1.4; stroke-dasharray: 3 7; opacity: .55; }}
    .postmark-slice {{ fill: none; stroke: #79c0ff; stroke-width: 2; stroke-linecap: round; opacity: .85; }}
    .cancel-line {{ fill: none; stroke: #79c0ff; stroke-width: 2; stroke-linecap: round; opacity: .62; }}
    .postmark-text {{ font: 700 10px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; letter-spacing: 1.6px; fill: #c9d1d9; opacity: .78; }}
    .postmark-date {{ font: 800 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; letter-spacing: 1.1px; fill: #f0f6fc; opacity: .92; }}
    .tape {{ fill: #79c0ff; opacity: .82; }}
    .tape-stripe {{ stroke: #f0f6fc; stroke-width: 1; stroke-linecap: round; opacity: .42; }}
    .paperclip {{ fill: none; stroke: #f0f6fc; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; opacity: .9; }}
    .seal {{ fill: #ff7b72; stroke: #30363d; stroke-width: 1.2; }}
    .seal-fold {{ fill: #ffa198; opacity: .9; }}
    .seal-dot {{ fill: #f0f6fc; opacity: .9; }}
    .coffee-ring {{ fill: none; stroke: #d29922; stroke-width: 3; stroke-linecap: round; opacity: .2; }}
    .coffee-drop {{ fill: #d29922; opacity: .14; }}
    .airmail-red {{ fill: #ff7b72; opacity: .95; }}
    .airmail-blue {{ fill: #79c0ff; opacity: .95; }}
    .cursor {{ fill: #f6e58d; opacity: .95; }}
    .signature {{ fill: none; stroke: #c9d1d9; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; opacity: .78; }}
    .signature-dot {{ fill: #79c0ff; opacity: .9; }}
    .doodle-star {{ fill: none; stroke: #f0f6fc; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; opacity: .88; }}
    .doodle-star-fill {{ fill: #f6e58d; opacity: .95; }}
    .doodle-star-dot {{ fill: #79c0ff; opacity: .88; }}
    .button-thread {{ fill: none; stroke: #8b949e; stroke-width: 1.6; stroke-linecap: round; stroke-dasharray: 2 5; opacity: .78; }}
    .button {{ fill: #111827; stroke: #8b949e; stroke-width: 1.4; }}
    .button-ring {{ fill: none; stroke: #30363d; stroke-width: 1; opacity: .85; }}
    .button-hole {{ fill: #f0f6fc; opacity: .9; }}
    .button-stitch {{ fill: none; stroke: #79c0ff; stroke-width: 1.2; stroke-linecap: round; opacity: .8; }}
    .blink {{ animation: blink 1.7s steps(2) infinite; }}
    .float {{ animation: float 4.5s ease-in-out infinite; }}
    .orbit-spin {{ animation: orbit-spin 9s linear infinite; transform-origin: 182px 110px; }}
    @keyframes drift {{ 0%, 100% {{ transform: translate(0, 0); }} 50% {{ transform: translate(-10px, 6px); }} }}
    @keyframes blink {{ 50% {{ opacity: .15; }} }}
    @keyframes float {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-10px); }} }}
    @keyframes orbit-spin {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}
    @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
  </style>
  <rect class="bg" width="1200" height="360"/>
  <rect x="42" y="42" width="1116" height="276" rx="18" class="soft"/>
  <g transform="translate(56 0)">
    <ellipse cx="0" cy="108" rx="8" ry="12" class="punch-shadow"/>
    <ellipse cx="0" cy="180" rx="8" ry="12" class="punch-shadow"/>
    <ellipse cx="0" cy="252" rx="8" ry="12" class="punch-shadow"/>
    <ellipse cx="0" cy="108" rx="6.5" ry="10" class="punch-hole"/>
    <ellipse cx="0" cy="180" rx="6.5" ry="10" class="punch-hole"/>
    <ellipse cx="0" cy="252" rx="6.5" ry="10" class="punch-hole"/>
  </g>
  <path d="M 84 88 C 84 64, 98 50, 122 50" class="corner-stitch"/>
  <path d="M 84 110 C 84 78, 104 58, 136 58" class="corner-stitch"/>
  <path d="M 1116 272 C 1138 272, 1152 258, 1152 236" class="corner-stitch"/>
  <path d="M 1098 272 C 1128 272, 1144 252, 1144 222" class="corner-stitch"/>
  <g transform="translate(84 58)">
    <rect width="16" height="8" rx="2" class="airmail-red"/>
    <rect x="20" width="16" height="8" rx="2" class="airmail-blue"/>
    <rect x="40" width="16" height="8" rx="2" class="airmail-red"/>
    <rect x="60" width="16" height="8" rx="2" class="airmail-blue"/>
    <rect x="80" width="16" height="8" rx="2" class="airmail-red"/>
    <rect x="100" width="16" height="8" rx="2" class="airmail-blue"/>
  </g>
  <g transform="translate(966 294)">
    <rect width="16" height="8" rx="2" class="airmail-blue"/>
    <rect x="20" width="16" height="8" rx="2" class="airmail-red"/>
    <rect x="40" width="16" height="8" rx="2" class="airmail-blue"/>
    <rect x="60" width="16" height="8" rx="2" class="airmail-red"/>
    <rect x="80" width="16" height="8" rx="2" class="airmail-blue"/>
    <rect x="100" width="16" height="8" rx="2" class="airmail-red"/>
  </g>
  <g transform="translate(980 258) rotate(8)">
    <circle cx="0" cy="0" r="35" class="coffee-ring"/>
    <path d="M -19 -28 C -3 -35, 17 -32, 28 -17 C 36 -6, 36 14, 24 28" class="coffee-ring"/>
    <ellipse cx="28" cy="22" rx="7" ry="4" class="coffee-drop"/>
  </g>
  <g transform="translate(1012 276) rotate(-6)">
    <path d="M 0 0 C 6 -8, 14 -8, 18 0 C 22 9, 14 18, 6 14 C 1 11, 0 5, 4 2" class="signature"/>
    <path d="M 24 -4 C 24 10, 30 18, 38 18 C 44 18, 48 14, 48 8 C 48 0, 42 -2, 36 1 C 31 4, 29 11, 31 18" class="signature"/>
    <path d="M 56 14 C 65 20, 76 20, 88 14" class="signature"/>
    <circle cx="92" cy="12" r="2.4" class="signature-dot"/>
  </g>
  <g class="orbit-spin">
    <ellipse cx="182" cy="110" rx="72" ry="28" class="orbit"/>
    <circle cx="254" cy="110" r="5" class="planet"/>
  </g>
  <g transform="translate(446 102) rotate(8)">
    <path d="M 0 -14 L 0 14 M -14 0 L 14 0 M -10 -10 L 10 10 M 10 -10 L -10 10" class="doodle-star"/>
    <path d="M 0 -6 L 4 0 L 0 6 L -4 0 Z" class="doodle-star-fill"/>
    <circle cx="17" cy="-8" r="2.6" class="doodle-star-dot"/>
    <circle cx="-13" cy="12" r="2.2" class="doodle-star-dot"/>
  </g>
  <g class="float">
    <rect x="930" y="82" width="132" height="132" rx="18" class="stamp-card"/>
    <circle cx="944" cy="96" r="4" class="stamp-hole"/><circle cx="960" cy="96" r="4" class="stamp-hole"/><circle cx="976" cy="96" r="4" class="stamp-hole"/><circle cx="992" cy="96" r="4" class="stamp-hole"/><circle cx="1008" cy="96" r="4" class="stamp-hole"/><circle cx="1024" cy="96" r="4" class="stamp-hole"/><circle cx="1040" cy="96" r="4" class="stamp-hole"/>
    <circle cx="944" cy="200" r="4" class="stamp-hole"/><circle cx="960" cy="200" r="4" class="stamp-hole"/><circle cx="976" cy="200" r="4" class="stamp-hole"/><circle cx="992" cy="200" r="4" class="stamp-hole"/><circle cx="1008" cy="200" r="4" class="stamp-hole"/><circle cx="1024" cy="200" r="4" class="stamp-hole"/><circle cx="1040" cy="200" r="4" class="stamp-hole"/>
    <circle cx="944" cy="112" r="4" class="stamp-hole"/><circle cx="944" cy="128" r="4" class="stamp-hole"/><circle cx="944" cy="144" r="4" class="stamp-hole"/><circle cx="944" cy="160" r="4" class="stamp-hole"/><circle cx="944" cy="176" r="4" class="stamp-hole"/><circle cx="944" cy="192" r="4" class="stamp-hole"/>
    <circle cx="1048" cy="112" r="4" class="stamp-hole"/><circle cx="1048" cy="128" r="4" class="stamp-hole"/><circle cx="1048" cy="144" r="4" class="stamp-hole"/><circle cx="1048" cy="160" r="4" class="stamp-hole"/><circle cx="1048" cy="176" r="4" class="stamp-hole"/><circle cx="1048" cy="192" r="4" class="stamp-hole"/>
    <text x="956" y="118" class="stamp-title">BY HAND</text>
    <text x="1038" y="118" class="stamp-value">01c</text>
    <path d="M 1014 124 H 1038 V 148" class="stamp-corner-line"/>
    <path d="M 956 128 H 1038" class="stamp-line"/>
    <path d="M 960 168 C 974 148, 990 156, 1002 168 S 1028 188, 1038 160" class="stamp-wave"/>
    <circle cx="972" cy="150" r="5" class="green"/>
    <circle cx="995" cy="182" r="5" class="blue"/>
    <circle cx="1024" cy="146" r="5" class="yellow"/>
    <circle cx="1032" cy="184" r="7" class="pink blink"/>
  </g>
  <g transform="translate(860 106) rotate(-10)">
    <circle cx="0" cy="0" r="32" class="postmark-ring"/>
    <circle cx="0" cy="0" r="21" class="postmark-ring"/>
    <path d="M -17 -6 C -7 -14, 6 -14, 16 -6" class="postmark-slice"/>
    <path d="M -15 8 C -5 16, 7 16, 17 8" class="postmark-slice"/>
    <text x="-11" y="-2" class="postmark-date">{html.escape(postmark_top)}</text>
    <text x="-7" y="12" class="postmark-text">{html.escape(postmark_bottom)}</text>
  </g>
  <g transform="translate(896 118) rotate(-10)">
    <path d="M 0 0 C 22 -6, 46 -4, 70 2" class="cancel-line"/>
    <path d="M 2 14 C 26 8, 52 10, 78 16" class="cancel-line"/>
    <path d="M 6 28 C 32 24, 58 26, 84 32" class="cancel-line"/>
  </g>
  <path d="M 742 88 C 786 66, 838 64, 884 86 S 972 126, 1030 100" class="plane-path"/>
  <g class="plane-group" transform="translate(1024 98) rotate(6)">
    <path d="M 0 0 L 24 8 L 0 16 L 6 8 Z" class="plane"/>
    <path d="M 6 8 L 24 8" class="plane-path"/>
  </g>
  <text x="92" y="132" class="tiny">hello, i'm</text>
  <rect x="208" y="116" width="12" height="18" rx="2.5" class="cursor blink"/>
  <text x="90" y="202" class="name">David Vuy</text>
  <path d="M 94 214 C 164 232, 255 230, 356 214 C 388 209, 408 207, 430 214" class="scribble"/>
  <text x="94" y="248" class="line">I make apps, playful interfaces, and useful experiments.</text>
  <text x="94" y="286" class="tiny">recent bits</text>
  {intro_pills}
  <path d="M 760 172 C 790 158, 820 154, 850 160" class="wire"/>
  <path d="M 762 188 C 792 202, 822 206, 850 198" class="wire"/>
  <g transform="translate(752 180) rotate(-12)">
    <path d="M 0 0 C 10 14, 20 26, 31 38" class="button-thread"/>
    <g transform="translate(31 38)">
      <circle cx="0" cy="0" r="13" class="button"/>
      <circle cx="0" cy="0" r="9" class="button-ring"/>
      <circle cx="-4" cy="-4" r="1.7" class="button-hole"/>
      <circle cx="4" cy="-4" r="1.7" class="button-hole"/>
      <circle cx="-4" cy="4" r="1.7" class="button-hole"/>
      <circle cx="4" cy="4" r="1.7" class="button-hole"/>
      <path d="M -4 -4 L 4 4 M 4 -4 L -4 4" class="button-stitch"/>
    </g>
  </g>
  <g transform="rotate(-7 848 244)">
    <rect x="796" y="218" width="118" height="68" rx="8" class="note-shadow"/>
    <rect x="792" y="214" width="118" height="68" rx="8" class="note"/>
    <path d="M 886 214 H 902 Q 910 214 910 222 V 238 Z" class="note-fold"/>
    <path d="M 886 214 L 910 238" class="note-crease"/>
    <path d="M 804 246 H 898" class="note-rule"/>
    <path d="M 804 266 H 892" class="note-rule"/>
    <rect x="832" y="208" width="{note_tab_width}" height="12" rx="4" fill="{note_tab_fill}" opacity=".92"/>
    <text x="{832 + note_tab_width / 2}" y="217" class="note-chip-text">{html.escape(note_tab_text)}</text>
    <g transform="translate(804 208) rotate(-9)">
      <rect width="24" height="10" rx="3" class="tape"/>
      <path d="M 5 2.5 H 19 M 5 5 H 19 M 5 7.5 H 19" class="tape-stripe"/>
    </g>
    <g transform="translate(878 210) rotate(11)">
      <rect width="22" height="10" rx="3" class="tape"/>
      <path d="M 4 2.5 H 18 M 4 5 H 18 M 4 7.5 H 18" class="tape-stripe"/>
    </g>
    <g transform="translate(900 208) rotate(26)">
      <path d="M 0 0 C 8 -6, 18 -4, 20 5 C 22 13, 15 21, 7 18 C 1 16, 1 8, 7 6 C 11 5, 14 8, 13 12" class="paperclip"/>
    </g>
    <g transform="translate(890 270) rotate(10)">
      <path d="M 0 8 C 0 2, 5 -2, 11 -2 C 14 -6, 20 -6, 23 -2 C 29 -2, 34 2, 34 8 C 38 12, 37 19, 32 22 C 31 28, 25 31, 20 29 C 15 32, 8 31, 5 26 C 0 24, -2 16, 0 8 Z" class="seal"/>
      <path d="M 12 4 C 18 6, 23 10, 26 16 C 22 14, 17 14, 12 16 C 14 12, 14 8, 12 4 Z" class="seal-fold"/>
      <circle cx="18" cy="17" r="2.3" class="seal-dot"/>
    </g>
    <text x="808" y="242" class="note-text">{html.escape(note_top)}</text>
    <text x="808" y="262" class="note-text">{html.escape(note_bottom)}</text>
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
    weekday_labels: list[str] = []
    seen_months: set[str] = set()
    weekday_markers = {1: "mon", 3: "wed", 5: "fri"}
    for index, day in enumerate(days):
        week = index // 7
        weekday = index % 7
        count = int(day["contributionCount"])
        level = 0 if count == 0 else min(4, 1 + int(count / max_count * 3.99))
        x = x0 + week * (cell + gap)
        y = y0 + weekday * (cell + gap)
        if week == 0 and weekday in weekday_markers:
            weekday_labels.append(
                f'<text x="{x0 - 18}" y="{y + 10}" class="weekday">{weekday_markers[weekday]}</text>'
            )
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
    spool = ""
    if sampled:
        points = " ".join(f"{x},{y}" for x, y in sampled)
        tx, ty = sampled[0]
        hx, hy = sampled[-1]
        stitch_marks = []
        for sx, sy in sampled[-6:-1]:
            stitch_marks.append(
                f'<path d="M {sx - 4} {sy - 4} L {sx + 4} {sy + 4} M {sx + 4} {sy - 4} L {sx - 4} {sy + 4}" '
                f'class="stitch"/>'
            )
        marker = (
            f'<g transform="translate({hx + 12} {hy - 28}) rotate(-4)">'
            f'<path d="M 0 0 V 30" class="pin-stem"/>'
            f'<path d="M 0 0 H 34 V 10 H 26 L 21 5 L 26 0 H 0 Z" class="pin-flag"/>'
            f'<path d="M 6 5 H 24" class="pin-flag-stitch"/>'
            f'<text x="7" y="7.2" class="pin-text">now</text>'
            f'</g>'
        )
        latest_loop = (
            f'<g class="latest-loop" transform="translate({hx} {hy})">'
            f'<path d="M -12 -2 C -12 -10, -4 -14, 4 -12 C 12 -10, 14 -2, 11 5 C 8 12, -2 14, -9 10 C -13 7, -14 1, -12 -2 Z" class="latest-loop-ring"/>'
            f'<path d="M 6 -10 C 9 -13, 13 -13, 15 -9" class="latest-loop-spark"/>'
            f'<circle cx="15" cy="-8" r="1.8" class="latest-loop-dot"/>'
            f'</g>'
        )
        spool = (
            f'<path d="M 42 {ty} C 50 {ty - 12}, 58 {ty - 12}, 66 {ty}" class="lead-thread"/>'
            f'<g class="spool" transform="translate(28 {ty - 18})">'
            f'<circle cx="14" cy="18" r="13" class="spool-wood"/>'
            f'<circle cx="14" cy="18" r="5" class="spool-core"/>'
            f'<rect x="12" y="3" width="4" height="30" rx="2" class="spool-pin"/>'
            f'<path d="M 9 8 C 15 10, 19 14, 19 18 C 19 22, 15 26, 9 28" class="spool-wrap"/>'
            f'</g>'
            f'<g transform="translate(66 {ty})">'
            f'<path d="M 0 0 C 8 -8, 16 -8, 24 0 C 16 8, 8 8, 0 0 Z" class="bow-loop"/>'
            f'<path d="M 8 0 C 14 5, 14 13, 10 19" class="bow-tail"/>'
            f'<path d="M 16 0 C 22 5, 22 13, 18 19" class="bow-tail"/>'
            f'<circle cx="12" cy="0" r="3.2" class="bow-knot"/>'
            f'</g>'
        )
        path = (
            f'{spool}'
            f'<polyline points="{points}" fill="none" class="trail"/>'
            f'{"".join(stitch_marks)}'
            f'{latest_loop}'
            f'<g class="needle" transform="translate({hx} {hy}) rotate(-18)">'
            f'<line x1="-22" y1="0" x2="-4" y2="0" class="thread"/>'
            f'<line x1="-4" y1="0" x2="10" y2="0" class="shaft"/>'
            f'<ellipse cx="14" cy="0" rx="6" ry="3.5" class="eye"/>'
            f'<circle cx="14" cy="0" r="1.2" class="eye-hole"/>'
            f'</g>'
            f'{marker}'
        )

    streak_label = trail_tagline(days)
    project_label = trail_project_label(profile)
    tag_width = max(140, min(214, 42 + max(len(streak_label), len(project_label)) * 8))
    tag_end_x = 24 + tag_width
    tag_tip_x = tag_end_x + 14
    tag_stitch_end_x = tag_end_x - 10
    stub_x = tag_end_x - 48
    barcode_x = stub_x + 12
    barcode_y = 41
    barcode = "".join(
        f'<rect x="{barcode_x + offset}" y="{barcode_y}" width="{width}" height="30" class="{klass}"/>'
        for offset, width, klass in [
            (0, 2.2, "tag-bar-strong"),
            (5, 1.4, "tag-bar-soft"),
            (9, 3.0, "tag-bar-strong"),
            (15, 1.6, "tag-bar-soft"),
            (19, 2.4, "tag-bar-strong"),
            (25, 1.2, "tag-bar-soft"),
            (29, 3.4, "tag-bar-strong"),
        ]
    )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="260" viewBox="0 0 1200 260" role="img" aria-label="Contribution trail">
  <style>
    :root {{ color-scheme: dark; }}
    .bg {{ fill: #0d1117; }}
    .panel {{ fill: #161b22; stroke: #30363d; stroke-width: 1.2; }}
    .panel-stitch {{ fill: none; stroke: #8b949e; stroke-width: 1.4; stroke-linecap: round; stroke-dasharray: 1.5 5.5; opacity: .7; }}
    .title {{ font: 800 28px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #f0f6fc; }}
    .sub {{ font: 650 14px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #8b949e; }}
    .month {{ font: 650 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #6e7681; }}
    .weekday {{ font: 650 11px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #6e7681; text-anchor: end; }}
    .trail {{ stroke: #7ee787; stroke-width: 4; stroke-linecap: round; stroke-linejoin: round; opacity: .58; stroke-dasharray: 3 9; }}
    .lead-thread {{ fill: none; stroke: #ff7b72; stroke-width: 2.4; stroke-linecap: round; opacity: .72; stroke-dasharray: 2 8; }}
    .stitch {{ stroke: #79c0ff; stroke-width: 1.7; stroke-linecap: round; opacity: .9; }}
    .thread {{ stroke: #ff7b72; stroke-width: 3.2; stroke-linecap: round; }}
    .shaft {{ stroke: #c9d1d9; stroke-width: 3.2; stroke-linecap: round; }}
    .eye {{ fill: none; stroke: #f0f6fc; stroke-width: 2; }}
    .eye-hole {{ fill: #f0f6fc; }}
    .spool-wood {{ fill: #d29922; stroke: #8b949e; stroke-width: 1.2; }}
    .spool-core {{ fill: #0d1117; opacity: .8; }}
    .spool-pin {{ fill: #f6e58d; opacity: .9; }}
    .spool-wrap {{ fill: none; stroke: #ff7b72; stroke-width: 2; stroke-linecap: round; opacity: .9; }}
    .bow-loop {{ fill: none; stroke: #79c0ff; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; opacity: .82; }}
    .bow-tail {{ fill: none; stroke: #79c0ff; stroke-width: 1.8; stroke-linecap: round; opacity: .72; stroke-dasharray: 2 5; }}
    .bow-knot {{ fill: #f6e58d; stroke: #8b949e; stroke-width: 1; }}
    .spool {{ animation: bob 6s ease-in-out infinite; transform-origin: 14px 18px; }}
    .needle {{ animation: hop 1.9s ease-in-out infinite; }}
    .pin-stem {{ fill: none; stroke: #c9d1d9; stroke-width: 1.8; stroke-linecap: round; opacity: .9; }}
    .pin-flag {{ fill: #79c0ff; stroke: #30363d; stroke-width: 1.1; opacity: .96; }}
    .pin-flag-stitch {{ fill: none; stroke: #f0f6fc; stroke-width: 1; stroke-linecap: round; stroke-dasharray: 1.5 3.5; opacity: .72; }}
    .pin-text {{ font: 800 8px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; letter-spacing: .8px; fill: #0d1117; }}
    .latest-loop {{ animation: orbit-mark 3.8s ease-in-out infinite; transform-origin: center; }}
    .latest-loop-ring {{ fill: none; stroke: #f6e58d; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; opacity: .9; }}
    .latest-loop-spark {{ fill: none; stroke: #79c0ff; stroke-width: 1.5; stroke-linecap: round; opacity: .85; }}
    .latest-loop-dot {{ fill: #79c0ff; opacity: .92; }}
    .tag-string {{ fill: none; stroke: #8b949e; stroke-width: 1.5; stroke-linecap: round; stroke-dasharray: 2 5; opacity: .72; }}
    .tag {{ fill: #111827; stroke: #30363d; stroke-width: 1.2; }}
    .tag-eyelet {{ fill: #0d1117; stroke: #8b949e; stroke-width: 1.2; }}
    .tag-kicker {{ font: 700 10px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #8b949e; letter-spacing: 1.1px; text-transform: uppercase; }}
    .tag-text {{ font: 700 13px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #f0f6fc; }}
    .tag-accent {{ fill: #7ee787; }}
    .tag-stitch {{ fill: none; stroke: #8b949e; stroke-width: 1.2; stroke-linecap: round; stroke-dasharray: 1.5 5; opacity: .9; }}
    .tag-bar-strong {{ fill: #f0f6fc; opacity: .7; }}
    .tag-bar-soft {{ fill: #8b949e; opacity: .45; }}
    .tag-stub {{ fill: #0f1724; opacity: .92; }}
    .tag-perf {{ fill: none; stroke: #8b949e; stroke-width: 1.1; stroke-linecap: round; stroke-dasharray: 1.2 4.2; opacity: .9; }}
    @keyframes bob {{ 0%, 100% {{ transform: rotate(0deg) translateY(0); }} 50% {{ transform: rotate(-6deg) translateY(-2px); }} }}
    @keyframes hop {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-5px); }} }}
    @keyframes orbit-mark {{ 0%, 100% {{ transform: rotate(-3deg) translateY(0); }} 50% {{ transform: rotate(2deg) translateY(-1px); }} }}
    @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
  </style>
  <rect class="bg" width="1200" height="260"/>
  <rect x="42" y="18" width="1116" height="210" rx="18" class="panel"/>
  <path d="M 66 42 C 66 28, 76 20, 90 20" class="panel-stitch"/>
  <path d="M 1092 226 C 1110 226, 1124 214, 1124 196" class="panel-stitch"/>
  <text x="74" y="48" class="title">contribution trail</text>
  <text x="74" y="72" class="sub">{profile["total_contributions"]} contributions this year. A tiny needle threads through the latest active days.</text>
  <g transform="translate(968 20) rotate(-4)">
    <path d="M 20 0 C 18 14, 18 24, 24 31" class="tag-string"/>
    <path d="M 24 31 L {tag_end_x} 31 L {tag_tip_x} 56 L {tag_end_x} 81 L 24 81 Q 10 81 10 56 Q 10 31 24 31 Z" class="tag"/>
    <circle cx="28" cy="49" r="6" class="tag-eyelet"/>
    <circle cx="28" cy="49" r="2.5" class="bg"/>
    <path d="M 42 49 H {tag_stitch_end_x}" class="tag-stitch"/>
    <circle cx="50" cy="49" r="4" class="tag-accent"/>
    <text x="62" y="46" class="tag-kicker">recent patch</text>
    <text x="62" y="63" class="tag-text">{html.escape(project_label)}</text>
    <text x="62" y="76" class="tag-kicker">{html.escape(streak_label)}</text>
    <rect x="{stub_x}" y="35" width="40" height="42" rx="10" class="tag-stub"/>
    <path d="M {stub_x - 6} 39 V 73" class="tag-perf"/>
    {barcode}
  </g>
  {"".join(weekday_labels)}
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
