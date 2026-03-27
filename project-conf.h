#ifndef PROJECT_CONF_H_
#define PROJECT_CONF_H_

/* ================================================================== */
/* Routing driver: always RPL-Classic (required for BRPL)             */
/* ================================================================== */
#undef  NETSTACK_CONF_ROUTING
#define NETSTACK_CONF_ROUTING rpl_classic_driver

/* Route table: need routes to all 35 sensor nodes at root and
 * intermediate nodes for storing-mode downward routing (echo replies) */
#define UIP_CONF_MAX_ROUTES 40

/* Neighbor table: each node has up to 25 radio neighbors in 6x6 grid.
 * Default 16 is insufficient; increase to prevent DAO relay failures. */
#define NBR_TABLE_CONF_MAX_NEIGHBORS 30

/* Enable IPv6 forwarding on non-root nodes */
#ifndef UIP_CONF_ROUTER
#define UIP_CONF_ROUTER 1
#endif

/* ================================================================== */
/* BRPL enable                                                         */
/* ================================================================== */
#define BRPL_CONF_ENABLE 1

/* Forward declaration so project-conf can reference rpl_brpl */
typedef struct rpl_of rpl_of_t;
extern rpl_of_t rpl_brpl;

/* ================================================================== */
/* Protocol variants (set via Makefile CFLAGS)                        */
/*   RPL_BASELINE_MODE=1  -> pure RPL / MRHOF                         */
/*   BRPL_MODE=1          -> BRPL, trust disabled                     */
/*   TABRPL_MODE=1        -> BRPL + on-node TA-BRPL trust             */
/* ================================================================== */

#if defined(BRPL_MODE) && (BRPL_MODE)
#define RPL_CONF_SUPPORTED_OFS {&rpl_brpl}
#define RPL_CONF_OF_OCP        RPL_OCP_BRPL
#endif

/* ================================================================== */
/* TA-BRPL: preferred-parent change callback                          */
/* Wires rpl_set_preferred_parent() → brpl_preferred_parent_changed() */
/* Without this, current_parent_id stays 0xffff and escape never fires */
/* ================================================================== */
#if defined(TABRPL_MODE) && (TABRPL_MODE)
#include <stdint.h>
#define RPL_CALLBACK_PARENT_SWITCH brpl_parent_switch_callback
#endif

#if defined(RPL_BASELINE_MODE) && (RPL_BASELINE_MODE)
/* Pure RPL: MRHOF + ETX metric container, trust disabled */
#undef  RPL_CONF_OF_OCP
#define RPL_CONF_OF_OCP        RPL_OCP_MRHOF
#undef  RPL_CONF_WITH_MC
#define RPL_CONF_WITH_MC       1
#undef  RPL_CONF_DAG_MC
#define RPL_CONF_DAG_MC        RPL_DAG_MC_ETX
#undef  BRPL_CONF_TRUST_ENABLE
#define BRPL_CONF_TRUST_ENABLE 0
#endif

/* ================================================================== */
/* RPL parameters (experiment: GRID 6x6, 36 nodes)                   */
/* ================================================================== */
/* DIO Imin = 4096 ms (2^12) per experiment spec */
#define RPL_CONF_DIO_INTERVAL_MIN      12
#define RPL_CONF_DIO_INTERVAL_DOUBLINGS 8
#define RPL_CONF_DIO_REDUNDANCY        10

/* ================================================================== */
/* Traffic parameters                                                  */
/* ================================================================== */
#ifndef SEND_INTERVAL_SECONDS
#define SEND_INTERVAL_SECONDS 30   /* 30 s per experiment spec */
#endif

#ifndef WARMUP_SECONDS
#define WARMUP_SECONDS 150         /* DODAG formation phase */
#endif

/* ================================================================== */
/* Congestion induction                                                */
/* ================================================================== */
#ifndef CONGESTION_INDUCTION_ENABLE
#define CONGESTION_INDUCTION_ENABLE 1
#endif

#ifndef CONGESTION_START_SECONDS
#define CONGESTION_START_SECONDS 200
#endif

#ifndef CONGESTION_END_SECONDS
#define CONGESTION_END_SECONDS   300
#endif

#ifndef CONGESTION_SEND_INTERVAL_SECONDS
#define CONGESTION_SEND_INTERVAL_SECONDS 15
#endif

/* ================================================================== */
/* TA-BRPL trust model parameters                                     */
/* ================================================================== */
#ifndef TA_TRUST_SCALE
#define TA_TRUST_SCALE            1000
#endif

/* --- Thresholds: tau_warn=0.60, tau_join=0.35, tau_black=0.20 --- *
 * Honest nodes reach T_fwd ≈ 0.63 in steady state (70% echo delivery
 * rate in lossless sim × PRR=1.0). tau_warn must be below this level
 * so honest nodes remain in NORMAL tier without cost penalty.        */
