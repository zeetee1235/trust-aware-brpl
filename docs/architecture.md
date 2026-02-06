# Trust-Aware BRPL 프로젝트 아키텍처

이 문서는 `/home/dev/WSN-IoT/trust-aware-brpl`의 전체 구조, 런타임 동작, 실험 파이프라인, 신뢰(Trust) 피드백 루프, 로그/분석 흐름을 빠짐없이 기술한다. 코드와 설정은 현 상태(레포 내 파일 기준)로 설명한다.

## 1. 전체 구조 한눈에 보기

```
[Sender motes] --UDP--> [Forwarder (Relay or Attacker)] --UDP--> [Root]
      |                      |                                     |
      |                      |-- CSV,FWD logs ---------------------|
      |-- CSV,TX/RTT logs -->|                                     
      |                                     |-- CSV,RX logs --------|

[COOJA.testlog] --> [tools/trust_engine] --> trust_feedback.txt
                                   |                         |
                                   |                         v
                                   |            (Cooja ScriptRunner)
                                   |--> trust_metrics.csv     |
                                   |--> blacklist.csv         |
                                                     (Serial input: "TRUST,node,trust")
                                                         | 
                                                         v
                                               [sender/attacker handle_trust_input]
```

핵심 루프는 다음 4단계다.

1. 모트가 CSV 로그를 출력한다. (`CSV,TX`, `CSV,RX`, `CSV,FWD`, `CSV,PARENT`, `CSV,RTT`)
2. `trust_engine`가 로그를 읽어 trust 값을 계산해 `TRUST,<node>,<value>`를 생성한다.
3. Cooja ScriptRunner가 trust_feedback 파일을 주기적으로 폴링해 모든 모트에 직렬 입력으로 주입한다.
4. 모트 앱(특히 sender/attacker)이 trust를 받아 블랙리스트/forwarder 선택에 반영한다.

## 2. 디렉터리 및 역할 맵

- `motes/`: Contiki-NG 애플리케이션(센서 송신자/공격자/루트)와 Trust/Blacklist 모듈.
- `configs/`: Cooja 시뮬레이션 설정(.csc) 및 실험용 템플릿.
- `scripts/`: 실험 자동화, 분석, 토폴로지 생성, 단일 테스트 실행.
- `tools/`: 로그 파서(`parse_results.py`)와 Trust 계산기(`trust_engine`).
- `contiki-ng-brpl/`: BRPL을 포함한 Contiki-NG 서브모듈(실제 네트워크 스택 구현).
- `docs/report/`: 보고서 및 결과 그림/테이블 출력 위치.
- `results/`: 실험 결과 로그 및 파생 산출물 저장.

## 3. 네트워크 애플리케이션 구성 (motes/)

### 3.1 Sender (센서 노드)

- 파일: `motes/sender.c`
- 역할: 주기적으로 UDP 패킷을 전송하고, 루트로부터 Echo를 받아 RTT를 로깅.
- 주요 동작 흐름:

1. `root_ipaddr`를 `aaaa::1`로 설정한다.
2. `simple_udp_register()`로 UDP 수신 콜백 등록.
3. `serial_line_init()` 후, `TRUST,<node>,<value>` 입력을 수신.
4. `handle_trust_input()`에서 다음을 수행한다.
   - `brpl_trust_override(node_id, trust)` 호출(현재 구현은 실질적 라우팅 반영 없음).
   - trust 값이 `BLACKLIST_TRUST_THRESHOLD` 아래면 블랙리스트 추가.
   - 특정 노드(ATTACKER/RELAY)에 대한 trust 변화에 따라 `set_forwarder()`로 다음 홉 변경.
5. Warmup 완료 후 `SEND_INTERVAL_SECONDS`마다 UDP 송신.

- 로그 출력:
  - `CSV,TX,<node_id>,<seq>,<t0>,<joined>`
  - `CSV,RTT,<seq>,<t0>,<t_ack>,<rtt_ticks>,<len>`
  - `CSV,PARENT,<node_id>,<parent_ip|none|unknown>`
  - `CSV,LLADDR,<node_id>,<lladdr>`

