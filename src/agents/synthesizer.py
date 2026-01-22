"""Agent C+D - 리서치 기반 페르소나 합성 + 아이디어 검증"""
import json
from pathlib import Path
from dataclasses import dataclass, asdict, field
from collections import defaultdict
from typing import Optional

from ..config import Config


@dataclass
class Persona:
    name: str
    archetype: str  # constructive_critic, bandwagon_casual, etc.
    player_type: str  # new | mid | hardcore
    session_pattern: str
    motivations: list[str]  # action, social, mastery, etc.
    goals: list[str]
    pains: list[str]
    triggers: list[str]
    win_conditions: list[str]
    mobile_considerations: list[str]  # Steam→Mobile 변환 포인트
    spending_segment: str  # whale | dolphin | minnow | non_payer
    evidence: dict = field(default_factory=dict)


@dataclass
class Validation:
    persona_name: str
    value_hypothesis: str
    failure_hypothesis: str
    evidence: list[str]
    fit_score: int  # 1-5
    confidence: str  # high | medium | low


@dataclass
class Risk:
    category: str  # execution | tech | balance | ops | ux
    description: str
    severity: str  # high | medium | low
    mitigation: str
    affected_personas: list[str]


@dataclass
class SynthesisResult:
    personas: list[Persona]
    validations: list[Validation]
    risks: list[Risk]
    top_personas: list[str]
    top_risk: str


# 리서치 기반 페르소나 합성 프롬프트
SYNTHESIS_SYSTEM_PROMPT = """당신은 게임 유저 리서치 전문가입니다.
Steam 리뷰 데이터와 검증된 페르소나 프레임워크를 기반으로 정교한 페르소나를 도출합니다.

## 페르소나 프레임워크 (리서치 기반)

### 5대 기본 아키타입:
1. **건설적 비평가 (Constructive Critic)**: 플타 24h+, 장문 리뷰, 장단점 구분
2. **유행 추종 캐주얼 (Bandwagon Casual)**: 짧은 리뷰, 감정적, 유행 민감
3. **분위기 탐구자 (Vibe Seeker)**: 아트/사운드 중시, 인디 선호, 감성적
4. **기술 문제 해결사 (Tech Troubleshooter)**: 성능/호환성 민감, 기술적 리뷰
5. **하드코어 경쟁러 (Competitive Hardcore)**: 실력 기반, 밸런스 민감, 랭크 지향

### 6대 동기 축 (Quantic Foundry):
- Action (파괴, 흥분) / Social (경쟁, 커뮤니티)
- Mastery (도전, 전략) / Achievement (완료, 파워)
- Immersion (판타지, 스토리) / Creativity (디자인, 발견)

### 모바일 과금 세분화:
- Whale ($100+/월), Dolphin ($10-100), Minnow ($1-10), Non-payer ($0)

## 모바일 보정 관점 (Steam→Mobile):
- **조작**: PC 마우스/키보드 → 터치스크린 (정밀도 감소)
- **세션**: 장시간 → 5~15분 짧은 세션
- **네트워크**: 안정적 → 불안정한 모바일 환경
- **성능**: 고사양 PC → 다양한 스마트폰 스펙
- **과금**: 일회성 구매 → F2P/가챠 모델

## 찌꺼기 데이터 필터링:
- AI 생성 리뷰: "것 같다", "에 대해" 등 형식적 표현, 줄바꿈 거의 없음
- 유효 리뷰: ㅋㅋ, ㅠㅠ 등 구어체, 줄바꿈 다수, 감정 이모지

반드시 JSON 형식으로 응답하세요."""

