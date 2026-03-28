# TA-BRPL v1~현재 시행착오 정리 (Postmortem)

작성일: 2026-03-28  
목적: v1부터 현재까지의 실험/튜닝 과정을 "삽질 포함"으로 정리하고, 같은 실수를 반복하지 않기 위한 기준 문서로 사용.

메인실험 목표/endpoint 고정 문서: `docs/MAIN_EXPERIMENT_PROTOCOL.md`

---

## 1) 목표와 평가 기준

- 1순위 목표: 공격자 경유/의존(attacker dependency) 감소
- 2순위 목표: churn 과민반응 억제
- 3순위 목표: PDR는 크게 깨지지 않게 유지
- 핵심 지표: `att_share`, `hit_ratio`, `churn`, `pdr_dur`

---

## 2) 공통 실험 매트릭스

- Topology: `GRID`, `BOTTLE`
- Protocol: `BRPL`, `TABRPL`
- Scenario: `SINK_ONLY`, `SINK_DROP50`
- Seed: 기본 5개
- 결과 위치 패턴: `results/sinkhole_sweep_policy_v*/summary.csv`

---

## 3) 버전별 삽질 타임라인

## v1 (baseline, `results/sinkhole_sweep`)

- 상태
- TA-BRPL이 BRPL 대비 `att_share`/`hit_ratio`/`churn`이 전반적으로 악화.
- 특히 churn 폭증.
- 수치 예시
- `GRID SINK_DROP50`: BRPL churn `0.06` vs TABRPL `2.14`
- `BOTTLE SINK_DROP50`: BRPL churn `0.44` vs TABRPL `2.71`
- 결론
- "trust를 넣으면 좋아진다" 가정이 틀림.
- 과민 반응으로 네트워크를 흔들고 공격 회피 이득을 회수하지 못함.

## v2 (`results/sinkhole_sweep_policy_v2`)

- 상태
- v1 대비 일부 안정화 시도.
- 그러나 평균 기준 여전히 열세.
- 평균 갭(TA-BRPL - BRPL)
- `avgΔpdr=-0.0426`, `avgΔatt=+0.0308`, `avgΔhit=+0.1009`, `avgΔchurn=+1.01`
- 결론
- 모델/정책 분리가 부족했고, churn 문제가 핵심 병목으로 확인됨.

## v3 계열 (`v3`, `v31a`, `v31b`, `v32`, `v3_ps*`, `v3_bc*`)

- 상태
- admission-centric 안정화로 v2 대비 개선.
- 하지만 아직 평균 열세.
- 대표 수치(v3)
- `avgΔpdr=-0.0343`, `avgΔatt=+0.0035`, `avgΔhit=+0.0324`, `avgΔchurn=+0.69`
- 결론
- "완전 실패"에서 "부분 실패"로 전진.
- churn은 낮췄지만 공격자 의존 우위는 아직 불충분.

## v4 (`v4_tj500`, `v4_tj510`, `v4_diag`, `v4_cond_escape`)

- 상태
- 단일 admission 임계값(`tau_join`) 보정 실험.
- `tj510`이 v3 대비 가장 균형적.
- 대표 수치(v4_tj510)
- `avgΔpdr=-0.0318`, `avgΔatt=-0.0029`, `avgΔhit=+0.0279`, `avgΔchurn=+0.62`
- 결론
- 임계값 1개 조정만으로도 방향성 개선 가능 확인.
- 그러나 "전 토폴로지 일관 우위" 수준은 아직 아님.

## v5 (`v5_ctrl_escape`)

- 상태
- escape 축을 다시 공격적으로 사용.
- 결과적으로 churn 재폭증.
- 대표 수치
- `avgΔchurn=+1.20` (악화)
- 결론
- "빠르게 탈출"은 해결책이 아니라는 점 재확인.
- trigger quality 없이 escape를 열면 다시 붕괴.

## v6 (`v6_cond_evict`, `v6_cond_evict_debug`)

- 상태
- conditional eviction 도입.
- 실제론 너무 보수적이라 거의 dead code.
- 결론
- "eviction이 효과 없다"가 아니라 "발동하지 않아서 검증 불가".
- 정책 설계와 발동 가능성은 별개로 검증해야 함.

## v7 (`v7_soft_release`)

- 상태
- soft release로 retention 완화 시도.
- 개선폭은 작고 핵심 병목(토폴로지 비일관성) 해결 실패.
- 결론
- 정책 레이어가 복잡해지는데 인과 증거는 약함.

## v8 계열 (`v8pre`, `v8a`, `v8b`)

- 핵심 진단 성공
- `T_fwd attribution bias` 확인.
- 공격자 drop이 upstream 무고 relay의 `T_fwd`도 떨어뜨려 escape 오탐 유발.
- 내부 분석에서 오탐 비율이 매우 높게 관측됨(대화 기준 81%).
- 대표 수치
- `v8a`: `avgΔatt`는 감소했지만 `avgΔchurn=+1.48`로 붕괴.
- 결론
- 탐지 자체보다 "탐지 신호를 decision policy에 연결하는 방식"이 문제.
- escape/evict를 성급히 다시 키우면 반드시 재악화됨.

## v9~v12

