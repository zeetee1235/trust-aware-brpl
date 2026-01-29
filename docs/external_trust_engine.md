# Trust-Aware BRPL: External Trust Engine Architecture

## 개요

Trust 계산이 이제 **외부 trust_engine**으로 완전히 위임되었습니다.

### 이전 구조
```
Mote (receiver_root.c)
  └── Trust 계산 (EWMA)
  └── Blacklist 관리
  └── Trust 피드백
```

### 새로운 구조
```
Mote (receiver_root.c)         Trust Engine (Rust)
  └── 패킷 수신 통계 수집   →    └── CSV,RX 로그 읽기
  └── CSV,RX 출력          →    └── Trust 계산 (EWMA/Bayes/Beta)
  └── TRUST 입력 수신      ←    └── 이상 탐지 & Blacklist
  └── Blacklist 적용       ←    └── TRUST 피드백 출력
```

## 장점

### 1. 성능 향상
- **경량 Mote**: 제한된 리소스의 IoT 노드에서 복잡한 계산 제거
- **고성능 계산**: Rust로 작성된 외부 엔진에서 빠르게 처리

### 2. 유연한 알고리즘
Trust engine은 여러 알고리즘 지원:
- **EWMA**: Exponentially Weighted Moving Average
- **Bayes**: Bayesian inference
- **Beta**: Beta distribution

### 3. 실시간 분석
- 로그 파일을 실시간으로 follow
- 동적으로 trust 업데이트
- 즉시 blacklist 판단

### 4. 확장성
- Trust 계산 로직을 mote 재컴파일 없이 변경 가능
- 새로운 알고리즘 추가 용이
- 다양한 파라미터 실험 가능

## 아키텍처

### Mote (Contiki-NG)

**receiver_root.c**
- RPL Root 역할
- UDP 패킷 수신
- CSV 형식으로 수신 정보 출력:
  ```
  CSV,RX,<sender_ipv6>,<seq>,<timestamp>,<len>
  ```
- Trust 피드백 입력 처리:
  ```
  TRUST,<node_id>,<trust_value>
  ```
- Blacklist 기반 패킷 필터링 (brpl-blacklist.c)

**sender.c / attacker.c**
- TRUST 입력을 받아 brpl_trust_override() 호출
- Trust 값 기반 parent 선택 (brpl-of.c)

### Trust Engine (Rust)

**입력**
- `logs/COOJA.testlog`: CSV,RX 로그 실시간 읽기
- 시뮬레이션 파라미터 (alpha, threshold 등)

**처리**
1. CSV,RX 라인 파싱
2. 각 노드별 패킷 수신 통계 추적
3. Missing packet 계산 (seq gap)
4. Trust 값 계산 (선택된 알고리즘)
5. Threshold 기반 이상 탐지

**출력**
- `logs/trust_updates.txt`: TRUST 피드백
  ```
  TRUST,<node_id>,<trust_value>
  ```
- `logs/trust_metrics.csv`: 상세 메트릭
  ```
  node_id,seq,missed,ewma,bayes,beta
  ```
- `logs/blacklist.csv`: Blacklist 이벤트
  ```
  node_id,seq,missed,ewma,bayes,beta
  ```

## 사용법

### 1. 외부 Trust Engine과 함께 실행

```bash
# 권장 방법 - 자동으로 trust_engine 실행
./scripts/run_with_trust_engine.sh 300

# 또는 시뮬레이션 파일 지정
./scripts/run_with_trust_engine.sh 300 configs/simulation_attack.csc
```

### 2. 수동 실행 (디버깅용)

터미널 1 - Trust Engine:
```bash
cd tools/trust_engine
cargo run --release -- \
  --input ../../logs/COOJA.testlog \
  --output ../../logs/trust_updates.txt \
  --metrics-out ../../logs/trust_metrics.csv \
  --blacklist-out ../../logs/blacklist.csv \
  --metric ewma \
  --alpha 0.2 \
  --ewma-min 700 \
  --miss-threshold 5 \
  --follow \
  --poll-ms 200
```

터미널 2 - Cooja:
```bash
./scripts/run_simulation.sh 300
```

### 3. Trust Engine 파라미터

```bash
--metric <ewma|bayes|beta>    # Trust 계산 알고리즘
--alpha <0..1>                 # EWMA smoothing factor (default: 0.2)
--ewma-min <value>             # EWMA threshold (default: 700)
--bayes-min <0..1>             # Bayes threshold (default: 0.3)
--beta-min <0..1>              # Beta threshold (default: 0.3)
--miss-threshold <n>           # Missing packet threshold (default: 5)
--follow                       # Follow log file (tail -f mode)
--poll-ms <ms>                 # Polling interval (default: 200)
```

## 데이터 흐름

```
1. Sensor 노드 → Root 노드
   UDP 패킷 전송: "seq=<n> t0=<timestamp>"

2. Root 노드 → Trust Engine
   CSV,RX,fd00::202,42,12345678,24
   (로그 파일에 기록)

3. Trust Engine 처리
   - seq gap 계산 (예: seq=40 → 42, missed=1)
   - EWMA 업데이트
   - Threshold 체크

4. Trust Engine → Mote
   TRUST,2,850
   (trust_updates.txt에 기록)

5. Simulation Script → Mote
   파일을 읽어서 각 mote에 주입
   (Cooja의 mote.getInterfaces().getLog().writeString())

6. Mote 내부
   - handle_trust_input()
   - brpl_trust_override()
   - Parent 선택 시 trust 고려 (brpl-of.c)
   - Blacklist 적용 (brpl-blacklist.c)
```

## 성능 고려사항

### RS232 버퍼 오버플로우 방지
- Trust 계산 로직이 mote에서 제거되어 **로그 출력 대폭 감소**
- 더 이상 `CSV,TRUST` 출력 불필요 (trust_engine이 계산)
- JVM 크래시 위험 감소

### 실시간성
- Trust engine은 200ms마다 로그 폴링
- 새로운 CSV,RX 발견 시 즉시 처리
- Trust 값은 1초 이내에 피드백

### 확장성
- Trust engine은 별도 프로세스로 실행
- 다중 시뮬레이션 동시 모니터링 가능
- 분산 처리 구조로 확장 가능

## 비교

### 이전 (내장 Trust)
- ✗ Mote 리소스 소모
- ✗ 알고리즘 변경 시 재컴파일 필요
- ✗ 제한된 알고리즘 (EWMA만)
- ✓ 낮은 지연시간

### 현재 (외부 Trust Engine)
- ✓ Mote 리소스 절약
- ✓ 알고리즘 동적 변경
- ✓ 다양한 알고리즘 지원
- ✓ 고급 분석 기능
- ✓ 로그 출력 감소로 안정성 향상
- ~ 약간의 지연 (200ms 폴링)

## 결론

외부 Trust Engine 아키텍처는:
- **보안 로직과 IoT 노드 분리** - 각자의 역할에 집중
- **유연한 실험 환경** - 다양한 알고리즘과 파라미터 테스트
- **실시간 분석** - 시뮬레이션 중 동적 모니터링
- **안정성 향상** - 로그 출력 감소로 JVM 크래시 방지

이는 실제 IoT 배포에서도 적용 가능한 구조입니다:
- Edge server에서 trust_engine 실행
- IoT 노드는 센싱과 전송에만 집중
- 중앙 서버에서 보안 의사결정