SYNTHESIS_USER_TEMPLATE = """## 입력 데이터

### 아이디어
{idea}

### 장르
{genre}

### 태깅된 리뷰 통계
{stats}

### pain_points 분포 (상위)
{pain_distribution}

### delights 분포 (상위)
{delight_distribution}

### 플레이어 타입 분포
{player_type_distribution}

### 샘플 인용문 (고품질 리뷰만)
{sample_quotes}

---

## 장르별 페르소나 가중치 참고
{genre_weights}

---

## 요청

아래 JSON 스키마에 맞춰 응답하세요:

1. **personas** (3~5개): 아키타입 기반, 장르 가중치 반영
   - 각 페르소나에 `archetype`, `motivations`, `mobile_considerations`, `spending_segment` 포함
   
2. **validations**: 페르소나별 가치 가설 + 실패 가설 (반증 조건 명시)

3. **risks** (TOP 5): 실행/기술/밸런스/운영/UX, 영향받는 페르소나 명시

4. **top_personas**: 아이디어에 가장 적합한 상위 2개

5. **top_risk**: 가장 심각한 리스크 1개

```json
{{
  "personas": [
    {{
      "name": "페르소나 이름",
      "archetype": "constructive_critic|bandwagon_casual|vibe_seeker|tech_troubleshooter|competitive_hardcore",
      "player_type": "new|mid|hardcore",
      "session_pattern": "short|long|variable",
      "motivations": ["action", "mastery"],
      "goals": ["목표1", "목표2"],
      "pains": ["고통점1", "고통점2"],
      "triggers": ["민감요소1"],
      "win_conditions": ["성공조건1"],
      "mobile_considerations": ["모바일 고려사항"],
      "spending_segment": "dolphin",
      "evidence": {{"tag": "값", "quote": "인용"}}
    }}
  ],
  "validations": [
    {{
      "persona_name": "페르소나 이름",
      "value_hypothesis": "가치 가설",
      "failure_hypothesis": "실패 가설 (반증 조건)",
      "evidence": ["근거1"],
      "fit_score": 4,
      "confidence": "high|medium|low"
    }}
  ],
  "risks": [
    {{
      "category": "balance",
      "description": "리스크 설명",
      "severity": "high",
      "mitigation": "완화 방안",
      "affected_personas": ["페르소나1"]
    }}
  ],
  "top_personas": ["이름1", "이름2"],
  "top_risk": "가장 큰 리스크"
}}
```"""


