# TA-BRPL 프로젝트 통합 기술 문서 (논문 초안 기반)

작성일: 2026-03-05  
기준 저장소: `/home/research/TA-BRPL` (로컬 워크트리 기준)

이 문서는 현재 코드/스크립트/실험 파이프라인을 논문 초안 작성용으로 한 번에 참조할 수 있도록 정리한 통합 문서다.

## 1) 연구 목표 및 핵심 주장

- 목적: LLN 환경에서 BRPL의 backpressure 기반 부모 선택에 trust penalty를 결합해 sinkhole/grayhole(선택적 포워딩) 공격 내성을 평가.
- 비교군:
  - `BRPL + Trust OFF`
  - `BRPL + Trust ON (TA-BRPL)`
  - `Pure RPL (MRHOF + ETX)` baseline
- 핵심 관심 지표:
  - PDR
  - Trust/Blacklist 동작 추적
  - 공격자 노출도/부모 선택 점유율 계열 지표(`exposure.csv`)

## 2) 저장소 구조 (연구에 실질적으로 중요한 영역)

- `motes/`: 시뮬레이션 노드 애플리케이션(루트/정상/공격자) + trust/blacklist 모듈
- `project-conf.h`: 실험 시 매크로 스위치 중심 설정 파일
- `scripts/`: 병렬 실행, 모니터링, 토폴로지 생성, 결과 후처리/플롯
- `configs/topologies/`: 고정 토폴로지 `.csc` 및 좌표 `.csv`
- `tools/trust_engine/` (Rust): 로그 기반 trust 계산 및 피드백/지표 파일 생성
- `tools/results_parser/` (Rust): 실험 디렉토리 스캔 후 `runs.csv`, `summary.csv` 생성
- `docs/report/`: 생성된 리포트/그림 산출물
- `contiki-ng-brpl/`: BRPL 수정이 반영된 Contiki-NG 서브트리

## 3) 라우팅/모드 아키텍처

### 3.1 빌드/런타임 모드 스위치

파일: `project-conf.h`

- BRPL 모드 활성 조건:
  - `#if defined(BRPL_MODE) && (BRPL_MODE)`
  - OF를 `rpl_brpl`로 설정
- Pure RPL baseline 모드 조건:
  - `#if defined(RPL_BASELINE_MODE) && (RPL_BASELINE_MODE)`
  - `RPL_OCP_MRHOF`, `RPL_CONF_WITH_MC=1`, `RPL_DAG_MC_ETX`
  - `BRPL_CONF_TRUST_ENABLE=0`

중요: `#ifdef`가 아니라 `#if defined(...) && (...)`를 사용하도록 정리되어, `MODE=0`일 때 오동작하지 않음.

### 3.2 모트 공통 빌드 특징

파일: `motes/Makefile.receiver`, `motes/Makefile.sender`, `motes/Makefile.attacker`

- `MAKE_ROUTING = MAKE_ROUTING_RPL_CLASSIC`
- 공통 포함 소스:
  - `brpl-trust.c`
  - `brpl-blacklist.c`
- `CSV_VERBOSE_LOGGING=1` 기본 주입

## 4) 공격 모델 구현 현황

### 4.1 공격 모드 정의

파일: `motes/attacker.c`

- `ATTACK_MODE_SELECTIVE=0`
- `ATTACK_MODE_SINKHOLE=1`
- `ATTACK_MODE_COMBINED=2`

### 4.2 Selective/Grayhole 데이터면 공격

- 공격자 노드가 root행 UDP forwarding 시 확률 드롭 (`ATTACK_DROP_PCT`).
- 구현 위치:
  - `udp_rx_callback()`
  - `ip_output()`

### 4.3 Sinkhole 제어면 공격 (DIO 조작)

파일: `contiki-ng-brpl/os/net/routing/rpl-classic/rpl-icmp6.c`

