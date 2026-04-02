# TA-BRPL 연구 진행 기록 복원본

작성일: 2026-04-02  
복원 근거: Git 전체 히스토리, GitHub PR/리뷰 기록, 초기 `readme.md`, 중간 구조 문서, 실험/회고 문서, 논문 초안 계열  
범위: 첫 커밋 `de6fbbe`부터 현재 `a55c3c1`까지

## 1. 이 문서는 무엇을 복원하나

이 문서는 "최종 결과가 무엇이냐"보다, 연구가 실제로 어떤 순서로 진행됐는지를 Git 히스토리 기준으로 복원한 기록이다.

즉 아래를 복원한다.

- 처음에 무엇을 문제로 잡았는가
- 어떤 구현을 먼저 만들었는가
- 어느 지점에서 실험 방식이 바뀌었는가
- 무엇이 실패였고, 그 실패가 다음 버전을 어떻게 바꿨는가
- 언제부터 논문화와 일반화 검증으로 연구 초점이 이동했는가

주의:

- 점(`.`), `fin`, `stable ver`처럼 커밋 메시지가 설명적이지 않은 구간은 변경 파일과 당시 문서를 근거로 해석했다.
- GitHub PR 본문과 리뷰 코멘트는 "당시 왜 그 변경을 넣었는지"를 설명하는 1차 보조 근거로 사용했다.
- 따라서 일부 구간은 "직접 서술"이 아니라 "Git 근거 기반 추론"이다.

---

## 2. 한 줄 요약

이 연구는 처음에는 "BRPL에 trust를 붙여 selective forwarding/sinkhole 공격을 막아보자"는 구현 중심 프로젝트로 시작했고, 곧바로 외부 trust engine 실험과 자동화로 확장됐다.  
그 다음 2월에는 Contiki-NG 서브모듈 통합과 여러 고정 토폴로지 실험을 거치며 TA-BRPL의 fixed-topology 동작을 안정화했고, 3월에는 병렬 대량실험, 랜덤 토폴로지 일반화, 메인 실험 프로토콜 고정, 논문화까지 진행되면서 "실험 가능한 시스템"에서 "논문 가능한 연구 체계"로 넘어갔다.

---

## 3. 복원된 연구 단계

## 단계 A. 최소 재현 환경 구축과 문제 정의

기간:
- 2026-01-26

대표 커밋:
- `de6fbbe` Initial commit of trust-aware-brpl

이 시점에 한 일:

- Cooja에서 바로 돌릴 수 있는 최소 실험 환경 구축
- `sender` / `receiver_root` 기반 UDP 트래픽 실험 구성
- `brpl-of.c`와 `project-conf.h`를 두고 BRPL 실험 골격 마련
- 결과 파서(`tools/parse_results.py`)와 실행 스크립트(`scripts/run_simulation.sh`, `scripts/build.sh`)까지 포함해 "실험 1회가 가능한 저장소"를 먼저 만듦

이때의 연구 질문:

- BRPL에 trust 메커니즘을 붙이면 selective forwarding 공격 대응이 가능할까?
- 지표는 PDR, delay, overhead 중심으로 먼저 보자.

복원 근거:

- 첫 커밋의 `readme.md`에 목표가 "Trust-Aware BRPL for Selective Forwarding Attack"으로 직접 적혀 있음
- 초기 README에는 이미 위협 모델, 실험 토폴로지, Phase 1~3 계획이 명시돼 있음

해석:

- 연구는 처음부터 "논문 문장"이 아니라 "돌아가는 실험 플랫폼"을 먼저 만드는 방식으로 시작됐다.
- 아직 이 단계는 trust 모델 자체보다 재현 가능한 시뮬레이터 루프를 확보하는 단계였다.

---

## 단계 B. 공격자 도입과 trust 계산의 첫 구현

기간:
- 2026-01-27 ~ 2026-01-29

대표 커밋:
- `26c504c`
- `d293e43`
- `9995d2a`
- `40f2446`

이 시점에 한 일:

- `motes/attacker.c` 추가로 selective forwarding 공격자를 본격 도입
- normal/attack 시나리오 분리
- 랜덤 토폴로지 초안 및 배치 실행 스크립트 추가
- root 기준 EWMA trust 계산 아이디어를 문서화
- `motes/brpl-trust.h`, `motes/brpl-blacklist.c` 계열이 등장하면서 "trust를 parent 선택 제한에 연결"하는 방향을 코드로 밀기 시작

당시 trust 개념:

- 노드별 마지막 seq를 추적해 누락 패킷 수를 계산
- `sample = 1000 / (1 + missed)` 형태의 단순 trust sample
- EWMA로 trust를 갱신

해석:

