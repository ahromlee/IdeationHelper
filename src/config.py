"""설정 로더 - 프리셋 기반 + 오버라이드"""
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

PRESETS = {
    "free": {
        "reviews_per_game": 30,
        "tagging_model": "gemini-flash",
        "analysis_model": "claude-3.5-sonnet",
        "merge_agents": True,
        "batch_size": 30,
    },
    "standard": {
        "reviews_per_game": 100,
        "tagging_model": "claude-3.5-sonnet",
        "analysis_model": "claude-3.5-sonnet",
        "merge_agents": True,  # C+D 병합
        "batch_size": 50,
    },
    "detailed": {
        "reviews_per_game": 300,
        "tagging_model": "gpt-4o",
        "analysis_model": "gpt-4o",
        "merge_agents": False,
        "batch_size": 50,
    },
}


@dataclass
class Config:
    # 프리셋
    preset: str
    
    # 리뷰 설정
    reviews_per_game: int
    tagging_model: str
    analysis_model: str
    merge_agents: bool
    batch_size: int
    
    # Steam 설정
    language: str
    sentiment_ratio: float
    recent_months: int
    
    # 출력 설정
    output_dir: Path
    raw_reviews_file: str
    tagged_reviews_file: str
    personas_file: str
    report_file: str


def load_config(config_path: str = "config.yaml") -> Config:
    """config.yaml 로드 + 프리셋 적용 + 오버라이드"""
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    
    preset_name = raw.get("preset", "standard")
    preset = PRESETS.get(preset_name, PRESETS["standard"])
    
    # 오버라이드 적용
    overrides = raw.get("overrides", {}) or {}
    
    return Config(
        preset=preset_name,
        reviews_per_game=overrides.get("reviews_per_game") or preset["reviews_per_game"],
        tagging_model=overrides.get("tagging_model") or preset["tagging_model"],
        analysis_model=overrides.get("analysis_model") or preset["analysis_model"],
        merge_agents=overrides.get("merge_agents") if overrides.get("merge_agents") is not None else preset["merge_agents"],
        batch_size=preset["batch_size"],
        language=raw.get("steam", {}).get("language", "korean"),
        sentiment_ratio=raw.get("steam", {}).get("sentiment_ratio", 0.5),
        recent_months=raw.get("steam", {}).get("recent_months", 6),
        output_dir=Path(raw.get("output", {}).get("dir", "./output")),
        raw_reviews_file=raw.get("output", {}).get("raw_reviews", "raw_reviews.jsonl"),
        tagged_reviews_file=raw.get("output", {}).get("tagged_reviews", "tagged_reviews.jsonl"),
        personas_file=raw.get("output", {}).get("personas", "personas.json"),
        report_file=raw.get("output", {}).get("report", "report.md"),
    )


def print_config(config: Config) -> None:
    """설정 출력 (디버깅용)"""
    print(f"━━━ Config [{config.preset.upper()}] ━━━")
    print(f"  리뷰/게임: {config.reviews_per_game}개")
    print(f"  태깅 모델: {config.tagging_model}")
    print(f"  분석 모델: {config.analysis_model}")
    print(f"  Agent 병합: {config.merge_agents}")
    print(f"  언어: {config.language}")
    print(f"  출력: {config.output_dir}/")
    print("━" * 30)
