from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

def scrape_search(query):
    results = []
    try:
        search_url = f"{BASE_URL}/search?q={urllib.parse.quote(query)}"
        response = scraper.get(search_url, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # البحث الشامل عن روابط الأنمي داخل الصفحة
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/titles/' in href:
                img = a.find('img')
                title = a.get('title') or (img.get('alt') if img else None)
                
                if not title:
                    h = a.find(['h2', 'h3', 'h4'])
                    if h: title = h.text.strip()
                
                if title and img and img.get('src'):
                    anime_id = href.strip('/').split('/')[-1]
                    if anime_id and not any(r['id'] == anime_id for r in results):
                        results.append({
                            "id": anime_id,
                            "title": title,
                            "poster": img['src'],
                            "url": href
                        })
    except Exception as e:
        print(f"Error scraping {query}: {e}")
    return results

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Arabic Anime API is running"}

@app.get("/search")
def search_anime(q: str):
    # البحث بالاسم كما هو
    results = scrape_search(q)
    
    # إذا ما لقى نتائج، ونتوقع إنه يبحث بالإنجليزي، ممكن نضيف كلمة anine أو نحاول بحث آخر
    # لكن موقع anime3rb يدعم البحث بالعربي والإنجليزي معاً، فالكود الحالي يكفي.
    
    return {"results": results}

@app.get("/episodes/{anime_id}")
def get_episodes(anime_id: str):
    try:
        anime_url = f"{BASE_URL}/titles/{anime_id}"
        response = scraper.get(anime_url, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        episodes = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            # الحلقات في أنمي ثري ار بي تكون على شكل /titles/{id}/{num}
            if anime_id in href and href != f"/titles/{anime_id}" and href != f"/titles/{anime_id}/":
                text = a.text.strip()
                num = ''.join(filter(str.isdigit, text))
                if not num:
                    num = href.split('/')[-1]
                
                # التأكد من أن الرقم صحيح
                if num.isdigit():
                    if not any(e['number'] == num for e in episodes):
                        episodes.append({"number": num, "url": href})
        
        # ترتيب الحلقات تصاعدياً
        episodes.sort(key=lambda x: int(x['number']))
        
        return {"anime_id": anime_id, "episodes": episodes}
    except Exception as e:
        return {"error": str(e)}

@app.get("/watch/{anime_id}/{ep_num}")
def watch_episode(anime_id: str, ep_num: str):
    try:
        episode_url = f"{BASE_URL}/titles/{anime_id}/{ep_num}"
        response = scraper.get(episode_url, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        iframe = soup.select_one('iframe')
        if iframe and iframe.get('src'):
            return {"video_url": iframe.get('src'), "type": "iframe"}
            
        return {"error": "No video source found"}
    except Exception as e:
        return {"error": str(e)}