- 이 구간은 "공격 구현"과 "trust 추정"이 서로 따로 있지 않고, 빠르게 붙였다 떼는 탐색 단계였다.
- 공격 강도, 배치, trust 반영 위치를 넓게 실험하면서 실험 축을 만들어가는 시기였다.

---

## 단계 C. 외부 Trust Engine 실험과 로그 기반 후처리 파이프라인

기간:
- 2026-01-29 ~ 2026-01-30

대표 커밋:
- `21eabf1` add-trust-engine
- `4780735`
- `a45b357`
- `12496c0`
- `fc57c6e`

이 시점에 한 일:

- Rust 기반 외부 trust engine 추가
- Cooja 로그를 파싱해 trust를 계산하고 `trust_updates.txt`로 피드백하는 구조 도입
- `run_with_trust_engine.sh`, `run_sim_with_trust_post.sh` 등 후처리/주입 자동화 구축
- JVM crash workaround 문서화
- 실험 모니터링, quick test, 결과 분석 스크립트 추가
- 첫 한글 보고서/그림 생성

연구 방식의 특징:

- trust를 네트워크 내부 로직으로만 두지 않고, 로그 기반 외부 엔진으로도 실험해 봄
- "시뮬레이터 제약 때문에 in-sim 구현이 어려우면 후처리 주입으로라도 돌려보자"는 태도가 보임

해석:

- 이 시점의 핵심은 알고리즘 완성보다 "관측-분석-피드백" 루프를 닫는 데 있었다.
- 즉 연구자는 꽤 초반부터 신뢰도 계산 자체보다 실험 자동화와 관측 가능성을 중요하게 본 것으로 보인다.

---

## 단계 D. Contiki-NG 서브모듈 통합과 TA-BRPL의 본격적인 in-protocol화

기간:
- 2026-02-06

대표 커밋:
- `84cf503` add submodule brpl
- `dc12219` Integrate contiki-ng-brpl submodule and add trust-aware features
- `bf9f511`

이 시점에 한 일:

- `contiki-ng-brpl` 서브모듈 도입
- 실험 저장소 외부의 임시 코드가 아니라, Contiki/BRPL 기반 본체와 결합된 연구 형태로 전환
- `motes/brpl-trust.c` 추가
- 다양한 고정 토폴로지 `T1/T2/T3`와 random variant 생성기 추가
- 빌드/실행 경로를 서브모듈 기준으로 정리
- 구조 문서(`docs/architecture.md`) 작성

연구 단계상 의미:

- "주변에서 실험하는 trust"에서 "라우팅 프로토콜에 붙어 있는 trust"로 이동한 전환점
- 이후의 모든 실험이 이 통합 구조를 바탕으로 진행됨

해석:

- 이 시점부터 프로젝트는 데모가 아니라 실질적인 시스템 연구로 올라섰다.
- 실험 축도 단일 시나리오에서 다중 토폴로지 비교로 커졌다.

---

## 단계 E. trust sweep과 고정 토폴로지 대량 탐색

기간:
- 2026-02-07 ~ 2026-02-11

대표 커밋:
- `ef82dc5` Add trust sweep automation and reporting
- `5036811` stable pipeline
- `84379ce`
- `25c44b0` stabled sinkhole
- `9775283`
- `e09bd81`
- `bb40900`
- `0e8d769`
- `31eb9e0`

이 시점에 한 일:

- trust 파라미터 스윕 자동화
- 실험 요약 스크립트와 보고서 자동 생성
- grayhole/sinkhole 계열 고정 토폴로지 실험 안정화
- 시뮬레이터 poll/temp 변수 최적화
- 영어/한글 보고서 누적

이 시기의 연구 패턴:

- 버전 이름보다 파라미터 탐색이 중심
- "신뢰를 넣으면 좋아질 것"을 증명하려 하기보다, 어떤 조합에서 덜 망하는지 찾는 쪽에 가까움
- 실험 결과를 archive로 축적해 재비교 가능한 형태를 유지함

복원되는 사실:

- 2월 초중반은 사실상 trust parameter search와 fixed-topology behavioral debugging 기간이었다.
- 이후 문서에서 정리된 `v1 ~ v13.x` 시행착오의 많은 기반이 이 구간에서 만들어졌다.

---

## 단계 F. 회귀 테스트와 신뢰 엔진 검증 체계 도입

기간:
- 2026-02-11 전후

대표 커밋:
- `6545a3d` test: add trust engine regression checks for blacklist and exposure metrics

이 시점에 한 일:

- blacklist, exposure metric에 대한 회귀 검사를 추가

해석:

- 이제 연구는 "이번 실험이 잘 나왔는가"를 넘어서 "기존에 힘들게 맞춘 동작이 깨지지 않는가"를 보기 시작했다.
- 즉 시행착오가 누적되면서 테스트 필요성이 생긴 구간이다.

