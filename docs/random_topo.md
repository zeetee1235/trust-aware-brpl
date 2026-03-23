
핵심은 하나다.

> **고정 grid 한 장으로 승부 보는 설계는 버리고,
> 통제된 랜덤 토폴로지 분포 위에서 반복 평가하는 방식으로 가야 한다.**

이 방향은 그냥 감이 아니라, 실제 RPL 보안/신뢰 논문들의 한계를 반영한 거다. 기존 논문들 중에는 **단일 고정 배치**나 **랜덤 배치 1개** 수준이 여전히 많고, 최근 연구들도 공격자 위치와 토폴로지 조건이 결과를 크게 바꾼다고 본다. 즉, SCI급으로 가려면 **“특정 topology lucky case”를 피하는 설계**가 중요하다. ([PMC][1])

---

## 최종 설계 철학

논문 메시지는 이렇게 잡아라.

**“TA-BRPL은 특정 배치에서만 잘 되는 기법이 아니라, 다양한 LLN 연결 구조에서 일관되게 attacker exposure와 parent churn을 줄이고 during/recovery 성능을 개선한다.”**

이 메시지를 받쳐주려면 실험 단위가 **single topology**가 아니라 **topology distribution**이어야 한다. SMTrust 같은 논문도 랜덤 배치를 썼고, SRF-IoT는 랜덤 topology와 랜덤 seed 반복을 사용했지만, 여전히 다수 연구가 단일/소수 시나리오에 머문다. 네가 여기서 더 나아가 **많은 랜덤 토폴로지 + 반복 실행 + 통계 비교**로 가면 설계 수준이 한 단계 올라간다. ([PMC][1])

---

## 1. 연구 질문을 먼저 고정

논문은 기능 소개가 아니라 **가설 검증 구조**여야 한다.
RQ는 3개면 충분하다.

**RQ1.** TA-BRPL이 baseline RPL/BRPL 대비 공격 환경에서 **during/recovery PDR**을 유의하게 개선하는가?
**RQ2.** 그 개선이 **attacker exposure 감소**와 **parent churn 감소**를 동반하는가?
**RQ3.** 이 경향이 특정 topology 하나가 아니라 **여러 랜덤 토폴로지 분포 전반**에서 유지되는가?

가설은 이렇게 두면 된다.

* H1: TA-BRPL은 baseline 대비 during/recovery PDR를 개선한다.
* H2: TA-BRPL은 attacker exposure와 churn을 동시에 낮춘다.
* H3: 이 효과는 sparse/medium/dense 조건에서 방향성이 유지된다.

이 구조가 있어야 나중에 표와 그림이 전부 자연스럽게 묶인다.

---

## 2. 토폴로지 설계: “랜덤”이 아니라 “통제된 랜덤”

SCI급에서 중요한 건 무작정 랜덤이 아니라 **샘플링 규칙의 명시성**이다.

### 권장 원칙

노드 수는 네 현재 36이어도 되고 40, 50이어도 되지만, **논문 메시지상 핵심은 노드 수가 아니라 샘플링 규칙**이다. 아래를 명시해야 한다.

* 노드 배치는 **uniform random placement**
* root/sink 위치는 **고정 규칙** 사용
* 동일 노드 수에서 **배치 영역 크기만 조절**해 밀도를 나눔
* topology는 생성 후 **연결성 필터**를 통과한 경우만 채택
* 너무 sparse하거나 너무 dense한 경우는 제외

SMTrust는 30노드, 110m×110m, random positioning을 썼고, SRF-IoT도 random topology와 random seed를 사용했다. 최근 RPL 공격 분석들은 **공격자 위치와 네트워크 밀도**가 성능에 큰 영향을 준다고 본다. 따라서 네 실험은 처음부터 density와 placement bias를 설계 변수로 다뤄야 한다. ([PMC][1])

### 내가 권장하는 topology 군

토폴로지 그룹은 3개로 나눠라.

