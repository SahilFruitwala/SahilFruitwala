#!/usr/bin/env python3
"""Refresh the profile README projects and blog lists from sahilfruitwala.com RSS.

Also pins a few live GitHub products that are not in the site feed yet, and
skips project links that currently 404.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


RSS_URL = "https://sahilfruitwala.com/rss.xml"
README_PATH = "README.md"
PROJECTS_START = "<!-- PROJECTS:START -->"
PROJECTS_END = "<!-- PROJECTS:END -->"
BLOG_START = "<!-- BLOGPOSTS:START -->"
BLOG_END = "<!-- BLOGPOSTS:END -->"
MAX_PROJECTS = 10
MAX_POSTS = 5
MIN_AWARE_DATE = datetime.min.replace(tzinfo=timezone.utc)
USER_AGENT = "SahilFruitwala-readme-bot/1.0 (+https://github.com/SahilFruitwala/SahilFruitwala)"

# Public GitHub products that are shipping but not in the site RSS yet.
FEATURED_EXTRAS: List[Dict] = [
    {
        "title": "Filemite",
        "link": "https://filemite.com",
        "description": "Tiny tools for images and PDFs — compress, convert, crop, merge, sign, and redact. Nothing is stored.",
        "date": datetime(2026, 10, 23, tzinfo=timezone.utc),
    },
    {
        "title": "SimpleRecord",
        "link": "https://sahilfruitwala.github.io/simple-record/",
        "description": "A fast screen and camera recorder for Mac. Scenes, replay buffer, and live streaming — no OBS, no Electron.",
        "date": datetime(2026, 10, 21, tzinfo=timezone.utc),
    },
    {
        "title": "OpenLink",
        "link": "https://links.sahilfruitwala.com",
        "description": "A minimal link-in-bio page: profile, projects, newsletter, and the rest of the internet in one spot.",
        "date": datetime(2026, 10, 23, tzinfo=timezone.utc),
    },
]

# Site RSS still points at GitHub repos that are private or renamed.
SKIP_GITHUB_REPOS = {"image-behind", "chorie"}


def fetch_rss(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def parse_date(raw: str) -> datetime:
    if not raw:
        return MIN_AWARE_DATE
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return MIN_AWARE_DATE
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def clean_text(value: str) -> str:
    return " ".join((value or "").split())


def clean_link(url: str) -> str:
    url = (url or "").strip()
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]
    cleaned = parsed._replace(path=path, query=urlencode(query), fragment="")
    return urlunparse(cleaned)


def github_repo_name(url: str) -> Optional[str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host not in {"github.com", "www.github.com"}:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    return parts[1].removesuffix(".git").lower()


def is_project_item(title: str) -> bool:
    return title.lower().startswith("project:")


def display_title(title: str) -> str:
    if is_project_item(title):
        return title.split(":", 1)[1].strip()
    return title


def iter_items(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    if channel is None:
        return
    for item in channel.findall("item"):
        title = clean_text(item.findtext("title") or "")
        if not title:
            continue
        yield {
            "title": title,
            "link": clean_link(item.findtext("link") or ""),
            "description": clean_text(item.findtext("description") or ""),
            "date": parse_date(item.findtext("pubDate") or ""),
        }


def extract_projects(xml_bytes: bytes) -> List[Dict]:
    projects: List[Dict] = []
    seen_titles = set()

    for extra in FEATURED_EXTRAS:
        title_key = extra["title"].casefold()
        seen_titles.add(title_key)
        projects.append(
            {
                "title": extra["title"],
                "link": clean_link(extra["link"]),
                "description": extra["description"],
                "date": extra["date"],
            }
        )

    rss_projects = []
    for item in iter_items(xml_bytes):
        if not is_project_item(item["title"]):
            continue
        title = display_title(item["title"])
        repo = github_repo_name(item["link"])
        if repo in SKIP_GITHUB_REPOS:
            continue
        if title.casefold() in seen_titles:
            continue
        rss_projects.append(
            {
                "title": title,
                "link": item["link"],
                "description": item["description"],
                "date": item["date"],
            }
        )

    rss_projects.sort(key=lambda item: item["date"], reverse=True)
    for item in rss_projects:
        seen_titles.add(item["title"].casefold())
        projects.append(item)
        if len(projects) >= MAX_PROJECTS:
            break

    return projects[:MAX_PROJECTS]


def extract_posts(xml_bytes: bytes) -> List[Dict]:
    posts = []
    for item in iter_items(xml_bytes):
        if is_project_item(item["title"]):
            continue
        if not item["link"]:
            continue
        posts.append(
            {
                "title": display_title(item["title"]),
                "link": item["link"],
                "description": item["description"],
                "date": item["date"],
            }
        )
    posts.sort(key=lambda item: item["date"], reverse=True)
    return posts[:MAX_POSTS]


def render_projects(projects: List[Dict]) -> str:
    if not projects:
        return "- No recent projects found right now. Please check back soon."
    lines = []
    for project in projects:
        if project["description"]:
            lines.append(f"- [{project['title']}]({project['link']}) — {project['description']}")
        else:
            lines.append(f"- [{project['title']}]({project['link']})")
    return "\n".join(lines)


def format_post_date(dt: datetime) -> str:
    if dt == MIN_AWARE_DATE:
        return ""
    return f"{dt.strftime('%b')} {dt.day}, {dt.year}"


def render_posts(posts: List[Dict]) -> str:
    if not posts:
        return "- No recent posts found right now. Please check back soon."
    lines = []
    for post in posts:
        date = format_post_date(post["date"])
        if date:
            lines.append(f"- {date} — [{post['title']}]({post['link']})")
        else:
            lines.append(f"- [{post['title']}]({post['link']})")
    return "\n".join(lines)


def replace_section(content: str, start_marker: str, end_marker: str, new_block: str) -> str:
    start_index = content.find(start_marker)
    end_index = content.find(end_marker)
    if start_index == -1 or end_index == -1:
        raise ValueError(f"Missing markers {start_marker} / {end_marker} in README.md")
    before = content[: start_index + len(start_marker)]
    after = content[end_index:]
    return f"{before}\n\n{new_block}\n\n{after}"


def update_readme(readme: str, xml_bytes: bytes) -> str:
    updated = replace_section(readme, PROJECTS_START, PROJECTS_END, render_projects(extract_projects(xml_bytes)))
    return replace_section(updated, BLOG_START, BLOG_END, render_posts(extract_posts(xml_bytes)))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rss-file", help="Use a local RSS snapshot instead of fetching")
    parser.add_argument("--readme", default=README_PATH)
    args = parser.parse_args(argv)

    try:
        xml_bytes = open(args.rss_file, "rb").read() if args.rss_file else fetch_rss(RSS_URL)
        with open(args.readme, "r", encoding="utf-8") as handle:
            readme = handle.read()
        updated = update_readme(readme, xml_bytes)
    except (OSError, urllib.error.URLError, ET.ParseError, ValueError) as exc:
        print(f"Failed to update README: {exc}", file=sys.stderr)
        return 1

    if updated != readme:
        with open(args.readme, "w", encoding="utf-8") as handle:
            handle.write(updated)
        print("README updated")
    else:
        print("README already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
