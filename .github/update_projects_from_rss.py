import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import List, Dict


RSS_URL = "https://www.sahilfruitwala.com/rss.xml"
README_PATH = "README.md"
START_MARKER = "<!-- PROJECTS:START -->"
END_MARKER = "<!-- PROJECTS:END -->"
MAX_ITEMS = 6
MIN_AWARE_DATE = datetime.min.replace(tzinfo=timezone.utc)


def fetch_rss(url: str) -> bytes:
    with urllib.request.urlopen(url) as response:
        return response.read()


def extract_projects(xml_bytes: bytes) -> List[Dict]:
    root = ET.fromstring(xml_bytes)

    # RSS structure: <rss><channel><item>...</item></channel></rss>
    channel = root.find("channel")
    if channel is None:
        return []

    projects = []

    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()

        # Only keep items explicitly marked as projects
        if not title.lower().startswith("project:"):
            continue

        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        pub_raw = (item.findtext("pubDate") or "").strip()

        # Parse date if possible so we can sort by recency
        dt = None
        if pub_raw:
            try:
                dt = parsedate_to_datetime(pub_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                dt = None

        # Clean up title for display (drop the leading "Project:" case-insensitively)
        if title.lower().startswith("project:"):
            display_title = title.split(":", 1)[1].strip()
        else:
            display_title = title

        # Collapse any internal newlines/extra whitespace in description
        description = " ".join(description.split())

        projects.append(
            {
                "title": display_title,
                "link": link,
                "description": description,
                "date": dt or MIN_AWARE_DATE,
            }
        )

    # Newest first
    projects.sort(key=lambda p: p["date"], reverse=True)
    return projects[:MAX_ITEMS]


def render_projects_markdown(projects: List[Dict]) -> str:
    lines = []
    for p in projects:
        title = p["title"]
        link = p["link"]
        description = p["description"]

        # Basic bullet: - [Title](link) — description
        if description:
            lines.append(f"- [{title}]({link}) — {description}")
        else:
            lines.append(f"- [{title}]({link})")

    # Fallback if for some reason we didn't find any projects
    if not lines:
        lines.append("- No recent projects found right now. Please check back soon.")

    return "\n".join(lines)


def replace_section(content: str, start_marker: str, end_marker: str, new_block: str) -> str:
    start_index = content.find(start_marker)
    end_index = content.find(end_marker)

    if start_index == -1 or end_index == -1:
        # Markers not found; return unchanged content
        return content

    before = content[: start_index + len(start_marker)]
    after = content[end_index:]

    # Ensure there is exactly one blank line between marker and content
    return f"{before}\n{new_block}\n{after}"


def main() -> None:
    rss_bytes = fetch_rss(RSS_URL)
    projects = extract_projects(rss_bytes)

    projects_md = render_projects_markdown(projects)

    with open(README_PATH, "r", encoding="utf-8") as f:
        readme = f.read()

    updated = replace_section(readme, START_MARKER, END_MARKER, "\n" + projects_md + "\n")

    if updated != readme:
        with open(README_PATH, "w", encoding="utf-8") as f:
            f.write(updated)


if __name__ == "__main__":
    main()

