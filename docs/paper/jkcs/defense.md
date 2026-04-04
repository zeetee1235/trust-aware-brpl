# TA-BRPL 논문 디펜스 질의응답 전체 기록

> 시뮬레이션 일시: 논문 디펜스 사전 준비  
> 역할: 심사위원/지도교수 (질문) ↔ 저자 (답변)  
> 논문: TA-BRPL: Trust-Aware Backpressure RPL for Mitigating Sinkhole-Induced Route Capture in Low-Power and Lossy Networks

---

## Q1. att_share 감소 1.7%p의 실용적 의미

### 심사위원 질문
> 논문에서 att_share 감소 ∆ = −0.0169를 핵심 성과로 제시하고 있다. 그런데 표 3을 보면 BRPL의 att_share 절대값이 0.110이다. 즉 TA-BRPL이 달성한 개선은 약 1.5~1.7%p 수준이다.  
> **이 수치가 실제 LLN 배치 환경에서 의미 있는 보안 개선이라고 주장할 근거가 있는가? 공격자가 여전히 전체 트래픽의 9% 이상을 장악하고 있는 상황에서, "경로 장악을 완화했다"는 주장이 실용적으로 타당한가?**

### 저자 답변
- TA-BRPL의 결과는 route capture의 **제거(elimination)가 아닌 통계적으로 유의한 감소(reduction)**
- BRPL 0.110 → TA-BRPL 0.093, 75개 topology-paired 비교에서 일관되게 관찰
- 잔여 att_share 9.3%가 남으므로 standalone 완전 방어로 해석 불가
- 주장 범위: "단일 sinkhole 조건의 LLN 시뮬레이션에서 공격자 의존도를 유의하게 낮추는 경량 완화책"으로 한정

### 심사위원 평가
> 솔직하고 방어적이지 않은 답변. 인정할 것은 인정하면서 주장의 범위를 명확히 한 점은 좋음.  
> **그러나 한계 인정 후 "그럼에도 기여는 X다"는 반격 논리가 부재.**

---

## Q2. "Lightweight" 표현의 검증 부재

### 심사위원 질문
> 세 가지 신뢰 신호(Tfwd, Tctrl, Thon)를 60초마다 계산하고, EWMA를 업데이트하고, review/blacklist 상태를 관리하는 연산이 배터리 기반 TelosB 수준의 센서 노드에서 실제로 "경량"이라는 주장을 어떤 근거로 하는가?  
> **에너지·지연 비용을 측정하지 않은 상태에서 "lightweight"라는 단어를 제목과 본문에 사용하는 것은 검증되지 않은 주장 아닌가?**

### 저자 답변
- `lightweight`는 실측으로 입증된 시스템 비용 claim이 아니라, "PKI/IDS/중앙 인프라 없이 BRPL 내부에 로컬 trust를 얹는다"는 **설계 의도**에 가까운 표현
- TelosB급 실노드에서 "경량"이라고 단정하는 것은 과함
- 구체적 문제점:
  - 60초마다 모든 이웃에 대해 trust 갱신
  - 최대 16개 이웃의 per-neighbor 상태 유지
  - 집계 함수가 `double`과 `pow()` 사용 → libm 링크 필요
  - FPU 없는 MSP430/TelosB (10KB RAM, 48KB Flash)에서 실측 없이 "경량"이라 보기 어려움
- 다만 완전히 근거 없는 표현도 아님:
  - 별도 trust 패킷 미전송
  - 기존 DIO/BRPL backlog 관측 재사용
  - 단, escape 시 DIO timer reset + DIS 송신 유발 → 제어 오버헤드 "0"도 아님

### 결론
- `lightweight` → `on-node`, `local`, `in-protocol`, `cryptography-free`로 교체 필요
- `main_v2.tex` 반영 완료:
  - Abstract: `lightweight trust penalty` → `on-node, cryptography-free trust penalty`
  - 결론부도 `lightweight defense`류 단정 표현 대신 설계적 표현으로 정리

### 추가 방어 증거
- 대표 사례 trust 시계열 그림 추가 완료:
  - `fig_jkcs_trust_timeseries.pdf`
  - 공격자 이웃에 대해 $T_{fwd}$, $T_{ctrl}$, $T_{hon}$, $T_{agg}$가 시간에 따라 어떻게 변하는지 직접 제시 가능
- 따라서 Q2/Q6 계열의 "trust가 실제로 어떻게 동작하는지 보이지 않는다"는 비판에는
  **정량 표 + 시계열 시각화**를 함께 제시하는 방식으로 대응 가능

---

