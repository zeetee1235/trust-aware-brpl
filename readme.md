### Trust-Aware BRPL for Selective Forwarding Attack

## 연구 개요

**목표**: BRPL(RPL-lite 기반) + Trust 메커니즘을 통한 Selective Forwarding 공격 대응

### 성능 지표
- PDR (Packet Delivery Ratio)
- End-to-End Delay  
- Overhead (제어 패킷 수)

### 1단계 구현
- **공격 모델**: 확률적 Selective Forwarding
- **공격자 수**: 1개 노드
- **Trust 계산**: Sink 기준 EWMA
- **방어 방식**: Trust 기반 Parent 선택 제한
- **시뮬레이터**: Contiki-NG + Cooja

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
./scripts/run_simulation.sh [시간(초)]
```

예시:
```bash
./scripts/run_simulation.sh 600    # 10분 실행 (기본값)
./scripts/run_simulation.sh 1800   # 30분 실행
```

실행 후 자동으로 `logs/COOJA.testlog` 파일 생성됨.

### 방법 2: GUI 모드 (디버깅/시각화용)

```bash
./scripts/run_cooja_gui.sh
```

또는 수동으로:
```bash
cd $CONTIKI_NG_PATH
./gradlew run
# File → Open Simulation → configs/simulation.csc 선택
```

GUI 모드에서:
- Start 버튼 클릭하여 시뮬레이션 시작
- LogListener에서 로그 확인
- File → Save log to file로 로그 저장

---


## 결과 분석

### CSV 로그 파싱

```bash
python3 tools/parse_results.py logs/COOJA.testlog
```

출력 예시:
```
[1] PDR (Packet Delivery Ratio)
Node  2: TX= 100, RX= 100, PDR=100.00%
Node  3: TX= 100, RX=  95, PDR= 95.00%
...

[2] End-to-End Delay (based on RTT)
Average: 45.23 ms
Min:     12.50 ms
Max:    120.00 ms

[3] Overhead (Control Packets)
RPL packets: 250
Control/Data: 31.25%
```

---

## 파일 구조

```
trust-aware-brpl/
├── brpl-of.c              # BRPL Objective Function
├── project-conf.h         # 프로젝트 설정
├── Makefile               # 빌드 설정
├── configs/
│   ├── simulation.csc     # Cooja 시뮬레이션 파일
│   ├── simulation_ref.csc # 참조 시뮬레이션
│   └── cooja_run.js        # Headless 제어 스크립트
├── scripts/
│   ├── run_simulation.sh  # 시뮬레이션 자동 실행
│   ├── run_cooja_gui.sh   # GUI 실행
│   ├── build.sh           # 빌드 자동화
│   └── setup_env.sh       # 환경 변수 설정
├── tools/
│   └── parse_results.py   # 결과 분석 스크립트
├── logs/                  # 실행 로그 (gitignore)
├── motes/
│   ├── receiver_root.c    # Root 노드 (Sink)
│   ├── sender.c           # Sensor 노드
│   ├── Makefile.receiver  # Root 빌드
│   └── Makefile.sender    # Sender 빌드
└── readme.md              # 이 문서
```

---

## 다음 단계

### Phase 1: 공격 노드 구현
- [0] Selective Forwarding 공격 코드 작성
- [0] 공격 확률 파라미터 설정
- [ ] Node 3를 공격 노드로 지정

### Phase 2: Trust 메커니즘
- [0] Trust 값 계산 (EWMA)
- [0] Trust 기반 Parent 선택
- [ ] Root에서 Trust 모니터링

### Phase 3: 성능 평가
- [ ] 정상 vs 공격 시나리오 비교
- [ ] PDR, Delay, Overhead 측정
- [ ] 결과 시각화

---

## 참고사항

### BRPL 파라미터

`project-conf.h`에서 설정:
- `SEND_INTERVAL_SECONDS`: 패킷 전송 주기 (기본: 30초)
- `WARMUP_SECONDS`: 네트워크 안정화 시간 (기본: 120초)
- `BRPL_QUEUE_WEIGHT`: 큐 페널티 가중치

### 디버깅

로그 레벨 조정:
```c
#define LOG_LEVEL_APP LOG_LEVEL_DBG
#define LOG_CONF_LEVEL_RPL LOG_LEVEL_DBG
```

### 트러블슈팅

**문제**: 노드가 연결되지 않음
- 해결: WARMUP_SECONDS 증가, Radio range 확인

**문제**: 빌드 실패
- 해결: CONTIKI_NG_PATH 환경변수 확인

**문제**: Cooja가 실행되지 않음
- 해결: Java 버전 확인 (OpenJDK 11+ 권장)


■ 연구 주제 (초안)

    기존에 구현한 BRPL(RPL-lite 기반)을 활용한 Trust-aware Routing 기법 설계

    Selective Forwarding 공격 환경에서의 성능 비교

■ 연구 목표

    BRPL + CoAP 환경에서

        PDR

        End-to-End Delay

        Overhead를 기준으로 성능 비교

    Trust 기반 제어를 통해 공격 노드 회피 가능성 검증

■ 1단계 구현 계획

    공격 모델: 확률적 Selective Forwarding

    공격자 수: 1개 노드

    Trust 계산: Sink 기준 EWMA

    방어 방식: Trust 기반 Parent 선택 제한

    시뮬레이터: Contiki-NG + Cooja

    라우팅 계층은 기존에 구현해둔 RPL-lite 기반 BRPL 구조를 그대로 활용할 예정입니다.

■ 향후 확장 방향 (예정)

    공격자 수 증가에 따른 영향 분석

    Trust 전파 방식 개선

    BRPL 파라미터 변화에 따른 성능 비교
