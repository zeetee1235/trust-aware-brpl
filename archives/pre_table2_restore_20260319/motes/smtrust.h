/*
 * smtrust.h
 * SMTrust: Social-metric Trust model for RPL (Contiki-NG / Cooja)
 *
 * TrustIndex(Ni, Nj) = w1·TMSR + w2·TM(H0) + w3·TMEL
 *                    + w4·TMLLS + w5·TMMobility + w6·TMRT
 *
 * Metrics:
 *   TMSR       — packet forwarding success rate (overhearing)
 *   TM(H0)     — historical TrustIndex from previous cycle
 *   TMEL       — energy level (energest-based)
 *   TMLLS      — link/location stability (RSSI normalised)
 *   TMMobility — mobility (static nodes = 1.0 in our experiment)
 *   TMRT       — recommended trust (1-hop neighbours' opinion)
 *
 * Parent selection:
 *   Phase 1: reject t1/t2 (below 0.46)
 *   Phase 2: prefer t4/t5 whenever available
 *   Phase 3: fall back to t3 only when no t4/t5 candidate wins
 *   Phase 4: use MRHOF metric ordering inside the same trust tier
 *
 * Attack detection:
 *   Rank attack   — DIO rank change without seq increment
 *   Blackhole     — TMSR drop below SUCCESS_THRESHOLD
 *
 * Trust values are kept in floating-point (double) as this runs on
 * Cooja (JVM-hosted simulation), not bare metal.
 *
 * Integration:
 *   - Call smtrust_init() at startup
 *   - Register smtrust_ip_processor with NETSTACK
 *   - Call smtrust_notify_sent(parent_id) before each UDP send
 *   - Call smtrust_periodic_update() every SMTRUST_UPDATE_INTERVAL s
 *   - Implements brpl_trust_get() override (scaled to 0..1000)
 *     for use as an RPL-MRHOF penalty when SMTRUST_MODE=1
 */

#ifndef SMTRUST_H_
#define SMTRUST_H_

#include <stdint.h>

/* ------------------------------------------------------------------ */
/* Parameters                                                          */
/* ------------------------------------------------------------------ */

/* Trust threshold for parent candidacy (t3 boundary = 0.46).
 * This is the boundary between "Poor Trust" (t2) and "Fair Trust" (t3),
 * not a signal that all values >= 0.46 should be treated equally. */
#ifndef SMTRUST_THRESHOLD
#define SMTRUST_THRESHOLD       0.46
#endif

/* Blackhole detection: TMSR below this → attack suspected */
#ifndef SMTRUST_SUCCESS_THRESHOLD
#define SMTRUST_SUCCESS_THRESHOLD 0.5
#endif

/* Do not blacklist a parent based on a single missed overhearing. */
#ifndef SMTRUST_MIN_FWD_SAMPLES
#define SMTRUST_MIN_FWD_SAMPLES  4
#endif

/* Rank anomaly: tolerate up to 2× DEFAULT_RANK_INCREMENT deviation */
#ifndef SMTRUST_RANK_THRESHOLD
#define SMTRUST_RANK_THRESHOLD  512   /* 2 × 256 */
#endif

/* Max number of neighbours tracked */
#ifndef SMTRUST_MAX_NODES
#define SMTRUST_MAX_NODES       20
#endif

/* Trust update interval (seconds) — synced to RPL trickle period */
#ifndef SMTRUST_UPDATE_INTERVAL
#define SMTRUST_UPDATE_INTERVAL 120
#endif

/* Only let trust reorder parents when route quality is already close. */
#ifndef SMTRUST_METRIC_NEAR_TIE
#define SMTRUST_METRIC_NEAR_TIE 96
#endif

/* Require a meaningful trust gap before overriding MRHOF ordering. */
#ifndef SMTRUST_TRUST_DIFF_STRONG_X100
#define SMTRUST_TRUST_DIFF_STRONG_X100 12
#endif

#ifndef SMTRUST_TRUST_DIFF_WEAK_X100
#define SMTRUST_TRUST_DIFF_WEAK_X100 18
#endif

/* RSSI normalisation bounds (dBm) */
#ifndef SMTRUST_RSSI_MIN
#define SMTRUST_RSSI_MIN       (-100)
#endif
#ifndef SMTRUST_RSSI_MAX
#define SMTRUST_RSSI_MAX       (-40)
#endif

