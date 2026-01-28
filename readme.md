# Trust-Aware BRPL for Selective Forwarding Attack

## 연구 개요

**목표**: BRPL(RPL-lite 기반) + Trust 메커니즘을 통한 Selective Forwarding 공격 대응

### 주요 기능
- **공격 모델**: 확률적 Selective Forwarding (UDP 패킷 드롭)
- **Trust 계산**: Root에서 EWMA 기반 신뢰도 계산
- **방어 메커니즘**: 
  - Trust 기반 Parent 선택 제한 (BRPL OF)
  - Blacklist 기반 네트워크 계층 패킷 필터링
- **외부 Trust Engine**: Rust 기반 고급 trust 계산 및 이상 탐지
- **시뮬레이터**: Contiki-NG + Cooja

### 성능 지표
- PDR (Packet Delivery Ratio)
- RTT (Round-Trip Time)
- Parent 변경 횟수
- Trust Score 변화
- 공격자 탐지 시간

---

## 환경 설정

### 1. Contiki-NG 설치

```bash
git clone https://github.com/contiki-ng/contiki-ng.git
cd contiki-ng
git submodule update --init --recursive
```

### 2. 필요 패키지 설치

```bash
sudo apt-get update
sudo apt-get install -y build-essential gcc-arm-none-eabi default-jre
```

### 3. 환경 변수 설정

프로젝트에서 제공하는 스크립트 사용:
```bash
source scripts/setup_env.sh
```

또는 수동으로 설정:
```bash
export CONTIKI_NG_PATH=/home/dev/contiki-ng
```

### 4. 빌드

프로젝트 루트에서 빌드 스크립트 사용 (권장):
```bash
./scripts/build.sh
```

또는 개별 빌드:
```bash
cd motes
make -f Makefile.receiver TARGET=cooja
make -f Makefile.sender TARGET=cooja
```

---

## Cooja 시뮬레이션 실행

### 방법 1: Headless 모드 (권장)

자동으로 실행하고 결과 저장:

```bash
./scripts/run_simulation.sh [시간(초)] [csc_file]
```

예시:
```bash
./scripts/run_simulation.sh 600    # 10분 실행 (기본값)
./scripts/run_simulation.sh 1800   # 30분 실행
./scripts/run_simulation.sh 600 configs/simulation_random_brpl_centered.csc
```

실행 후 자동으로 `results/run-<timestamp>/COOJA.testlog` 파일 생성됨.

### 안정화 버전 (JVM 크래시 완화)

```bash
./scripts/run_simulation_stable.sh [시간(초)] [csc_file]
```

이 스크립트는 다음을 자동으로 설정:
- JVM 힙 크기 증가 (-Xmx4G -Xms2G)
- SerialSocketServer 비활성화
- Native access 경고 억제

### 방법 2: GUI 모드 (디버깅/시각화용)

```bash
./scripts/run_cooja_gui.sh
```

또는 수동으로:
```bash
cd $CONTIKI_NG_PATH
./gradlew run
# File → Open Simulation → configs/simulation.csc 선택
```1. 기본 분석

CSV 로그 파싱:
```bash
python3 tools/parse_results.py results/run-<timestamp>/COOJA.testlog
```

### 2. Trust 검증

Trust 기반 parent 선택 검증:
```bash
python3 tools/validate_trust_parent.py results/run-<timestamp>/COOJA.testlog
```

### 3. Blacklist 기능 테스트

Blacklist 동작 확인:
```bash
python3 tools/test_blacklist.py results/run-<timestamp>/COOJA.testlog
```

### 4. JVM 크래시 분석

Cooja 크래시 발생 시:
```bash
python3 tools/analyze_cooja_crash.py /tmp/hs_err_pid*.log
```

### 5. 배치 실험 통계

여러 시드 배치 실험 결과 요약:
```bash
Rscript tools/summary.R results/batch-<timestamp>
```

출력:
- `summary_stats.csv`: 통계 요약
- `plots/`: 시각화 그래프e  2: TX= 100, RX= 100, PDR=100.00%
Node  3: TX= 100, RX=  95, PDR= 95.00%
...

