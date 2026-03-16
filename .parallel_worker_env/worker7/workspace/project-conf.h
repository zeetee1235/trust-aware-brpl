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
/* TA-BRPL trust model parameters (experiment.md §6)                  */
/* ================================================================== */
#ifndef TA_TRUST_SCALE
#define TA_TRUST_SCALE            1000
#endif

/* Thresholds: tau_warn=0.75, tau_join=0.55, tau_black=0.35 */
#ifndef TA_TRUST_TAU_WARN
#define TA_TRUST_TAU_WARN         750
#endif
#ifndef TA_TRUST_TAU_JOIN
#define TA_TRUST_TAU_JOIN         550
#endif
#ifndef TA_TRUST_TAU_BLACK
#define TA_TRUST_TAU_BLACK        350
#endif

/* Initial trust = 0.5 */
#ifndef TA_TRUST_INIT
#define TA_TRUST_INIT             500
#endif

/* EWMA: lambda_normal=0.7, lambda_decrease=0.2 (asymmetric) */
#ifndef TA_TRUST_LAMBDA_NORMAL
#define TA_TRUST_LAMBDA_NORMAL    700
#endif
#ifndef TA_TRUST_LAMBDA_DECREASE
#define TA_TRUST_LAMBDA_DECREASE  200
#endif

/* Trust update interval = 150 s */
#ifndef TA_TRUST_UPDATE_INTERVAL
#define TA_TRUST_UPDATE_INTERVAL  150
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

/* Blacklist quarantine duration */
#ifndef TA_TRUST_BLACKLIST_DURATION
#define TA_TRUST_BLACKLIST_DURATION 300
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
#define TRUST_MIN                 550
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