/* Metric weights (must sum to 1.0) */
#ifndef SMTRUST_W1
#define SMTRUST_W1  0.25   /* TMSR         */
#endif
#ifndef SMTRUST_W2
#define SMTRUST_W2  0.15   /* TM(H0)       */
#endif
#ifndef SMTRUST_W3
#define SMTRUST_W3  0.15   /* TMEL         */
#endif
#ifndef SMTRUST_W4
#define SMTRUST_W4  0.20   /* TMLLS        */
#endif
#ifndef SMTRUST_W5
#define SMTRUST_W5  0.15   /* TMMobility   */
#endif
#ifndef SMTRUST_W6
#define SMTRUST_W6  0.10   /* TMRT         */
#endif

/* Trust level labels */
typedef enum {
  SMTRUST_L1_NO_TRUST   = 0,   /* [0.00, 0.20] */
  SMTRUST_L2_POOR       = 1,   /* [0.21, 0.45] */
  SMTRUST_L3_FAIR       = 2,   /* [0.46, 0.70] */
  SMTRUST_L4_GOOD       = 3,   /* [0.71, 0.90] */
  SMTRUST_L5_FULL       = 4,   /* [0.91, 1.00] */
} smtrust_level_t;

/* Per-neighbour trust record */
typedef struct {
  uint16_t node_id;
  uint8_t  valid;
  uint8_t  is_suspicious;

  /* TMSR counters */
  uint32_t pkts_sent;       /* packets we forwarded to this node    */
  uint32_t pkts_observed;   /* forwarding events observed           */

  /* TMLLS: RSSI samples */
  int32_t  rssi_sum;
  uint16_t rssi_count;
  int16_t  rssi_last;

  /* Rank attack detection */
  uint16_t prev_rank;
  uint8_t  prev_dio_seq;
  uint8_t  dio_seq_seen;

  /* TMRT: recommended trust from neighbours (accumulated, averaged) */
  double   tmrt_sum;
  uint8_t  tmrt_count;

  /* Trust components (current cycle) */
  double   tmsr;
  double   tm_h0;      /* = trust_index from previous cycle         */
  double   tmel;
  double   tmlls;
  double   tm_mobility; /* static topology → always 1.0             */
  double   tmrt;

  /* Current TrustIndex */
  double   trust_index;
} smtrust_entry_t;

/* ------------------------------------------------------------------ */
/* Public API                                                          */
/* ------------------------------------------------------------------ */

/** Initialise module, register netstack input hook. */
void smtrust_init(void);

/** Notify that a packet was sent to neighbour node_id. */
void smtrust_notify_sent(uint16_t node_id);

/**
 * Run one full trust update cycle for all neighbours:
 *   recomputes all metrics → TrustIndex → logs CSV.
 * Call every SMTRUST_UPDATE_INTERVAL seconds.
 */
void smtrust_periodic_update(void);

/** Get TrustIndex ∈ [0.0, 1.0] for node_id. */
double smtrust_get(uint16_t node_id);

/** Get trust level (L1–L5) for node_id. */
smtrust_level_t smtrust_level(uint16_t node_id);

/**
 * Returns 1 if node_id is admissible as a parent candidate.
 * Current policy rejects t1/t2 and suspicious nodes; t3/t4/t5 remain
 * admissible, with final preference decided by smtrust_compare_parents().
 */
int smtrust_is_parent_candidate(uint16_t node_id);

/** Log trust table via printf. */
void smtrust_log_all(void);

/*
 * Overrides brpl_trust_get() weak symbol.
 * Returns TrustIndex scaled to [0, 1000] for BRPL integration.
 * (SMTrust runs on pure MRHOF, so this returns 1000 unless SMTRUST_BRPL=1.)
 */
uint16_t brpl_trust_get(uint16_t node_id);

/*
 * Append custom SMTrust options to outgoing DIOs.
 * Returns the new buffer position.
 */
int smtrust_append_dio_options(uint8_t *buffer, int pos, int max_len);

/*
 * Optional parent ordering hook used by MRHOF when SMTRUST_MODE is enabled.
 * Policy:
 *   - prefer t4/t5 over t3 regardless of metric gap
 *   - compare within the same trust tier using trust-first only for
 *     near-tie metrics, otherwise defer to MRHOF
 * Returns -1 to prefer p1, 1 to prefer p2, 0 for no override.
 */
int smtrust_compare_parents(uint16_t p1_id, uint16_t p2_id,
                            uint16_t p1_rank, uint16_t p2_rank,
                            uint16_t self_rank,
                            uint16_t p1_metric, uint16_t p2_metric);

#endif /* SMTRUST_H_ */
