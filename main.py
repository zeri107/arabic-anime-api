from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import cloudscraper
from bs4 import BeautifulSoup
import urllib.parse
import requests
import re
import json
from pathlib import Path

app = FastAPI(title="Multi-Source Arabic Anime API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept-Language": "ar,en-US;q=0.7,en;q=0.3",
}

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "desktop": True}
)

VIDEOS_FILE = Path(__file__).with_name("videos.json")


def load_videos():
    """تحميل روابط الفيديو اليدوية، مع إرجاع كائن فارغ إذا لم يوجد الملف."""
    try:
        if not VIDEOS_FILE.exists():
            return {}
        return json.loads(VIDEOS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print("videos.json error:", exc)
        return {}


def valid_url(url):
    return isinstance(url, str) and (url.startswith("https://") or url.startswith("http://"))


def episode_config(anime_id, episode_number):
    item = load_videos().get(str(anime_id), {}).get(str(episode_number))
    if not isinstance(item, dict):
        return None
    # دعم الصيغة القديمة ذات url واحد، لتبقى الملفات السابقة صالحة.
    if item.get("url"):
        item = {**item, "servers": [{
            "name": item.get("name", "السيرفر الأساسي"),
            "url": item.get("url"),
            "type": item.get("type", "mp4"),
            "quality": item.get("quality", "غير محدد"),
            "download": bool(item.get("download", False)),
        }]}
    servers = []
    for server in item.get("servers", []):
        if not isinstance(server, dict) or not valid_url(server.get("url")):
            continue
        video_type = str(server.get("type", "mp4")).lower()
        if video_type not in {"mp4", "iframe"}:
            continue
        servers.append({
            "name": server.get("name", "سيرفر"),
            "url": server["url"],
            "type": video_type,
            "quality": server.get("quality", "غير محدد"),
            "download": bool(server.get("download", False)),
        })
    subtitles = [
        {"label": s.get("label", "العربية"), "url": s.get("url"),
         "srclang": s.get("srclang", "ar"), "default": bool(s.get("default", False))}
        for s in item.get("subtitles", [])
        if isinstance(s, dict) and valid_url(s.get("url"))
    ]
    return {"title": item.get("title", ""), "servers": servers, "subtitles": subtitles}


def manual_video(anime_id, episode_number, server_name=None, quality=None):
    config = episode_config(anime_id, episode_number)
    if not config:
        return None
    servers = config["servers"]
    if server_name:
        servers = [s for s in servers if s["name"] == server_name]
    if quality:
        matching = [s for s in servers if s["quality"] == quality]
        if matching:
            servers = matching
    if not servers:
        return None
    selected = servers[0]
    return {"video_url": selected["url"], "type": selected["type"],
            "quality": selected["quality"], "server": selected["name"],
            "download": selected["download"], "subtitles": config["subtitles"],
            "servers": config["servers"]}


def search_anime3rb(q):
    try:
        url = f"https://anime3rb.com/search?q={urllib.parse.quote(q)}"
        response = scraper.get(url, headers=HEADERS, timeout=30)
        if response.status_code != 200 or "Just a moment" in response.text:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        results, seen = [], set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/titles/" not in href and "/anime/" not in href:
                continue
            anime_id = href.strip("/").split("/")[-1]
            img = a.find("img")
            title = a.get("title") or (img.get("alt") if img else None) or a.get_text(" ", strip=True)
            if anime_id and title and anime_id not in seen:
                seen.add(anime_id)
                poster = (img.get("src") or img.get("data-src") or "") if img else ""
                if poster.startswith("/"):
                    poster = "https://anime3rb.com" + poster
                results.append({"id": anime_id, "title": title.strip(), "poster": poster, "source": "anime3rb"})
        return results
    except Exception as exc:
        print("Anime3rb search error:", exc)
        return []


def search_anime4up(q):
    try:
        url = f"https://anime4up.cam/?s={urllib.parse.quote(q)}"
        response = scraper.get(url, headers=HEADERS, timeout=30)
        if response.status_code != 200:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        results, seen = [], set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/anime/" not in href and "/episode/" in href:
                continue
            img = a.find("img")
            title = (img.get("alt") if img else None) or a.get_text(" ", strip=True)
            if not title or len(title) < 2:
                continue
            anime_id = href.rstrip("/").split("/")[-1]
            if anime_id in seen or anime_id in ("", "#"):
                continue
            seen.add(anime_id)
            poster = (img.get("src") or img.get("data-src") or "") if img else ""
            results.append({"id": anime_id, "title": title.strip(), "poster": poster, "source": "anime4up"})
        return results
    except Exception as exc:
        print("Anime4up search error:", exc)
        return []


def search_anilist(q):
    """مصدر احتياطي للبحث باستخدام AniList GraphQL."""
    try:
        query = """
        query ($search: String) {
          Page(perPage: 12) {
            media(search: $search, type: ANIME) {
              id
              title { romaji english native }
              coverImage { large }
            }
          }
        }
        """
        response = requests.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": {"search": q}},
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        items = response.json().get("data", {}).get("Page", {}).get("media", [])
        return [
            {
                "id": str(item["id"]),
                "title": (item.get("title", {}).get("english")
                          or item.get("title", {}).get("romaji")
                          or item.get("title", {}).get("native")
                          or "بدون عنوان"),
                "poster": (item.get("coverImage") or {}).get("large", ""),
                "source": "anilist",
            }
            for item in items
        ]
    except Exception as exc:
        print("AniList search error:", exc)
        return []


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Multi-Source API is running"}


@app.get("/search")
def search_anime(q: str):
    q = q.strip()
    if not q:
        return {"results": [], "error": "اكتب اسم الأنمي"}
    results = search_anime3rb(q)
    if not results:
        results = search_anime4up(q)
    if not results:
        results = search_anilist(q)
    return {"results": results}


@app.get("/episodes/{source}/{anime_id}")
def get_episodes(source: str, anime_id: str):
    try:
        if source == "anilist":
            query = """
            query ($id: Int) {
              Media(id: $id, type: ANIME) { episodes }
            }
            """
            response = requests.post(
                "https://graphql.anilist.co",
                json={"query": query, "variables": {"id": int(anime_id)}},
                headers={**HEADERS, "Content-Type": "application/json"},
                timeout=30,
            )
            response.raise_for_status()
            total = (response.json().get("data", {}).get("Media") or {}).get("episodes") or 0
            episodes = []
            for number in range(1, int(total) + 1):
                episode = {"number": str(number), "url": ""}
                config = episode_config(anime_id, number)
                if config and config["servers"]:
                    episode.update({
                        "available": True,
                        "server_count": len(config["servers"]),
                        "subtitle_count": len(config["subtitles"]),
                    })
                episodes.append(episode)
            return {
                "anime_id": anime_id,
                "episodes": episodes,
                "notice": "تُشغّل الحلقات التي لها روابط قانونية في videos.json فقط."
            }

        if source == "anime4up":
            url = f"https://anime4up.cam/anime/{anime_id}/"
        else:
            url = f"https://anime3rb.com/titles/{anime_id}"
        response = scraper.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(response.text, "html.parser")
        episodes, seen = [], set()
        for a in soup.find_all("a", href=True):
            text = a.get_text(" ", strip=True)
            match = re.search(r"(?:الحلقة|episode|ep)?\s*(\d+)", text, re.I)
            if match:
                number = match.group(1)
                href = a["href"]
                if number not in seen and (anime_id in href or "/episode/" in href):
                    seen.add(number)
                    episodes.append({"number": number, "url": href})
        episodes.sort(key=lambda item: int(item["number"]))
        return {"anime_id": anime_id, "episodes": episodes}
    except Exception as exc:
        return {"anime_id": anime_id, "episodes": [], "error": str(exc)}


@app.get("/watch/{source}/{anime_id}/{ep_num}")
def watch_episode(source: str, anime_id: str, ep_num: str, server: str | None = None, quality: str | None = None):
    if source == "anilist":
        video = manual_video(anime_id, ep_num, server, quality)
        return video or {"error": "لا يوجد رابط فيديو قانوني لهذه الحلقة في videos.json."}
    try:
        if source == "anime4up":
            url = f"https://anime4up.cam/episode/{anime_id}-الحلقة-{ep_num}/"
        else:
            url = f"https://anime3rb.com/titles/{anime_id}/{ep_num}"
        response = scraper.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(response.text, "html.parser")
        for iframe in soup.find_all("iframe"):
            if iframe.get("src"):
                return {"video_url": iframe["src"], "type": "iframe"}
        for script in soup.find_all("script"):
            text = script.string or script.get_text()
            match = re.search(r"(https?://[^\s\"']+\.m3u8[^\s\"']*)", text)
            if match:
                return {"video_url": match.group(1), "type": "direct"}
        return {"error": "No video source found"}
    except Exception as exc:
        return {"error": str(exc)}