## Q3. 가중치 (0.5/0.3/0.2)의 근거 부재

### 심사위원 질문
> 식 (5)의 가중치 (wf, wc, wh) = (0.5, 0.3, 0.2)의 근거가 무엇인가?  
> 논문 어디에도 이론적 도출이나 체계적인 sensitivity analysis가 없다.  
> **단순히 실험적으로 "잘 됐기 때문"이라면, 다른 네트워크 환경이나 공격 강도에서도 이 가중치가 최적이라는 보장이 있는가? 파라미터 튜닝 자체가 이 토폴로지 셋에 과적합된 것은 아닌가?**

### 저자 답변
- 이론적으로 도출된 최적 가중치가 아닌, **신호의 관측성·특이성에 대한 직관과 반복 실험을 통해 안정화한 경험적 operating point**
- 다른 네트워크 환경이나 공격 강도에서 최적이라는 보장 없음
- 체계적 sensitivity analysis와 held-out validation 없이 과적합 가능성 완전 배제 불가
- 랜덤 토폴로지 75쌍 실험으로 어느 정도 일반화 시도

### 현재 방어 가능 범위
- 원고에는 "최적 가중치"가 아니라 "경험적 operating point"라는 수준으로만 써야 안전
- 가중치 sensitivity heatmap을 추가 반영함:
  - `fig_jkcs_weight_sensitivity_heatmap.pdf`
  - 9쌍 miniset의 10개 국소 조합 모두에서 평균 `Δatt_share < 0`
  - 범위: 약 `-0.0174 ~ -0.0204`
- 따라서 디펜스에서는
  > "이 값은 이론적 최적점이 아니라 반복 실험으로 안정화한 operating point이며,
  > 9쌍 miniset의 탐색적 국소 sensitivity scan에서도 주변 조합 대비 특이점처럼 보이지는 않았다.
  > 다만 이는 메인 75쌍 실험과 동일한 증거 수준의 검증이 아니라 보조 진단이다."
  로 답하는 것이 가장 정직함

### 심사위원 평가
> 앞부분 인정은 좋음.  
> 그러나 "랜덤 토폴로지에서 실험했다", "fixed topology에서는 검증됐다"는 답변은 **과적합 문제를 비껴간 것**.  
> 핵심 문제: 75개 랜덤 토폴로지가 가중치 튜닝 시 사용한 데이터셋과 동일하거나 동일한 분포라면, 그 결과는 독립적인 검증이 아님.

---

## Q4. 파라미터 튜닝셋과 평가셋의 분리 문제

### 심사위원 질문
> **가중치 0.5/0.3/0.2를 결정하는 과정에서 사용한 토폴로지/시드와, 최종 성능을 보고한 75쌍 실험의 토폴로지/시드가 완전히 분리되어 있는가?**  
> 만약 동일한 실험 셋에서 파라미터를 조정하고 성능도 보고했다면, 이것은 train set으로 test한 것과 구조적으로 다르지 않다.

### 저자 답변
엄밀히는, 완전히 분리되어 있다고 말하기 어려움.

- **1차 분리는 있음**: 가중치(0.5/0.3/0.2)는 주로 고정 토폴로지(GRID6x6)에서 튜닝됨 → 랜덤 75쌍 메인셋에서 직접 고른 것은 아님
- **Strict hold-out은 아님**: ablation에 사용한 `topo_001~003`, `seed=1`이 최종 메인셋(`results/random_topo_main_v1`)에 포함
- tau sweep manifest(`topology_seeds=1..80`)와 최종 75쌍 메인셋(`topo_001..025`, `run-seed=1..5`) 토폴로지/시드 일부 겹침 확인

**가장 정직한 결론:**
> "고정 토폴로지 튜닝과 75쌍 랜덤 토폴로지 메인 실험은 1차적으로 분리되어 있지만, 전체 개발 과정 기준으로 최종 75쌍이 완전히 unseen test set은 아니다. **model-selection leakage와 optimistic bias 비판이 구조적으로 성립한다.**"

**원고 수정 방향:**
- "held-out generalization을 입증했다" 표현 삭제
- "고정 토폴로지에서 다듬은 설계를 부분적으로 겹치는 random-topology corpus에서 재현했다"로 하향

### 심사위원 평가
> 이 디펜스에서 가장 정직하고 완성도 높은 답변.  
> 코드 저장소 흔적까지 근거로 제시하고, "model-selection leakage"라는 표현으로 비판의 언어를 스스로 가져온 점이 신뢰를 줌.

---

## Q5. 혼잡 이점 보존의 미검증