- 관련 매크로/상수:
  - `SEND_INTERVAL_SECONDS`, `WARMUP_SECONDS`, `TRUST_SCALE`, `TRUST_ENABLED`, `TRUST_SWITCH_THRESHOLD`.
  - 기본 전송 대상은 `set_forwarder()`로 결정되며, 신뢰도 기반 스위칭이 구현되어 있다.

### 3.2 Attacker (Selective Forwarding 공격자)

- 파일: `motes/attacker.c`
- 역할: 루트로 전달되는 UDP 트래픽을 확률적으로 드롭.
- 주요 동작 흐름:

1. `ATTACK_DROP_PCT`로 공격 강도를 설정.
2. `ip_output()` 훅에서 패킷을 필터링.
3. 루트 목적지 UDP 패킷만 대상.
4. `handle_trust_input()`에서 trust를 받아 블랙리스트에 반영.
5. `CSV,FWD`를 주기적으로 출력해 전달률/드롭율을 로그로 남김.

- 로그 출력:
  - `CSV,FWD,<node_id>,<fwd_total>,<udp_to_root>,<dropped>`
  - `CSV,PARENT,<node_id>,<parent_ip|none|unknown>`
  - `CSV,LLADDR,<node_id>,<lladdr>`

- 공격 대상 식별:
  - UDP 포트 `8765`, 목적지 `aaaa::1`.
  - `ATTACK_WARMUP_SECONDS` 이후 공격 활성화.

### 3.3 Receiver Root (RPL Root)

- 파일: `motes/receiver_root.c`
- 역할: RPL 루트 설정 및 UDP 수신/로그.
- 주요 동작:

1. 루트 주소 `aaaa::1` 및 prefix `aaaa::/64` 설정.
2. `NETSTACK_ROUTING.root_start()`로 루트 시작.
3. 수신된 패킷에 대해 `CSV,RX` 로그 출력.
4. Echo 패킷을 송신해 송신자 RTT 계산에 활용.

- 로그 출력:
  - `CSV,RX,<src_ip>,<seq>,<t_recv>,<t0>,<len>`

- 신뢰도 계산은 수행하지 않는다. Trust 계산은 외부 `trust_engine`에서 수행.

### 3.4 Trust/Blacklist 모듈

- Trust stub
  - 파일: `motes/brpl-trust.c`, `motes/brpl-trust.h`
  - `brpl_trust_override()`는 외부에서 주입된 trust 값을 parent 단위로 저장한다.
  - trust가 `TRUST_PARENT_MIN`보다 낮으면 해당 parent를 RPL parent table에서 제거하여 필터링한다.
  - BRPL weight 계산 로직 자체는 변경하지 않고, parent 후보군을 trust 정책으로 제한한다.

- Blacklist
  - 파일: `motes/brpl-blacklist.c`, `motes/brpl-blacklist.h`
  - 노드 ID 기반 리스트 관리 (`BLACKLIST_MAX_NODES`, 기본 32).
  - `brpl_blacklist_should_drop_packet()`로 전송 패킷 필터.
  - trust 임계값은 `BLACKLIST_TRUST_THRESHOLD` (기본 700)로 설정.

## 4. 네트워크/라우팅 설정 (project-conf.h)

- 파일: `project-conf.h`
- 목적: Contiki-NG 빌드 시 공통 설정 제공.

핵심 설정:

- `BRPL_CONF_ENABLE 1`: BRPL 활성화.
- `RPL_CONF_SUPPORTED_OFS {&rpl_brpl}`: BRPL objective function 지정.
- `NETSTACK_CONF_ROUTING rpl_classic`: BRPL 사용을 위해 RPL-Classic 강제.
- `UIP_CONF_ROUTER 1`: 비루트 노드에서 IPv6 포워딩 활성화.
- DIO 파라미터 튜닝: 빠른 컨버전스를 위해 `RPL_CONF_DIO_INTERVAL_MIN` 등 수정.
- Trust 파라미터: `TRUST_SCALE`, `TRUST_ALPHA_NUM/DEN`, `TRUST_PARENT_MIN` 등 정의.
- CSV 로깅 샘플링: `CSV_LOG_SAMPLE_RATE`로 버퍼 오버플로우 방지.

