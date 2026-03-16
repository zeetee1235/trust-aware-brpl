/*
 * ta-brpl-trust.h
 * On-node trust model for TA-BRPL (Trust-Aware Backpressure RPL)
 *
 * Three-component trust model:
 *   T_fwd  : Forwarding Trust (selective forwarding detection)
 *   T_ctrl : Control-plane Trust (rank/DIO/version anomaly)
 *   T_hon  : Congestion Honesty Trust (backlog advertisement)
 *
 * Aggregation  : Weighted geometric mean
 * Update policy: EWMA with asymmetric lambda (fast decay, slow recovery)
 * Thresholds   : tau_warn=0.75, tau_join=0.55, tau_black=0.35
 */

#ifndef TA_BRPL_TRUST_H_
#define TA_BRPL_TRUST_H_

#include <stdint.h>

/* ------------------------------------------------------------------ */
/* Scale and thresholds (all values in [0, TA_TRUST_SCALE])           */
/* ------------------------------------------------------------------ */
#ifndef TA_TRUST_SCALE
#define TA_TRUST_SCALE         1000
#endif

/* tau_warn : normal operation, allowed as parent candidate */
#ifndef TA_TRUST_TAU_WARN
#define TA_TRUST_TAU_WARN      750
#endif

/* tau_join : suspect, penalised in cost function but not excluded */
#ifndef TA_TRUST_TAU_JOIN
#define TA_TRUST_TAU_JOIN      550
#endif

/* tau_black : excluded from parent set */
#ifndef TA_TRUST_TAU_BLACK
#define TA_TRUST_TAU_BLACK     350
#endif

/* Initial trust value (0.5) */
#ifndef TA_TRUST_INIT
#define TA_TRUST_INIT          500
#endif

/* ------------------------------------------------------------------ */
/* EWMA parameters (scaled by TA_TRUST_SCALE)                         */
/* ------------------------------------------------------------------ */
/* Lambda when behaviour is normal (slow change, resist on-off attack) */
#ifndef TA_TRUST_LAMBDA_NORMAL
#define TA_TRUST_LAMBDA_NORMAL   700
#endif

/* Lambda when trust decreases (fast response to attacks) */
#ifndef TA_TRUST_LAMBDA_DECREASE
#define TA_TRUST_LAMBDA_DECREASE 200
#endif

/* ------------------------------------------------------------------ */
/* T_fwd Bayesian smoothing params (alpha, beta)                      */
/* ------------------------------------------------------------------ */
#ifndef TA_TRUST_FWD_ALPHA
#define TA_TRUST_FWD_ALPHA   1
#endif
#ifndef TA_TRUST_FWD_BETA
#define TA_TRUST_FWD_BETA    1
#endif

/* ------------------------------------------------------------------ */
/* T_ctrl component weights (w1+w2+w3 = 10)                           */
/* ------------------------------------------------------------------ */
#ifndef TA_TRUST_CTRL_W_RANK
#define TA_TRUST_CTRL_W_RANK  5
#endif
#ifndef TA_TRUST_CTRL_W_DIO
#define TA_TRUST_CTRL_W_DIO   3
#endif
#ifndef TA_TRUST_CTRL_W_VER
#define TA_TRUST_CTRL_W_VER   2
#endif

/* ------------------------------------------------------------------ */
/* Aggregation weights (wf + wc + wh = 10)                            */
/* ------------------------------------------------------------------ */
#ifndef TA_TRUST_W_FWD
#define TA_TRUST_W_FWD  5   /* 0.5 */
#endif
#ifndef TA_TRUST_W_CTRL
#define TA_TRUST_W_CTRL 3   /* 0.3 */
#endif
#ifndef TA_TRUST_W_HON
#define TA_TRUST_W_HON  2   /* 0.2 */
#endif

/* ------------------------------------------------------------------ */
/* Blacklist quarantine duration (seconds)                             */
/* ------------------------------------------------------------------ */
#ifndef TA_TRUST_BLACKLIST_DURATION
#define TA_TRUST_BLACKLIST_DURATION 300
#endif

#ifndef TA_TRUST_RESTORE_ON_RELEASE
#define TA_TRUST_RESTORE_ON_RELEASE TA_TRUST_TAU_JOIN
#endif

/* After blacklist release, keep an elevated routing penalty for a short
 * cooldown window and decay it linearly back to 1.0. */
#ifndef TA_TRUST_RELEASE_COOLDOWN_SECONDS
#define TA_TRUST_RELEASE_COOLDOWN_SECONDS 120
#endif

#ifndef TA_TRUST_RELEASE_PENALTY_SCALE_START
#define TA_TRUST_RELEASE_PENALTY_SCALE_START 1600
#endif

#ifndef TA_TRUST_ATTACK_PARENT_PENALTY_SCALE
#define TA_TRUST_ATTACK_PARENT_PENALTY_SCALE 1700
#endif