* **Sparse**
* **Medium**
* **Dense**

이건 node count를 바꾸는 게 아니라 **배치 면적 또는 평균 degree 목표**를 바꿔 만드는 게 좋다.
이유는 간단하다. RPL/BRPL 계열은 **대체 경로 수**와 **병목 형성 가능성**에 성능이 크게 좌우되고, 기존 문헌도 사실상 면적/밀도 차이로 서로 다른 난이도를 실험하고 있다. ([PMC][1])

---

## 3. topology seed와 run seed를 분리

이건 필수다.

랜덤 실험에서 seed를 하나만 쓰면 **토폴로지 랜덤성**과 **실행 랜덤성**이 섞인다.
SCI급으로 가려면 아래처럼 분리해야 한다.

* **Topology seed**: 노드 위치와 연결 구조 생성
* **Run seed**: 동일 topology에서 MAC/무선/타이밍 변동

### 권장 규모

* density 그룹당 topology seed: **20~30개**
* 각 topology당 run seed: **5~10개**

즉 density 3개 기준으로 보면,
최소도 **3 × 20 × 5 = 300 runs per protocol**이고,
좀 더 탄탄하게 가면 **3 × 30 × 10 = 900 runs per protocol**도 가능하다.

이때 **통계 표본 단위는 run이 아니라 topology 평균값**으로 잡아라.
같은 topology에서 5번 돌린 값을 먼저 평균내고, 그 평균들을 가지고 프로토콜 비교를 해야 한다. 그래야 같은 topology를 독립 표본처럼 과대평가하지 않는다. SRF-IoT도 random seed 반복을 썼고, 최근 연구 흐름도 다양한 시나리오를 반복 수집하는 쪽으로 가고 있다. ([MDPI][2])

---

## 4. topology 채택/제외 기준을 논문에 명시

이걸 안 쓰면 리뷰어가 바로 물고 늘어진다.

### 채택 기준 예시

* root에서 모든 정상 노드가 reachable
* 네트워크가 단절되지 않음
* 평균 neighbor degree가 사전 정의 범위 안에 있음
* baseline pre-phase PDR가 너무 낮은 topology는 제외
* 극단적으로 병목만 있는 topology는 별도 분석군으로 분리 가능

왜 이런 필터가 필요하냐면,
너무 sparse하면 baseline이든 proposed든 **다 같이 망하고**,
너무 dense하면 **다 같이 잘 돼서 차이가 안 난다**.
공정 비교를 위해서는 “실제 LLN으로서 의미 있는 topology 분포”를 정의해야 한다. 기존 연구에서도 배치 면적, range, 배치 방식으로 난이도를 사실상 조절한다. ([PMC][1])

---

## 5. 공격자 배치: 완전 랜덤 금지, 조건부 랜덤 추천

이 부분이 진짜 중요하다.

최근 연구들은 **공격자 위치가 PDR와 제어오버헤드에 큰 영향**을 준다고 분명히 말한다. sink 가까운 쪽이나 경유도가 높은 위치의 공격자가 훨씬 치명적이라는 보고가 있다. 그래서 공격자를 아무 non-root 노드나 랜덤으로 고르면, 어떤 실험은 너무 약하고 어떤 실험은 너무 강해져 분산이 커진다. ([MDPI][3])

### 권장 배치 방식

공격자는 **조건부 랜덤**으로 뽑아라.

1. pre-phase에서 실제 포워딩에 참여한 non-root 노드 집합 추출
2. 그중 forwarding count, parent selection frequency, centrality가 높은 상위 후보군 구성
3. 그 후보군 안에서 랜덤으로 공격자 선택

이렇게 하면:

* leaf 공격자처럼 영향 없는 샘플을 줄일 수 있고
* 반대로 항상 같은 choke-point만 고정하는 인위성도 줄일 수 있다

즉, **공정하면서도 충분히 어려운 공격 배치**가 된다.

---

## 6. 비교 프로토콜 설계

