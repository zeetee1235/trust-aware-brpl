# JVM 크래시 해결 방법

## 문제 분석
Cooja 시뮬레이터에서 `ContikiRS232` 버퍼 오버플로우와 native 코드 SIGSEGV 발생

## 적용된 해결책

### 1. CSV 로그 출력 최소화 (완료)
- `CSV_VERBOSE_LOGGING` 플래그 추가 (기본값: 0)
- TRUST_IN, BLACKLIST 관련 빈번한 로그를 조건부 컴파일
- INJECT TRUST 로그 비활성화

### 2. 로그 레벨 낮춤 (완료)
- `LOG_LEVEL_APP`, `LOG_CONF_LEVEL_RPL`, `LOG_CONF_LEVEL_IPV6` → `LOG_LEVEL_WARN`

### 3. 추가 권장 사항

#### A. 짧은 시간 시뮬레이션 실행
```bash
# 60초 실행
./scripts/run_simulation.sh 60

# 120초 실행  
./scripts/run_simulation.sh 120
```

#### B. 배치 실행으로 여러 짧은 시뮬레이션 실행
```bash
for i in {1..5}; do
  ./scripts/run_simulation.sh 60
  sleep 2
done
```

#### C. Verbose 로깅이 필요한 경우
```bash
# DEFINES에 CSV_VERBOSE_LOGGING=1 추가
make -C motes -f Makefile.sender TARGET=cooja DEFINES=BRPL_MODE=1,CSV_VERBOSE_LOGGING=1
```

#### D. 시뮬레이션 스피드 조정
시뮬레이션 파일 (.csc)에서 속도 조정:
- 더 느린 속도로 실행하면 RS232 버퍼 압박 감소
- 하지만 실제 시간은 더 오래 걸림

## JVM 크래시가 발생하는 근본 원인

Cooja의 `ContikiRS232` JNI 인터페이스가 대량의 printf 출력을 처리할 때:
1. RS232 버퍼가 가득 참
2. Native 코드에서 버퍼 오버플로우 발생
3. `doInterfaceActionsBeforeTick` 함수에서 SIGSEGV

이는 Cooja/Contiki-NG의 알려진 한계이며, 현재 환경에서는:
- **가장 효과적인 해결책: 시뮬레이션 시간을 짧게 (60-120초) 유지**
- **여러 번 실행하여 데이터 수집**

## 기존 성공한 시뮬레이션

`results/batch-20260129-013513/` 폴더에는 성공적으로 완료된 배치 실행 결과가 있습니다.
이 결과를 분석에 활용할 수 있습니다.

## 참고
- 대부분의 데이터는 CSV 형식으로 출력되므로, verbose 로깅 없이도 분석 가능
- RTT, TRUST, PDR 등 핵심 지표는 여전히 로그됨