- DIO rank 조작:
  - 공격자이면서 sinkhole/combined 모드이면 광고 rank를 `ROOT_RANK + 1`로 설정
- DIO ETX(MC) 조작:
  - 공격자이면 `adv_etx = adv_etx * SINKHOLE_ETX_SCALE_PERMILLE / 1000`
  - 기본 scale: `500` (즉 0.5배)

관련 매크로:
- `ATTACKER_NODE_ID` (기본 2)
- `SINKHOLE_ETX_SCALE_PERMILLE` (`motes/attacker-params.h`, 기본 500)

## 5) Trust + Blacklist 구현

### 5.1 BRPL metric 내 trust penalty 결합

파일: `contiki-ng-brpl/os/net/routing/rpl-classic/rpl-brpl.c`

- base weight 계산 후 `brpl_apply_trust_penalty()` 적용
- penalty는 `trust`, `lambda`, `gamma` 기반 비선형 감쇠
- parent 비교 시 최종 score가 더 낮은 parent를 선택

즉, 현재 구현은 “trust를 metric에 직접 결합”하는 구조가 맞다.

### 5.2 Trust 소스

- grayhole trust: `brpl_trust_get()`를 통해 외부 주입값 사용
  - 실제 구현: `motes/brpl-trust.c` (`brpl_trust_override`로 업데이트)
- sinkhole trust:
  - 광고 이상치 기반 (`sink_adv`)
  - 안정성 기반 (`sink_stab`)
  - EWMA로 누적 후 total trust 결합

### 5.3 Blacklist 정책 (임계값 기반 + 히스테리시스)

파일: `motes/brpl-blacklist.h`, `motes/sender.c`, `motes/attacker.c`

- 정규화 임계값:
  - `BLACKLIST_TRUST_THRESHOLD_NORM` 기본 `0.900`
  - `BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM` 기본 `0.950`
- 동작:
  - `trust < threshold`면 add
  - `trust >= clear_threshold`면 remove
- 패킷 필터:
  - `brpl_blacklist_should_drop_packet()`

즉, 현재 구현은 “임계값 기반 blacklist 정책”이 맞다.

## 6) 외부 Trust Engine (Rust) 파이프라인

파일: `tools/trust_engine/src/main.rs`

- 입력: `logs/COOJA.testlog`
- 출력:
  - trust 피드백 텍스트(노드 시리얼 주입용)
  - `trust_metrics.csv`, `blacklist.csv`, `exposure.csv`, `parent_switch.csv`, `stats.csv`, `trust_final.log`
- worker가 trust ON인 경우에만 실행하며 `--follow` 모드로 로그를 tail

기본적으로 worker에서 전달하는 주요 파라미터:
- `--alpha` (EWMA)
- `--miss-threshold`
- `--fwd-drop-threshold`
- sink 관련 계수(`sink-*`)
- `--trust-alpha`
- `--attacker-id`

## 7) 실험 실행 시스템

### 7.1 메인 런처

파일: `scripts/run_experiments_parallel.sh`

- 동적 큐 기반 병렬 실행
- 기본 워커 수: `NUM_WORKERS=8`
- 큐 파일:
  - `queue_all.txt`
  - `queue_all.txt.cursor`
  - `queue_all.txt.total`
  - lock 파일 기반 `flock` 사용

### 7.2 워커

파일: `scripts/run_experiments_worker.sh`

핵심 포인트:
- `--print-experiments`로 전체 실험 조합 출력
- 동적 큐 pop 후 1개씩 수행
- 워커별 격리 환경 `.parallel_worker_env/workerX` 생성
- Cooja `.csc`를 런타임 sed/python으로 변형해 매크로 주입
- RPL baseline 시:
  - `RPL_BASELINE_MODE=1`, `BRPL_MODE=0`
  - `CONTIKI_RUNTIME_PATH=$PURE_RPL_CONTIKI_PATH`
  - `<commands>`에 `CONTIKI=<path>` 주입