메인 실험은 과하게 벌리지 마라.
SCI급에서 더 중요한 건 **깊이**지, 프로토콜 이름 개수가 아니다.

### 메인 비교군

* **RPL (MRHOF + ETX)**
* **BRPL**
* **TA-BRPL**

이 3개면 충분하다.

### Ablation은 별도

* TA-BRPL without stabilization
* * switch margin
* * dwell
* * suspect reroute
* full version

이렇게 가면 메인 메시지는 깔끔하고,
기여도 분해는 ablation으로 처리할 수 있다.

---

## 7. 지표 설계: PDR 하나로는 약하다

실제 관련 논문들도 packet loss, throughput, topology stability, parent switch 같은 지표를 함께 본다. SRF-IoT는 PDR, dropped packets, parent switches, overhead를 같이 봤고, SMTrust는 topology stability, packet loss, throughput, power consumption을 같이 봤다. ([MDPI][2])

네 논문 메인 지표는 아래 4개가 맞다.

* **During PDR**
* **Recovery PDR**
* **Attacker exposure**
  (패킷 기준인지, 경로 기준인지 정의를 문서에 명시)
* **Parent churn**

보조 지표는:

* pre-phase PDR
* control overhead
* fallback frequency
* usable parent count
* dropped packet ratio

즉, 논문 메시지는
“PDR가 조금 올랐다”가 아니라
**“attacker exposure와 churn을 동시에 낮추면서 during/recovery 성능을 개선했다”**로 가야 한다.

---

## 8. 통계 처리: 평균만 쓰면 약하다

SCI급이면 최소한 아래는 있어야 한다.

* **mean ± 95% CI**
* **median + IQR**
* **boxplot / violin plot / CDF**
* **win rate**
  (전체 topology 중 baseline보다 좋은 비율)

그리고 비교는 **paired test**가 자연스럽다.
같은 topology 세트에서 RPL, BRPL, TA-BRPL을 모두 돌리므로:

* paired t-test
* 또는 Wilcoxon signed-rank test

이걸 써서 “통계적으로 유의한가”를 보여줘라.

### 아주 좋은 추가 지표

* **Topology win rate**: TA-BRPL이 BRPL보다 나은 topology 비율
* **Effect size**: Cohen’s d 또는 Cliff’s delta

이거까지 넣으면 실험 파트가 확 강해진다.

---

## 9. 실험 규모: SCI급으로 보이는 최소선

현실적으로 추천하는 두 단계다.

### 파일럿

* density 3개
* topology 10개씩
* run 3개씩
* protocol 3개

여기서 variance, 생성 규칙, attacker placement를 점검한다.

### 본 실험

* density 3개
* topology 25개씩
* run 5개씩
* protocol 3개

그러면 총 **375 runs per protocol**,
3개 프로토콜이면 **1125 runs**다.

이 정도면 “무식하게 많이 돌렸다”가 아니라
**설계적으로 충분히 반복된 연구**로 보인다.

---

## 구현 반영 (코드 기준)

아래 설계가 코드로 반영되어 있다.

- `scripts/generate_random_topologies.py`
  - density 그룹(`sparse/medium/dense`)별 면적 설정
  - `topology seed` 기반 위치 생성 (root는 중앙 고정)
  - 연결성(root에서 전 노드 도달) + 평균 degree 범위 필터
  - 공격자 노드: 고중심성 후보군(top fraction)에서 조건부 랜덤 선택
  - 프로토콜별 `.csc` 시나리오 생성 + `manifest.json` 출력

- `scripts/run_random_topo_sweep.sh`
  - 토폴로지 생성기 호출 후 manifest 기반 잡 큐 구성
  - `density × topology seed × run seed × protocol` 워커풀 실행
  - run seed는 실행 시 `.csc`의 `<randomseed>`만 패치해 분리 유지
  - 출력: `results/random_topo/<density>/<topology>/<protocol>/<run_seed>/sim.log`

### 실행 예시

파일럿(빠른 검증):