[2] End-to-End Delay (based        # BRPL Objective Function + Trust 필터링
├── project-conf.h                 # 프로젝트 설정
├── Makefile                       # 빌드 설정
├── .gitattributes                 # Git 언어 통계 설정
├── configs/                       # Cooja 시뮬레이션 파일
│   ├── simulation*.csc            # 다양한 시나리오
│   └── cooja_run.js               # Headless 제어 스크립트
├── scripts/
│   ├── run_simulation.sh          # 시뮬레이션 자동 실행
│   ├── run_simulation_stable.sh   # JVM 안정화 버전
│   ├── run_batch_compare.sh       # 배치 비교 실험
│   ├── run_cooja_gui.sh           # GUI 실행
│   ├── build.sh                   # 빌드 자동화
│   ├── setup_env.sh               # 환경 변수 설정
│   └── gen_random_topology.py     # 랜덤 토폴로지 생성
├── tools/
│   ├── parse_results.py           # 결과 분석
│   ├── summary.R                  # 배치 결과 통계
│   ├── validate_trust_parent.py   # Trust 검증
│   ├── test_blacklist.py          # Blacklist 테스트
│   ├── analyze_cooja_crash.py     # JVM 크래시 분석
│   └── trust_engine/              # Rust 기반 외부 Trust Engine
├── logs/                          # 실행 로그 (gitignore)
├── results/                       # 실험 결과 저장
├── motes/
│   ├── receiver_root.c            # Root 노드 (Sink)
│   ├── sender.c                   # Sensor 노드
│   ├── attacker.c                 # 공격 노드
│   ├── brpl-trust.h               # Trust API
│   ├── brpl-blacklist.h           # Blacklist API
│   ├── brpl-blacklist.c           # Blacklist 구현
│   ├── Makefile.receiver          # Root 빌드
│   ├── Makefile.sender            # Sender 빌드
│   └── Makefile.attacker          # Attacker 빌드
├── docs/
│   └── project_overview.md        # 상세 프로젝트 개요
└── readme.md        ation.csc     # Cooja 시뮬레이션 파일
│   ├── simulation_ref.csc # 참조 시뮬레이션
│   └── cooja_run.js        # Headless 제어 스크립트
├── scripts/
│   ├── run_simulation.sh  # 시뮬레이션 자동 실행
│  구현 완료 사항

### Phase 1: 공격 구현 (완료)
- [x] Selective Forwarding 공격 코드 (attacker.c)
- [x] 공격 확률 파라미터 설정 (ATTACK_DROP_PCT)
- [x] 포워딩 통계 로깅 (CSV,FWD)

### Phase 2: Trust 메커니즘 (완료)
- [x] Root에서 EWMA Trust 계산
- [x] BRPL OF의 Trust 기반 Parent 선택
- [x] Trust 값 로깅 및 모니터링
- [x] 외부 Trust Engine 연동
- [x] Blacklist 기반 패킷 필터링

### Phase 3: 검증 및 분석 (완료)
- [x] Trust→Parent 배제 검증 도구
- [x] JVM 크래시 원인 분석 및 완화
- [x] Blacklist 기능 테스트 도구
- [x] 배치 실험 자동화
- [x] 결과 분석 및 시각화

### 향후 개선 사항
- [ ] 다중 공격자 시나리오
- [ ] 다양한 공격 유형 (Rank Attack, Version Attack)
- [ ] 분산 Trust 계산
- [ ] Adaptive Trust 업데이트
- [ ] 에너지 소비 분석
## 다음 단계

### Phase 1: 공격 노드 구현
- [0] Selective Forwarding 공격 코드 작성
- [0] 공격 확률 파라미터 설정
- [ ] Node 3를 공격 노드로 지정

### Phase 2: Trust 메커니즘
- [주요 설정 파라미터

### project-conf.h
- `RPL_OF_BRPL`: BRPL OF 활성화 (1/0)
- `BRPL_WITH_TRUST`: Trust 필터링 활성화 (1/0)
- `TRUST_PARENT_MIN`: Parent 선택 최소 trust 임계값 (기본: 700)
- `TRUST_ALPHA`: EWMA 알파 값 (기본: 20, 실제 0.2)
- `SEND_INTERVAL_SECONDS`: 패킷 전송 주기 (기본: 30초)
- `WARMUP_SECONDS`: 네트워크 안정화 시간 (기본: 120초)

### brpl-blacklist.h
- `BLACKLIST_MAX_NODES`: 최대 blacklist 크기 (기본: 32)
- `BLACKLIST_TRUST_THRESHOLD`: Blacklist 추가 임계값 (기본: 300)

### Makefile.attacker
- `ATTACK_DROP_PCT`: 패킷 드롭 비율 (기본: 50%)
- `ATTACK_ENABLED`: 공격 활성화 (1/0)

## 디버깅

### 로그 레벨 조정
```c
#define LOG_LEVEL_APP LOG_LEVEL_DBG
#define LOG_CONF_LEVEL_RPL LOG_LEVEL_DBG
```

### CSV 로그 포맷
- `CSV,TX,<node>,<seq>,<t0>,<joined>` - 패킷 전송
- `CSV,RX,<ip>,<seq>,<t_recv>,<len>` - 패킷 수신
- `CSV,RTT,<seq>,<t0>,<t_ack>,<rtt>,<len>` - Round-trip time
- `CSV,PARENT,<node>,<parent_ip>` - Parent 선택
- `CSV,TRUST,<node>,<seq>,<missed>,<trust>` - Trust 계산
- `CSV,TRUST_IN,<self>,<node>,<trust>` - Trust 업데이트 수신
- `CSV,FWD,<id>,<total>,<udp_to_root>,<dropped>` - 포워딩 통계
- `CSV,BLACKLIST_ADD,<node>,<count>` - Blacklist 추가
- `CSV,PKT_DROP_DEST,<node>` - 패킷 드롭

## 트러블슈팅

### 노드가 연결되지 않음
- WARMUP_SECONDS 증가 (예: 180초)
- Radio range 확인 (TX_RANGE, INTERFERENCE_RANGE)
- 토폴로지에서 노드 간 거리 확인

### 빌드 실패
- CONTIKI_NG_PATH 환경변수 확인
- `source scripts/setup_env.sh` 실행
- Contiki-NG가 올바르게 설치되었는지 확인

### Cooja 실행 실패 또는 크래시
- Java 버전 확인 (OpenJDK 11+ 또는 21 권장)
- JVM 힙 크기 증가: `export JAVA_OPTS="-Xmx4G"`
- 안정화 스크립트 사용: `./scripts/run_simulation_stable.sh`
- 크래시 로그 분석: `python3 tools/analyze_cooja_crash.py`

### Trust가 업데이트되지 않음
- Root에서 패킷 수신 확인 (CSV,RX 로그)
- 외부 Trust Engine 사용 시 logs/trust_updates.txt 생성 확인
- Serial input이 올바르게 파싱되는지 확인 (CSV,TRUST_IN 로그)

### Blacklist가 동작하지 않음
- Trust 값이 BLACKLIST_TRUST_THRESHOLD 이하로 떨어지는지 확인
- 외부 Trust Engine과 함께 사용 권장
- 테스트 도구로 확인: `python3 tools/test_blacklist.py`

## 상세 문서

프로젝트의 전체 구조, 동작 원리, 실험 방법 등 상세한 내용은 다음 문서를 참조하세요:
- [docs/project_overview.md](docs/project_overview.md) - 전체 프로젝트 개요
- [QUICKSTART.md](QUICKSTART.md) - 빠른 시작 가이드
- [memo.md](memo.md) - 개발 노트

### 트러블슈팅

**문제**: 노드가 연결되지 않음
- 해결: WARMUP_SECONDS 증가, Radio range 확인

**문제**: 빌드 실패
- 해결: CONTIKI_NG_PATH 환경변수 확인

**문제**: Cooja가 실행되지 않음
- 해결: Java 버전 확인 (OpenJDK 11+ 권장)


