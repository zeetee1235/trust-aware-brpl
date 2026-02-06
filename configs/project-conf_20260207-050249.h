#ifndef PROJECT_CONF_H_
#define PROJECT_CONF_H_

/* Enable BRPL routing in Contiki-NG */
#define BRPL_CONF_ENABLE 1

/* Allow build-time override for trust parameters via *_CONF */
#ifndef TRUST_LAMBDA
#ifdef TRUST_LAMBDA_CONF
#define TRUST_LAMBDA TRUST_LAMBDA_CONF
#endif
#endif
#ifndef TRUST_PENALTY_GAMMA
#ifdef TRUST_PENALTY_GAMMA_CONF
#define TRUST_PENALTY_GAMMA TRUST_PENALTY_GAMMA_CONF
#endif
#endif

/* Forward declaration for custom BRPL objective function. */
typedef struct rpl_of rpl_of_t;
extern rpl_of_t rpl_brpl;

#ifdef BRPL_MODE
/* BRPL config: set objective function to BRPL explicitly. */
#define RPL_CONF_SUPPORTED_OFS {&rpl_brpl}
#define RPL_CONF_OF_OCP RPL_OCP_BRPL
#endif

/* Force RPL-Classic routing for BRPL support. */
#undef NETSTACK_CONF_ROUTING
#define NETSTACK_CONF_ROUTING rpl_classic_driver

/* Enable IPv6 forwarding on non-root nodes (required for manual routes). */
#ifndef UIP_CONF_ROUTER
#define UIP_CONF_ROUTER 1
#endif

#ifndef SEND_INTERVAL_SECONDS
#define SEND_INTERVAL_SECONDS 10
#endif

#ifndef WARMUP_SECONDS
#define WARMUP_SECONDS 60
#endif

/* RPL Fast Network Formation for Multi-hop Topology */
/* Reduce DIO interval for faster convergence in multi-hop scenarios */
#define RPL_CONF_DIO_INTERVAL_MIN 8    /* Default: 12 (4.096s) -> 8 (256ms) */
#define RPL_CONF_DIO_INTERVAL_DOUBLINGS 10  /* Max interval ~256s */
#define RPL_CONF_DIO_REDUNDANCY 10     /* Suppress threshold */

/* Trust (EWMA) parameters */
#ifndef TRUST_MAX_NODES
#define TRUST_MAX_NODES 256
#endif
#ifndef TRUST_SCALE
#define TRUST_SCALE 1000
#endif
#ifndef TRUST_ALPHA_NUM
#define TRUST_ALPHA_NUM 2
#endif
#ifndef TRUST_ALPHA_DEN
#define TRUST_ALPHA_DEN 10
#endif
#ifndef TRUST_PARENT_MIN
#define TRUST_PARENT_MIN 700
#endif

#ifndef TRUST_LAMBDA
#define TRUST_LAMBDA 0
#endif

#ifndef TRUST_GAMMA
#define TRUST_GAMMA 1
#endif

/* CSV logging control (reduce RS232 buffer overflow) */
#ifndef CSV_LOG_SAMPLE_RATE
#define CSV_LOG_SAMPLE_RATE 10  /* Only log 1 out of every N events */
#endif

/* Keep logs readable in Cooja for experiment parsing. */
#define LOG_LEVEL_APP LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_RPL LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_IPV6 LOG_LEVEL_WARN

/* Enable verbose CSV logging for parent candidate tracing */
#undef CSV_VERBOSE_LOGGING
#define CSV_VERBOSE_LOGGING 1
#ifndef CSV_LOG_SAMPLE_RATE
#define CSV_LOG_SAMPLE_RATE 1
#endif

#endif /* PROJECT_CONF_H_ */
#undef TRUST_LAMBDA_CONF
#define TRUST_LAMBDA_CONF 10
#undef TRUST_PENALTY_GAMMA_CONF
#define TRUST_PENALTY_GAMMA_CONF 10
