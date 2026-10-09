#!/usr/bin/env python3
"""Update only the AUTO-* regions of a GitHub profile README.

Public repositories only. No third-party dependencies, no personal token needed
in GitHub Actions. Frameworks are inferred only from curated repository topics.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

USERNAME = os.environ.get("PROFILE_USERNAME", "Piyumal78")
README = Path(os.environ.get("PROFILE_README", "README.md"))
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
MAX_REPOS = 100  # public, non-fork repos scanned; older repos beyond this excluded
FEATURED_COUNT = 8
# Exact repo names, case-insensitive; missing entries are silently ignored.
PINNED = ["ELMS", "Intelligent-air-system-demo"]
EXCLUDED = {USERNAME.casefold()}

TOPIC_TECH = {
    "react": "React", "reactjs": "React", "nextjs": "Next.js",
    "next-js": "Next.js", "nodejs": "Node.js", "node-js": "Node.js",
    "express": "Express.js", "expressjs": "Express.js",
    "spring-boot": "Spring Boot", "springboot": "Spring Boot",
    "flask": "Flask", "fastapi": "FastAPI", "django": "Django",
    "nestjs": "NestJS", "tailwindcss": "Tailwind CSS",
    "typescript": "TypeScript", "javascript": "JavaScript",
    "python": "Python", "java": "Java", "cpp": "C++", "csharp": "C#",
    "firebase": "Firebase", "firestore": "Firestore",
    "postgresql": "PostgreSQL", "postgres": "PostgreSQL",
    "mysql": "MySQL", "mongodb": "MongoDB", "redis": "Redis",
    "docker": "Docker", "kubernetes": "Kubernetes", "azure": "Azure",
    "aws": "AWS", "prisma": "Prisma", "keycloak": "Keycloak",
    "mqtt": "MQTT", "iot": "IoT", "esp32": "ESP32",
    "arduino": "Arduino", "react-native": "React Native",
    "flutter": "Flutter", "qdrant": "Qdrant", "waha": "WAHA",
    "github-actions": "GitHub Actions", "socketio": "Socket.IO",
    "rest-api": "REST API", "graphql": "GraphQL",
}


def api(path: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "profile-readme-updater",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    request = Request("https://api.github.com" + path, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"GitHub API HTTP {exc.code} for {path}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not reach GitHub API for {path}: {exc}") from exc


def repositories():
    result = []
    for page in range(1, (MAX_REPOS + 99) // 100 + 1):
        batch = api(
            f"/users/{quote(USERNAME, safe='')}/repos"
            f"?type=owner&sort=pushed&direction=desc&per_page=100&page={page}"
        )
        if not isinstance(batch, list):
            raise RuntimeError("Unexpected response from GitHub repository API")
        result.extend(batch)
        if len(batch) < 100:
            break
    return [
        repo for repo in result[:MAX_REPOS]
        if not repo.get("fork")
        and not repo.get("archived")
        and not repo.get("disabled")
        and repo.get("name", "").casefold() not in EXCLUDED
    ]


def md(value):
    """Avoid breaking README tables with untrusted repo descriptions."""
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return html.escape(text, quote=True).replace("|", "&#124;")


def tech_from(repo, languages):
    technologies = []
    # GitHub language payload keys are sorted by number of bytes in the API.
    if not isinstance(languages, dict):
        raise RuntimeError(f"Bad language response for {repo['name']}")
    for lang in languages:
        if lang not in technologies:
            technologies.append(lang)
    for topic in repo.get("topics") or []:
        mapped = TOPIC_TECH.get(topic.lower())
        if mapped and mapped not in technologies:
            technologies.append(mapped)
    return technologies


def sort_repos(repos):
    by_name = {r["name"].casefold(): r for r in repos}
    ordered = [by_name[name.casefold()] for name in PINNED if name.casefold() in by_name]
    included = {r["name"].casefold() for r in ordered}
    ordered.extend(sorted(
        (r for r in repos if r["name"].casefold() not in included),
        key=lambda r: r.get("pushed_at") or "", reverse=True,
    ))
    return ordered


def project_text(repos, per_repo):
    if not repos:
        return "No public, non-fork projects found yet."
    lines = ["| Project | Description | Technologies |", "| --- | --- | --- |"]
    for r in sort_repos(repos)[:FEATURED_COUNT]:
        name = md(r["name"])
        description = md(r.get("description") or "Explore the repository")
        tech = md(", ".join(per_repo[r["name"]][:6]) or "See repository")
        # URL is generated rather than trusting arbitrary values returned in repos.
        url = f"https://github.com/{quote(USERNAME, safe='')}/{quote(r['name'], safe='')}"
        lines.append(f"| [{name}]({url}) | {description} | {tech} |")
    lines.append("")
    lines.append(f"[View all public repositories](https://github.com/{quote(USERNAME, safe='')}?tab=repositories)")
    return "\n".join(lines)


def skills_text(per_repo):
    counts = Counter(tech for technologies in per_repo.values() for tech in set(technologies))
    if not counts:
        return "No repository languages or mapped topics detected yet."
    result = []
    for tech, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].lower())):
        # Shields endpoint label uses percent encoding; hyphens escaped as double hyphens.
        encoded = quote(tech.replace("-", "--"), safe="")
        result.append(f"![{md(tech)}](https://img.shields.io/badge/{encoded}-252B3A?style=for-the-badge)")
    return "\n".join(result)


def activity_text(repos, per_repo):
    counts = Counter(t for technologies in per_repo.values() for t in set(technologies))
    stars = sum(int(r.get("stargazers_count") or 0) for r in repos)
    forks = sum(int(r.get("forks_count") or 0) for r in repos)
    top = md(", ".join(t for t, _ in counts.most_common(5)) or "None detected")
    return "\n".join([
        "| Metric | Public repository snapshot |",
        "| --- | ---: |",
        f"| Active non-fork repositories scanned | {len(repos)} |",
        f"| Stars across scanned repositories | {stars} |",
        f"| Forks across scanned repositories | {forks} |",
        f"| Distinct detected technologies | {len(counts)} |",
        f"| Frequently used technologies | {top} |",
    ])


def insert(content, key, text):
    start = f"<!-- AUTO-{key}:START -->"
    end = f"<!-- AUTO-{key}:END -->"
    regex = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if len(regex.findall(content)) != 1:
        raise ValueError(f"Expected exactly one pair of {key} markers in README")
    return regex.sub(lambda _: f"{start}\n{text}\n{end}", content, count=1)


def main():
    if not README.is_file():
        raise FileNotFoundError(f"Missing README: {README}")
    original = README.read_text(encoding="utf-8")
    # Validate all markers BEFORE querying the API or writing any changes.
    for key in ("PROJECTS", "SKILLS", "ACTIVITY"):
        insert(original, key, "validation")

    repos = repositories()
    print(f"Scanning {len(repos)} eligible public repositories")
    per_repo = {}
    for r in repos:
        path = f"/repos/{quote(USERNAME, safe='')}/{quote(r['name'], safe='')}/languages"
        per_repo[r["name"]] = tech_from(r, api(path))

    updated = insert(original, "PROJECTS", project_text(repos, per_repo))
    updated = insert(updated, "SKILLS", skills_text(per_repo))
    updated = insert(updated, "ACTIVITY", activity_text(repos, per_repo))
    if updated == original:
        print("No README changes")
    else:
        README.write_text(updated, encoding="utf-8")
        print("Updated README.md")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Profile update failed: {exc}", file=sys.stderr)
        sys.exit(1)