현재 기본 실험셋(코드 기준):
- 토폴로지 9개: `CLUSTER/GRID/RING x S/M/L`
- attack rate: `0~100` (5% step)
- seed:
  - QUICK_PREVIEW=1: `123456` 1개
  - QUICK_PREVIEW=0: 5개
- 시나리오:
  - `1_rpl_mrhof_normal`
  - `2_brpl_normal_notrust`
  - `3_rpl_mrhof_attack`
  - `4_brpl_attack_notrust`
  - `6_brpl_attack_trust`
  - `8_brpl_normal_trust` (옵션 포함 상태)

현재 trust ON attack sweep 기본값:
- `ATTACK_MODE_SET=(2)` (combined only)
- `SINK_DELTA_SET=(1)`
- `TRUST_ALPHA_SET=(1.0)`
- `LAMBDA_SET=(6)`
- `GAMMA_SET=(4)`
- `BLACKLIST_TRUST_THRESHOLD_NORM_SET=(0.80 0.90 0.95)`
- `BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM_SET=(0.95)`

실험 개수(코드 출력 기준):
- QUICK_PREVIEW=1: 927 runs
- QUICK_PREVIEW=0: 4635 runs

### 7.3 모니터링

파일: `scripts/monitor_parallel.sh`

- 최신 실험 디렉토리 자동 탐색 (`results/experiments-*`)
- 좁은 터미널 폭에서 compact 모드 자동 전환
- 워커별 진행/성공/실패/CPU/MEM 요약

## 8) 토폴로지 세트 (현재 고정본)

### 8.1 생성기

파일: `scripts/generate_fixed_topologies.py`

- 필드: 100x100
- 무선 파라미터:
  - `TX_RANGE=21.0`
  - `INT_RANGE=42.0`
- 제약:
  - root 직접 도달 노드 비율 `<= 30%`

### 8.2 현재 토폴로지 파일

`configs/topologies/*.csv` 기준:

- `CLUSTER_S`: 20 (root1, attacker1, relay2, sender16)
- `CLUSTER_M`: 40 (root1, attacker1, relay2, sender36)
- `CLUSTER_L`: 60 (root1, attacker1, relay2, sender56)
- `GRID_S`: 20 (root1, attacker1, sender18)
- `GRID_M`: 40 (root1, attacker1, sender38)
- `GRID_L`: 60 (root1, attacker1, sender58)
- `RING_S`: 20 (root1, attacker1, sender18)
- `RING_M`: 40 (root1, attacker1, sender38)
- `RING_L`: 60 (root1, attacker1, sender58)

### 8.3 시각화

파일: `scripts/generate_topology_svgs.py`

- 출력:
  - `figures/topology_svgs/{TOPO}.svg`
  - `figures/topology_svgs/all_topologies.svg`

## 9) 결과 파싱 및 분석 파이프라인

### 9.1 1차 파서 (Rust)

파일: `tools/results_parser/src/main.rs`

- 입력: `results/experiments-...`
- 출력:
  - `parsed/runs.csv`
  - `parsed/summary.csv`
- 포함 메타:
  - topology/routing/traffic/trust_on/attack_rate/attack_mode/sink_delta/lambda/gamma/alpha/seed
  - 파일 존재/상태, exposure/trust final 통계

### 9.2 PDR 부착

파일: `scripts/attach_pdr.py`

- `COOJA.testlog`를 재파싱해 `pdr`, `pdr_tx_total`, `pdr_rx_total` 추가
- shard 병렬 처리 지원:
  - `--shard-id`, `--num-shards`

### 9.3 플롯

파일: `scripts/plot_pdr_sweep_figures.R`

생성 figure 예:
- trust on/off vs attack rate
- topology별 x=attack_rate, y=PDR
- attack mode별 x=attack_rate, y=PDR
- lambda/gamma/alpha/delta sweep
- delta heatmap