### 심사위원 질문
> 방금 "혼잡 이점 + 보안 이점 = TA-BRPL"이라고 했다.  
> 그런데 논문 실험 설계에 혼잡(congestion) 시나리오가 없다.  
> **"혼잡 이점을 보존했다"는 주장을 어떻게 검증했는가? TA-BRPL의 trust penalty가 BRPL의 queue gradient 기반 부하 분산을 방해하지 않는다는 것을, 즉 혼잡 환경에서 BRPL 대비 열화가 없다는 것을 실험으로 보인 적이 있는가?**

### 저자 답변
- 현재 원고 기준으로 그 주장을 직접 검증했다고 보기 어려움
- 혼잡 유도 구간(200–300s, 송신률 2배)은 존재하나, 공식 평가 지표는 공격 구간의 att_share, hit_ratio, PDR_dur, churn뿐
- `pdr_pre`는 계산하나 paired summary 통계 검정에서 미포함
- 저장소에 혼잡을 끈 변형(`Makefile.tabrpl_nocongestion`)이 존재 → 저자 스스로 분리 실험 필요성 인식했으나 논문 본문 미보고

**정확한 주장 수준:**
> "brief congestion-induction phase가 포함된 공격 시나리오에서도 attack-phase PDR 비열세를 보였다"  
> "혼잡 이점을 보존했다"는 표현은 과함

### 추가 방어 증거
- `fig_jkcs_churn_att_scatter.pdf` 추가 완료
- H1(격리 개선)과 H3(churn 상한)의 관계를 75개 topology pair 수준에서 직접 시각화
- 전체적으로 `Δatt_share`와 `Δchurn`의 상관은 거의 0에 가까워,
  "att\_share를 줄이기 위해 churn을 희생했다"는 단순 교환관계로 보기는 어렵다는 점을 시각적으로 방어 가능

---

## Q6. 동급 보안 라우팅과의 직접 비교 부재

### 심사위원 질문
> 표 1에서 SecTrust-RPL, RFTrust, PCC-RPL을 비교해놓고, 실험에서는 단 하나도 직접 비교하지 않았다.  
> 표 1의 비교는 결국 구현도 재현도 없이 논문 텍스트만 읽고 만든 정성적 주장이다.  
> **이 상태에서 "기존 연구 대비 우월하다"는 함의를 독자에게 주는 것이 정당한가? 왜 Contiki-NG에서 이 중 하나라도 구현해 비교하지 않았는가?**

### 저자 답변
**정당성만 놓고 보면, 우월하다는 함의를 주는 것은 정당하지 않음.**

- 표 1은 "네 축 비교"로 규정한 **문헌 기반 포지셔닝 표**이며, 실험적 성능 비교표가 아님
- 방어 가능한 주장: "기존 연구와 다른 설계 위치를 차지한다"
- 방어 불가능한 주장: "기존 연구보다 성능상 우월하다"

**구현하지 않은 이유:**
- TA-BRPL은 BRPL 위에 직접 얹은 변형 → 가장 근접한 counterfactual baseline인 BRPL 대비 incremental contribution을 먼저 고립하려 함
- RFTrust/PCC-RPL은 별도 탐지/정책/튜닝을 가진 동급 보안 라우팅 → Contiki-NG에서 공정 재구현 및 파라미터 맞춤 공수가 별도 필요
- 단, 이는 비교를 못 한 이유일 뿐, **우월성 암시를 정당화하는 이유는 아님**

**원고 수정 방향:**
- 표 1 캡션에 "literature-based qualitative positioning; empirical comparison은 향후 과제" 명시
- 우월성 암시 문장 삭제 또는 완화

---

## Q7. 핵심 학술 기여 — "왜 Accept해야 하는가"

### 심사위원 질문
> 파라미터 과적합 가능성이 있고, 에너지 비용이 미측정이고, 혼잡 이점이 미검증이고, 절대적 방어 효과가 1.7%p 수준이고, 단일 공격자 UDGM 시뮬레이션에 한정된 이 논문이,  
> **기존 연구 대비 어떤 점에서 명확하고 반박하기 어려운 학술적 기여를 하는가? 한계 인정 말고, 기여로 답하라.**

### 저자 답변

**C1. 평가 프레임 재정의**
- sinkhole 평가의 1차 목표를 PDR → route capture 억제(att_share, hit_ratio)로 이동
- "얼마나 많이 떨어졌는가"보다 "얼마나 많이 장악됐는가"를 먼저 보는 평가 프레임을 명시
- 개념적 기여로서 후속 연구가 채택 가능한 평가 기준 제시