#ifndef TA_TRUST_TAU_WARN
#define TA_TRUST_TAU_WARN         600
#endif
#ifndef TA_TRUST_TAU_JOIN
#define TA_TRUST_TAU_JOIN         510
#endif
#ifndef TA_TRUST_TAU_BLACK
#define TA_TRUST_TAU_BLACK        200
#endif

/* Initial trust = 0.5 */
#ifndef TA_TRUST_INIT
#define TA_TRUST_INIT             500
#endif

/* EWMA: lambda_normal=0.7 (slow recovery), lambda_decrease=0.4 (balanced response)
 * lambda_decrease=0.2 was too aggressive: 80% weight on each new observation caused
 * excessive variance and FP blacklisting during route churn. With 0.4, honest nodes
 * transition smoothly from PRR=1000 to echo-based ≈630 and stay above tau_warn=600. */
#ifndef TA_TRUST_LAMBDA_NORMAL
#define TA_TRUST_LAMBDA_NORMAL    700
#endif
#ifndef TA_TRUST_LAMBDA_DECREASE
#define TA_TRUST_LAMBDA_DECREASE  400
#endif

/* Trust update interval = 60 s */
#ifndef TA_TRUST_UPDATE_INTERVAL
#define TA_TRUST_UPDATE_INTERVAL  60
#endif

/* ETX-based PRR estimation clamps for T_fwd (per-mille scale). */
#ifndef TA_PRR_MIN
#define TA_PRR_MIN               100
#endif
#ifndef TA_PRR_BLEND_WEIGHT
#define TA_PRR_BLEND_WEIGHT      1000
#endif
#ifndef TA_PRR_FALLBACK
#define TA_PRR_FALLBACK          1000
#endif
#ifndef TA_TFWD_SHARPEN_SCALE
#define TA_TFWD_SHARPEN_SCALE    1000
#endif

/* Aggregation weights: T_fwd=50%, T_ctrl=30%, T_hon=20% */
#ifndef TA_TRUST_W_FWD
#define TA_TRUST_W_FWD  5
#endif
#ifndef TA_TRUST_W_CTRL
#define TA_TRUST_W_CTRL 3
#endif
#ifndef TA_TRUST_W_HON
#define TA_TRUST_W_HON  2
#endif

/* --- Blacklist parameters --- */
/* Quarantine duration after blacklisting (seconds) */
#ifndef TA_TRUST_BLACKLIST_DURATION
#define TA_TRUST_BLACKLIST_DURATION 120
#endif
/* Trust restored to when un-blacklisted (= tau_join) */
#ifndef TA_TRUST_RESTORE_ON_RELEASE
#define TA_TRUST_RESTORE_ON_RELEASE 350
#endif
/* Minimum time between consecutive releases (seconds) */
#ifndef TA_TRUST_RELEASE_COOLDOWN_SECONDS
#define TA_TRUST_RELEASE_COOLDOWN_SECONDS 120
#endif
/* Penalty scaling at first release (basis 1000) */
#ifndef TA_TRUST_RELEASE_PENALTY_SCALE_START
#define TA_TRUST_RELEASE_PENALTY_SCALE_START 1600
#endif

/* --- Attack persistence penalty --- */
/* Window for measuring sustained attack (seconds) */
#ifndef TA_TRUST_ATTACK_PERSIST_WINDOW_SECONDS
#define TA_TRUST_ATTACK_PERSIST_WINDOW_SECONDS 120
#endif
/* Per-window penalty step (basis 1000) */
#ifndef TA_TRUST_ATTACK_PERSIST_PENALTY_STEP
#define TA_TRUST_ATTACK_PERSIST_PENALTY_STEP 250
#endif
/* Maximum total persistence penalty (basis 1000) */
#ifndef TA_TRUST_ATTACK_PERSIST_PENALTY_MAX
#define TA_TRUST_ATTACK_PERSIST_PENALTY_MAX 2600
#endif
/* Applied when node IS the current parent (basis 1000) */
#ifndef TA_TRUST_ATTACK_PARENT_PENALTY_SCALE
#define TA_TRUST_ATTACK_PARENT_PENALTY_SCALE 1900
#endif

