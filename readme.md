# TA-BRPL

이 저장소는 **현재 연구 진행 중**입니다.

## 빠른 사용 순서

```bash
./scripts/cleanup_before_sweep.sh --apply
./scripts/run_sweep.sh --jobs 12 --rerun
python3 scripts/parse_results.py
Rscript scripts/plot_main_figures.R
```

## 파일/디렉토리 사용법

- `motes/`
  - Contiki 펌웨어 소스.
  - `ta-brpl-trust.c`, `ta-brpl-trust.h`: TA-BRPL 신뢰/검증 로직.
  - `attacker.c`, `sinkhole_attacker.c`: 공격 노드 동작.
  - `sender.c`, `receiver_root.c`: 트래픽 송신/루트 수신 로직.
  - `Makefile.*`: 프로토콜/변형별 빌드 설정.

- `configs/scenarios/`
  - Cooja 시나리오(`.csc`) 모음.
  - `tmp_*.csc`는 실행 중 생성되는 임시 파일.

- `scripts/run_sweep.sh`
  - 병렬 실험 실행 스크립트.
  - 예: `./scripts/run_sweep.sh --jobs 12 --rerun`

- `scripts/parse_results.py`
  - 시뮬레이션 로그를 CSV 요약으로 파싱.
  - 예: `python3 scripts/parse_results.py`

- `scripts/plot_main_figures.R`
  - 메인 Figure PDF 생성.
  - 예: `Rscript scripts/plot_main_figures.R`

- `scripts/plot_figures.py`
  - 보조/커스텀 Figure 생성용 Python 플로팅 스크립트.

- `scripts/plot_additional_figures.py`
  - 추가 분석 Figure 생성 스크립트.

- `scripts/generate_random_topologies.py`
  - 랜덤 토폴로지 생성기.

- `scripts/generate_threshold_sweep_variants.py`
  - threshold 스윕용 시나리오/설정 변형 생성.

- `scripts/generate_soft_penalty_sweep_variants.py`
  - soft-penalty 스윕 변형 생성.

- `scripts/generate_relative_sweep_variants.py`
  - 상대 파라미터 스윕 변형 생성.

- `scripts/cleanup_before_sweep.sh`
  - 재실험 전 대용량 산출물/로그 정리.
  - 미리보기: `./scripts/cleanup_before_sweep.sh`
  - 실제 삭제: `./scripts/cleanup_before_sweep.sh --apply`

- `results/`
  - 파싱된 CSV 결과 저장 위치.

- `figures/`
  - 생성된 Figure(PDF/PNG) 저장 위치.

- `docs/paper/`
  - 논문 원고(`paper.tex`, `paper_draft.tex`) 및 관련 파일.

- `docs/`
  - 모델/실험 설계 문서.

- `agent/`
  - 내부 실험/모델 노트.

## 나중에 한 번에 돌릴 때

- 랜덤 토폴로지 스윕 실행:
  - `./scripts/run_random_topo_sweep.sh --jobs 12 --rerun`
  - 기본값: `protocols=4`, `densities=3`, `topology-seeds=1-80`, `run-seeds=1-5`
  - 총 run 수: `4 x 3 x 80 x 5 = 4800`

- 파라미터 스윕 번들 실행:
  - `./scripts/run_param_sweep_bundle.sh --jobs 12 --rerun`
  - 기본값: `seeds=30`, `losses=3`, `families=threshold,soft,relative,margin,path,prr`
  - 기본 프로토콜 LOSS 스윕 run 수: `4 x 30 x 3 = 360`
  - family 변형 수:
    - `threshold=15`, `soft=4`, `relative=7`, `margin=4`, `path=4`, `prr=5` (합계 `39`)
  - family 스윕 run 수: `39 x 30 x 3 = 3510`
  - 번들 기본 총 run 수: `360 + 3510 = 3870`

- LOSS x 공격 드롭 매트릭스까지 포함해서 한 번에:
  - `./scripts/run_param_sweep_bundle.sh --jobs 12 --rerun --with-loss-attack`
  - 매트릭스 추가 run 수: `loss(3) x drop(5) x protocols(4) x seeds(30) = 1800`
  - 전체 총 run 수: `3870 + 1800 = 5670`