## 5. Cooja 시뮬레이션 구성 (configs/)

### 5.1 기본 토폴로지

- 파일: `configs/simulation.csc`
- 노드 구성:
  - Node 1: Root (0,0)
  - Node 2: Relay (40,20)
  - Node 3: Attacker (40,0)
  - Node 4~8: Sender (80,0), (80,20), (80,-20), (90,15), (90,-15)

- 라디오 매체:
  - UDGM
  - Tx range 50m, interference 100m

### 5.2 모트 타입 정의

- `attacker_type`: `motes/attacker.c` 빌드
- `relay_type`: `motes/attacker.c`를 공격 비활성(`ATTACK_DROP_PCT=0`)으로 빌드
- `sender_type`: `motes/sender.c`
- `root_type`: `motes/receiver_root.c`

### 5.3 Trust 피드백 주입 (Cooja ScriptRunner)

- `@TRUST_FEEDBACK_PATH@` 파일을 주기적으로 폴링.
- `TRUST,<node>,<value>` 라인을 각 모트의 로그 인터페이스로 write.
- 결과적으로 `serial_line_event_message`가 발생하고, sender/attacker가 trust 값을 처리.

## 6. 실험 실행 파이프라인 (scripts/)

### 6.1 통합 실험 실행

- 파일: `scripts/run_experiments.sh`
- 기능 요약:
  - 시나리오 매트릭스 생성(MRHOF/BRPL, 공격 여부, Trust 여부)
  - Cooja config 생성/치환
  - 필요 시 `tools/trust_engine` 빌드
  - Headless Cooja 실행
  - 로그 파싱 및 요약 CSV 생성

- 주요 출력:
  - `results/experiments-YYYYMMDD-HHMMSS/...`
  - `experiment_summary.csv` (PDR, delay, tx/rx 등 요약)
  - `trust_metrics.csv`, `blacklist.csv` (trust_engine 출력)

### 6.2 단일 시나리오 테스트

- 파일: `scripts/single_test.sh`
- 목적: 빠른 토폴로지 검증 및 기본 공격 효과 확인.
- 핵심 로직은 `run_experiments.sh`의 축약 버전.

### 6.3 토폴로지 생성기

- 파일: `scripts/gen_random_topology.py`
- 랜덤 노드 배치로 `.csc` 생성.
- 연결성 보장 로직(각 노드는 기존 노드 중 하나와 Tx range 내).
- 공격자 위치 고정 옵션 지원.

### 6.4 분석 스크립트

- 파일: `scripts/analyze_results.R`
- 결과 요약 CSV(`experiment_summary.csv`)로부터 다음 산출물을 생성:
  - `docs/report/figure1_normal.png`
  - `docs/report/figure2_attack.png`
  - `docs/report/figure3_defense.png`
  - `docs/report/figure4_trust.png`
  - `docs/report/table1_overhead.csv`
  - 추가 그림(figure5~figure9)

## 7. Trust Engine 아키텍처 (tools/trust_engine)

- 파일: `tools/trust_engine/src/main.rs`
- 입력: Cooja 로그 파일(기본 `COOJA.testlog`) 또는 Serial Socket.
- 출력:
  - trust 업데이트 파일(`TRUST,<node>,<value>`)
  - trust 메트릭 CSV (`trust_value`, `trust_raw` 포함)
  - 블랙리스트 CSV (`trust_value`, `trust_raw` 포함)

- 계산 흐름:
  - `CSV,FWD` 라인을 읽어 forwarder의 성공/실패 비율 계산.
  - Beta 기반 신뢰 추정 후 EWMA로 시간적 평활화.
  - Bayes/Beta/EWMA 출력 모드는 선택 가능.
  - 임계값 미달 시 블랙리스트 처리(신뢰도 0으로 출력).