---

## 단계 G. 연구 환경 고도화와 병렬 실험 체계 구축

기간:
- 2026-02-23 ~ 2026-03-05

대표 커밋:
- `219501e`
- `ec3a2ea`
- `628763e`
- `9a2011e`
- `67ddf37`
- `c0abbf9`
- `7bce50c` add parallel experiment
- `fb4bf36`
- `6446be9`
- `9992e67` stable ver

이 시점에 한 일:

- Nix 환경 추가
- 연구용 PC 셋업 스크립트 추가
- Java 21 업그레이드로 Cooja 호환성 정리
- 재시작 시 임시 파일/프로세스 정리
- 빌드 캐시 재사용 제거
- 병렬 worker 기반 대량 실험 실행 구조 추가

왜 중요한가:

- 이전까지의 실험은 자동화되어 있어도 "많이 돌리기"에 병목이 있었음
- 이 시점부터는 실험 설계가 파라미터 탐색을 넘어 대량 비교 실험을 감당할 수 있는 인프라를 갖춤

해석:

- 연구자는 3월 초에 "알고리즘 개선" 못지않게 "실험을 대규모로 안정적으로 돌리는 법"에 시간을 많이 투자했다.
- 이는 곧 fixed-topology 최적화만으로 끝내지 않고, 더 큰 검증으로 가려는 준비였다고 볼 수 있다.

---

## 단계 H. 논문 쓰기 시작과 연구 질문의 재정의

기간:
- 2026-03-05 ~ 2026-03-06

대표 커밋:
- `aeb0499` start writing paper
- `b2d0cc0`

이 시점에 한 일:

- `docs/paper/` 계열이 본격 등장
- 실험 결과를 단순 로그가 아니라 논문 구조로 재배열하기 시작

이 시점의 의미:

- 연구가 "작동하는가?"에서 "무엇을 주장할 수 있는가?"로 이동
- 어떤 지표를 primary로 둘지, 어떤 실패를 솔직하게 적을지 정리하기 시작

해석:

- 논문 작성이 단순 결과 정리가 아니라, 연구 목표 재정의의 시작점이었다.

---

## 단계 I. 통합 문서화와 fixed-topology 메커니즘 정리

기간:
- 2026-03-16 ~ 2026-03-24

대표 커밋:
- `40f9150` docs v0.3.3
- `b18f19d` feat: integrate TA-BRPL trust updates, unified docs, and refreshed figures

이 시점에 한 일:

- 흩어져 있던 아키텍처/리스크/검증/구현 계획 문서를 `docs/TA_BRPL_UNIFIED.md`로 통합
- trust update 로직과 파라미터 조합을 더 정리
- 논문용 figure와 fixed-topology 설명 자산 대거 생성

연구 서사의 변화:

- 단순히 코드가 아니라 "TA-BRPL은 어떤 계층 구조와 설계 철학을 갖는가"를 명문화
- `T_fwd`, `T_ctrl`, `T_hon`, validation, switch gate, dwell 같은 개념이 체계적으로 문서화됨

해석:

- 이 단계는 연구자의 머릿속에서 흩어져 있던 설계가 문서상 하나의 메커니즘으로 정리된 구간이다.
- 즉 실험 코드를 논문용 설명 가능한 모델로 재구성한 시기다.

---

## 단계 J. 랜덤 토폴로지 일반화 검증으로의 전환

기간:
- 2026-03-24

대표 커밋:
- `03106a5` feat: add random-topology framework and full paper pseudocode updates
- `ba86e46` Add sweep automation, loss/attack scenarios, and README run matrix
- `74a05c4` Add robust sweep orchestration, rich monitoring, storage controls, and expanded random topology sweep

이 시점에 한 일:

- 랜덤 토폴로지 프레임워크를 본격 추가
- density별, topology seed별, run seed별로 구조화된 실험 행렬 구축
- `BRPL`, `RPL`, `SMTRUST`, `TABRPL` 비교 템플릿 확대
- 모니터링, 저장공간 관리, 자동 요약까지 포함한 대규모 sweep orchestration 구축

이때 연구 질문이 바뀜:

- "고정 grid에서 잘 되는가?"가 아니라
- "이 효과가 topology distribution 전체에서 유지되는가?"가 중심이 됨

복원 근거:

- `docs/random_topo.md`는 사실상 이 전환의 선언문 역할을 함
- "single topology lucky case를 피해야 한다"는 문제의식이 명시돼 있음

해석:

- 이 구간이 가장 중요한 연구 방향 전환점이다.
- fixed-topology 튜닝 연구에서 random-topology generalization 연구로 올라간 시기다.

---

## 단계 K. 메인 실험 프로토콜 고정과 주장 범위 제한