**C2. 설계 기여**
- trust를 별도 IDS가 아닌 BRPL 점수 내부에 소프트 패널티로 직접 결합
- hard exclusion은 review/blacklist로 분리하여 이분법 탈피
- 비대칭 EWMA + switch-margin + dwell로 trust-aware routing과 stability control을 하나의 라우팅 설계로 통합

**C3. 부정적 실증 결과 (가장 과소평가된 기여)**
- 표 3에서 RPL(0.110)과 BRPL(0.110)의 att_share가 거의 동일
- **backpressure와 queue-awareness만으로는 sinkhole route capture가 자동 완화되지 않는다**는 사실의 실증
- 단순 성능 수치보다 더 중요한 학술적 메시지

**C4. 설계 원리 식별**
- Ablation: Tfwd only → CI가 0을 가로지름 + PDR 하락
- Full model만 일관된 개선
- "다중 신호 결합 + 안정화 정책이 함께 필요하다"는 설계 법칙 실증
- 이 메시지는 이제 `fig_jkcs_ablation_forest.pdf`로 표보다 훨씬 직접적으로 제시 가능

**C5. 평가 방법론**
- 밀도별 층화 랜덤 75쌍 + 5 MAC 시드 + topology-paired difference + H1/H2/H3 사전 선언
- 단일 hand-crafted topology + PDR 평균 관행보다 엄밀한 검증 틀
- 후속 연구가 재사용 가능한 methodological baseline

---

## 종합 피드백 (심사위원)

### 잘 한 것
- 코드와 데이터를 근거로 제시한 기술적 깊이
- "model-selection leakage"처럼 비판의 언어를 스스로 가져온 점
- `pow()`와 MSP430 FPU 문제까지 스스로 짚은 점

### 구조적 약점
- Q1~Q5까지 거의 모든 답변이 "인정합니다"로 끝남
- **한계 인정 → "그럼에도 기여는 X다"의 세트가 매 답변마다 필요**
- Q7에서 처음으로 기여를 능동적으로 제시 → 가장 좋은 답변

---

## 원고 수정 체크리스트

### 즉시 수정 (디펜스 전)
- [x] `lightweight` → `on-node` / `local` / `in-protocol` / `cryptography-free` 교체
  - 현황: `main_v2.tex` 영문 초록 반영 완료
  - 현황: 결론도 설계/구조 중심 표현으로 유지
- [x] 표 1 캡션에 `qualitative positioning` 명시
  - 현황: empirical performance comparison이 아님을 캡션에 명시 완료
- [x] 우월성 암시 문장 삭제 또는 완화
  - 현황: Related Work 및 향후 연구의 표현을 `상대적 특성`, `설계적 위치` 중심으로 완화 완료

### 디펜스용 시각 자료 보강
- [x] trust 신호 시계열 추가
  - 산출물: `fig_jkcs_trust_timeseries.pdf`
  - 목적: "trust가 실제로 어떻게 작동하는지 보여주지 않는다"는 비판 대응
- [x] 가중치 sensitivity heatmap
  - 현황: 완료 (`fig_jkcs_weight_sensitivity_heatmap.pdf`)
  - 범위: 9쌍 miniset의 10개 국소 조합을 사용한 탐색적 보조 sensitivity scan
- [x] churn vs. att\_share 산점도 추가
  - 산출물: `fig_jkcs_churn_att_scatter.pdf`
  - 목적: H1-H3 trade-off 가시화
- [x] Ablation forest plot 추가
  - 산출물: `fig_jkcs_ablation_forest.pdf`
  - 목적: Full model만 CI가 0 아래임을 직관적으로 제시

### 디펜스 후 Revision
- [x] `held-out generalization을 입증했다` 표현 삭제
  - 현황: `main_v2.tex`에는 해당 강한 표현이 명시적으로 보이지 않음
- [x] 7절 한계: tuning/evaluation 분리 불완전성 항목 추가
  - 현황: `main_v2.tex` 한계절에 strict held-out 미보장과 model-selection leakage 가능성을 직접 명시
- [x] 7절 한계: 혼잡-only 비교 미수행 추가
  - 현황: 혼잡-only / 공격-only / 혼잡+공격 분리 비교 미수행을 한계절에 직접 명시
- [x] 가중치 선택 근거 문장 명확화
  - 현황: `(0.5, 0.3, 0.2)`를 이론적 최적값이 아닌 `경험적 operating point`로 본문에 명시
