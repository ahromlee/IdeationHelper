"""Agent E - 리포트 생성"""
import json
from pathlib import Path
from datetime import datetime

from ..config import Config
from .synthesizer import SynthesisResult


REPORT_TEMPLATE = """# Vibe Validation Report
> 생성일: {date}  
> 프리셋: {preset}

---

## 1. Summary

- **아이디어**: {idea_oneline}
- **적합 페르소나 (Top 2)**: {top_personas}
- **최대 리스크**: {top_risk}
- **다음 액션**: {next_action}

---

## 2. Personas ({persona_count}개)

{personas_section}

---

## 3. Persona-fit Matrix

| Persona | Value Hypothesis | Failure Hypothesis | Evidence | Fit |
|---------|------------------|-------------------|----------|-----|
{matrix_rows}

---

## 4. Risks TOP 5

{risks_section}

---

## 5. Minimal Experiment & Telemetry

### 실험 (1주 내 가능)
{experiments}

### 필수 로그 이벤트
- `session_start` / `session_end` (세션 길이)
- `stage_complete` / `stage_fail` (진행도)
- `retry_count` (좌절 지점)
- `first_exit_point` (이탈 시점)

### 성공/실패 기준
{success_criteria}

---

## 6. Decision

**{decision}**

{decision_notes}

---

## Appendix: 데이터 기반

- 분석 리뷰 수: {total_reviews}개
- 수집 게임: {games}
- 긍정/부정 비율: {sentiment_ratio}
"""


class ReportEditor:
    """리포트 생성 Agent"""
    
    def __init__(self, config: Config):
        self.config = config
    
    def generate(
        self,
        synthesis_result: SynthesisResult,
        idea: str,
        genre: str,
        competitors: list[dict],
        stats: dict = None,
    ) -> Path:
        """
        최종 리포트 생성
        """
        print("📝 리포트 생성 중...")
        
        # 섹션 생성
        personas_section = self._format_personas(synthesis_result.personas)
        matrix_rows = self._format_matrix(synthesis_result.validations)
        risks_section = self._format_risks(synthesis_result.risks)
        experiments = self._suggest_experiments(synthesis_result, genre)
        success_criteria = self._suggest_criteria(synthesis_result)
        decision, decision_notes = self._make_decision(synthesis_result)
        
        # 통계 정보
        if stats:
            total_reviews = stats.get("summary", {}).get("total_reviews", "N/A")
            sentiment = stats.get("summary", {}).get("sentiment", {})
            pos = sentiment.get("pos", 0)
            neg = sentiment.get("neg", 0)
            sentiment_ratio = f"{pos}:{neg}" if pos or neg else "N/A"
        else:
            total_reviews = "N/A"
            sentiment_ratio = "N/A"
        
        # 템플릿 채우기
        report = REPORT_TEMPLATE.format(
            date=datetime.now().strftime("%Y-%m-%d %H:%M"),
            preset=self.config.preset.upper(),
            idea_oneline=idea[:100] + ("..." if len(idea) > 100 else ""),
            top_personas=", ".join(synthesis_result.top_personas) or "N/A",
            top_risk=synthesis_result.top_risk or "N/A",
            next_action=experiments.split("\n")[0] if experiments else "프로토타입 테스트",
            persona_count=len(synthesis_result.personas),
            personas_section=personas_section,
            matrix_rows=matrix_rows,
            risks_section=risks_section,
            experiments=experiments,
            success_criteria=success_criteria,
            decision=decision,
            decision_notes=decision_notes,
            total_reviews=total_reviews,
            games=", ".join([c["name"] for c in competitors]),
            sentiment_ratio=sentiment_ratio,
        )
        
        # 저장
        output_path = self.config.output_dir / self.config.report_file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        
        print(f"💾 저장: {output_path}")
        return output_path
    
    def _format_personas(self, personas) -> str:
        """페르소나 섹션 포맷"""
        sections = []
        for i, p in enumerate(personas, 1):
            section = f"""### Persona #{i}: {p.name}
- **유형**: {p.player_type} / {p.session_pattern} 세션
- **목표**: {', '.join(p.goals)}
- **고통점**: {', '.join(p.pains)}
- **민감 요소**: {', '.join(p.triggers)}
- **성공 조건**: {', '.join(p.win_conditions)}
"""
            sections.append(section)
        return "\n".join(sections)
    
    def _format_matrix(self, validations) -> str:
        """검증 매트릭스 포맷"""
        rows = []
        for v in validations:
            evidence = "; ".join(v.evidence[:2]) if v.evidence else "-"
            row = f"| {v.persona_name} | {v.value_hypothesis} | {v.failure_hypothesis} | {evidence} | {v.fit_score}/5 |"
            rows.append(row)
        return "\n".join(rows)
    
    def _format_risks(self, risks) -> str:
        """리스크 섹션 포맷"""
        lines = []
        for i, r in enumerate(risks[:5], 1):
            severity_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(r.severity, "⚪")
            line = f"{i}. {severity_emoji} **[{r.category.upper()}]** {r.description}\n   - 완화: {r.mitigation}"
            lines.append(line)
        return "\n\n".join(lines)
    
    def _suggest_experiments(self, result: SynthesisResult, genre: str) -> str:
        """실험 제안"""
        experiments = [
            "1. **프로토타입 플테**: 핵심 메카닉만 구현 → 5명 테스트 → 이탈 시점 기록",
            "2. **컨셉 반응 조사**: 스크린샷/영상 → 커뮤니티 반응 수집",
            "3. **A/B 난이도**: 첫 스테이지 2버전 → 완료율 비교",
        ]
        return "\n".join(experiments)
    
    def _suggest_criteria(self, result: SynthesisResult) -> str:
        """성공/실패 기준"""
        criteria = """- **성공**: 첫 세션 완료율 > 60%, 재방문율 > 30%
- **실패**: 첫 세션 완료율 < 30%, 평균 세션 < 3분
- **관찰**: 이탈 시점 분포, 재시도 횟수, 피드백 감성"""
        return criteria
    
    def _make_decision(self, result: SynthesisResult) -> tuple[str, str]:
        """의사결정 제안"""
        # 간단한 휴리스틱
        high_risks = [r for r in result.risks if r.severity == "high"]
        avg_fit = sum(v.fit_score for v in result.validations) / max(len(result.validations), 1)
        
        if len(high_risks) >= 3 or avg_fit < 2:
            return "Kill", "리스크가 너무 높거나 페르소나 적합도가 낮음. 아이디어 재검토 필요."
        elif len(high_risks) >= 1 or avg_fit < 3.5:
            notes = "수정 방향:\n"
            for r in high_risks[:2]:
                notes += f"- {r.category}: {r.mitigation}\n"
            return "Iterate", notes
        else:
            return "Go", "페르소나 적합도 양호, 리스크 관리 가능. 프로토타입 진행 권장."
