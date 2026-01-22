"""Agent B - 리뷰 태깅 (배치 처리)"""
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

from ..config import Config


@dataclass
class TaggedReview:
    game: str
    appid: str
    review_id: str
    language: str
    sentiment: str
    player_type_guess: str  # new | mid | hardcore | unknown
    session_style: list[str]  # short | long | unknown
    pain_points: list[str]
    delights: list[str]
    quotes: list[str]
    notes: str


# 태깅용 프롬프트
TAGGING_SYSTEM_PROMPT = """당신은 게임 리뷰 분석 전문가입니다. 
주어진 리뷰들을 분석하여 JSON 배열로 태깅 결과를 반환하세요.

각 리뷰에 대해 다음을 판단하세요:
- player_type_guess: 플레이타임과 리뷰 내용으로 추정 (new: <10h, mid: 10-100h, hardcore: >100h, unknown)
- session_style: ["short"], ["long"], 또는 ["unknown"]
- pain_points: 해당되는 것만 선택 ["aiming","controls","matchmaking","pacing","progression","monetization","performance","netcode","uiux","toxicity","content","other"]
- delights: 해당되는 것만 선택 ["gunfeel","movement","fairness","clarity","depth","social","collection","other"]
- quotes: 핵심 문장 1개 (없으면 빈 배열)
- notes: 1줄 요약

반드시 JSON 배열만 반환하세요. 설명 없이 순수 JSON만."""

TAGGING_USER_TEMPLATE = """아래 {count}개 리뷰를 태깅해주세요:

{reviews}

JSON 배열로 반환 (review_id, player_type_guess, session_style, pain_points, delights, quotes, notes 포함):"""