- [x] 향후 연구: RFTrust, PCC-RPL 직접 비교를 F1 과제로 강화
  - 현황: 향후 연구 절에 동급 비교를 다음 revision의 우선 과제(F1)로 명시

### 추가로 만들어야될 figure

우선순위 높음
첫째, 신뢰 신호 시계열 그래프입니다. Q2, Q6에서 "trust가 실제로 어떻게 작동하는지 보여주지 않는다"는 약점이 드러났습니다. 대표 토폴로지 1개에서 Tfwd, Tctrl, Thon, Tagg가 공격 구간에 어떻게 변화하는지 시계열로 보여주면, 신뢰 파이프라인이 실제로 동작한다는 직접적 증거가 됩니다.
  - 현황: 완료 (`fig_jkcs_trust_timeseries.pdf`)
둘째, 가중치 sensitivity 히트맵입니다. Q3에서 가중치 근거 부재가 가장 날카롭게 지적됐습니다. wf/wc/wh를 격자 탐색해서 att_share Δ를 색으로 표현하면, 0.5/0.3/0.2가 극단적 최적점이 아니라 완만한 안정 구간에 있음을 시각적으로 보여줄 수 있습니다.
  - 현황: 완료 (`fig_jkcs_weight_sensitivity_heatmap.pdf`)
  - 해석 주의: held-out optimality가 아니라 탐색적 보조 민감도 진단
우선순위 중간
셋째, churn vs. att_share 산점도입니다. H1(격리 개선)과 H3(churn 상한)의 trade-off를 토폴로지별로 점으로 찍으면, "churn을 희생해서 att_share를 줄인 것"이 아님을 보여줄 수 있습니다. 현재 이 두 지표가 별도 figure에만 있어서 관계가 보이지 않습니다.
  - 현황: 완료 (`fig_jkcs_churn_att_scatter.pdf`)
넷째, Ablation 결과 시각화입니다. 현재 Table 6으로만 존재하는데, Full / Tfwd only / Tfwd+Tctrl의 Δatt CI를 forest plot으로 표현하면 "Full model만 0 아래"라는 메시지가 훨씬 강하게 전달됩니다.
  - 현황: 완료 (`fig_jkcs_ablation_forest.pdf`)

### Figure별 보완 메모
- Figure 5 (`fig_jkcs_churn_att_scatter.pdf`)
  - 주의점: H3 상한 `Δchurn <= +0.1`을 개별 topology hard cap처럼 읽히게 하면 취약함
  - 확인값: `75`개 중 `12`개가 상한 초과, 이 중 `10`개가 sparse, `2`개가 medium
  - 현재 정리: 본문과 캡션에서 `63/75`는 상한 이내이지만 outlier가 존재함을 명시하고, H3는 topology-wise cap이 아니라 paired mean + CI 가설이라고 설명
- Figure 8 / Table 6
  - 원인: 원자료(`summary.md`)는 Full의 `Δatt_share = -0.0335`이고, Table 6은 이를 소수 셋째 자리로 반올림해 `-0.034`로 표기
  - 현재 정리: forest plot 수치 라벨도 소수 셋째 자리로 맞춰 Table 6과 표시 일관성 확보
- Figure 9 (`fig_jkcs_trust_timeseries.pdf`)
  - 기존 약점: 특정 topology를 사실상 임의로 고른 것처럼 보일 수 있었음
  - 현재 정리: `Δatt_share < 0` 및 `Δchurn <= +0.1` 후보 중 공격 구간 `T_agg` 하락이 실제로 보이는 경우만 남기고, 그중 `Δatt_share`가 후보군 중앙값에 가장 가까운 사례를 대표 예시로 선택하는 규칙으로 변경
  - 현재 대표 사례는 이 규칙에 따라 자동 선택됨
  - 추가 보강: 그림과 캡션에 공격 시작 `350s` 및 종료 `650s` 점선을 명시

---

## 핵심 수치 요약

| 지표 | BRPL | TA-BRPL | Δ | p값 |
|------|------|---------|---|-----|
| att_share | 0.110 | 0.093 | −0.0169 | < 10⁻⁴ |
| hit_ratio | 0.117 | 0.101 | −0.0166 | < 10⁻⁴ |
| PDR_dur | 0.950 | 0.961 | +0.0102 | 0.002 |
| churn | 0.037 | 0.073 | +0.0364 | CI 상한 0.057 < 0.1 ✓ |

- att_share 승률: 전체 **76%**, 중밀도 **84%**
- PDR 비열세 통과율: **93.3%** (실패 5건 모두 저밀도)
- 사전 선언 churn 상한: **+0.1** → CI 상한 0.057로 충족