Beta + EWMA 신뢰 추정식:

- `T_j = (alpha0 + s_j) / (alpha0 + beta0 + s_j + f_j)`
- `T_j(t) = lambda * T_j(t-1) + (1 - lambda) * T_j`

- 기본 설정값:
  - `--metric ewma`, `--alpha 0.2`, `--ewma-min 0.7` 등.

## 8. 로그/데이터 포맷

모든 메트릭은 CSV 라인으로 로그에 기록된다.

- `CSV,TX,<node_id>,<seq>,<t0>,<joined>`: sender 전송 로그.
- `CSV,RX,<src_ip>,<seq>,<t_recv>,<t0>,<len>`: root 수신 로그.
- `CSV,RTT,<seq>,<t0>,<t_ack>,<rtt_ticks>,<len>`: sender echo 수신 로그.
- `CSV,FWD,<node_id>,<fwd_total>,<udp_to_root>,<dropped>`: forwarder/attacker 통계.
- `CSV,PARENT,<node_id>,<parent_ip|none|unknown>`: preferred parent 기록.
- `CSV,RPL_PARENT,<self>,<new>,<old>,<rank>`: RPL preferred parent 변경 로그.
- `CSV,LLADDR,<node_id>,<lladdr>`: 링크 계층 주소.
- `CSV,TRUST_SET,<self>,<node>,<trust>`: trust 값 저장 이벤트.
- `CSV,TRUST_BLOCK,<self>,<node>,<trust>`: trust 정책에 의해 parent 제거.
- `CSV,BRPL_STATE,<self>,<qx>,<qmax>,<q_avg>,<rho>,<theta>,<pmax>`: BRPL 내부 상태.
- `CSV,BRPL_WEIGHT,<self>,<parent>,<qx>,<qy>,<qmax>,<p_tilde>,<p_norm>,<dq_norm>,<theta>,<weight>`: 부모 후보별 weight 구성 요소.
- `CSV,BRPL_BEST,<self>,<p1>,<w1>,<p2>,<w2>,<chosen>`: BRPL parent 비교/선택 로그.
- `CSV,BRPL_DIO,<self>,<parent>,<rank>,<q>,<qmax>,<valid>`: DIO 기반 neighbor queue 업데이트.
- `CSV,BRPL_TRUST,<self>,<parent>,<trust>,<trust_min>,<gamma>,<weight_trust>`: trust penalty 적용 결과.

`tools/parse_results.py`는 위 로그를 분석해 다음을 계산한다.

- PDR (Packet Delivery Ratio)
- 평균 지연(지연은 RTT/2로 추정)
- RPL 제어 패킷 오버헤드
- Exposure (공격자 경유 비율)

## 9. BRPL/Trust 통합의 실제 동작 범위

이 프로젝트의 trust 반영은 다음 2단계에 집중되어 있다.

1. `trust_engine` → trust_feedback → serial input을 통해 모트에 trust 값 주입.
2. `brpl_trust_override()`가 trust 값을 저장하고 `TRUST_PARENT_MIN` 미만 parent를 제거한다.

추가로 BRPL weight 계산 마지막에 trust penalty를 곱해 반영한다:

- `W_trust = W_brpl * (T_j ^ gamma)`
- optional clamp: `T'_j = max(T_min, T_j)`

기본 파라미터: `TRUST_PENALTY_GAMMA=1`, `TRUST_MIN=300` (scale=1000 기준).

## 10. 빌드/실행 경로 요약

- 모트 빌드:
  - `motes/Makefile.sender`, `motes/Makefile.attacker`, `motes/Makefile.receiver`
  - `CONTIKI = ../contiki-ng-brpl`

- 실험 실행:
  - `scripts/run_experiments.sh`
  - `configs/simulation.csc` 템플릿 변환
  - Cooja headless 실행 → `COOJA.testlog` 생성

- 분석:
  - `tools/parse_results.py` (개별 로그 분석)
  - `scripts/analyze_results.R` (그림/표 생성)