class ReviewTagger:
    """리뷰 태깅 Agent (배치 처리)"""
    
    PAIN_POINTS = [
        "aiming", "controls", "matchmaking", "pacing", "progression",
        "monetization", "performance", "netcode", "uiux", "toxicity", 
        "content", "other"
    ]
    
    DELIGHTS = [
        "gunfeel", "movement", "fairness", "clarity", "depth",
        "social", "collection", "other"
    ]
    
    def __init__(self, config: Config, llm_client=None):
        self.config = config
        self.llm_client = llm_client  # 외부에서 주입
        self.batch_size = config.batch_size
    
    def tag_reviews(self, raw_reviews_path: Path) -> Path:
        """
        리뷰 파일을 읽어 태깅 후 저장
        
        Returns:
            태깅된 파일 경로
        """
        output_path = self.config.output_dir / self.config.tagged_reviews_file
        
        # 원본 리뷰 로드
        reviews = []
        with open(raw_reviews_path, "r", encoding="utf-8") as f:
            for line in f:
                reviews.append(json.loads(line))
        
        print(f"🏷️ 태깅 시작: {len(reviews)}개 리뷰")
        
        # 배치 처리
        tagged = []
        for i in range(0, len(reviews), self.batch_size):
            batch = reviews[i:i + self.batch_size]
            print(f"   배치 {i // self.batch_size + 1}: {len(batch)}개 처리 중...")
            
            batch_tagged = self._tag_batch(batch)
            tagged.extend(batch_tagged)
        
        # 저장
        with open(output_path, "w", encoding="utf-8") as f:
            for t in tagged:
                f.write(json.dumps(asdict(t), ensure_ascii=False) + "\n")
        
        print(f"💾 저장: {output_path}")
        return output_path
    
    def _tag_batch(self, batch: list[dict]) -> list[TaggedReview]:
        """배치 태깅 (LLM 호출)"""
        
        # 프롬프트 생성
        reviews_text = "\n---\n".join([
            f"[ID: {r['review_id']}] (playtime: {r.get('playtime_hours', 0)}h, sentiment: {r['sentiment']})\n{r['text'][:500]}"
            for r in batch
        ])
        
        user_prompt = TAGGING_USER_TEMPLATE.format(
            count=len(batch),
            reviews=reviews_text
        )
        
        # LLM 호출
        if self.llm_client:
            response = self._call_llm(user_prompt)
            parsed = self._parse_response(response, batch)
        else:
            # LLM 없으면 기본 태깅
            parsed = self._fallback_tagging(batch)
        
        return parsed
    
    def _call_llm(self, user_prompt: str) -> str:
        """LLM API 호출 (추상화)"""
        # Cursor 내에서 실행 시 이 부분은 직접 호출됨
        # 외부 실행 시 llm_client 사용
        if hasattr(self.llm_client, "chat"):
            resp = self.llm_client.chat(
                model=self.config.tagging_model,
                messages=[
                    {"role": "system", "content": TAGGING_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ]
            )
            return resp.get("content", "[]")
        return "[]"
    
    def _parse_response(self, response: str, batch: list[dict]) -> list[TaggedReview]:
        """LLM 응답 파싱"""
        try:
            # JSON 추출
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
            else:
                return self._fallback_tagging(batch)
            
            # 원본과 매칭
            result = []
            review_map = {r["review_id"]: r for r in batch}
            
            for item in data:
                rid = item.get("review_id", "")
                if rid not in review_map:
                    continue
                
                orig = review_map[rid]
                result.append(TaggedReview(
                    game=orig["game"],
                    appid=orig["appid"],
                    review_id=rid,
                    language=orig["language"],
                    sentiment=orig["sentiment"],
                    player_type_guess=item.get("player_type_guess", "unknown"),
                    session_style=item.get("session_style", ["unknown"]),
                    pain_points=item.get("pain_points", []),
                    delights=item.get("delights", []),
                    quotes=item.get("quotes", []),
                    notes=item.get("notes", ""),
                ))
            
            return result
            
        except json.JSONDecodeError:
            return self._fallback_tagging(batch)
    
    def _fallback_tagging(self, batch: list[dict]) -> list[TaggedReview]:
        """LLM 실패 시 규칙 기반 태깅"""
        result = []
        
        for r in batch:
            text = r.get("text", "").lower()
            playtime = r.get("playtime_hours", 0)
            
            # 플레이어 타입 추정
            if playtime < 10:
                player_type = "new"
            elif playtime < 100:
                player_type = "mid"
            elif playtime > 100:
                player_type = "hardcore"
            else:
                player_type = "unknown"
            
            # 키워드 기반 태깅
            pain_points = []
            delights = []
            
            pain_keywords = {
                "lag": "performance", "버그": "performance", "렉": "performance",
                "매칭": "matchmaking", "matchmaking": "matchmaking",
                "조작": "controls", "control": "controls",
                "과금": "monetization", "pay": "monetization", "p2w": "monetization",
                "밸런스": "pacing", "balance": "pacing",
            }
            
            delight_keywords = {
                "타격감": "gunfeel", "gunplay": "gunfeel", "shooting": "gunfeel",
                "이동": "movement", "movement": "movement",
                "공정": "fairness", "fair": "fairness",
                "깊이": "depth", "depth": "depth",
            }
            
            for kw, tag in pain_keywords.items():
                if kw in text and tag not in pain_points:
                    pain_points.append(tag)
            
            for kw, tag in delight_keywords.items():
                if kw in text and tag not in delights:
                    delights.append(tag)
            
            result.append(TaggedReview(
                game=r["game"],
                appid=r["appid"],
                review_id=r["review_id"],
                language=r["language"],
                sentiment=r["sentiment"],
                player_type_guess=player_type,
                session_style=["unknown"],
                pain_points=pain_points or ["other"],
                delights=delights or ["other"],
                quotes=[],
                notes="(auto-tagged)",
            ))
        
        return result


def get_tagging_prompt() -> tuple[str, str]:
    """프롬프트 반환 (Cursor에서 직접 사용 시)"""
    return TAGGING_SYSTEM_PROMPT, TAGGING_USER_TEMPLATE