기간:
- 2026-03-27 ~ 2026-03-28

대표 문서/커밋:
- `docs/MAIN_EXPERIMENT_PROTOCOL.md`
- `docs/base.md`
- `docs/TA_BRPL_V1_TO_NOW_POSTMORTEM.md`
- `18c0dd7` stabled ver

이 시점에 한 일:

- 메인 실험 endpoint를 사전에 고정
- 주장 우선순위를 `PDR 절대 우위`가 아니라 `attacker isolation with bounded stability cost`로 재정의
- v1부터 v14.1까지 시행착오와 turning point를 문서화
- admission/retention 분석, stuck state profiling 등 실패 원인 분석 도구 추가

가장 중요한 연구적 성숙:

- "무조건 좋아졌다"가 아니라 "무엇을 성공으로 볼지"를 먼저 잠그는 방식으로 바뀜
- 랜덤 토폴로지에서 일반화 실패 또는 pre-fix/post-fix 반전까지도 기록에 포함

해석:

- 이 시점의 연구는 구현 중심이 아니라 검증 설계 중심이다.
- 연구자는 주장의 범위를 줄이는 대신, 더 방어 가능한 메시지를 택했다.

---

## 단계 L. 현재 상태: 논문화, 한국어 문서화, ablation 확장

기간:
- 2026-03-30 현재

대표 커밋:
- `5cd74bf`
- `a55c3c1`

현재까지 복원되는 상태:

- 한국어/영문 논문 원고가 병행 관리됨
- main v1 / v2, quickcheck, ablation, random topology 결과가 논문용 artifact로 생성됨
- full model 뿐 아니라 `FWD`, `FWDCTRL` 등 축약 ablation도 비교하는 단계까지 도달
- 연구의 핵심 메시지는 "공격자 격리와 stability cost의 trade-off를 어떻게 설계하느냐"로 수렴

---

## 3.5 TA-BRPL 모델링 진화 상세 복원

위 타임라인은 연구 흐름을 보여주지만, TA-BRPL 자체가 어떤 식으로 모델링되었는지는 따로 더 세밀하게 볼 필요가 있다.  
특히 이 프로젝트는 단순히 trust score 하나를 넣은 것이 아니라,

- trust를 무엇으로 정의할 것인가
- 그 trust를 어디에서 계산할 것인가
- BRPL score에 어떻게 결합할 것인가
- 언제 soft penalty로 두고 언제 hard exclusion으로 올릴 것인가
- churn 폭증을 막기 위해 어떤 gate를 더할 것인가

를 여러 단계에 걸쳐 바꿔 왔다.

아래는 그 모델링 축만 따로 복원한 내용이다.

### 모델링 1단계. `seq-miss` 기반 trust와 외부 주입형 구조

시기:
- 2026-01-27 ~ 2026-01-29

근거:
- 초기 `memo.md`
- `docs/project_overview.md`
- `21eabf1` 이전 코드/문서

초기 trust 개념은 매우 단순했다.

- 노드별 마지막 sequence를 기억
- 누락 개수 `missed` 계산
- `sample = 1000 / (1 + missed)`로 신뢰 샘플 생성
- EWMA로 평활화

이 모델의 장점:

- 구현이 단순하고 빨리 돌려볼 수 있음
- root 기준 수신 로그만 있어도 계산 가능

이 모델의 한계:

- 실제 드롭 위치와 누락 위치를 구분하지 못함
- forwarding failure와 path-level loss를 쉽게 혼동함
- trust가 "전달 행동의 직접 측정"이 아니라 "수신 누락의 간접 추정"에 가까움

해석:

- 이 단계의 trust는 라우팅 모델이라기보다 빠른 실험용 heuristic에 가까웠다.
- 그래서 이후에 forwarding ratio 기반 정의로 넘어가는 것이 사실상 필연적이었다.

### 모델링 2단계. GitHub PR #1이 보여주는 핵심 전환:
### `seq-miss trust`에서 `forwarding-ratio trust + exposure`로

시기:
- 2026-02-06

근거:
- GitHub PR `zeetee1235/TA-BRPL#1`
- merge 대상 커밋 `bf9f511`

이 PR은 모델링 관점에서 굉장히 중요하다. PR 제목부터
"Refresh trust model: EWMA from forwarding ratios, exposure reporting, and docs"다.

이 PR에서 실제로 바뀐 것:

- trust engine의 관측 단위를 sequence miss에서 forwarding ratio로 변경
- `CSV,FWD`를 파싱해 `success` / `failed`를 누적
- EWMA, Bayes, Beta reputation을 병렬 계산
- threshold를 정수 스케일(예: 700)에서 확률 스케일(예: 0.7)로 재해석
- `Exposure` 지표(E1, E3)를 결과 파서에 추가

