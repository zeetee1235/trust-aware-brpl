# Trust-Aware BRPL (Selective Forwarding)

상세 내용은 보고서에 정리되어 있습니다.

- 최신 보고서(Markdown): `docs/report/report.md`
- 보고서(한글, 구버전): `docs/report/report_kr.pdf`
- 결과 그래프: `docs/report/figure*.png`

## 빠른 실행(예비 실험)

```bash
# 배치 실험(예비 설정)
./scripts/run_experiments.sh

# 결과 분석 및 그림 생성
Rscript scripts/analyze_results.R results/<latest_run_dir>
```

## 핵심 파일

- 시뮬레이션 토폴로지: `configs/simulation.csc`
- 실험 스크립트: `scripts/run_experiments.sh`
- 결과 분석: `scripts/analyze_results.R`
