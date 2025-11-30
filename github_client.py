from __future__ import annotations

from typing import Optional

import aiohttp

GITHUB_API_URL = "https://api.github.com/repos"
GITHUB_HEADERS = {"Accept": "application/vnd.github.v3.raw"}


async def fetch_readme(
    session: aiohttp.ClientSession, owner: str, repo: str
) -> Optional[str]:
    url = f"{GITHUB_API_URL}/{owner}/{repo}/readme"
    try:
        async with session.get(url, headers=GITHUB_HEADERS) as resp:
            if resp.status == 200:
                return await resp.text()
    except Exception as exc:
        print(f"Error fetching README: {exc}")
    return None