즉 이 시점부터 trust 정의는 더 이상

- "패킷이 안 왔으니 누군가 문제일 것이다"

가 아니라,

- "이 노드를 거친 포워딩이 실제로 얼마나 성공했는가"

로 바뀐다.

이 전환이 중요한 이유:

- trust가 라우팅 의사결정에 들어갈 때 의미가 훨씬 또렷해짐
- `trust = 조건부 전달 성공확률의 경험적 추정치`라는 논문용 방어 논리가 생김
- 동시에 `Exposure`를 같이 도입하면서
  "PDR 향상"보다 "공격자 노출 감소"를 중심 지표로 보는 프레임도 시작됨

GitHub 리뷰 기록도 중요한 단서를 준다.

- Codex 리뷰는 `udp_to_root`가 증가하지 않아도 `dropped`가 늘 수 있는 케이스를 지적했다.
- 이건 trust 모델이 단순 비율 계산이어도 관측 정의가 잘못되면 blackhole을 놓칠 수 있음을 보여준다.

해석:

- 2026-02-06의 전환은 단순 구현 수정이 아니라,
  TA-BRPL 연구의 "신뢰 정의" 자체가 더 라우팅-의미론적인 방향으로 재정의된 순간이다.

### 모델링 3단계. `motes/brpl-trust.c` 시기의 의미:
### "내장 trust"라기보다 "주입된 trust를 읽는 얇은 인터페이스"

시기:
- 2026-02-06 (`dc12219`)

근거:
- `motes/brpl-trust.c` 초기 버전

`dc12219` 시점의 `motes/brpl-trust.c`는 생각보다 단순하다.

- 내부에 `trust_values[]`, `trust_valid[]` 테이블만 둠
- `brpl_trust_get(node_id)`로 값을 읽음
- `brpl_trust_override(node_id, trust)`로 외부 주입을 받음
- `TRUST_PARENT_MIN` 이하 parent는 허용하지 않음

즉 이 시기의 BRPL trust 계층은

- 복잡한 trust를 "자체 계산"하는 모델이 아니라
- 외부/상위 계층에서 계산된 trust를 BRPL이 읽을 수 있게 하는 adapter

에 가깝다.

해석:

- 연구 초중반의 핵심은 trust model 그 자체보다
  "BRPL parent selection에 trust를 연결하는 interface"를 만드는 일이었다.
- 따라서 이 시기의 모델링은 "계산"보다 "결합"이 중심이었다.

### 모델링 4단계. GitHub PR #2가 보여주는 파라미터화:
### `lambda`, `gamma`를 독립 축으로 실험하기 시작

시기:
- 2026-02-07

근거:
- GitHub PR `zeetee1235/TA-BRPL#2`
- merge 대상 커밋 `ef82dc5`

이 PR은 trust sweep 자동화 PR처럼 보이지만, 모델링 쪽에서도 의미가 크다.

추가된 핵심 축:

- `TRUST_LAMBDA`
- `TRUST_GAMMA`

이 둘은 이후 연구 전체에서

- trust 업데이트 민감도
- trust penalty 강도 또는 곡률

를 조절하는 독립 축으로 작동한다.

즉 이 시점부터 연구는 단순히 "trust on/off" 비교가 아니라,

- trust를 얼마나 빨리 낮출 것인가
- 낮은 trust를 parent score에서 얼마나 강하게 벌점 줄 것인가

를 실험 행렬의 일부로 다룬다.

GitHub 리뷰 기록도 의미 있다.

- Codex 리뷰는 topology 이름에 underscore가 들어가면 run parser가 깨질 수 있다고 지적했다.
- 이건 모델의 수학 자체보다 실험 체계 문제지만, 결과 집계가 틀리면 모델링 결론도 틀려진다는 점에서 중요하다.

해석:

- 이 단계는 "모델 정의"보다 "모델 파라미터 공간을 체계적으로 훑는 틀"이 만들어진 시기다.

### 모델링 5단계. `ta-brpl-trust.c`의 등장:
### 3신호 trust 모델로의 본격 전환

시기:
- 2026-03-16 (`859ca18`) 이후

근거:
- `motes/ta-brpl-trust.c` 첫 등장

여기서부터 TA-BRPL은 이름 그대로의 독립 trust model을 갖는다.

첫 버전에서 이미 다음 구조가 명시돼 있다.

- `T_fwd`
  `F_ij`, `S_ij` 기반 forwarding trust
- `T_ctrl`
  rank deviation, DIO excess, version mismatch 기반 control-plane trust
- `T_hon`
  advertised queue와 estimated queue 차이를 보는 honesty trust

결합 방식도 명시적이다.

