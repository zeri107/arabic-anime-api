from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import cloudscraper
from bs4 import BeautifulSoup
import urllib.parse

app = FastAPI(title="Arabic Anime API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_URL = "https://anime3rb.com"
scraper = cloudscraper.create_scraper()

class SearchResponse(BaseModel):
    id: str
    title: str
    poster: str
    url: str

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Arabic Anime API is running"}

@app.get("/search")
def search_anime(q: str):
    try:
        search_url = f"{BASE_URL}/search?q={urllib.parse.quote(q)}"
        response = scraper.get(search_url, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        for card in soup.select('.anime-card, .card'):
            title_elem = card.select_one('h3, .title, a')
            link_elem = card.select_one('a')
            img_elem = card.select_one('img')
            
            if title_elem and link_elem:
                title = title_elem.text.strip()
                link = link_elem.get('href', '')
                anime_id = link.split('/')[-1] if '/' in link else link
                poster = img_elem.get('src') if img_elem else ""
                
                if anime_id:
                    results.append(SearchResponse(
                        id=anime_id,
                        title=title,
                        poster=poster,
                        url=link
                    ))
        
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/episodes/{anime_id}")
def get_episodes(anime_id: str):
    try:
        anime_url = f"{BASE_URL}/titles/{anime_id}"
        response = scraper.get(anime_url, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        episodes = []
        for ep_elem in soup.select('.episode-card, .episode-item, li a[href*="episode"]'):
            ep_text = ep_elem.text.strip()
            ep_link = ep_elem.get('href', '')
            if ep_text and ep_link:
                episodes.append({
                    "number": ep_text,
                    "url": f"{BASE_URL}{ep_link}" if ep_link.startswith('/') else ep_link
                })
        
        return {"anime_id": anime_id, "episodes": episodes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/watch/{anime_id}/{ep_num}")
def watch_episode(anime_id: str, ep_num: str):
    try:
        episode_url = f"{BASE_URL}/titles/{anime_id}/{ep_num}"
        response = scraper.get(episode_url, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        iframe = soup.select_one('iframe')
        if iframe and iframe.get('src'):
            return {"video_url": iframe.get('src'), "type": "iframe"}
        
        video_tag = soup.select_one('video source')
        if video_tag and video_tag.get('src'):
            return {"video_url": video_tag.get('src'), "type": "direct"}
            
        raise HTTPException(status_code=404, detail="Video source not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
