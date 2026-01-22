"""Agent A - Steam 리뷰 수집기"""
import requests
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Generator
from dataclasses import dataclass, asdict

from ..config import Config


@dataclass
class Review:
    game: str
    appid: str
    review_id: str
    language: str
    sentiment: str  # pos | neg
    text: str
    playtime_hours: float
    timestamp: str


class ReviewMiner:
    """Steam 리뷰 수집 Agent"""
    
    BASE_URL = "https://store.steampowered.com/appreviews/{appid}"
    
    def __init__(self, config: Config):
        self.config = config
        self.output_dir = config.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def collect(self, competitors: list[dict]) -> Path:
        """
        경쟁작들의 리뷰 수집
        
        Args:
            competitors: [{"name": "Game Name", "appid": "12345"}, ...]
        
        Returns:
            저장된 파일 경로
        """
        output_path = self.output_dir / self.config.raw_reviews_file
        
        with open(output_path, "w", encoding="utf-8") as f:
            for comp in competitors:
                print(f"📥 수집 중: {comp['name']} ({comp['appid']})")
                
                reviews = self._fetch_reviews(
                    appid=comp["appid"],
                    game_name=comp["name"],
                    limit=self.config.reviews_per_game,
                )
                
                count = 0
                for review in reviews:
                    f.write(json.dumps(asdict(review), ensure_ascii=False) + "\n")
                    count += 1
                
                print(f"   ✓ {count}개 수집 완료")
        
        print(f"\n💾 저장: {output_path}")
        return output_path
    
    def _fetch_reviews(
        self, 
        appid: str, 
        game_name: str, 
        limit: int
    ) -> Generator[Review, None, None]:
        """Steam API로 리뷰 가져오기 (긍정/부정 균형)"""
        
        # 긍정/부정 각각 수집
        pos_limit = int(limit * self.config.sentiment_ratio)
        neg_limit = limit - pos_limit
        
        # 긍정 리뷰
        yield from self._fetch_by_sentiment(appid, game_name, "positive", pos_limit)
        
        # 부정 리뷰
        yield from self._fetch_by_sentiment(appid, game_name, "negative", neg_limit)
    
    def _fetch_by_sentiment(
        self, 
        appid: str, 
        game_name: str, 
        review_type: str,  # positive | negative
        limit: int
    ) -> Generator[Review, None, None]:
        """특정 sentiment의 리뷰만 가져오기"""
        
        cursor = "*"
        collected = 0
        cutoff_date = datetime.now() - timedelta(days=self.config.recent_months * 30)
        
        # 언어 매핑
        lang_map = {
            "korean": "korean",
            "english": "english", 
            "all": "all"
        }
        language = lang_map.get(self.config.language, "all")
        
        while collected < limit:
            params = {
                "json": 1,
                "num_per_page": min(100, limit - collected),
                "cursor": cursor,
                "review_type": review_type,
                "purchase_type": "all",
                "filter": "recent",
            }
            
            if language != "all":
                params["language"] = language
            
            try:
                resp = requests.get(
                    self.BASE_URL.format(appid=appid),
                    params=params,
                    timeout=10
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"   ⚠️ API 오류: {e}")
                break
            
            reviews = data.get("reviews", [])
            if not reviews:
                break
            
            for r in reviews:
                if collected >= limit:
                    break
                
                # 날짜 필터
                ts = r.get("timestamp_created", 0)
                review_date = datetime.fromtimestamp(ts) if ts else None
                if review_date and review_date < cutoff_date:
                    continue
                
                yield Review(
                    game=game_name,
                    appid=appid,
                    review_id=r.get("recommendationid", ""),
                    language=r.get("language", "unknown"),
                    sentiment="pos" if r.get("voted_up") else "neg",
                    text=r.get("review", "")[:2000],  # 최대 2000자
                    playtime_hours=round(r.get("author", {}).get("playtime_forever", 0) / 60, 1),
                    timestamp=datetime.fromtimestamp(ts).isoformat() if ts else "",
                )
                collected += 1
            
            # 다음 페이지
            cursor = data.get("cursor")
            if not cursor:
                break
            
            time.sleep(1)  # Rate limit 준수
        
        return