#ifndef TA_TRUST_ATTACK_PERSIST_WINDOW_SECONDS
#define TA_TRUST_ATTACK_PERSIST_WINDOW_SECONDS 120
#endif

#ifndef TA_TRUST_ATTACK_PERSIST_PENALTY_STEP
#define TA_TRUST_ATTACK_PERSIST_PENALTY_STEP 250
#endif

#ifndef TA_TRUST_ATTACK_PERSIST_PENALTY_MAX
#define TA_TRUST_ATTACK_PERSIST_PENALTY_MAX 2600
#endif

#ifndef TA_TRUST_ESCAPE_TRIGGER_SECONDS
#define TA_TRUST_ESCAPE_TRIGGER_SECONDS 180
#endif

#ifndef TA_TRUST_ESCAPE_PENALTY_SCALE
#define TA_TRUST_ESCAPE_PENALTY_SCALE 3200
#endif

#ifndef TA_TRUST_ESCAPE_TRUST_THRESHOLD
#define TA_TRUST_ESCAPE_TRUST_THRESHOLD TA_TRUST_TAU_WARN
#endif

/* Max number of neighbours tracked */
#ifndef TA_TRUST_MAX_NEIGHBORS
#define TA_TRUST_MAX_NEIGHBORS 16
#endif

/* Trust update interval (seconds) */
#ifndef TA_TRUST_UPDATE_INTERVAL
#define TA_TRUST_UPDATE_INTERVAL 150
#endif

/* DIO anomaly: number of DIOs per window considered normal */
#ifndef TA_TRUST_DIO_NORMAL_RATE
#define TA_TRUST_DIO_NORMAL_RATE 5
#endif

/* ------------------------------------------------------------------ */
/* Trust status                                                        */
/* ------------------------------------------------------------------ */
typedef enum {
  TA_TRUST_NORMAL,      /* T >= tau_warn  : full parent candidate  */
  TA_TRUST_SUSPECT,     /* tau_join <= T < tau_warn : cost penalty  */
  TA_TRUST_UNTRUSTED,   /* tau_black <= T < tau_join : excluded     */
  TA_TRUST_BLACKLISTED  /* T < tau_black : quarantined              */
} ta_trust_status_t;

/* ------------------------------------------------------------------ */
/* Public API                                                          */
/* ------------------------------------------------------------------ */

/**
 * Initialise trust module and register IP input overhearing hook.
 * Call once at startup.
 */
void ta_trust_init(void);

/**
 * Notify that a data packet was sent to neighbour node_id.
 * Increments S_ij for T_fwd computation.
 */
void ta_trust_notify_sent(uint16_t node_id);

/**
 * Notify that a forwarding event was observed for neighbour node_id
 * (via passive overhearing).  Increments F_ij.
 */
void ta_trust_notify_forwarded(uint16_t node_id);

/**
 * Notify that a DIO was received from neighbour node_id.
 * Used for T_ctrl rank/version/frequency anomaly detection.
 */
void ta_trust_notify_dio(uint16_t node_id, uint16_t rank, uint8_t version);

/**
 * Notify the advertised backlog from neighbour node_id (from BRPL DIO).
 * Used for T_hon computation.
 * q_adv and q_max are in raw queue-length units.
 */
void ta_trust_notify_backlog(uint16_t node_id, uint16_t q_adv, uint16_t q_max);

/**
 * Run one trust update cycle (EWMA + aggregate) for all neighbours.
 * Should be called every TA_TRUST_UPDATE_INTERVAL seconds.
 */
void ta_trust_update_all(void);

/**
 * Get current trust value for node_id in [0, TA_TRUST_SCALE].
 * Returns TA_TRUST_INIT for unknown nodes.
 */
uint16_t ta_trust_get(uint16_t node_id);

/**
 * Get trust status classification for node_id.
 */
ta_trust_status_t ta_trust_get_status(uint16_t node_id);

/**
 * Returns 1 if node_id may be considered as a parent candidate.
 * (trust >= tau_join and not blacklisted)
 */
int ta_trust_is_parent_candidate(uint16_t node_id);

/**
 * Print trust table via printf (CSV format).
 */
void ta_trust_log_all(void);

/*
 * Overrides the __attribute__((weak)) brpl_trust_get() symbol in rpl-brpl.c.
 * The BRPL objective function calls this to obtain trust for parent scoring.
 */
uint16_t brpl_trust_get(uint16_t node_id);

/*
 * Optional dynamic multiplier for trust penalty.
 * Returns 1000 in steady state and a larger value during post-release cooldown.
 */
uint16_t brpl_penalty_scale_get(uint16_t node_id);

/*
 * Returns 1 if node_id is currently in escape mode and should not
 * receive preferred-parent hysteresis.
 */
int brpl_escape_mode_get(uint16_t node_id);

#endif /* TA_BRPL_TRUST_H_ */
