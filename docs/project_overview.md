# Project Overview: Trust-Aware BRPL (Selective Forwarding)

## 목적
- BRPL(RPL-lite 기반) 환경에서 Selective Forwarding 공격을 시뮬레이션하고, Trust 기반 방어/평가를 수행한다.
- Cooja 시뮬레이터를 사용해 실험을 자동화하고 로그를 수집/분석한다.
- 외부 Trust Engine(Rust)을 통해 로그 기반 trust 계산 및 피드백 주입을 지원한다.

## 전체 구조 요약
```
trust-aware-brpl/
├── brpl-of.c                  # BRPL OF(ETX+Queue penalty) + Trust 필터링
├── project-conf.h             # BRPL 모드, Trust 파라미터, 로그 레벨
├── configs/                   # Cooja 시뮬레이션(.csc)
├── motes/                     # Root/Sender/Attacker mote 코드
├── scripts/                   # 실행/배치/토폴로지 생성 스크립트
├── tools/                     # 결과 분석 + 외부 Trust Engine
├── logs/                      # 실행 로그 (gitignore)
├── results/                   # 각 실행 결과 저장
├── docs/                      # 문서
└── readme.md                  # 기본 사용 안내
```

## 핵심 기능
### 1) 공격 시나리오 (Selective Forwarding)
- 공격 노드(attacker)가 **포워딩되는 UDP 패킷을 확률적으로 드롭**
- 드롭 대상: Root(aaaa::1)로 전달되는 UDP(포트 8765)
- 드롭 비율은 빌드 정의(ATTACK_DROP_PCT)로 제어
- 공격 상태/통계 로그 출력

### 2) Trust 계산 (내장)
- Root(receiver_root.c)에서 수신 seq 기반 **EWMA trust** 계산
- 계산식(요약)
  - missed = (seq gap)
  - sample = TRUST_SCALE / (1 + missed)
  - trust = alpha*sample + (1-alpha)*prev
- 로그: `CSV,TRUST,<node_id>,<seq>,<missed>,<trust>`

### 3) Trust 기반 Parent 선택 (BRPL OF)
- BRPL OF에서 **trust < TRUST_PARENT_MIN** 인 이웃을 parent 후보에서 배제
- ETX + queue penalty 기반 path cost와 결합

### 4) 외부 Trust Engine (Rust)
- Cooja 로그를 파싱하여 EWMA / Bayesian / Beta reputation 계산
- Trust 업데이트를 `logs/trust_updates.txt`로 출력
- ScriptRunner가 해당 파일을 폴링해 mote에 `TRUST,<node>,<value>` 주입
- 이상 탐지/블랙리스트: 임계치 기반으로 trust=0 주입

## 주요 컴포넌트 상세

### A) BRPL Objective Function
- 파일: `brpl-of.c`
- 기능:
  - ETX 기반 링크 신뢰도 + queue penalty
  - trust_table 유지, TRUST_PARENT_MIN 기준으로 parent 후보 제한
  - trust override API 제공: `brpl_trust_override()`

### B) Root (Sink)
- 파일: `motes/receiver_root.c`
- 기능:
  - RPL root 설정, UDP receiver
  - seq/RTT 로그 출력
  - EWMA trust 계산 및 CSV 출력

### C) Sender (Sensor)
- 파일: `motes/sender.c`
- 기능:
  - 주기적 UDP 전송 (seq + t0)
  - RTT 측정
  - preferred parent 로그
  - serial input으로 trust override 수신 (`TRUST,<node>,<value>`)

### D) Attacker
- 파일: `motes/attacker.c`
- 기능:
  - 포워딩 UDP 패킷 selective drop
  - preferred parent 로그
  - forwarding 통계(`CSV,FWD`)
  - serial input으로 trust override 수신

## 로그 포맷 요약
- 송신: `CSV,TX,<node>,<seq>,<t0>,<joined>`
- 수신: `CSV,RX,<ip>,<seq>,<t_recv>,<len>`
- RTT: `CSV,RTT,<seq>,<t0>,<t_ack>,<rtt>,<len>`
- Parent: `CSV,PARENT,<node>,<parent_ip|none>`
- Trust (root): `CSV,TRUST,<node>,<seq>,<missed>,<trust>`
- Trust override (mote): `CSV,TRUST_IN,<self>,<node>,<trust>`
- Forwarding stats: `CSV,FWD,<id>,<total>,<udp_to_root>,<dropped>`

## 시뮬레이션 설정
- 랜덤 토폴로지 생성기: `scripts/gen_random_topology.py`
  - 노드 수, 영역 크기, seed, 공격자 위치 고정 가능