출력 디렉토리 기본: `docs/report/pdr_sweep`

## 10) 재현용 커맨드 (현재 코드 기준)

### 10.1 전체 병렬 실행

```bash
NUM_WORKERS=8 \
PURE_RPL_CONTIKI_PATH=/home/dev/contiki-ng \
QUICK_PREVIEW=0 \
./scripts/run_experiments_parallel.sh
```

### 10.2 모니터링

```bash
./scripts/monitor_parallel.sh "results/experiments-*"
```

### 10.3 결과 파싱 + PDR + 플롯

```bash
tools/results_parser/target/release/results_parser \
  --input results/experiments-YYYYMMDD-HHMMSS \
  --output-dir results/experiments-YYYYMMDD-HHMMSS/parsed

python3 scripts/attach_pdr.py \
  --runs-csv results/experiments-YYYYMMDD-HHMMSS/parsed/runs.csv \
  --output results/experiments-YYYYMMDD-HHMMSS/parsed/runs_pdr.csv \
  --workers 8 \
  --only-attack

Rscript scripts/plot_pdr_sweep_figures.R \
  results/experiments-YYYYMMDD-HHMMSS/parsed/runs_pdr.csv \
  docs/report/pdr_sweep
```

## 11) 로깅/산출물 의미

주요 CSV/로그:
- `logs/COOJA.testlog`: 원시 로그(모든 파서의 근거)
- `cooja_output.log`: 실행 성공/실패 판정(`TEST OK` 포함)
- `trust_engine.log`: trust engine 런타임 로그
- `trust_feedback.txt`: 노드로 주입되는 TRUST 라인
- `trust_metrics.csv`: trust 시계열
- `blacklist.csv`: 블랙리스트 이벤트
- `exposure.csv`: 공격자 노출/전달 지표(E1/E3)
- `parent_switch.csv`: parent switch 시계열
- `stats.csv`: 요약 시계열
- `trust_final.log`: 종료 시 trust 값 스냅샷

## 12) 코드상 확인된 핵심 사실 요약

- Trust penalty는 BRPL 메트릭에 직접 결합되어 parent 선택에 반영됨.
- Blacklist는 정규화 임계값 기반(hysteresis 포함)으로 동작함.
- Sinkhole 공격은 공격자 DIO의 rank/ETX를 동시에 유리하게 조작하도록 구현됨.
- Pure RPL baseline(MRHOF+ETX)과 BRPL/TA-BRPL이 동일 실험 프레임에서 같이 실행되도록 worker가 구성됨.
- 병렬 실행은 동적 큐 방식이며 현재 기본 워커는 8개.

## 13) 논문 작성 시 즉시 활용 가능한 서술 포인트

- 실험 파이프라인 분리:
  - Cooja 시뮬레이터(패킷/라우팅 이벤트 생성)
  - 외부 trust engine(로그 기반 trust 산출/피드백)
  - 사후 파서/플롯(PDR 중심 정량화)
- 공격 강도 축:
  - drop rate 0~100, 5% step
- 비교 축:
  - Routing family: RPL(MRHOF), BRPL, TA-BRPL
  - Trust: ON/OFF
  - Topology: 9 fixed instances
- 재현성:
  - 토폴로지 좌표 고정(`.csv`)
  - 시나리오/파라미터 조합 자동 생성(`--print-experiments`)

## 14) 현재 문서의 범위와 한계

- 이 문서는 "연구 코드/실험 파이프라인" 중심이다.
- `contiki-ng-brpl` 전체(플랫폼/OS 일반 코드)는 벤더 코드 규모가 커서 BRPL/공격/실험 관련 변경 지점 위주로만 다뤘다.
- 로컬 워크트리가 실험 중간 산출물/수정 상태를 포함할 수 있으므로, 최종 논문 수치 인용 전에는 대상 실험 디렉토리를 명시해 재검증하는 것을 권장한다.