```bash
./scripts/run_random_topo_sweep.sh \
  --protocols RPL,BRPL,TABRPL \
  --densities sparse,medium,dense \
  --topology-seeds 1-3 \
  --run-seeds 1-2 \
  --jobs 12 \
  --rerun
```

본 실험(문서 권장 스케일):

```bash
./scripts/run_random_topo_sweep.sh \
  --protocols RPL,BRPL,TABRPL \
  --densities sparse,medium,dense \
  --topology-seeds 1-25 \
  --run-seeds 1-5 \
  --jobs 12 \
  --rerun
```

사전 확인(dry-run):

```bash
./scripts/run_random_topo_sweep.sh \
  --protocols TABRPL \
  --densities medium \
  --topology-seeds 1-2 \
  --run-seeds 1-2 \
  --jobs 4 \
  --dry-run
```

### 현재 스모크 테스트 상태

- `TABRPL, medium, topology_seed=1, run_seed=1` 1건 실행 완료
- 결과 로그 생성 확인:
  - `results/random_topo/medium/topo_001/TABRPL/1/sim.log`

## 10. 논문용 그림/표 구성

이렇게 가면 된다.

### 표

* Table 1: network/simulator configuration
* Table 2: topology generation rules
* Table 3: attacker selection policy
* Table 4: metrics definitions
* Table 5: aggregate results by density

### 그림

* Fig. 1: evaluation workflow
* Fig. 2: example sparse / medium / dense topologies
* Fig. 3: during PDR boxplots
* Fig. 4: recovery PDR boxplots
* Fig. 5: attacker exposure CDF
* Fig. 6: parent churn comparison
* Fig. 7: win rate by density
* Fig. 8: ablation summary

이 정도면 결과 파트가 SCI 논문답게 보인다.

---

## 11. 네 논문에서 써야 할 설계 문장

논문 본문에는 거의 이런 식으로 들어가면 된다.

> To avoid topology-specific bias, we evaluate all protocols over a distribution of randomly generated LLN topologies rather than a single fixed deployment.
> The topology randomness is separated from runtime randomness by using distinct topology seeds and run seeds.
> We further stratify the evaluation by network density and use a constrained attacker selection policy to ensure comparable attack severity across scenarios.

이 서술은 지금 문헌들의 약점을 정확히 보완하는 포인트다. 기존 연구들에서 random deployment는 흔하지만, 공격자 위치와 토폴로지 조건이 결과를 크게 바꾸고, 단일/소수 시나리오에 의존하는 경우가 많다. ([PMC][1])

---

## 최종 권장안

딱 한 줄로 정리하면:

> **SCI급으로 가려면, “grid에서 잘 됨”이 아니라
> “랜덤 topology 분포 전체에서 일관되게 이김”을 보여주는 설계로 가라.**

실행안은 이거다.

* single fixed topology 폐기
* sparse / medium / dense 3군
* 군당 topology 20~30개
* topology당 run 5~10개
* topology seed / run seed 분리
* 연결성/난이도 필터 적용
* 공격자는 central forwarding 후보군에서 조건부 랜덤 선택
* 메인 비교군은 RPL / BRPL / TA-BRPL
* 메인 지표는 during PDR / recovery PDR / attacker exposure / churn
* 결과는 topology 평균 기준으로 통계 비교
* 평균, CI, win rate, effect size까지 포함



[1]: https://pmc.ncbi.nlm.nih.gov/articles/PMC9506070/ "
            A Trust-Based Model for Secure Routing against RPL Attacks in Internet of Things - PMC
        "
[2]: https://www.mdpi.com/2624-800X/2/1/9 "A Trust-Based Intrusion Detection System for RPL Networks: Detecting a Combination of Rank and Blackhole Attacks | MDPI"
[3]: https://www.mdpi.com/2624-831X/7/1/4 "Trust-Aware Distributed and Hybrid Intrusion Detection for Rank Attacks in RPL IoT Environments"