- 상태
- re-entry suppression, recent-switch guard 등 단일 축 반복 튜닝.
- 일부 grid5 실험에서 변화가 미미하거나 방향성 불안정.
- 결론
- "attacker 차단을 더 세게"보다 "우회 경로(AN relax)에서 attacker가 통과하는 구조적 구멍"을 찾아야 한다는 결론으로 수렴.

## v13.1~v13.5 (grid5)

- 상태
- oscillation 억제 및 guard 강화 실험 반복.
- 그래도 GRID에서 열세가 남고 churn/attacker 지표 개선이 제한적.
- 결론
- 규칙 강도 조정보다 로직 우회 경로 차단이 먼저.

## v13.6 (gatefix, grid5)

- 핵심 변경
- `AN` relax 경로에서 suspicion 필터 우회 제거.
- 결과
- 정책 로그는 개선됐지만 지표는 거의 동일.
- 결론
- 우회 경로 하나는 막았지만 loss mode에서 아직 남은 구멍 존재.

## v13.7 (warnfast, grid5)

- 핵심 변경
- warning 민감도 상향.
- 결과
- `SINK_ONLY` 크게 개선.
- `SINK_DROP50`는 개선됐지만 아직 BRPL 대비 약한 구간 존재.
- 결론
- 초반 admission 누수는 크게 줄였으나 loss 환경 정책 보강 필요.

## v13.8 (lossgate, full40) — 큰 전환점

- 핵심 변경
- loss mode에서 `AN` relax 우회 금지 + quality gate 강제.
- 결과
- attacker 격리는 전 토폴로지/시나리오에서 BRPL 대비 우위.
- 대표 평균 갭
- `avgΔpdr=-0.0009`, `avgΔatt=-0.0416`, `avgΔhit=-0.0147`, `avgΔchurn=+0.47`
- 해석
- 격리는 성공했지만 BOTTLE churn 비용이 큼.

## v13.9 / v13.10 / v13.11 (full40)

- 시도
- `NN margin`, `recent-switch margin`, `NN hold` 단일 정책 조정.
- 결과
- 지표 변화 거의 없음(사실상 동일).
- 결론
- 해당 파라미터들이 실제 경계조건에 거의 안 걸리는 구간이었음.
- "좋아 보이는 튜닝"과 "실제로 듣는 튜닝"은 다름.

## v13.12 (escape cooldown=360, full40) — 단일 정책 소폭 성공

- 핵심 변경
- `TA_TRUST_ESCAPE_COOLDOWN_SECONDS: 120 -> 360`
- 결과(v13.8 대비)
- `BOTTLE SINK_ONLY`: churn `1.04 -> 0.90` (개선), pdr `0.9819 -> 0.9938` (개선)
- `BOTTLE SINK_DROP50`: churn `0.91 -> 0.80` (개선), pdr `0.7576 -> 0.7639` (개선)
- 격리 성능은 유지(여전히 BRPL 대비 att_share 낮음).
- 결론
- "단일 간단 정책으로 churn을 조금이라도 줄인다" 목표 달성.
- 다만 churn 절대값은 여전히 높아 후속 최적화 여지 큼.

---

## 4) 삽질 패턴 요약 (재발 방지)

- 1. escape/evict를 먼저 세게 여는 실수
- 결과: churn 폭증, 토폴로지 불안정, 성능 역전.

- 2. `T_fwd`를 원인-행위 분리 없이 직접 의사결정에 연결
- 결과: attribution bias로 무고한 relay까지 처벌.

- 3. "수치가 변할 것 같은" 파라미터를 실제 경계조건 검증 없이 튜닝
- 결과: 버전만 증가하고 지표는 그대로.

- 4. full40 전에 원인 분해 없이 전역 튜닝 반복
- 결과: 실험 비용 증가, 인과 설명력 저하.

- 5. att_share만 보고 성공 판단
- hit_ratio/churn/PDR 동반 확인 없으면 실사용 가치가 흔들림.

---

## 5) 현재 상태(2026-03-28)

- 기준 추천 버전: `v13.12` (`results/sinkhole_sweep_policy_v13_12_escapecool360_full40`)
- 상태 한 줄 요약
- "격리 우위는 확보했고, churn은 단일 정책으로 소폭 완화했으나 BOTTLE 비용은 아직 남아 있음"

---

## 6) 다음 실험 원칙 (짧게)

- 원칙 1
- 한 번에 정책 1개만 바꾼다.

- 원칙 2
- 먼저 `왜`를 로그로 분해한 뒤 튜닝한다.

- 원칙 3
- 성공 조건은 3개 동시 확인.
- `att_share` 유지/개선, `churn` 개선, `pdr_dur` 급락 없음.

---

## 7) 참고 결과 경로

- 초기 baseline: `results/sinkhole_sweep/summary.csv`
- v2: `results/sinkhole_sweep_policy_v2/summary.csv`
- v3: `results/sinkhole_sweep_policy_v3/summary.csv`
- v4(tj510): `results/sinkhole_sweep_policy_v4_tj510/summary.csv`
- v5: `results/sinkhole_sweep_policy_v5_ctrl_escape/summary.csv`
- v8a: `results/sinkhole_sweep_policy_v8a/summary.csv`
- v13.8(full40): `results/sinkhole_sweep_policy_v13_8_lossgate_full40/summary.csv`
- v13.12(full40): `results/sinkhole_sweep_policy_v13_12_escapecool360_full40/summary.csv`
