from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import cloudscraper
from bs4 import BeautifulSoup
import urllib.parse
import re

app = FastAPI(title="Multi-Source Arabic Anime API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# إعداد متصفح وهمي قوي جداً
scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ar,en-US;q=0.7,en;q=0.3",
}

# ==========================================
# 1. محرك Anime3rb (الأساسي)
# ==========================================
def search_anime3rb(q):
    try:
        url = f"https://anime3rb.com/search?q={urllib.parse.quote(q)}"
        response = scraper.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/titles/' in href or '/anime/' in href:
                anime_id = href.strip('/').split('/')[-1]
                img = a.find('img')
                title = a.get('title') or (img.get('alt') if img else None)
                if title and len(title) > 1:
                    poster = img.get('src') if img else ""
                    if poster and poster.startswith('/'):
                        poster = "https://anime3rb.com" + poster
                    results.append({
                        "id": anime_id, "title": title, "poster": poster,
                        "source": "anime3rb"
                    })
        return results
    except Exception as e:
        print(f"Error Anime3rb: {e}")
        return []

# ==========================================
# 2. محرك Anime4up (الاحتياطي)
# ==========================================
def search_anime4up(q):
    try:
        url = f"https://anime4up.cam/?s={urllib.parse.quote(q)}"
        response = scraper.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        for div in soup.find_all('div', class_='anime-card-container'):
            a = div.find('a', href=True)
            if a:
                href = a['href']
                anime_id = href.strip('/').split('/')[-1]
                img = div.find('img')
                title = img.get('alt') if img else "Unknown"
                poster = img.get('src') if img else ""
                results.append({
                    "id": anime_id, "title": title, "poster": poster,
                    "source": "anime4up"
                })
        return results
    except Exception as e:
        print(f"Error Anime4up: {e}")
        return []

# ==========================================
# 3. نقاط النهاية (Endpoints)
# ==========================================
@app.get("/")
def read_root():
    return {"status": "ok", "message": "Multi-Source API is running"}

@app.get("/search")
def search_anime(q: str):
    print(f"--- Searching for: {q} ---")
    
    # البحث في أنمي ثري آر بي أولاً
    results = search_anime3rb(q)
    
    # إذا ما لقى نتائج، نبحث في أنمي فور أب
    if not results:
        print("--- Fallback to Anime4up ---")
        results = search_anime4up(q)
        
    return {"results": results}

@app.get("/episodes/{source}/{anime_id}")
def get_episodes(source: str, anime_id: str):
    print(f"--- Fetching episodes for {anime_id} from {source} ---")
    try:
        if source == "anime4up":
            # جلب حلقات أنمي فور أب (طريقة تقريبية)
            url = f"https://anime4up.cam/anime/{anime_id}/"
            response = scraper.get(url, headers=HEADERS, timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')
            episodes = []
            for a in soup.find_all('a', href=True):
                if '/episode/' in a['href'] and anime_id in a['href']:
                    num = re.search(r'(\d+)', a.text)
                    if num:
                        episodes.append({"number": num.group(1), "url": a['href']})
            return {"anime_id": anime_id, "episodes": episodes}
            
        else: # anime3rb
            url = f"https://anime3rb.com/titles/{anime_id}"
            response = scraper.get(url, headers=HEADERS, timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')
            episodes = []
            seen = set()
            for a in soup.find_all('a', href=True):
                if anime_id in a['href'] and a['href'] != f"/titles/{anime_id}":
                    num = re.search(r'(\d+)', a.text)
                    if num and num.group(1) not in seen:
                        seen.add(num.group(1))
                        episodes.append({"number": num.group(1), "url": a['href']})
            episodes.sort(key=lambda x: int(x['number']))
            return {"anime_id": anime_id, "episodes": episodes}
            
    except Exception as e:
        return {"error": str(e), "episodes": []}

@app.get("/watch/{source}/{anime_id}/{ep_num}")
def watch_episode(source: str, anime_id: str, ep_num: str):
    print(f"--- Fetching video: {anime_id} EP {ep_num} from {source} ---")
    try:
        if source == "anime4up":
            url = f"https://anime4up.cam/episode/{anime_id}-الحلقة-{ep_num}/"
        else:
            url = f"https://anime3rb.com/titles/{anime_id}/{ep_num}"

        response = scraper.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # البحث عن iframe
        iframes = soup.find_all('iframe')
        for iframe in iframes:
            if iframe.get('src'):
                return {"video_url": iframe.get('src'), "type": "iframe"}
                
        # البحث عن m3u8
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                m3u8 = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', script.string)
                if m3u8:
                    return {"video_url": m3u8.group(1), "type": "direct"}

        return {"error": "No video source found"}
    except Exception as e:
        return {"error": str(e)}