## 11. 파일/구성 요소 목록 (빠짐없이 확인용)

- 루트 문서/설정:
  - `readme.md`
  - `project-conf.h`

- Contiki/BRPL:
  - `contiki-ng-brpl/` (서브모듈)

- 모트 애플리케이션:
  - `motes/attacker.c`
  - `motes/sender.c`
  - `motes/receiver_root.c`
  - `motes/brpl-trust.c`, `motes/brpl-trust.h`
  - `motes/brpl-blacklist.c`, `motes/brpl-blacklist.h`
  - `motes/Makefile.sender`, `motes/Makefile.attacker`, `motes/Makefile.receiver`

- 시뮬레이션/토폴로지:
  - `configs/simulation.csc`
  - `scripts/gen_random_topology.py`

- 실험 및 분석:
  - `scripts/run_experiments.sh`
  - `scripts/single_test.sh`
  - `tools/parse_results.py`
  - `scripts/analyze_results.R`
  - `tools/trust_engine/`

- 결과/보고서:
  - `results/`
  - `docs/report/`
  - `docs/report/report.md`

## 11. 최근 변경사항 (Change Log)

### 11.1 라우팅 스택 / 빌드
- RPL-Classic 강제 사용:
  - `motes/Makefile.sender`
  - `motes/Makefile.attacker`
  - `motes/Makefile.receiver`
- `project-conf.h`에서 `NETSTACK_CONF_ROUTING`을 강제로 `rpl_classic`으로 설정.

### 11.2 Trust 반영 방식
- `motes/brpl-trust.c`는 **trust 값 저장 + 조회**만 수행.
- BRPL weight 계산 마지막에 trust penalty 곱 적용:
  - `W_trust = W_brpl * (T_j ^ gamma)`
  - `T'_j = max(T_min, T_j)` clamp
  - 기본값: `TRUST_MIN=300`, `TRUST_PENALTY_GAMMA=1`
- 관련 로그 추가:
  - `CSV,BRPL_TRUST,<self>,<parent>,<trust>,<trust_min>,<gamma>,<weight_trust>`

### 11.3 Trust Engine 출력 포맷
- `tools/trust_engine` 출력 CSV 확장:
  - `trust_value` (0..1)
  - `trust_raw` (0..1000)

### 11.4 토폴로지 생성 및 파일
- 수동 좌표 기반 생성 스크립트 추가:
  - `scripts/gen_topology.py`
- 랜덤 생성 스크립트는 BRPL-only로 단순화:
  - `scripts/gen_random_topology.py`
- 표준 토폴로지 세트 추가:
  - CSV: `configs/topologies/T1_S.csv`, `T1_M.csv`, `T1_L.csv`, `T2_S.csv`, `T2_M.csv`, `T2_L.csv`, `T3.csv`
  - CSC: `configs/topologies/*.csc`
- `configs/`의 기존 임시/legacy `.csc` 정리.

### 11.5 테스트 자동화
- `scripts/single_test.sh`에서 `TRUST_ENABLED` 환경변수로 ON/OFF 제어.
- Trust ON/OFF 비교 실행 스크립트:
  - `scripts/compare_trust.sh`

### 11.6 CSV 로깅 확장
- BRPL 내부 상태/weight/선택/링크 메트릭 로그 추가:
  - `CSV,BRPL_STATE`, `CSV,BRPL_WEIGHT`, `CSV,BRPL_BEST`, `CSV,BRPL_DIO`, `CSV,BRPL_METRIC`
- RPL parent 변경 로그 추가:
  - `CSV,RPL_PARENT`

---

이 문서는 현재 레포의 실제 구현과 로그/신뢰도 루프를 기준으로 작성되었다. BRPL weight 계산 자체를 수정하는 변경이 들어갈 경우(예: trust 항 직접 곱/가중), 해당 변경 사항을 본 문서에 즉시 업데이트해야 한다.
- `CSV,BRPL_METRIC,<self>,<parent>,<link_metric>,<rank>,<p_tilde>`: BRPL 기본 링크/랭크 메트릭.