/* --- Escape mechanism --- */
/* Seconds with low-trust current parent before escape triggers */
#ifndef TA_TRUST_ESCAPE_TRIGGER_SECONDS
#define TA_TRUST_ESCAPE_TRIGGER_SECONDS 720
#endif
/* Additional penalty scale applied on escape (basis 1000) */
#ifndef TA_TRUST_ESCAPE_PENALTY_SCALE
#define TA_TRUST_ESCAPE_PENALTY_SCALE 3200
#endif
/* Trust threshold below which escape arms (= tau_warn) */
#ifndef TA_TRUST_ESCAPE_TRUST_THRESHOLD
#define TA_TRUST_ESCAPE_TRUST_THRESHOLD 600
#endif
#ifndef TA_TRUST_ESCAPE_CONSECUTIVE_UPDATES
#define TA_TRUST_ESCAPE_CONSECUTIVE_UPDATES 4
#endif
#ifndef TA_TRUST_ESCAPE_COOLDOWN_SECONDS
#define TA_TRUST_ESCAPE_COOLDOWN_SECONDS 0
#endif
#ifndef TA_TRUST_ESCAPE_REQUIRE_BETTER_PARENT
#define TA_TRUST_ESCAPE_REQUIRE_BETTER_PARENT 1
#endif
#ifndef TA_TRUST_ESCAPE_BETTER_TRUST_MARGIN
#define TA_TRUST_ESCAPE_BETTER_TRUST_MARGIN 0
#endif
#ifndef TA_TRUST_ESCAPE_BETTER_PATH_MARGIN
#define TA_TRUST_ESCAPE_BETTER_PATH_MARGIN 0
#endif

/* --- Conservative conditional eviction (current parent only) --- */
#ifndef TA_TRUST_COND_EVICT_ENABLE
#define TA_TRUST_COND_EVICT_ENABLE 1
#endif
#ifndef TA_TRUST_COND_EVICT_MIN_PARENT_AGE_SECONDS
#define TA_TRUST_COND_EVICT_MIN_PARENT_AGE_SECONDS 900
#endif
#ifndef TA_TRUST_COND_EVICT_LOW_UPDATES
#define TA_TRUST_COND_EVICT_LOW_UPDATES 6
#endif
#ifndef TA_TRUST_COND_EVICT_COOLDOWN_SECONDS
#define TA_TRUST_COND_EVICT_COOLDOWN_SECONDS 900
#endif
#ifndef TA_TRUST_COND_EVICT_BETTER_TRUST_MARGIN
#define TA_TRUST_COND_EVICT_BETTER_TRUST_MARGIN 60
#endif
#ifndef TA_TRUST_COND_EVICT_BETTER_PATH_MARGIN
#define TA_TRUST_COND_EVICT_BETTER_PATH_MARGIN 40
#endif

/* --- Soft conditional release (stability-preserving retention relaxation) --- */
#ifndef TA_TRUST_SOFT_RELEASE_ENABLE
#define TA_TRUST_SOFT_RELEASE_ENABLE 1
#endif
#ifndef TA_TRUST_SOFT_RELEASE_MIN_PARENT_AGE_SECONDS
#define TA_TRUST_SOFT_RELEASE_MIN_PARENT_AGE_SECONDS 360
#endif
#ifndef TA_TRUST_SOFT_RELEASE_LOW_UPDATES
#define TA_TRUST_SOFT_RELEASE_LOW_UPDATES 4
#endif
#ifndef TA_TRUST_SOFT_RELEASE_MIN_SUSPICION
#define TA_TRUST_SOFT_RELEASE_MIN_SUSPICION 1
#endif
#ifndef TA_TRUST_SOFT_RELEASE_BETTER_TRUST_MARGIN
#define TA_TRUST_SOFT_RELEASE_BETTER_TRUST_MARGIN 0
#endif
#ifndef TA_TRUST_SOFT_RELEASE_BETTER_PATH_MARGIN
#define TA_TRUST_SOFT_RELEASE_BETTER_PATH_MARGIN 0
#endif
#ifndef TA_TRUST_SOFT_RELEASE_COOLDOWN_SECONDS
#define TA_TRUST_SOFT_RELEASE_COOLDOWN_SECONDS 180
#endif

/* --- v8b: landing-quality gate and loss-adaptive switch margin --- */
#ifndef TA_TRUST_SWITCH_CANDIDATE_TFWD_MIN
#define TA_TRUST_SWITCH_CANDIDATE_TFWD_MIN TA_TRUST_TAU_WARN
#endif
#ifndef TA_TRUST_SWITCH_REQUIRE_CLEAN
#define TA_TRUST_SWITCH_REQUIRE_CLEAN 1
#endif
#ifndef TA_TRUST_LOSS_ADAPTIVE_MARGIN
#define TA_TRUST_LOSS_ADAPTIVE_MARGIN 180
#endif
#ifndef TA_TRUST_REENTRY_COOLDOWN_SECONDS
#define TA_TRUST_REENTRY_COOLDOWN_SECONDS 240
#endif
/* In loss-aware switch mode, require a challenger to show either:
 * (a) recent forwarding success evidence, or
 * (b) at least minimal fresh control visibility + stronger aggregate trust. */