- 가중 기하평균 `T_tilde = T_fwd^wf * T_ctrl^wc * T_hon^wh`
- 비대칭 EWMA
  하락 시 더 빠른 `lambda_decrease`, 상승 시 더 느린 기본 람다

이 시점의 중요한 점:

- trust가 더 이상 "외부에서 온 한 숫자"가 아니다
- on-node 관측과 protocol 상태를 같이 쓰는 composite model이 된다

해석:

- 이때부터 TA-BRPL은 진짜 "모델"이라고 부를 만한 구조를 갖는다.
- 특히 `T_ctrl`, `T_hon`이 추가되면서
  forwarding loss만으로는 설명 안 되는 sinkhole 유인과 queue dishonesty를 함께 보려는 설계 철학이 드러난다.

### 모델링 6단계. `trust_total`만으로는 안 된다는 인식:
### `trust_fwd` 분리와 blackhole dilution 문제

시기:
- 2026-03-24 전후

근거:
- `b18f19d` 시점 `motes/ta-brpl-trust.c`

이 시점의 코드 주석은 매우 중요하다.
핵심 내용은 다음이다.

- pure blackhole attacker는 `T_ctrl≈1000`, `T_hon≈1000`을 유지할 수 있음
- 그러면 geometric mean을 써도 `T_fwd`의 하락이 희석될 수 있음
- 그래서 forwarding evidence만 따로 보는 `trust_fwd`를 별도로 추적해야 함

즉 연구자는 여기서 다음 사실을 인정한다.

- "세 신호를 합치면 더 robust할 것이다"라는 직관이 항상 맞지 않는다
- 어떤 공격은 오히려 다중 신호 결합이 핵심 증거를 희석시킬 수 있다

그래서 추가된 것:

- `trust_fwd` 독립 추적
- `low_tfwd_streak`
- `TA_TRUST_FINAL_TFWD_MAX`
- `TA_TRUST_FINAL_TFWD_STREAK`

해석:

- 이건 TA-BRPL 모델링의 큰 성숙 포인트다.
- 단일 aggregate score에 집착하지 않고,
  공격 유형별로 어떤 성분은 분리해서 봐야 한다는 교훈이 코드 구조에 반영되었다.

### 모델링 7단계. review/validation 계층의 도입:
### trust score와 hard exclusion을 분리

시기:
- 2026-03-24 이후

근거:
- `b18f19d` 이후 `ta-brpl-trust.c`
- `docs/TA_BRPL_UNIFIED.md`
- `docs/TA_BRPL_V1_TO_NOW_POSTMORTEM.md`

이 시기부터 모델은 단순 trust score를 넘어서,
``soft trust``와 ``hard validation``의 이중 구조를 갖는다.

코드상으로 보이는 요소:

- `TA_TRUST_REVIEW_WINDOWS`
- `TA_TRUST_REVIEW_BAD_TO_PENALIZED`
- `TA_TRUST_REVIEW_BAD_TO_BLACKLIST`
- `TA_TRUST_VALIDATION_MIN_PARENT_AGE_SECONDS`
- `TA_TRUST_VALIDATION_MIN_SENT`
- `TA_TRUST_VALIDATION_GOOD/BAD` 계열 threshold

이 구조의 의미:

- trust가 낮다고 즉시 blacklist하지 않음
- 일정 관측 창(window), 최소 관측량, 누적 review score를 본 뒤에
  `normal -> under -> penalized -> blacklist` 식으로 승급

왜 중요했나:

- 초기 버전들의 핵심 실패가 churn 폭증이었기 때문
- 즉 trust sensitivity 자체보다,
  trust 신호를 언제 hard action으로 연결할지가 더 중요한 문제가 되었음

해석:

- 이 단계에서 TA-BRPL은 단순 score-based routing이 아니라
  "soft routing penalty + conservative validation promotion" 구조로 바뀐다.

### 모델링 8단계. `contiki-ng-brpl`에서의 BRPL 결합 진화:
### multiplicative scaling에서 additive penalty + hysteresis gate로

시기:
- 2026-02-06 ~ 2026-03-24

근거:
- submodule `contiki-ng-brpl`의 `rpl-brpl.c` 히스토리
- 관련 GitHub PR `zeetee1235/contiki-ng-brpl#2`, `#3`

이 축은 특히 중요하다. trust model이 아무리 좋아도,
BRPL parent score와 잘못 결합되면 오히려 역효과가 난다.

#### 8-1. 2026-02-06 `26bb815`

초기 trust-aware `rpl-brpl.c`는

- `brpl_trust_get()` hook 추가
- trust-clamped 값 사용
- `weight * trust / scale` 형태의 multiplicative penalty

를 쓴다.

이 구조의 문제:

- BRPL score 해석에 따라 낮은 trust가 오히려 더 작은 score를 만들어
  잘못하면 더 매력적인 parent가 될 수 있음

#### 8-2. 2026-03-16 `094b502` / GitHub PR `contiki-ng-brpl#2`

이 PR에서 중요한 수정:

- TA trust를 BRPL routing trust signal로 직접 사용
- `brpl_penalty_scale_get()`, `brpl_escape_mode_get()` 같은 hook 추가
- current parent penalty scale 도입
- preferred parent changed callback 도입
- MRHOF/ICMP/DAG handling 정리

그리고 GitHub 리뷰는 명확한 위험도 지적한다.

- `smtrust_is_parent_candidate()`로 reject한 parent를 fallback에서 다시 고를 수 있다는 문제

즉, hard trust gate와 fallback logic이 충돌할 수 있다는 사실이 드러난다.

#### 8-3. 2026-03-24 `521724e` / GitHub PR `contiki-ng-brpl#3`

이 시점의 `rpl-brpl.c`는 훨씬 성숙하다.

- `brpl_trust_parent_allowed()` hard exclude hook
- `brpl_validation_penalty_scale_get()` validation-aware scale
- `brpl_apply_trust_penalty()` 정교화
- `switch margin` gate
- `parent dwell` gate
- `preferred parent` 추적
- extensive CSV logging

다만 GitHub 리뷰는 여기서도 중요한 문제를 짚는다.

- BRPL은 낮은 score가 더 좋은데, trust scaling을 잘못하면 distrusted parent가 더 유리해질 수 있음
- dwell tracking을 전역으로 두면 DAG 간 간섭이 생길 수 있음

해석:

- 이 기록은 TA-BRPL 모델링에서 "신뢰 계산"만큼이나
  "BRPL cost 함수와의 결합 방향"이 얼마나 어려운 문제였는지 보여준다.
- 최종적으로 연구가 churn/stability cost를 핵심 메시지로 잡게 된 것도
  바로 이 결합 문제를 여러 번 겪었기 때문이다.

### 모델링 9단계. 최종적으로 정리된 모델 철학

2026년 3월 말 문서와 코드를 종합하면,
TA-BRPL 모델링은 다음 철학으로 수렴한다.

- `T_fwd`, `T_ctrl`, `T_hon`을 모두 쓰되 공격 종류에 따라 `trust_fwd`를 별도로 본다
- trust score는 soft penalty에 우선 쓰고, hard blacklist는 review/validation이 따로 책임진다
- BRPL 결합은 단순 곱셈보다 additive penalty + hysteresis gate가 더 안전하다
- route capture 억제가 1차 목표이고, churn cost는 bounded하게 관리해야 한다

즉 최종 TA-BRPL은

- 단일 trust score 모델
- 단일 threshold blacklist 모델
- 단순 BRPL multiplier 모델

이 아니라,

- 다성분 trust model
- 이중 승급 validation model
- penalty scale / escape / switch margin / dwell이 함께 있는 routing control model

로 진화했다.

---

## 3.6 GitHub 기록이 추가로 보여주는 전환점

로컬 Git만으로도 큰 흐름은 보이지만, GitHub PR 기록은 "그 변경을 왜 넣었는가"를 더 직접적으로 설명해 준다.

### TA-BRPL 저장소 PR

- PR `#1`
  `Refresh trust model: EWMA from forwarding ratios, exposure reporting, and docs`
  의미:
  trust 정의와 평가지표가 동시에 바뀐 전환점

- PR `#2`
  `Add trust sweep runner, summary/reporting scripts, and expose TRUST_LAMBDA/TRUST_GAMMA`
  의미:
  trust 모델을 실험 행렬 위에서 탐색 가능한 형태로 만든 전환점

- PR `#3`
  `Codex-generated pull request`
  의미:
  trust engine regression test를 도입해 누적 실험의 동작 보존을 확인하기 시작한 시점

### `contiki-ng-brpl` 서브모듈 PR

- PR `#2`
  `fix(rpl-classic): adjust trust-aware BRPL routing behavior`
  의미:
  trust-aware routing hook과 preferred-parent change 추적이 정리된 시점

- PR `#3`
  `Trust aware brpl`
  의미:
  trust-aware BRPL을 본격적인 OF 수준 메커니즘으로 밀어 넣은 큰 구조 변경

해석:

- 로컬 저장소는 "실험/논문/분석"의 변화가 강하게 보이고,
- 서브모듈 PR은 "라우팅 내부 결합 로직"의 변화가 더 잘 보인다.

둘을 같이 봐야 TA-BRPL 연구의 실제 전개가 온전히 복원된다.

---

## 4. 연구가 실제로 어떻게 진행됐는지 요약하면

복원된 흐름은 아래와 같다.