- 기본 랜덤 시나리오(csc)
  - `configs/simulation_random_brpl_centered.csc`
  - `configs/simulation_random_brpl_centered_no_attack.csc`
  - `configs/simulation_random_mrhof_centered.csc`
  - `configs/simulation_random_mrhof_centered_no_attack.csc`

## 실행 스크립트
- `scripts/run_simulation.sh`
  - headless Cooja 실행
  - 결과를 `results/run-<timestamp>/`에 저장
  - `logs/COOJA.testlog` 생성
- `scripts/run_batch_compare.sh`
  - BRPL/MRHOF ON/OFF 여러 시드 배치 실행
  - 결과를 `results/batch-<timestamp>/` 구조로 저장

## 결과 분석
- Python: `tools/parse_results.py`
- R 요약: `tools/summary.R`

## 외부 Trust Engine (Rust)
- 위치: `tools/trust_engine`
- 기능
  - log 파싱(파일/serial socket)
  - EWMA/Bayes/Beta trust 계산
  - trust_updates.txt 출력
  - 이상탐지/블랙리스트 기록
- 출력
  - `logs/trust_updates.txt`
  - `logs/trust_metrics.csv`
  - `logs/blacklist.csv`

## 현재 상태 요약
- Selective forwarding 공격 구현 완료
- BRPL/MRHOF 기본 비교 실험 진행 중
- 외부 Trust Engine 연동(파일 폴링) 동작 확인
- headless 환경에서 SerialSocketServer는 제한되어 비활성화 필요

## 완료된 개선 사항
### ✅ BRPL OF 로그 기반 trust→parent 배제 검증 (완료)
- **검증 도구**: `tools/validate_trust_parent.py`
- **검증 결과**: Trust < TRUST_PARENT_MIN(700)인 노드는 parent로 선택되지 않음
- **사용법**: `python3 tools/validate_trust_parent.py results/run-*/COOJA.testlog`
- **주요 발견**:
  - Node 35가 trust=674로 임계값 이하로 떨어짐
  - 해당 노드는 parent로 선택되지 않음 확인
  - Trust 필터링이 정상 작동함

### ✅ Cooja headless 환경의 JVM 크래시 원인 분석 (완료)
- **분석 도구**: `tools/analyze_cooja_crash.py`
- **크래시 원인**: `doInterfaceActionsBeforeTick()` 함수의 SIGSEGV
  - Contiki-NG 네이티브 라이브러리의 메모리 액세스 위반
  - SerialSocketServer 플러그인의 headless 모드 불안정성
  - 다중 mote 타입 사용 시 race condition 발생
- **완화 방안**:
  1. SerialSocketServer 비활성화 (`export SERIAL_SOCKET_DISABLE=1`)
  2. JVM 힙 크기 증가 (`-Xmx4G -Xms2G`)
  3. Native access 경고 억제 (`--enable-native-access=ALL-UNNAMED`)
  4. 시뮬레이션 시간 단축 및 노드 수 감소
- **안정화 스크립트**: `scripts/run_simulation_stable.sh` 생성

### ✅ 패킷 필터링(blacklist drop) 네트워크 계층 추가 (완료)
- **구현 파일**: 
  - `motes/brpl-blacklist.h` - Blacklist API 정의
  - `motes/brpl-blacklist.c` - Blacklist 구현
- **주요 기능**:
  - Trust < BLACKLIST_TRUST_THRESHOLD(300)인 노드 자동 blacklist
  - 네트워크 계층에서 패킷 필터링 (`ip_output()` hook)
  - Blacklist된 노드로부터/노드로의 패킷 드롭
  - IPv6/Link-layer 주소 기반 필터링 지원
- **통합 위치**:
  - `sender.c`: Trust input 처리 시 자동 blacklist 추가/제거
  - `attacker.c`: 패킷 포워딩 전 blacklist 체크
- **로그 포맷**:
  - `CSV,BLACKLIST_ADD,<node>,<count>`
  - `CSV,BLACKLIST_REMOVE,<node>,<count>`
  - `CSV,PKT_DROP_DEST,<node>` or `CSV,PKT_DROP_SRC,<node>`
- **테스트 도구**: `tools/test_blacklist.py`
- **사용 예**:
  ```bash
  # Blacklist 동작 확인
  python3 tools/test_blacklist.py results/run-*/COOJA.testlog
  
  # Trust engine과 함께 사용
  ./trust_engine --threshold 300 --input logs/COOJA.testlog
  ```

## 검증 및 분석 도구
- `tools/validate_trust_parent.py` - Trust 기반 parent 선택 검증
- `tools/analyze_cooja_crash.py` - JVM 크래시 분석 및 완화 방안
- `tools/test_blacklist.py` - Blacklist 기능 테스트
- `tools/parse_results.py` - 시뮬레이션 결과 파싱
- `tools/summary.R` - 배치 결과 통계 분석