#ifndef TA_TRUST_SWITCH_RECENT_SENT_MIN
#define TA_TRUST_SWITCH_RECENT_SENT_MIN 3
#endif
#ifndef TA_TRUST_SWITCH_RECENT_SUCCESS_MIN
#define TA_TRUST_SWITCH_RECENT_SUCCESS_MIN 500
#endif
#ifndef TA_TRUST_SWITCH_RECENT_MIN_DIO
#define TA_TRUST_SWITCH_RECENT_MIN_DIO 1
#endif
#ifndef TA_TRUST_SWITCH_LOSS_MIN_TRUST
#define TA_TRUST_SWITCH_LOSS_MIN_TRUST 650
#endif
/* --- v10: recent-switch-aware re-entry suppression --- */
#ifndef TA_TRUST_RECENT_SWITCH_WINDOW_SECONDS
#define TA_TRUST_RECENT_SWITCH_WINDOW_SECONDS 180
#endif
#ifndef TA_TRUST_RECENT_SWITCH_MARGIN
#define TA_TRUST_RECENT_SWITCH_MARGIN 120
#endif
#ifndef TA_TRUST_REENTRY_MARGIN
#define TA_TRUST_REENTRY_MARGIN 220
#endif
#ifndef TA_TRUST_RECENT_SWITCH_BLOCK_COUNT
#define TA_TRUST_RECENT_SWITCH_BLOCK_COUNT 2
#endif
#ifndef TA_TRUST_RECENT_ATTACKER_PARENT_WINDOW_SECONDS
#define TA_TRUST_RECENT_ATTACKER_PARENT_WINDOW_SECONDS 300
#endif
/* --- v11: normal-to-normal oscillation suppression --- */
#ifndef TA_TRUST_NN_HOLD_SECONDS
#define TA_TRUST_NN_HOLD_SECONDS 180
#endif
#ifndef TA_TRUST_NN_EXTRA_MARGIN
#define TA_TRUST_NN_EXTRA_MARGIN 140
#endif
#ifndef TA_TRUST_NN_RECENT_SWITCH_MARGIN
#define TA_TRUST_NN_RECENT_SWITCH_MARGIN 220
#endif
#ifndef TA_TRUST_NONATT_TO_ATT_EXTRA_MARGIN
#define TA_TRUST_NONATT_TO_ATT_EXTRA_MARGIN 260
#endif
#ifndef TA_TRUST_ATT_TO_NONATT_MARGIN_RELAX
#define TA_TRUST_ATT_TO_NONATT_MARGIN_RELAX 80
#endif

#ifndef TA_TRUST_MAX_NEIGHBORS
#define TA_TRUST_MAX_NEIGHBORS 16
#endif

/* ================================================================== */
/* BRPL trust bridge: pass BRPL trust params through                  */
/* ================================================================== */
/* TRUST_SCALE used inside rpl-brpl.c */
#ifndef TRUST_SCALE
#define TRUST_SCALE               1000
#endif

/* Minimum trust value for parent candidate (= tau_join) */
#ifndef TRUST_MIN
#define TRUST_MIN                 TA_TRUST_TAU_JOIN
#endif

/* EWMA penalty applied inside BRPL scoring (basis 1000) */
#ifndef BRPL_CONF_TRUST_LAMBDA_PENALTY
#define BRPL_CONF_TRUST_LAMBDA_PENALTY 450
#endif

/* Extra backpressure penalty for current parent when trust is low (basis 1000) */
#ifndef BRPL_CONF_CURRENT_PARENT_PENALTY_SCALE
#define BRPL_CONF_CURRENT_PARENT_PENALTY_SCALE 700
#endif

/* Parent switch hysteresis:
 * switch from current preferred parent only when improvement is meaningful. */
#ifndef BRPL_CONF_SWITCH_MARGIN_PPM
#define BRPL_CONF_SWITCH_MARGIN_PPM 170
#endif
#ifndef BRPL_CONF_SWITCH_MARGIN_ABS
#define BRPL_CONF_SWITCH_MARGIN_ABS 90
#endif
#ifndef BRPL_CONF_PARENT_DWELL_SECONDS
#define BRPL_CONF_PARENT_DWELL_SECONDS 180
#endif

/* ================================================================== */
/* Queue (congestion model)                                            */
/* ================================================================== */
/* BRPL queue max = 8 packets (QUEUEBUF_NUM, per experiment.md §7)    */
#ifndef BRPL_CONF_QUEUE_MAX
#define BRPL_CONF_QUEUE_MAX       8
#endif

/* ================================================================== */
/* Logging (keep Cooja serial buffer manageable)                      */
/* ================================================================== */
#define LOG_CONF_LEVEL_RPL  LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_IPV6 LOG_LEVEL_WARN

#ifndef CSV_VERBOSE_LOGGING
#define CSV_VERBOSE_LOGGING 1
#endif

#endif /* PROJECT_CONF_H_ */