1. 먼저 최소한의 Cooja 실험 플랫폼을 만들었다.
2. 공격자와 trust 계산을 붙여서 작은 실험을 돌렸다.
3. 외부 trust engine까지 붙이며 관측-피드백 루프를 실험했다.
4. Contiki-NG/BRPL 본체에 trust를 통합해 TA-BRPL 구조를 만들었다.
5. 고정 토폴로지에서 trust 파라미터와 정책을 대량 탐색했다.
6. 시행착오가 누적되면서 회귀 테스트와 안정화가 필요해졌다.
7. 병렬 실행과 환경 자동화를 통해 대규모 실험 인프라를 만들었다.
8. 논문 초안을 쓰면서 연구 질문을 다시 정리했다.
9. fixed-topology 성공만으로는 부족하다고 보고 random-topology 일반화 검증으로 넘어갔다.
10. 메인 프로토콜과 endpoint를 고정하고, bounded-cost isolation이라는 더 방어적인 메시지로 정리했다.
11. 동시에 trust 모델 자체도 `단순 heuristic -> composite trust -> validation-aware routing control`로 계속 진화했다.

---

## 5. Git 기준으로 보이는 연구자의 작업 스타일

Git 히스토리만 놓고 봐도 다음 특징이 뚜렷하다.

- 구현보다 늦게 문서가 붙은 것이 아니라, 매우 초반부터 README/메모/보고서가 같이 갔다.
- 실험이 막히면 알고리즘만 만진 것이 아니라 실행 환경, JVM, 빌드, 아카이빙, 병렬화까지 함께 손봤다.
- 결과가 안 좋을 때 덮지 않고 `postmortem`, `base`, `MAIN_EXPERIMENT_PROTOCOL` 같은 문서로 실패와 기준을 따로 남겼다.
- 로컬 커밋만이 아니라 GitHub PR과 리뷰 흔적까지 보면, 변경 이유와 잠재 버그를 공개적으로 검토하는 흐름이 있었다.
- 연구 초점이 자연스럽게
  "기능 추가"
  "파라미터 탐색"
  "메커니즘 진단"
  "일반화 검증"
  "논문화"
  순으로 이동했다.
- 특히 모델링은
  "seq-miss trust"
  "forwarding ratio trust + exposure"
  "3신호 on-node trust"
  "review/validation 계층"
  "BRPL hysteresis gating"
  순으로 층이 계속 늘어났다.

이건 단순 개발 기록이 아니라, 실험 시스템 연구가 커지는 전형적인 패턴에 가깝다.

---

## 6. 지금 문서 체계에서 같이 보면 좋은 파일

- `docs/TA_BRPL_V1_TO_NOW_POSTMORTEM.md`
  버전별 시행착오 중심 회고
- `docs/MAIN_EXPERIMENT_PROTOCOL.md`
  메인 실험 해석 기준과 endpoint 잠금
- `docs/base.md`
  v1~v13.12 중심의 개발 전주기 보고서
- `docs/TA_BRPL_UNIFIED.md`
  현재 TA-BRPL 구조와 구현 철학의 통합 문서
- `docs/random_topo.md`
  random-topology 일반화 검증으로 넘어간 이유
- `motes/brpl-trust.c`
  외부 trust 주입형 초기 BRPL adapter
- `motes/ta-brpl-trust.c`
  현재 TA-BRPL trust/validation 핵심 구현
- `contiki-ng-brpl/os/net/routing/rpl-classic/rpl-brpl.c`
  BRPL score와 trust가 실제로 결합되는 위치

---

## 7. 최종 복원 결론

이 저장소의 연구는 대략 이렇게 진행됐다.

- 1월 말: "trust-aware BRPL을 일단 돌려보는" 프로토타입과 공격/로그 기반 trust 실험
- 2월 초중반: Contiki 통합 후 고정 토폴로지에서 trust 정책을 반복 튜닝하며 실패 원인을 축적
- 2월 초중반: 동시에 trust 정의를 seq-miss 중심에서 forwarding-ratio/exposure 중심으로 바꾸고, lambda/gamma sweep으로 파라미터화
- 3월 초: 대량실험이 가능한 환경과 병렬 인프라 구축
- 3월 중후반: `T_fwd/T_ctrl/T_hon` 기반 on-node 모델, review/validation 계층, BRPL gate를 정교화하면서 논문화와 일반화 검증까지 병행

즉 이 연구는 단순히 "알고리즘 하나를 만들었다"기보다,

- 실험 시스템을 만들고,
- trust 라우팅 메커니즘과 BRPL 결합 함수를 반복 수정하고,
- fixed-topology 과적합 문제를 인식하고,
- random-topology 일반화까지 검증하려는 방향으로 확장된 연구

로 복원된다.
