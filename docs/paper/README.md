# Paper Figure Pipeline (`docs/paper`)

이 디렉토리는 논문용 Figure를 독립적으로 생성하기 위한 전용 워크스페이스다.

## 생성 대상 Figure

- `fig1_ta_brpl_architecture.svg`: TA-BRPL 시스템 구조
- `fig2_attack_model.svg`: Sinkhole + Grayhole 공격 모델
- `fig3_topologies_medium.svg`: Cluster/Grid/Ring (M-scale) 토폴로지
- `fig4_pdr_no_attack.png`: 공격 없음 PDR 비교 (RPL/BRPL/TA-BRPL)
- `fig5_pdr_vs_attack_cluster.png`: Cluster에서 PDR vs Attack Rate
- `fig6_pdr_vs_attack_grid.png`: Grid에서 PDR vs Attack Rate
- `fig7_pdr_vs_attack_ring.png`: Ring에서 PDR vs Attack Rate
- `fig8_attacker_exposure.png`: Attacker parent exposure (BRPL vs TA-BRPL)

추가(선택):
- `fig6_alt_trust_effect_delta.png`: ΔPDR(Trust ON-OFF)
- `fig8_alt_trust_blacklist_dynamics.png`: Trust/Blacklist 동작 시계열

## 사용 방법

최신 결과에서 자동 생성:

```bash
docs/paper/scripts/build_all.sh
```

특정 CSV를 지정:

```bash
docs/paper/scripts/build_all.sh \
  results/experiments-20260305-174246/parsed_quick/runs_pdr.csv \
  docs/paper/figures
```

## 내부 스크립트

- `docs/paper/scripts/build_schematic_svgs.py`
  - Figure 1~3 SVG 생성
- `docs/paper/scripts/build_paper_figures.R`
  - Figure 4~8 (및 추가 figure) 생성
  - `run_name`을 직접 파싱해 시나리오를 식별하므로 `results_parser`의 legacy 네이밍 불일치에 영향을 덜 받음
- `docs/paper/data/attacker_parent_ratio_cache.csv`
  - `COOJA.testlog`에서 계산한 attacker parent ratio 캐시

## 스타일 가이드

- 학술 그림 톤을 위해 serif 기반 테마, 저채도 배경, 강한 대비의 핵심 색상을 사용.
- 시스템/공격도는 단순 박스열이 아니라 pipeline/branch/annotation이 있는 도식으로 구성.

## LaTeX 초안

- 메인 원고: `docs/paper/paper_draft.tex`
- 참고문헌: `docs/paper/references.bib`
- 빌드 스크립트: `docs/paper/build_latex.sh`

빌드:

```bash
docs/paper/build_latex.sh
```