class PersonaSynthesizer:
    """리서치 기반 페르소나 합성 + 검증 Agent"""
    
    def __init__(self, config: Config, llm_client=None):
        self.config = config
        self.llm_client = llm_client
        self.frameworks = self._load_frameworks()
    
    def _load_frameworks(self) -> dict:
        """페르소나 프레임워크 로드"""
        framework_path = Path(__file__).parent.parent / "data" / "persona_frameworks.json"
        if framework_path.exists():
            with open(framework_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    
    def synthesize(
        self,
        tagged_reviews_path: Path,
        idea: str,
        genre: str
    ) -> SynthesisResult:
        """태깅된 리뷰로 페르소나 합성 + 아이디어 검증"""
        print("🧠 리서치 기반 페르소나 합성 시작...")
        
        # 통계 계산
        stats = self._compute_stats(tagged_reviews_path)
        
        # 장르별 가중치 조회
        genre_weights = self._get_genre_weights(genre)
        
        # 프롬프트 생성
        user_prompt = SYNTHESIS_USER_TEMPLATE.format(
            idea=idea,
            genre=genre,
            stats=json.dumps(stats["summary"], ensure_ascii=False, indent=2),
            pain_distribution=json.dumps(stats["pain_dist"], ensure_ascii=False, indent=2),
            delight_distribution=json.dumps(stats["delight_dist"], ensure_ascii=False, indent=2),
            player_type_distribution=json.dumps(
                stats["summary"].get("player_types", {}), 
                ensure_ascii=False, 
                indent=2
            ),
            sample_quotes="\n".join([f'- "{q}"' for q in stats["quotes"][:8]]),
            genre_weights=json.dumps(genre_weights, ensure_ascii=False, indent=2),
        )
        
        # LLM 호출
        if self.llm_client:
            response = self._call_llm(user_prompt)
            result = self._parse_response(response, stats)
        else:
            # Fallback: 프레임워크 기반 규칙 생성
            result = self._framework_based_synthesis(stats, idea, genre)
        
        # 결과 저장
        output_path = self.config.output_dir / self.config.personas_file
        self._save_result(result, output_path)
        
        print(f"💾 저장: {output_path}")
        return result
    
    def _get_genre_weights(self, genre: str) -> dict:
        """장르별 페르소나 가중치 반환"""
        mappings = self.frameworks.get("genre_persona_mapping", {}).get("mappings", {})
        
        # 장르 매칭
        genre_lower = genre.lower()
        for key in mappings:
            if key in genre_lower or genre_lower in key:
                return mappings[key]
        
        # 기본값
        return {
            "constructive_critic": 0.25,
            "bandwagon_casual": 0.25,
            "vibe_seeker": 0.20,
            "tech_troubleshooter": 0.15,
            "competitive_hardcore": 0.15
        }
    
    def _compute_stats(self, path: Path) -> dict:
        """태깅 데이터 통계 계산 (품질 필터링 포함)"""
        reviews = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                reviews.append(json.loads(line))
        
        # 기본 통계
        total = len(reviews)
        by_game = defaultdict(int)
        by_sentiment = defaultdict(int)
        by_player_type = defaultdict(int)
        pain_counts = defaultdict(int)
        delight_counts = defaultdict(int)
        quotes = []
        
        # 품질 필터 적용
        filters = self.frameworks.get("data_quality_filters", {}).get("rules", {})
        quality_thresholds = filters.get("quality_thresholds", {})
        min_length = quality_thresholds.get("min_review_length", 50)
        
        high_quality_count = 0
        
        for r in reviews:
            by_game[r["game"]] += 1
            by_sentiment[r["sentiment"]] += 1
            by_player_type[r["player_type_guess"]] += 1
            
            for p in r.get("pain_points", []):
                pain_counts[p] += 1
            for d in r.get("delights", []):
                delight_counts[d] += 1
            
            # 고품질 리뷰만 인용 수집
            if r.get("quotes") and r.get("player_type_guess") in ["mid", "hardcore"]:
                quotes.extend(r["quotes"])
                high_quality_count += 1
        
        return {
            "summary": {
                "total_reviews": total,
                "high_quality_reviews": high_quality_count,
                "by_game": dict(by_game),
                "sentiment": dict(by_sentiment),
                "player_types": dict(by_player_type),
            },
            "pain_dist": dict(sorted(pain_counts.items(), key=lambda x: -x[1])[:10]),
            "delight_dist": dict(sorted(delight_counts.items(), key=lambda x: -x[1])[:10]),
            "quotes": quotes[:20],
        }
    
    def _call_llm(self, user_prompt: str) -> str:
        """LLM 호출"""
        if hasattr(self.llm_client, "chat"):
            resp = self.llm_client.chat(
                model=self.config.analysis_model,
                messages=[
                    {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ]
            )
            return resp.get("content", "{}")
        return "{}"
    
    def _parse_response(self, response: str, stats: dict) -> SynthesisResult:
        """LLM 응답 파싱"""
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
            else:
                raise ValueError("No JSON found")
            
            personas = []
            for p in data.get("personas", []):
                personas.append(Persona(
                    name=p.get("name", "Unknown"),
                    archetype=p.get("archetype", "constructive_critic"),
                    player_type=p.get("player_type", "mid"),
                    session_pattern=p.get("session_pattern", "variable"),
                    motivations=p.get("motivations", []),
                    goals=p.get("goals", []),
                    pains=p.get("pains", []),
                    triggers=p.get("triggers", []),
                    win_conditions=p.get("win_conditions", []),
                    mobile_considerations=p.get("mobile_considerations", []),
                    spending_segment=p.get("spending_segment", "minnow"),
                    evidence=p.get("evidence", {}),
                ))
            
            validations = []
            for v in data.get("validations", []):
                validations.append(Validation(
                    persona_name=v.get("persona_name", ""),
                    value_hypothesis=v.get("value_hypothesis", ""),
                    failure_hypothesis=v.get("failure_hypothesis", ""),
                    evidence=v.get("evidence", []),
                    fit_score=v.get("fit_score", 3),
                    confidence=v.get("confidence", "medium"),
                ))
            
            risks = []
            for r in data.get("risks", []):
                risks.append(Risk(
                    category=r.get("category", "execution"),
                    description=r.get("description", ""),
                    severity=r.get("severity", "medium"),
                    mitigation=r.get("mitigation", ""),
                    affected_personas=r.get("affected_personas", []),
                ))
            
            return SynthesisResult(
                personas=personas,
                validations=validations,
                risks=risks,
                top_personas=data.get("top_personas", []),
                top_risk=data.get("top_risk", ""),
            )
            
        except Exception as e:
            print(f"   ⚠️ 파싱 오류: {e}, 프레임워크 기반 생성으로 전환")
            return self._framework_based_synthesis(stats, "", "")
    
    def _framework_based_synthesis(
        self, 
        stats: dict, 
        idea: str, 
        genre: str
    ) -> SynthesisResult:
        """프레임워크 기반 규칙 생성 (LLM 실패 시)"""
        
        archetypes = self.frameworks.get("base_archetypes", {}).get("archetypes", {})
        weights = self._get_genre_weights(genre)
        
        # 가중치 상위 3~4개 아키타입 선택
        sorted_archetypes = sorted(weights.items(), key=lambda x: -x[1])[:4]
        
        personas = []
        validations = []
        
        player_types = stats.get("summary", {}).get("player_types", {})
        top_pains = list(stats.get("pain_dist", {}).keys())[:3]
        top_delights = list(stats.get("delight_dist", {}).keys())[:3]
        
        for archetype_key, weight in sorted_archetypes:
            if archetype_key not in archetypes:
                continue
            
            arch = archetypes[archetype_key]
            
            # 데이터 기반 커스터마이징
            custom_pains = arch.get("pains", [])[:2] + top_pains[:1]
            custom_goals = arch.get("goals", [])[:2]
            
            persona = Persona(
                name=arch.get("name_ko", archetype_key),
                archetype=archetype_key,
                player_type=arch.get("player_type", "mid").split("_")[0],
                session_pattern=arch.get("session_pattern", "variable"),
                motivations=["mastery", "action"] if "competitive" in archetype_key else ["immersion", "creativity"],
                goals=custom_goals,
                pains=custom_pains,
                triggers=arch.get("triggers", [])[:2],
                win_conditions=["아이디어가 고통점 해결", "기대 충족"],
                mobile_considerations=[
                    "터치 조작 최적화 필요" if arch.get("player_type") == "hardcore" else "캐주얼 접근성 유지"
                ],
                spending_segment="dolphin" if "critic" in archetype_key else "minnow",
                evidence={
                    "weight": weight,
                    "player_count": player_types.get(arch.get("player_type", "mid").split("_")[0], 0),
                },
            )
            personas.append(persona)
            
            validations.append(Validation(
                persona_name=persona.name,
                value_hypothesis=f"{persona.name}에게 {custom_goals[0] if custom_goals else '핵심 가치'} 제공",
                failure_hypothesis=f"{custom_pains[0] if custom_pains else '주요 고통점'} 미해결 시 이탈",
                evidence=["프레임워크 기반 추론"],
                fit_score=4 if weight > 0.2 else 3,
                confidence="medium",
            ))
        
        # 기본 리스크
        risks = [
            Risk("balance", "핵심 메카닉 밸런스 불안", "high", "베타 테스트 강화", [p.name for p in personas[:2]]),
            Risk("ux", "모바일 조작 불편", "high", "터치 UI 최적화", [p.name for p in personas if "hardcore" in p.archetype]),
            Risk("tech", "성능 이슈", "medium", "다양한 기기 테스트", []),
            Risk("ops", "콘텐츠 업데이트 부담", "medium", "시즌제 운영", []),
            Risk("execution", "개발 일정 지연", "low", "MVP 범위 축소", []),
        ]
        
        return SynthesisResult(
            personas=personas,
            validations=validations,
            risks=risks,
            top_personas=[p.name for p in personas[:2]],
            top_risk="핵심 메카닉 밸런스 불안",
        )
    
    def _save_result(self, result: SynthesisResult, output_path: Path) -> None:
        """결과 저장"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "personas": [asdict(p) for p in result.personas],
                "validations": [asdict(v) for v in result.validations],
                "risks": [asdict(r) for r in result.risks],
                "top_personas": result.top_personas,
                "top_risk": result.top_risk,
            }, f, ensure_ascii=False, indent=2)


def get_synthesis_prompts() -> tuple[str, str]:
    """프롬프트 반환 (Cursor에서 직접 사용 시)"""
    return SYNTHESIS_SYSTEM_PROMPT, SYNTHESIS_USER_TEMPLATE
