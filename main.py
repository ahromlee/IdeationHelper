#!/usr/bin/env python3
"""
Vibe Ideation Validator - Main Orchestrator

Usage:
    python main.py --idea "아이디어 텍스트" --genre "shooter" --competitors "Counter-Strike 2:730,PUBG:578080"
    
Or interactive:
    python main.py
"""
import argparse
import json
import sys
import io
from pathlib import Path

# Windows 콘솔 UTF-8 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from src.config import load_config, print_config, Config
from src.agents import ReviewMiner, ReviewTagger, PersonaSynthesizer, ReportEditor

console = Console(force_terminal=True, legacy_windows=False)


def parse_competitors(comp_str: str) -> list[dict]:
    """'Game1:appid1,Game2:appid2' 형식 파싱"""
    competitors = []
    for item in comp_str.split(","):
        item = item.strip()
        if ":" in item:
            name, appid = item.rsplit(":", 1)
            competitors.append({"name": name.strip(), "appid": appid.strip()})
        else:
            # appid만 있는 경우
            competitors.append({"name": item, "appid": item})
    return competitors


def run_pipeline(
    config: Config,
    idea: str,
    genre: str,
    competitors: list[dict],
    llm_client=None,
):
    """전체 파이프라인 실행"""
    
    console.print(Panel(f"[bold cyan]🚀 Vibe Validation 시작[/]\n프리셋: {config.preset.upper()}"))
    
    # Agent A: 리뷰 수집
    console.print("\n[bold]━━━ Agent A: Review Miner ━━━[/]")
    miner = ReviewMiner(config)
    raw_path = miner.collect(competitors)
    
    # Agent B: 태깅
    console.print("\n[bold]━━━ Agent B: Review Tagger ━━━[/]")
    tagger = ReviewTagger(config, llm_client)
    tagged_path = tagger.tag_reviews(raw_path)
    
    # Agent C+D: 페르소나 합성 + 검증
    console.print("\n[bold]━━━ Agent C+D: Persona Synthesizer ━━━[/]")
    synthesizer = PersonaSynthesizer(config, llm_client)
    result = synthesizer.synthesize(tagged_path, idea, genre)
    
    # 통계 로드 (리포트용)
    stats = synthesizer._compute_stats(tagged_path)
    
    # Agent E: 리포트 생성
    console.print("\n[bold]━━━ Agent E: Report Editor ━━━[/]")
    editor = ReportEditor(config)
    report_path = editor.generate(result, idea, genre, competitors, stats)
    
    # 완료
    console.print(Panel(
        f"[bold green]✅ 완료![/]\n\n"
        f"📁 출력 파일:\n"
        f"  - {config.output_dir / config.raw_reviews_file}\n"
        f"  - {config.output_dir / config.tagged_reviews_file}\n"
        f"  - {config.output_dir / config.personas_file}\n"
        f"  - [bold]{report_path}[/]",
        title="결과"
    ))
    
    return report_path


def interactive_mode(config: Config):
    """대화형 모드"""
    console.print(Panel("[bold]🎮 Vibe Ideation Validator[/]\n대화형 모드", style="cyan"))
    
    # 입력 받기
    idea = Prompt.ask("\n[bold]아이디어[/] (여러 줄은 \\n으로)")
    genre = Prompt.ask("[bold]장르[/]", default="shooter")
    comp_str = Prompt.ask(
        "[bold]경쟁작[/] (형식: Game1:appid1,Game2:appid2)",
        default="Counter-Strike 2:730"
    )
    
    competitors = parse_competitors(comp_str)
    
    console.print(f"\n[dim]경쟁작: {competitors}[/]")
    
    if Prompt.ask("\n진행할까요?", choices=["y", "n"], default="y") == "y":
        run_pipeline(config, idea, genre, competitors)
    else:
        console.print("[yellow]취소됨[/]")


def main():
    parser = argparse.ArgumentParser(description="Vibe Ideation Validator")
    parser.add_argument("--config", default="config.yaml", help="설정 파일 경로")
    parser.add_argument("--idea", help="검증할 아이디어")
    parser.add_argument("--genre", help="장르")
    parser.add_argument("--competitors", help="경쟁작 (Game1:appid1,Game2:appid2)")
    parser.add_argument("--preset", choices=["free", "standard", "detailed"], help="프리셋 오버라이드")
    
    args = parser.parse_args()
    
    # 설정 로드
    config = load_config(args.config)
    
    # 프리셋 오버라이드
    if args.preset:
        from src.config import PRESETS
        preset = PRESETS[args.preset]
        config.preset = args.preset
        config.reviews_per_game = preset["reviews_per_game"]
        config.tagging_model = preset["tagging_model"]
        config.analysis_model = preset["analysis_model"]
        config.merge_agents = preset["merge_agents"]
        config.batch_size = preset["batch_size"]
    
    print_config(config)
    
    # 실행 모드 결정
    if args.idea and args.competitors:
        competitors = parse_competitors(args.competitors)
        run_pipeline(config, args.idea, args.genre or "unknown", competitors)
    else:
        interactive_mode(config)


if __name__ == "__main__":
    main()
