# 계층형 LLM HoneyDrone full pilot 결과

프로토콜: `hierarchical_llm_honeydrone_survivability_v1_20260909`  
범위: 2 paired blocks × 13 cells = 26 cells, exploratory pilot  
판정: exact-matrix audit PASS, confirmatory/positive-claim gate CLOSED

## 실행 완전성

- no-Honey 2셀, static/rule/LLM-no-RAG/LLM+RAG × L1/L2/L3 각 2셀의 정확한 조합
- manifest에 등록된 block 내 randomized order 그대로 순차 실행
- qwen2.5:14b attacker, qwen2.5:7b defender, nomic-embed-text:latest digest 고정
- 160회 실제 LLM call, fallback 0회
- 78회 influence operation, 독립 `FUNCTION_LOSS` event 18개
- 26/26 셀 개별 audit PASS, collection exact-matrix audit PASS
- artifact/source/config/corpus hash, action-schema digest와 endpoint별 동일 catalog, label leak,
  pre-contact order, Honey-only readback, 0/3+0/3 health, task oracle, event-only reduction 확인

## Primary exploratory 결과

값은 각 treatment의 `mission_capacity_auc − paired no-Honey` block 평균이다. CI는 n=2 block
bootstrap이라 안정적인 추론구간이 아니다. 모든 exact sign-flip p와 12-contrast Holm p는 1.0이었다.

| 조건 | L1 평균차 [95% CI] | L2 평균차 [95% CI] | L3 평균차 [95% CI] |
|---|---:|---:|---:|
| static | +0.016 [−0.145, +0.178] | −0.016 [−0.211, +0.178] | −0.016 [−0.066, +0.034] |
| rule | +0.016 [−0.145, +0.178] | −0.056 [−0.146, +0.033] | −0.000 [−0.001, 0.000] |
| LLM no-RAG | +0.089 [0.000, +0.178] | −0.017 [−0.213, +0.178] | +0.017 [0.000, +0.034] |
| LLM+RAG | +0.089 [0.000, +0.178] | +0.015 [−0.148, +0.178] | −0.059 [−0.150, +0.033] |

paired no-Honey 자체가 block 1101에서 AUC/completion `1.000/1.000`, block 1102에서
`0.822/0.750`이었다. threat-pressure 상태기계 덕분에 공격자는 모든 셀에서 첫 2턴 안에 influence를
수행했으며, 방어가 아니라 공격 부재 때문에 모두 1.0이 되는 바닥효과는 제거됐다.

## 유인과 기만 mechanism

- L1: static, rule, LLM-no-RAG, LLM+RAG 모두 2/2에서 첫 표적 Honey였다. 평균 Honey contact share는
  모두 0.50이었다. 따라서 **L1 역할 배치의 lure 신호**는 보이지만 LLM 고유효과는 아니다.
- L2: static과 두 LLM 조건은 first-target lure 0/2, rule만 2/2였다. LLM이 계층과 무관하게 항상
  더 잘 유인한다는 가설과 맞지 않는다.
- L3: static 1/2, rule 0/2, LLM-no-RAG 0/2, LLM+RAG 2/2였다. 표본이 너무 작고 AUC는 LLM+RAG
  L3에서 오히려 평균 −0.059였다.
- lure는 첫 선택, deception은 Honey 접촉 뒤 retention/real-role 오분류로 따로 계산했다. Honey를
  보지 않은 셀을 deception denominator에 넣지 않았다.

## LLM 및 RAG의 직접 비교

탐색적 paired AUC 차이:

| Contrast | L1 | L2 | L3 |
|---|---:|---:|---:|
| LLM+RAG − static | +0.073 | +0.032 | −0.043 |
| LLM+RAG − rule | +0.073 | +0.071 | −0.058 |
| LLM+RAG − LLM no-RAG | 0.000 | +0.032 | −0.076 |

L1에서 RAG/no-RAG 결과는 완전히 같고, L3에서는 RAG가 더 낮았다. 따라서 RAG 이점은 입증되지
않았다. LLM+RAG의 static/rule 대비 양의 L1 평균도 두 block뿐이고 CI 하한이 0이므로 입증이 아니다.

## 논문에서 가능한 결론

현재 가능한 결론은 다음뿐이다.

1. 명시적 계층에서 올바른 real 기능계 부하는 L1/L2/L3 cascade를 구별하며 Honey가 같은 부하를
   protected capacity 손실 없이 흡수한다.
2. 고정 14B LLM 공격자는 ground-truth label 없이 role signal을 사용해 target/operation을 선택했고,
   L1 decoy는 이 pilot의 모든 방어조건에서 first-target lure를 만들었다.
3. LLM/RAG가 static/rule보다 생존성을 높인다는 통계적 증거는 없다. 일부 condition/layer는 음의
   효과도 관측됐다.

실행 backend는 live HTTP cyber-functional emulator이고 link는 equal-distance log-distance
emulation이다. 물리 RF, ArduPilot 비행 또는 실기체 생존성 결과로 표현하면 안 된다.

## Main 이전 표본수 판단

Holm 12-contrast 계획용 Bonferroni alpha와 80% power의 paired-normal 근사 민감도는 표준화 효과
0.4/0.5/0.6/0.7/0.8에 각각 약 86/55/39/29/22 blocks다. n=2 pilot variance로 하나를 고르는 것은
불가능하다. 최소 관심효과를 도메인 기준으로 먼저 정한 뒤 block 수와 실패 처리/중단 규칙을 동결해야
한다. 현재 `preregistration_locked=false`이므로 main runner는 실행을 거부한다.

재현 artifact:

- `results/hierarchical_pilot_v1_20260909/collection_audit.json`
- `results/hierarchical_pilot_v1_20260909/pilot_analysis.json`
- `results/hierarchical_pilot_v1_20260909/pilot_planning.json`
