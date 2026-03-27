/*
 * ta-brpl-trust.c
 * On-node TA-BRPL trust model implementation.
 *
 * Trust components (all in [0, TA_TRUST_SCALE]):
 *
 *   T_fwd(ij)  = (F_ij + alpha) / (S_ij + alpha + beta)
 *                via passive overhearing (netstack IP input hook)
 *
 *   T_ctrl(ij) = 1 - A_ij
 *                A_ij = (w_rank*A_rank + w_dio*A_dio + w_ver*A_ver) / 10
 *
 *   T_hon(ij)  = 1 - min(1, |Q_adv - Q_est| / Q_max)
 *                Q_est approximated from local queue occupancy
 *
 *   T̃_ij = T_fwd^wf * T_ctrl^wc * T_hon^wh   (weighted geometric mean)
 *   T_ij(t+1) = lambda*T_ij(t) + (1-lambda)*T̃_ij
 *               asymmetric: lambda_decrease when trust falling
 */

#include "contiki.h"

#include "ta-brpl-trust.h"
#include "sys/log.h"
#include "sys/clock.h"
#include "net/netstack.h"
#include "net/packetbuf.h"
#include "net/ipv6/uip.h"
#include "net/ipv6/uipbuf.h"
#include "net/ipv6/uip-icmp6.h"
#include "net/linkaddr.h"
#include "net/link-stats.h"
#include "net/routing/rpl-classic/rpl-private.h"
#include "net/routing/rpl-classic/brpl-queue.h"
#include "net/routing/rpl-classic/brpl-switch-policy.h"

#include <string.h>
#include <stdio.h>
#include <math.h>

#define LOG_MODULE "TA-TRUST"
#define LOG_LEVEL  LOG_LEVEL_WARN

#ifndef TA_TRUST_FWD_BLACKLIST_STREAK
#define TA_TRUST_FWD_BLACKLIST_STREAK 3
#endif

/* Two-stage validation before hard exclusion. */
#ifndef TA_TRUST_REVIEW_WINDOWS
#define TA_TRUST_REVIEW_WINDOWS 3
#endif
#ifndef TA_TRUST_REVIEW_BAD_TO_PENALIZED
#define TA_TRUST_REVIEW_BAD_TO_PENALIZED 2
#endif
#ifndef TA_TRUST_REVIEW_BAD_TO_BLACKLIST
#define TA_TRUST_REVIEW_BAD_TO_BLACKLIST 2
#endif
#ifndef TA_TRUST_REVIEW_GOOD_RESET
#define TA_TRUST_REVIEW_GOOD_RESET 2
#endif
#ifndef TA_TRUST_REVIEW_PENALTY_SCALE
#define TA_TRUST_REVIEW_PENALTY_SCALE 1200
#endif
#ifndef TA_TRUST_PENALIZED_PENALTY_SCALE
#define TA_TRUST_PENALIZED_PENALTY_SCALE 1600
#endif
#ifndef TA_TRUST_REVIEW_SCORE_UNDER
#define TA_TRUST_REVIEW_SCORE_UNDER 8
#endif
#ifndef TA_TRUST_REVIEW_SCORE_PENALIZED
#define TA_TRUST_REVIEW_SCORE_PENALIZED 14
#endif
#ifndef TA_TRUST_REVIEW_SCORE_BLACKLIST
#define TA_TRUST_REVIEW_SCORE_BLACKLIST 7
#endif
#ifndef TA_TRUST_BLACKLIST_MIN_WINDOWS
#define TA_TRUST_BLACKLIST_MIN_WINDOWS 2
#endif
#ifndef TA_TRUST_VALIDATION_MIN_PARENT_AGE_SECONDS
#define TA_TRUST_VALIDATION_MIN_PARENT_AGE_SECONDS 120
#endif
#ifndef TA_TRUST_VALIDATION_MIN_SENT
#define TA_TRUST_VALIDATION_MIN_SENT 3
#endif
#ifndef TA_TRUST_VALIDATION_MIN_WINDOWS
#define TA_TRUST_VALIDATION_MIN_WINDOWS 3
#endif
#ifndef TA_TRUST_VALIDATION_MIN_ACC_SENT
#define TA_TRUST_VALIDATION_MIN_ACC_SENT 8
#endif
#ifndef TA_TRUST_VALIDATION_BAD_SUCCESS_MAX
#define TA_TRUST_VALIDATION_BAD_SUCCESS_MAX 150
#endif
#ifndef TA_TRUST_VALIDATION_STRONG_SUCCESS_MAX
#define TA_TRUST_VALIDATION_STRONG_SUCCESS_MAX 100
#endif
#ifndef TA_TRUST_VALIDATION_GOOD_SUCCESS_MIN
#define TA_TRUST_VALIDATION_GOOD_SUCCESS_MIN 550
#endif
#ifndef TA_TRUST_VALIDATION_BAD_INC
#define TA_TRUST_VALIDATION_BAD_INC 3
#endif
#ifndef TA_TRUST_VALIDATION_STRONG_BONUS
#define TA_TRUST_VALIDATION_STRONG_BONUS 2
#endif
#ifndef TA_TRUST_VALIDATION_GOOD_DEC
#define TA_TRUST_VALIDATION_GOOD_DEC 2
#endif
#ifndef TA_TRUST_VALIDATION_IDLE_DEC
#define TA_TRUST_VALIDATION_IDLE_DEC 1
#endif
#ifndef TA_TRUST_CTRL_LOW_RANK_FACTOR
#define TA_TRUST_CTRL_LOW_RANK_FACTOR 2
#endif
#ifndef TA_TRUST_CTRL_LOW_RANK_MIN_STREAK
#define TA_TRUST_CTRL_LOW_RANK_MIN_STREAK 3
#endif
#ifndef TA_TRUST_CTRL_LOW_RANK_STREAK_BONUS
#define TA_TRUST_CTRL_LOW_RANK_STREAK_BONUS 2
#endif
#ifndef TA_TRUST_CTRL_LOW_RANK_PENALTY_MAX
#define TA_TRUST_CTRL_LOW_RANK_PENALTY_MAX 350
#endif
#ifndef TA_ADMISSION_WARN_STREAK
#define TA_ADMISSION_WARN_STREAK 2
#endif
#ifndef TA_ADMISSION_BLOCK_STREAK
#define TA_ADMISSION_BLOCK_STREAK 4
#endif
#ifndef TA_ADMISSION_WARN_COUNT
#define TA_ADMISSION_WARN_COUNT 3
#endif
#ifndef TA_ADMISSION_BLOCK_COUNT
#define TA_ADMISSION_BLOCK_COUNT 6
#endif
#ifndef TA_ADMISSION_WARN_JOIN_PENALTY_SCALE
#define TA_ADMISSION_WARN_JOIN_PENALTY_SCALE 1400
#endif
#ifndef TA_TRUST_VALIDATION_BAD_STREAK_FOR_BLACKLIST
#define TA_TRUST_VALIDATION_BAD_STREAK_FOR_BLACKLIST 1
#endif
#ifndef TA_TRUST_FINAL_TFWD_MAX
#define TA_TRUST_FINAL_TFWD_MAX 300
#endif
#ifndef TA_TRUST_FINAL_TFWD_STREAK
#define TA_TRUST_FINAL_TFWD_STREAK 2
#endif
#ifndef TA_TRUST_LAMBDA_DECREASE_FWD
#define TA_TRUST_LAMBDA_DECREASE_FWD 200
#endif
#define TA_REVIEW_STATE_NORMAL    0
#define TA_REVIEW_STATE_UNDER     1
#define TA_REVIEW_STATE_PENALIZED 2

/* ------------------------------------------------------------------ */
/* Per-neighbour record                                                */
/* ------------------------------------------------------------------ */
typedef struct {
  uint16_t node_id;
  uint8_t  valid;

  /* T_fwd */
  uint32_t fwd_sent;       /* S_ij: packets sent to this neighbour     */
  uint32_t fwd_observed;   /* F_ij: forwarding observations (EWMA acc) */
  uint32_t fwd_observed_new; /* fresh observations this update window  */
  uint32_t fwd_sent_new;   /* fresh sends this update window (not halved) */

  /* T_ctrl */
  uint16_t ctrl_rank_last;         /* last advertised rank              */
  uint16_t ctrl_rank_dev_count;    /* rank deviation events             */
  uint16_t ctrl_dio_count;         /* DIO count in current window       */
  uint16_t ctrl_dio_excess;        /* excess DIO events (> normal rate) */
  uint8_t  ctrl_version_last;      /* last seen RPL version             */
  uint8_t  ctrl_version_seen;      /* whether we have a baseline        */
  uint16_t ctrl_version_mismatch;  /* version inconsistency count       */
  uint16_t ctrl_low_rank_count;    /* sustained near-root rank lure     */
  uint8_t  ctrl_low_rank_streak;   /* consecutive suspicious DIOs        */

  /* T_hon */
  uint16_t hon_q_adv;      /* advertised backlog (0..q_max)            */
  uint16_t hon_q_max;      /* max queue size as reported               */
  uint8_t  hon_valid;      /* whether backlog data is available        */

  /* Aggregated trust (0..TA_TRUST_SCALE) */
  uint16_t trust;

  /* T_fwd EWMA tracked independently from the geometric-mean aggregate.
   * A pure blackhole attacker keeps T_ctrl≈1000 and T_hon≈1000, so the
   * geometric mean floors at sqrt(T_fwd)≈0.4 even when T_fwd→0.17.
   * With tau_join=350 that aggregate floor (≈408) never triggers exclusion.
   * Tracking T_fwd separately lets us exclude based on forwarding evidence
   * alone, bypassing the T_ctrl/T_hon dilution for blackhole detection.  */
  uint16_t trust_fwd;

  /* Blacklist */
  uint8_t       blacklisted;
  clock_time_t  blacklist_until;
  uint8_t       release_active;
  uint8_t       release_redrop_armed;
  clock_time_t  release_started_at;
  uint8_t       low_trust_updates;
  uint8_t       low_tfwd_streak;
  uint8_t       review_state;
  uint8_t       review_windows_seen;
  uint8_t       review_bad_windows;
  uint8_t       review_good_windows;
  clock_time_t  review_parent_since;
  uint8_t       review_score;
  uint16_t      val_sent_acc;
  uint16_t      val_obs_acc;
  clock_time_t  reentry_block_until;
  clock_time_t  recent_attacker_parent_until;

  /* Admission accounting (new-parent candidates only). */
  uint32_t adm_new_eval;
  uint32_t adm_new_allow;
  uint32_t adm_new_block_blacklist;
  uint32_t adm_new_block_trust;
  uint32_t adm_new_block_review;
  uint32_t adm_new_block_severe;

} ta_trust_entry_t;

/* ------------------------------------------------------------------ */
/* State                                                               */
/* ------------------------------------------------------------------ */
static ta_trust_entry_t trust_table[TA_TRUST_MAX_NEIGHBORS];
static uint8_t trust_table_size;
/* O(1) node_id -> trust entry index map (node IDs are lladdr suffix, 0..255). */
static uint8_t trust_index_by_node_id[256];
static uint16_t current_parent_id = 0xffff;
static clock_time_t current_parent_since;
static uint8_t current_parent_escape_armed;
static clock_time_t current_parent_escape_cooldown_until;
static clock_time_t current_parent_cond_evict_cooldown_until;
static uint8_t current_parent_soft_release_armed;
static clock_time_t current_parent_soft_release_cooldown_until;
static clock_time_t recent_switch_window_started_at;
static uint8_t recent_switch_count;

static ta_trust_entry_t *find_entry(uint16_t node_id);

/* Admission suspicion level for non-current parent candidates.
 * 0: normal, 1: warning (allowed but heavier join penalty), 2: block. */
static uint8_t
admission_suspicion_level(const ta_trust_entry_t *e)
{
  if(e == NULL) {
    return 0;
  }

  if(e->ctrl_low_rank_streak >= TA_ADMISSION_BLOCK_STREAK ||
     e->ctrl_low_rank_count >= TA_ADMISSION_BLOCK_COUNT) {
    return 2;
  }

  if(e->ctrl_low_rank_streak >= TA_ADMISSION_WARN_STREAK ||
     e->ctrl_low_rank_count >= TA_ADMISSION_WARN_COUNT ||
     e->ctrl_rank_dev_count > 0) {
    return 1;
  }

  return 0;
}

static void
reset_review_state(ta_trust_entry_t *e)
{
  e->review_state = TA_REVIEW_STATE_NORMAL;
  e->review_windows_seen = 0;
  e->review_bad_windows = 0;
  e->review_good_windows = 0;
  e->review_parent_since = 0;
  e->review_score = 0;
  e->val_sent_acc = 0;
  e->val_obs_acc = 0;
}

static clock_time_t
current_parent_elapsed(void)
{
  if(current_parent_id == 0xffff || current_parent_since == 0) {
    return 0;
  }
  return clock_time() - current_parent_since;
}

static uint8_t
is_attacker_like_entry(const ta_trust_entry_t *e)
{
  uint8_t suspicion;

  if(e == NULL) {
    return 0;
  }
  suspicion = admission_suspicion_level(e);

  /* Switch-type classification is used for margin/guard behavior.
   * In lossy phases, tfwd-only drops can mislabel benign relays as
   * attacker-like and trigger normal-to-normal oscillation. */
  if(suspicion >= 2) {
    return 1;
  }
  if(e->review_state == TA_REVIEW_STATE_PENALIZED) {
    return 1;
  }
  /* Require at least some control-plane suspicion for tfwd-based tagging. */
  if(e->trust_fwd < TA_TRUST_TAU_JOIN && suspicion >= 1) {
    return 1;
  }
  return 0;
}

static uint8_t
is_current_parent_severe_attacker_like(void)
{
  ta_trust_entry_t *cur = find_entry(current_parent_id);

  if(cur == NULL) {
    return 0;
  }
  if(admission_suspicion_level(cur) >= 2) {
    return 1;
  }
  if(cur->review_state == TA_REVIEW_STATE_PENALIZED) {
    return 1;
  }
  if(cur->trust_fwd < TA_TRUST_TAU_JOIN) {
    return 1;
  }
  return 0;
}

static uint8_t
recent_switch_count_in_window(void)
{
  clock_time_t now = clock_time();
  clock_time_t window =
    (clock_time_t)TA_TRUST_RECENT_SWITCH_WINDOW_SECONDS * CLOCK_SECOND;

  if(window == 0) {
    return 0;
  }
  if(recent_switch_window_started_at == 0 || now <= recent_switch_window_started_at) {
    recent_switch_window_started_at = now;
    recent_switch_count = 0;
    return 0;
  }
  if(now - recent_switch_window_started_at >= window) {
    recent_switch_window_started_at = now;
    recent_switch_count = 0;
    return 0;
  }
  return recent_switch_count;
}

static uint16_t
attack_persistence_penalty_scale(const ta_trust_entry_t *e)
{
  uint16_t scale = TA_TRUST_SCALE;

  if(e == NULL) {
    return scale;
  }

  /* Only penalise the currently used parent when forwarding evidence
   * already indicates degradation. This avoids network-wide false
   * penalties in benign pre-attack periods. */
  if(e->node_id != current_parent_id || e->trust_fwd >= TA_TRUST_TAU_WARN) {
    return scale;
  }

  scale = TA_TRUST_ATTACK_PARENT_PENALTY_SCALE;

  clock_time_t elapsed = current_parent_elapsed();
  clock_time_t window = (clock_time_t)TA_TRUST_ATTACK_PERSIST_WINDOW_SECONDS * CLOCK_SECOND;

  if(window > 0) {
    uint32_t steps = elapsed / window;
    uint32_t extra = steps * TA_TRUST_ATTACK_PERSIST_PENALTY_STEP;
    uint32_t candidate = (uint32_t)scale + extra;
    if(candidate > TA_TRUST_ATTACK_PERSIST_PENALTY_MAX) {
      candidate = TA_TRUST_ATTACK_PERSIST_PENALTY_MAX;
    }
    scale = (uint16_t)candidate;
  }

  if(elapsed >= (clock_time_t)TA_TRUST_ESCAPE_TRIGGER_SECONDS * CLOCK_SECOND &&
     e->trust_fwd < TA_TRUST_TAU_JOIN &&
     scale < TA_TRUST_ESCAPE_PENALTY_SCALE) {
    scale = TA_TRUST_ESCAPE_PENALTY_SCALE;
  }

  return scale;
}

static uint16_t
ta_sharpen_tfwd(uint16_t trust)
{
#if TA_TFWD_SHARPEN_SCALE <= 1000
  return trust;
#else
  int32_t centered = (int32_t)trust - (int32_t)(TA_TRUST_SCALE / 2);
  int32_t scaled = (centered * TA_TFWD_SHARPEN_SCALE) / 1000;
  int32_t sharpened = (int32_t)(TA_TRUST_SCALE / 2) + scaled;

  if(sharpened < 0) {
    sharpened = 0;
  } else if(sharpened > TA_TRUST_SCALE) {
    sharpened = TA_TRUST_SCALE;
  }
  return (uint16_t)sharpened;
#endif
}

static int
ta_has_better_parent_candidate(uint16_t current_node_id,
                               uint16_t current_trust,
                               uint16_t trust_margin,
                               uint16_t path_margin,
                               uint16_t min_trust,
                               uint8_t require_clean_candidate)
{
#if TA_TRUST_ESCAPE_REQUIRE_BETTER_PARENT
  rpl_dag_t *dag = rpl_get_any_dag();

  if(dag != NULL) {
    rpl_parent_t *current_parent = NULL;
    rpl_parent_t *p;
    uint32_t current_path_cost = 0xffffffff;
    extern nbr_table_t *rpl_parents;

    for(p = nbr_table_head(rpl_parents); p != NULL;
        p = nbr_table_next(rpl_parents, p)) {
      const linkaddr_t *ll = rpl_get_parent_lladdr(p);
      if(ll != NULL && ll->u8[LINKADDR_SIZE - 1] == current_node_id) {
        current_parent = p;
        break;
      }
    }

    if(current_parent != NULL) {
      current_path_cost = (uint32_t)rpl_get_parent_link_metric(current_parent)
                        + (uint32_t)current_parent->rank;
    }

    for(p = nbr_table_head(rpl_parents); p != NULL;
        p = nbr_table_next(rpl_parents, p)) {
      const linkaddr_t *ll = rpl_get_parent_lladdr(p);
      ta_trust_entry_t *candidate;
      uint16_t node_id;
      uint16_t trust;
      uint32_t path_cost;

      if(ll == NULL) {
        continue;
      }

      node_id = ll->u8[LINKADDR_SIZE - 1];
      if(node_id == current_node_id) {
        continue;
      }

      candidate = find_entry(node_id);
      if(candidate != NULL && candidate->blacklisted) {
        continue;
      }

      trust = candidate != NULL ? candidate->trust : TA_TRUST_INIT;
      if(trust < min_trust) {
        continue;
      }
      if(require_clean_candidate) {
        if(candidate == NULL ||
           candidate->review_state != TA_REVIEW_STATE_NORMAL ||
           admission_suspicion_level(candidate) != 0 ||
           candidate->trust_fwd < TA_TRUST_TAU_WARN) {
          continue;
        }
      }
      if(trust + trust_margin < current_trust) {
        continue;
      }

      path_cost = (uint32_t)rpl_get_parent_link_metric(p) + (uint32_t)p->rank;
      if(current_path_cost != 0xffffffff &&
         path_cost > current_path_cost + path_margin) {
        continue;
      }

      return 1;
    }
  }

  return 0;
#else
  (void)current_node_id;
  (void)current_trust;
  (void)trust_margin;
  (void)path_margin;
  (void)min_trust;
  (void)require_clean_candidate;
  return 1;
#endif
}

static int
should_conditional_evict_current_parent(const ta_trust_entry_t *e)
{
#if TA_TRUST_COND_EVICT_ENABLE
  clock_time_t now = clock_time();

  if(e == NULL || e->node_id != current_parent_id) {
    return 0;
  }
  if(current_parent_elapsed() <
     (clock_time_t)TA_TRUST_COND_EVICT_MIN_PARENT_AGE_SECONDS * CLOCK_SECOND) {
    return 0;
  }
  if(current_parent_cond_evict_cooldown_until != 0 &&
     now < current_parent_cond_evict_cooldown_until) {
    return 0;
  }
  if(e->low_trust_updates < TA_TRUST_COND_EVICT_LOW_UPDATES) {
    return 0;
  }
  if(admission_suspicion_level(e) < 2) {
    return 0;
  }
  if(!(e->review_state == TA_REVIEW_STATE_PENALIZED ||
       e->trust_fwd < TA_TRUST_TAU_JOIN)) {
    return 0;
  }
  if(!ta_has_better_parent_candidate(e->node_id,
                                     e->trust,
                                     TA_TRUST_COND_EVICT_BETTER_TRUST_MARGIN,
                                     TA_TRUST_COND_EVICT_BETTER_PATH_MARGIN,
                                     TA_TRUST_TAU_WARN,
                                     1)) {
    return 0;
  }
  return 1;
#else
  (void)e;
  return 0;
#endif
}

static int
soft_release_mode_for_entry(const ta_trust_entry_t *e)
{
#if TA_TRUST_SOFT_RELEASE_ENABLE
  clock_time_t now = clock_time();

  if(e == NULL || e->node_id != current_parent_id) {
    return 0;
  }
  if(current_parent_elapsed() <
     (clock_time_t)TA_TRUST_SOFT_RELEASE_MIN_PARENT_AGE_SECONDS * CLOCK_SECOND) {
    return 0;
  }
  if(current_parent_soft_release_cooldown_until != 0 &&
     now < current_parent_soft_release_cooldown_until) {
    return 0;
  }
  if(e->low_trust_updates < TA_TRUST_SOFT_RELEASE_LOW_UPDATES) {
    return 0;
  }
  if(admission_suspicion_level(e) < TA_TRUST_SOFT_RELEASE_MIN_SUSPICION) {
    return 0;
  }
  if(!ta_has_better_parent_candidate(e->node_id,
                                     e->trust,
                                     TA_TRUST_SOFT_RELEASE_BETTER_TRUST_MARGIN,
                                     TA_TRUST_SOFT_RELEASE_BETTER_PATH_MARGIN,
                                     TA_TRUST_TAU_WARN,
                                     1)) {
    return 0;
  }
  return 1;
#else
  (void)e;
  return 0;
#endif
}

static int
escape_mode_for_entry(const ta_trust_entry_t *e)
{
  clock_time_t now = clock_time();

  if(e == NULL || e->node_id != current_parent_id) {
    return 0;
  }

  /* Never escape from the DODAG root: it is a sink and does not forward
   * packets, so T_fwd naturally converges to 0 — this is not malicious. */
  {
    rpl_dag_t *dag = rpl_get_any_dag();
    if(dag != NULL && dag->instance != NULL) {
      rpl_parent_t *p;
      extern nbr_table_t *rpl_parents;
      for(p = nbr_table_head(rpl_parents); p != NULL;
          p = nbr_table_next(rpl_parents, p)) {
        const linkaddr_t *ll = rpl_get_parent_lladdr(p);
        if(ll != NULL && ll->u8[LINKADDR_SIZE - 1] == e->node_id) {
          if(p->rank <= ROOT_RANK(dag->instance)) {
            return 0;
          }
          break;
        }
      }
    }
  }

  /* Gate on T_ctrl rank-lure signal, NOT T_fwd.
   *
   * T_fwd has an upstream attribution problem: when an attacker drops
   * packets, echo-based T_fwd falls for innocent relay nodes that route
   * through the attacker, causing 80%+ false-positive escape cascades.
   *
   * ctrl_low_rank_streak is a direct per-hop DIO anomaly count: it rises
   * only when THIS neighbour advertises a suspiciously low rank (sinkhole
   * lure), with no blame transferred from upstream hops.  It is therefore
   * accurate in both SINK_ONLY (rank lure, no drop — T_fwd stays high)
   * and SINK_DROP50 (rank lure + drop — T_fwd cascades to innocent nodes).
   *
   * TA_TRUST_ESCAPE_CTRL_MIN_STREAK defaults to TA_TRUST_CTRL_LOW_RANK_MIN_STREAK
   * (3 consecutive suspicious DIOs).  The low_trust_updates consecutive-
   * window check is omitted here because the streak field already encodes
   * consecutive bad DIO windows; it is still used by COND_EVICT / soft-
   * release which remain T_fwd–driven. */
#ifndef TA_TRUST_ESCAPE_CTRL_MIN_STREAK
#define TA_TRUST_ESCAPE_CTRL_MIN_STREAK TA_TRUST_CTRL_LOW_RANK_MIN_STREAK
#endif
#ifndef TA_TRUST_ESCAPE_CTRL_RANK_DEV_MIN
#define TA_TRUST_ESCAPE_CTRL_RANK_DEV_MIN 2
#endif
  if(e->ctrl_low_rank_streak < TA_TRUST_ESCAPE_CTRL_MIN_STREAK) {
    return 0;
  }
  /* v8a: require an additional evidence signal to reduce false-positive
   * escape cascades on GRID-like topologies.
   * Escape fires only when rank-lure streak AND (validation under review
   * OR rank deviation accumulation) are both present. */
  if(!(e->review_state >= TA_REVIEW_STATE_UNDER ||
       e->ctrl_rank_dev_count >= TA_TRUST_ESCAPE_CTRL_RANK_DEV_MIN)) {
    return 0;
  }
  if(current_parent_elapsed() < (clock_time_t)TA_TRUST_ESCAPE_TRIGGER_SECONDS * CLOCK_SECOND) {
    return 0;
  }
  if(current_parent_escape_cooldown_until != 0 && now < current_parent_escape_cooldown_until) {
    return 0;
  }
  if(!ta_has_better_parent_candidate(e->node_id,
                                     e->trust,
                                     TA_TRUST_ESCAPE_BETTER_TRUST_MARGIN,
                                     TA_TRUST_ESCAPE_BETTER_PATH_MARGIN,
                                     TA_TRUST_TAU_JOIN,
                                     0)) {
    return 0;
  }

  return 1;
}

static uint16_t
penalty_scale_for_entry(const ta_trust_entry_t *e)
{
  uint16_t scale = TA_TRUST_SCALE;

  if(e != NULL && e->release_active) {
    clock_time_t now = clock_time();
    clock_time_t cooldown = (clock_time_t)TA_TRUST_RELEASE_COOLDOWN_SECONDS * CLOCK_SECOND;
    if(cooldown == 0 || now <= e->release_started_at) {
      scale = TA_TRUST_RELEASE_PENALTY_SCALE_START;
    } else if(now - e->release_started_at < cooldown) {
      uint32_t remaining = (uint32_t)(cooldown - (now - e->release_started_at));
      uint32_t extra = (uint32_t)(TA_TRUST_RELEASE_PENALTY_SCALE_START - TA_TRUST_SCALE);
      scale = (uint16_t)(TA_TRUST_SCALE + (extra * remaining) / cooldown);
    }
  }

  if(e != NULL) {
    uint32_t combined = ((uint32_t)scale * attack_persistence_penalty_scale(e))
                        / TA_TRUST_SCALE;
    if(combined > 0xffff) {
      combined = 0xffff;
    }
    scale = (uint16_t)combined;

    /* Validation model is separated from trust model:
     * review_state/review_score do not affect trust penalty scale. */
  }

  return scale;
}

/* ------------------------------------------------------------------ */
/* Internal helpers                                                    */
/* ------------------------------------------------------------------ */
static ta_trust_entry_t *
find_entry(uint16_t node_id)
{
  if(node_id > 255) {
    return NULL;
  }
  uint8_t idx = trust_index_by_node_id[node_id];
  if(idx == 0xff || idx >= trust_table_size) {
    return NULL;
  }
  if(trust_table[idx].valid && trust_table[idx].node_id == node_id) {
    return &trust_table[idx];
  }
  return NULL;
}

static ta_trust_entry_t *
get_or_create(uint16_t node_id)
{
  ta_trust_entry_t *e = find_entry(node_id);
  if(e != NULL) {
    return e;
  }
  if(node_id > 255) {
    LOG_WARN("node id out of map range: %u\n", node_id);
    return NULL;
  }
  if(trust_table_size >= TA_TRUST_MAX_NEIGHBORS) {
    LOG_WARN("trust table full, dropping node %u\n", node_id);
    return NULL;
  }
  uint8_t idx = trust_table_size++;
  e = &trust_table[idx];
  memset(e, 0, sizeof(*e));
  e->node_id = node_id;
  e->valid   = 1;
  e->trust     = TA_TRUST_INIT;
  e->trust_fwd = TA_TRUST_INIT;
  trust_index_by_node_id[node_id] = idx;
  return e;
}

/* ------------------------------------------------------------------ */
/* T_fwd  = (F + alpha) / (E + alpha + beta)                          */
/* E = expected forwarding events = sent * PRR (channel-loss-aware)   */
/* PRR is estimated from Contiki-NG link-stats ETX for the neighbour. */
/* ------------------------------------------------------------------ */
static const linkaddr_t *
find_lladdr_by_node_id(uint16_t node_id)
{
  rpl_dag_t *dag = rpl_get_any_dag();

  if(dag != NULL) {
    rpl_parent_t *p;
    extern nbr_table_t *rpl_parents;

    for(p = nbr_table_head(rpl_parents); p != NULL;
        p = nbr_table_next(rpl_parents, p)) {
      const linkaddr_t *ll = rpl_get_parent_lladdr(p);
      if(ll != NULL && ll->u8[LINKADDR_SIZE - 1] == node_id) {
        return ll;
      }
    }
  }

  return NULL;
}

static uint32_t
ta_estimate_prr(const linkaddr_t *lladdr)
{
  const struct link_stats *stats;
  uint32_t raw_prr;
  uint32_t prr;

  if(lladdr == NULL) {
    return TA_PRR_FALLBACK;
  }

  stats = link_stats_from_lladdr(lladdr);
  if(stats == NULL || !link_stats_is_fresh(stats) || stats->etx == 0) {
    return TA_PRR_FALLBACK;
  }

  raw_prr = ((uint32_t)LINK_STATS_ETX_DIVISOR * TA_TRUST_SCALE) / stats->etx;
  if(raw_prr > TA_TRUST_SCALE) {
    raw_prr = TA_TRUST_SCALE;
  }

  prr = ((uint32_t)TA_PRR_BLEND_WEIGHT * raw_prr
       + (uint32_t)(TA_TRUST_SCALE - TA_PRR_BLEND_WEIGHT) * TA_TRUST_SCALE)
      / TA_TRUST_SCALE;
  if(prr > TA_TRUST_SCALE) {
    prr = TA_TRUST_SCALE;
  }
  if(prr < TA_PRR_MIN) {
    prr = TA_PRR_MIN;
  }

  return prr;
}

static uint16_t
compute_t_fwd(const ta_trust_entry_t *e)
{
  const linkaddr_t *lladdr = find_lladdr_by_node_id(e->node_id);
  uint32_t prr = ta_estimate_prr(lladdr);

  /* Use PRR as proxy when this neighbour was NOT actively used as a
   * parent in the CURRENT update window (fwd_sent_new == 0).
   *
   * fwd_sent_new counts only fresh sends this window (reset each cycle,
   * never halved).  This distinguishes two cases that the old condition
   * (fwd_observed_new == 0 OR fwd_sent < threshold) conflated:
   *
   * (a) Node NOT being used as parent this window (fwd_sent_new = 0):
   *     No active traffic → no reliable echo evidence → PRR fallback.
   *     Handles both bootstrapping and post-churn idle windows without
   *     penalising honest nodes that simply aren't on the active path.
   *
   * (b) Node IS current parent this window (fwd_sent_new > 0) but
   *     produces zero echoes:
   *     Packets sent and acknowledged at MAC layer, yet root never
   *     received them → classic IP-layer blackhole signature.
   *     Fall through to echo-based formula → low T_fwd → attacker
   *     excluded within 2-3 update windows.
   *
   * This fixes the prior inversion where attackers (always observed=0)
   * received PRR ≈ 1000 while honest nodes with 70% echo delivery
   * received T_fwd ≈ 0.63, causing TA-BRPL to score worse than RPL. */
  if(e->fwd_sent_new == 0) {
    return (uint16_t)prr;
  }

  uint32_t expected = (e->fwd_sent * prr + 500) / TA_TRUST_SCALE;

  uint32_t num = e->fwd_observed + TA_TRUST_FWD_ALPHA;
  uint32_t den = expected        + TA_TRUST_FWD_ALPHA + TA_TRUST_FWD_BETA;
  if(den == 0) {
    return TA_TRUST_SCALE;
  }
  uint32_t val = (num * TA_TRUST_SCALE) / den;
  if(val > TA_TRUST_SCALE) {
    val = TA_TRUST_SCALE;
  }
  return ta_sharpen_tfwd((uint16_t)val);
}

/* ------------------------------------------------------------------ */
/* T_ctrl = 1 - A_ij                                                  */
/* A_ij   = (w_rank*A_rank + w_dio*A_dio + w_ver*A_ver) / 10          */
/* Each A_x is normalised to [0, TA_TRUST_SCALE]                      */
/* ------------------------------------------------------------------ */
static uint16_t
compute_t_ctrl(const ta_trust_entry_t *e)
{
  /* A_rank: fraction of DIO observations with rank deviation          */
  uint16_t total_dio = e->ctrl_dio_count;
  uint16_t a_rank = (total_dio > 0)
    ? (uint16_t)((uint32_t)e->ctrl_rank_dev_count * TA_TRUST_SCALE / total_dio)
    : 0;
  if(a_rank > TA_TRUST_SCALE) a_rank = TA_TRUST_SCALE;

  /* A_dio: DIO frequency anomaly (excess DIOs / normal rate)          */
  uint16_t a_dio = 0;
  if(e->ctrl_dio_count > TA_TRUST_DIO_NORMAL_RATE) {
    uint32_t excess = e->ctrl_dio_count - TA_TRUST_DIO_NORMAL_RATE;
    a_dio = (uint16_t)((excess * TA_TRUST_SCALE) /
                       (e->ctrl_dio_count > 0 ? e->ctrl_dio_count : 1));
    if(a_dio > TA_TRUST_SCALE) a_dio = TA_TRUST_SCALE;
  }

  /* A_ver: version inconsistency fraction                             */
  uint16_t a_ver = (total_dio > 0)
    ? (uint16_t)((uint32_t)e->ctrl_version_mismatch * TA_TRUST_SCALE / total_dio)
    : 0;
  if(a_ver > TA_TRUST_SCALE) a_ver = TA_TRUST_SCALE;

  /* A_lure: sustained "too-good" low-rank advertising.
   * Sinkholes repeatedly advertise near-root rank (e.g., 257) while
   * remaining non-root nodes. We track persistent occurrences and add
   * an extra control-plane penalty on top of rank/dio/version signals. */
  uint16_t a_lure = (total_dio > 0)
    ? (uint16_t)((uint32_t)e->ctrl_low_rank_count * TA_TRUST_SCALE / total_dio)
    : 0;
  if(a_lure > TA_TRUST_SCALE) a_lure = TA_TRUST_SCALE;

  /* Weighted sum (weights sum to 10)                                  */
  uint32_t anomaly = ((uint32_t)TA_TRUST_CTRL_W_RANK * a_rank
                    + (uint32_t)TA_TRUST_CTRL_W_DIO  * a_dio
                    + (uint32_t)TA_TRUST_CTRL_W_VER  * a_ver) / 10;
  anomaly += ((uint32_t)TA_TRUST_CTRL_LOW_RANK_PENALTY_MAX * a_lure)
             / TA_TRUST_SCALE;
  if(anomaly > TA_TRUST_SCALE) anomaly = TA_TRUST_SCALE;

  return (uint16_t)(TA_TRUST_SCALE - anomaly);
}

/* ------------------------------------------------------------------ */
/* T_hon = 1 - min(1, |Q_adv - Q_est| / Q_max)                       */
/* Q_est approximated from local queue occupancy                       */
/* ------------------------------------------------------------------ */
static uint16_t
compute_t_hon(const ta_trust_entry_t *e)
{
  if(!e->hon_valid || e->hon_q_max == 0) {
    return TA_TRUST_SCALE; /* no data yet */
  }

  /* Q_est: use local queue occupancy as distributed proxy             */
  uint16_t q_local = brpl_queue_length();
  uint16_t q_max_local = brpl_queue_max();
  uint16_t q_est = (q_max_local > 0)
    ? (uint16_t)((uint32_t)q_local * e->hon_q_max / q_max_local)
    : 0;

  int32_t diff = (int32_t)e->hon_q_adv - (int32_t)q_est;
  if(diff < 0) diff = -diff;

  uint32_t ratio = ((uint32_t)diff * TA_TRUST_SCALE) / e->hon_q_max;
  if(ratio > TA_TRUST_SCALE) ratio = TA_TRUST_SCALE;

  return (uint16_t)(TA_TRUST_SCALE - ratio);
}

/* ------------------------------------------------------------------ */
/* Weighted geometric mean via pow()                                   */
/* T̃ = T_fwd^(wf/10) * T_ctrl^(wc/10) * T_hon^(wh/10)              */
/* ------------------------------------------------------------------ */
static uint16_t
aggregate_trust(uint16_t t_fwd, uint16_t t_ctrl, uint16_t t_hon)
{
  double wf = (double)TA_TRUST_W_FWD  / 10.0;
  double wc = (double)TA_TRUST_W_CTRL / 10.0;
  double wh = (double)TA_TRUST_W_HON  / 10.0;

  double tf = (double)t_fwd  / TA_TRUST_SCALE;
  double tc = (double)t_ctrl / TA_TRUST_SCALE;
  double th = (double)t_hon  / TA_TRUST_SCALE;

  /* Clamp to avoid log(0) */
  if(tf < 0.001) tf = 0.001;
  if(tc < 0.001) tc = 0.001;
  if(th < 0.001) th = 0.001;

  double result = pow(tf, wf) * pow(tc, wc) * pow(th, wh);
  if(result > 1.0) result = 1.0;
  if(result < 0.0) result = 0.0;

  return (uint16_t)(result * TA_TRUST_SCALE);
}

/* ------------------------------------------------------------------ */
/* EWMA update with asymmetric lambda                                  */
/* T(t+1) = lambda*T(t) + (1-lambda)*T̃                              */
/* ------------------------------------------------------------------ */
static uint16_t
ewma_update(uint16_t t_old, uint16_t t_new_obs)
{
  /* Use faster lambda when trust is decreasing (attack response)      */
  uint32_t lambda = (t_new_obs < t_old)
    ? TA_TRUST_LAMBDA_DECREASE
    : TA_TRUST_LAMBDA_NORMAL;

  uint32_t result = (lambda * t_old + (TA_TRUST_SCALE - lambda) * t_new_obs)
                    / TA_TRUST_SCALE;
  return (uint16_t)(result > TA_TRUST_SCALE ? TA_TRUST_SCALE : result);
}

static uint16_t
ewma_update_fwd(uint16_t t_old, uint16_t t_new_obs)
{
  uint32_t lambda = (t_new_obs < t_old)
    ? TA_TRUST_LAMBDA_DECREASE_FWD
    : TA_TRUST_LAMBDA_NORMAL;

  uint32_t result = (lambda * t_old + (TA_TRUST_SCALE - lambda) * t_new_obs)
                    / TA_TRUST_SCALE;
  return (uint16_t)(result > TA_TRUST_SCALE ? TA_TRUST_SCALE : result);
}

/* ------------------------------------------------------------------ */
/* Blacklist management                                                */
/* ------------------------------------------------------------------ */
static void
check_blacklist(ta_trust_entry_t *e)
{
  clock_time_t now = clock_time();

  if(e->blacklisted) {
    /* Release after quarantine period */
    if(now >= e->blacklist_until) {
      e->blacklisted = 0;
      e->trust = TA_TRUST_RESTORE_ON_RELEASE;
      e->trust_fwd = TA_TRUST_RESTORE_ON_RELEASE;
      e->low_tfwd_streak = 0;
      reset_review_state(e);
      e->release_active = 1;
      e->release_redrop_armed = 1;
      e->release_started_at = now;
      printf("CSV,TRUST_UNBLACKLIST,%u,%lu,%u,%u,%u\n",
             e->node_id,
             (unsigned long)now,
             (unsigned)e->trust,
             (unsigned)penalty_scale_for_entry(e),
             (unsigned)TA_TRUST_RELEASE_COOLDOWN_SECONDS);
    }
    return;
  }

  /* Hard exclude is controlled by the validation model only.
   * Trust model remains for routing penalty/escape, not blacklist. */
  if((e->review_windows_seen >= TA_TRUST_BLACKLIST_MIN_WINDOWS &&
      e->review_score >= TA_TRUST_REVIEW_SCORE_BLACKLIST &&
      e->review_bad_windows >= TA_TRUST_VALIDATION_BAD_STREAK_FOR_BLACKLIST) ||
     (e->review_windows_seen >= TA_TRUST_BLACKLIST_MIN_WINDOWS &&
      e->low_tfwd_streak >= TA_TRUST_FINAL_TFWD_STREAK)) {
    e->blacklisted = 1;
    reset_review_state(e);
    e->low_tfwd_streak = 0;
    e->release_active = 0;
    e->release_redrop_armed = 0;
    e->blacklist_until = now + (clock_time_t)(TA_TRUST_BLACKLIST_DURATION
                                              * CLOCK_SECOND);
    printf("CSV,TRUST_BLACKLIST,%u,%u,%lu\n",
           e->node_id,
           e->trust,
           (unsigned long)now);
  }
}

/* ------------------------------------------------------------------ */
/* IP input hook — overhearing detection                               */
/* ------------------------------------------------------------------ */
static enum netstack_ip_action
ta_ip_input_hook(void)
{
  /* Only interested in non-locally-originated packets                 */
  if(uip_ds6_is_my_addr(&UIP_IP_BUF->srcipaddr)) {
    return NETSTACK_IP_PROCESS;
  }

  /* Identify MAC sender of the received frame                         */
  const linkaddr_t *mac_sender = packetbuf_addr(PACKETBUF_ADDR_SENDER);
  if(mac_sender == NULL) {
    return NETSTACK_IP_PROCESS;
  }
  uint16_t mac_id = mac_sender->u8[LINKADDR_SIZE - 1];

  /* T_fwd is measured exclusively via echo_rx_callback in sender.c:
   * the sender tracks which parent each data TX used (take_tx_parent),
   * and credits that parent when a root echo confirms end-to-end
   * delivery.  The IP hook does NOT credit T_fwd here because:
   *   (a) downward echo replies are routed through the parent and would
   *       give FALSE positive credits to selective-forwarding attackers;
   *   (b) CSMA discards unicast frames not addressed to this node, so
   *       genuine upward overhearing is impossible in 802.15.4.       */

  /* DIO interception for T_ctrl                                       */
  if(UIP_IP_BUF->proto == UIP_PROTO_ICMP6) {
    struct uip_icmp_hdr *icmp6 = UIP_ICMP_BUF;
    if(icmp6->type == ICMP6_RPL) {
      uint8_t *rpl_payload = ((uint8_t *)icmp6) + sizeof(struct uip_icmp_hdr);
      uint8_t  code = icmp6->icode;

#ifndef RPL_CODE_DIO
#define RPL_CODE_DIO 0x02
#endif
      if(code == RPL_CODE_DIO) {
        /* DIO body: [RPLInstanceID][Version][Rank(2B)][...] */
        uint8_t  version = rpl_payload[1];
        uint16_t rank    = ((uint16_t)rpl_payload[2] << 8) | rpl_payload[3];
        ta_trust_notify_dio(mac_id, rank, version);
      }
    }
  }

  return NETSTACK_IP_PROCESS;
}

static struct netstack_ip_packet_processor ta_ip_processor = {
  .process_input  = ta_ip_input_hook,
  .process_output = NULL
};

/* ------------------------------------------------------------------ */
/* Public API                                                          */
/* ------------------------------------------------------------------ */
void
ta_trust_init(void)
{
  memset(trust_table, 0, sizeof(trust_table));
  trust_table_size = 0;
  memset(trust_index_by_node_id, 0xff, sizeof(trust_index_by_node_id));
  current_parent_cond_evict_cooldown_until = 0;
  current_parent_escape_armed = 1;
  current_parent_soft_release_armed = 1;
  current_parent_soft_release_cooldown_until = 0;
  recent_switch_window_started_at = 0;
  recent_switch_count = 0;
  netstack_ip_packet_processor_add(&ta_ip_processor);
  LOG_INFO("TA-BRPL trust module initialised\n");
}

void
ta_trust_notify_sent(uint16_t node_id)
{
  ta_trust_entry_t *e = get_or_create(node_id);
  if(e == NULL) return;
  e->fwd_sent++;
  e->fwd_sent_new++;
}

void
ta_trust_notify_forwarded(uint16_t node_id)
{
  ta_trust_entry_t *e = get_or_create(node_id);
  if(e == NULL) return;
  e->fwd_observed++;
  e->fwd_observed_new++;
}

void
ta_trust_notify_dio(uint16_t node_id, uint16_t rank, uint8_t version)
{
  ta_trust_entry_t *e = get_or_create(node_id);
  if(e == NULL) return;

  e->ctrl_dio_count++;

  rpl_dag_t *dag = rpl_get_any_dag();
  if(dag != NULL && dag->instance != NULL && rank != 0) {
    uint16_t min_inc = dag->instance->min_hoprankinc;
    uint16_t root_rank = ROOT_RANK(dag->instance);
    uint32_t low_rank_threshold = (uint32_t)root_rank
                                + (uint32_t)TA_TRUST_CTRL_LOW_RANK_FACTOR * min_inc;
    uint8_t sustained_low_rank = 0;

    /* Case 1: blatant sinkhole — rank below root level */
    if(rank < min_inc) {
      e->ctrl_rank_dev_count++;

    /* Case 2: significant rank decrease without DODAG version change.
     * A sinkhole that spoofs a low rank (e.g. 512→257) without a
     * DODAG version bump is caught here.  Threshold = min_hoprankinc/2
     * to avoid false positives from small ETX-driven improvements.
     * Mirrors the detection logic in smtrust.c:detect_rank_attack(). */
    } else if(e->ctrl_version_seen &&
              rank < e->ctrl_rank_last &&
              (uint32_t)(e->ctrl_rank_last - rank) > (uint32_t)(min_inc / 2) &&
              version == e->ctrl_version_last) {
      e->ctrl_rank_dev_count++;
    }

    if(e->ctrl_version_seen &&
       version == e->ctrl_version_last &&
       rank <= low_rank_threshold) {
      if(e->ctrl_low_rank_streak < 0xff) {
        e->ctrl_low_rank_streak++;
      }
      if(e->ctrl_low_rank_streak >= TA_TRUST_CTRL_LOW_RANK_MIN_STREAK) {
        sustained_low_rank = 1;
      }
    } else if(e->ctrl_low_rank_streak > 0) {
      e->ctrl_low_rank_streak--;
    }

    if(sustained_low_rank) {
      uint32_t next = (uint32_t)e->ctrl_low_rank_count
                    + TA_TRUST_CTRL_LOW_RANK_STREAK_BONUS;
      e->ctrl_low_rank_count = (next > 0xffffu) ? 0xffffu : (uint16_t)next;
    }
  }

  /* Update version and rank baseline */
  if(!e->ctrl_version_seen) {
    e->ctrl_version_last = version;
    e->ctrl_rank_last    = rank;
    e->ctrl_version_seen = 1;
  } else {
    if(version != e->ctrl_version_last) {
      e->ctrl_version_mismatch++;
      e->ctrl_version_last = version;
      /* DODAG reset: new rank baseline, any change is now legitimate */
      e->ctrl_rank_last = rank;
    } else {
      e->ctrl_rank_last = rank;
    }
  }
}

void
ta_trust_notify_backlog(uint16_t node_id, uint16_t q_adv, uint16_t q_max)
{
  ta_trust_entry_t *e = get_or_create(node_id);
  if(e == NULL) return;
  e->hon_q_adv   = q_adv;
  e->hon_q_max   = q_max;
  e->hon_valid   = 1;
}

void
ta_trust_update_all(void)
{
  int escape_triggered = 0;

  for(uint8_t i = 0; i < trust_table_size; i++) {
    ta_trust_entry_t *e = &trust_table[i];
    if(!e->valid) continue;

    /* Skip update for currently blacklisted nodes until quarantine ends */
    if(e->blacklisted) {
      check_blacklist(e);
      continue;
    }

    /* Also pull BRPL backlog if available from RPL parent table       */
    {
      rpl_dag_t *dag = rpl_get_any_dag();
      if(dag != NULL) {
        rpl_parent_t *p;
        extern nbr_table_t *rpl_parents;
        for(p = nbr_table_head(rpl_parents); p != NULL;
            p = nbr_table_next(rpl_parents, p)) {
          const linkaddr_t *ll = rpl_get_parent_lladdr(p);
          if(ll != NULL &&
             ll->u8[LINKADDR_SIZE - 1] == e->node_id &&
             p->brpl_queue_valid) {
            ta_trust_notify_backlog(e->node_id,
                                    p->brpl_queue,
                                    p->brpl_queue_max > 0
                                      ? p->brpl_queue_max
                                      : BRPL_CONF_QUEUE_MAX);
            break;
          }
        }
      }
    }

    uint16_t t_fwd  = compute_t_fwd(e);
    uint16_t t_ctrl = compute_t_ctrl(e);
    uint16_t t_hon  = compute_t_hon(e);
    uint16_t t_agg  = aggregate_trust(t_fwd, t_ctrl, t_hon);

    uint16_t t_old = e->trust;
    e->trust     = ewma_update(t_old,        t_agg);
    e->trust_fwd = ewma_update_fwd(e->trust_fwd, t_fwd);

    /* Validation model (separate from trust model):
     * hard-exclude is decided ONLY from forwarding evidence persistence.
     * trust/trust_fwd are not used in blacklist decisions. */
    {
      uint8_t prev_review_state = e->review_state;
      uint8_t parent_changed = (e->review_parent_since != 0 &&
                                e->review_parent_since != current_parent_since);
      uint8_t parent_matured = (current_parent_elapsed() >=
        (clock_time_t)TA_TRUST_VALIDATION_MIN_PARENT_AGE_SECONDS * CLOCK_SECOND);
      uint8_t review_window = (e->node_id == current_parent_id &&
                               e->fwd_sent_new >= TA_TRUST_VALIDATION_MIN_SENT &&
                               parent_matured);
      uint8_t bad_signal = 0;
      uint8_t strong_bad = 0;
      uint8_t good_signal = 0;
      uint16_t success_pm = 1000;

      if(parent_changed) {
        reset_review_state(e);
      }

      if(review_window) {
        if(e->review_parent_since == 0) {
          e->review_parent_since = current_parent_since;
        }
        if(e->review_windows_seen < 0xff) {
          e->review_windows_seen++;
        }

        /* Accumulate forwarding evidence in the same parent session.
         * This is independent from trust_fwd/trust and gives validation
         * a conservative, statistically smoother signal. */
        {
          uint32_t ns = (uint32_t)e->val_sent_acc + e->fwd_sent_new;
          uint32_t no = (uint32_t)e->val_obs_acc + e->fwd_observed_new;
          e->val_sent_acc = (ns > 65535u) ? 65535u : (uint16_t)ns;
          e->val_obs_acc  = (no > 65535u) ? 65535u : (uint16_t)no;
        }

        if(e->val_sent_acc > 0) {
          success_pm = (uint16_t)(((uint32_t)e->val_obs_acc * 1000u) / e->val_sent_acc);
        }
        if(e->trust_fwd <= TA_TRUST_FINAL_TFWD_MAX) {
          if(e->low_tfwd_streak < 0xff) {
            e->low_tfwd_streak++;
          }
        } else if(e->low_tfwd_streak > 0) {
          e->low_tfwd_streak--;
        }
        bad_signal = (e->val_sent_acc >= TA_TRUST_VALIDATION_MIN_ACC_SENT &&
                      success_pm <= TA_TRUST_VALIDATION_BAD_SUCCESS_MAX);
        strong_bad = (e->val_sent_acc >= (TA_TRUST_VALIDATION_MIN_ACC_SENT + 2) &&
                      success_pm <= TA_TRUST_VALIDATION_STRONG_SUCCESS_MAX);
        good_signal = (e->val_sent_acc >= TA_TRUST_VALIDATION_MIN_ACC_SENT &&
                       success_pm >= TA_TRUST_VALIDATION_GOOD_SUCCESS_MIN);

        if(bad_signal) {
          uint8_t delta = TA_TRUST_VALIDATION_BAD_INC;
          if((uint16_t)e->review_score + delta > 255) {
            e->review_score = 255;
          } else {
            e->review_score += delta;
          }
          if(e->review_bad_windows < 0xff) {
            e->review_bad_windows++;
          }
          if(strong_bad &&
             e->review_bad_windows >= TA_TRUST_VALIDATION_BAD_STREAK_FOR_BLACKLIST) {
            uint8_t bonus = TA_TRUST_VALIDATION_STRONG_BONUS;
            if((uint16_t)e->review_score + bonus > 255) {
              e->review_score = 255;
            } else {
              e->review_score += bonus;
            }
          }
          e->review_good_windows = 0;
        } else {
          uint8_t delta = TA_TRUST_VALIDATION_GOOD_DEC;
          if(!good_signal && delta > 1) {
            delta = 1;
          }
          if(e->review_score > delta) {
            e->review_score -= delta;
          } else {
            e->review_score = 0;
          }
          if(e->review_bad_windows > 0) {
            e->review_bad_windows--;
          }
          if(e->review_good_windows < 0xff) {
            e->review_good_windows++;
          }
        }
      } else {
        if(e->review_score > 0) {
          uint8_t delta = TA_TRUST_VALIDATION_IDLE_DEC;
          e->review_score = (e->review_score > delta) ? (e->review_score - delta) : 0;
        }
        if(e->review_bad_windows > 0) e->review_bad_windows--;
        if(e->low_tfwd_streak > 0) {
          e->low_tfwd_streak--;
        }
        e->val_sent_acc >>= 1;
        e->val_obs_acc  >>= 1;
      }

      if(e->review_score >= TA_TRUST_REVIEW_SCORE_PENALIZED) {
        e->review_state = TA_REVIEW_STATE_PENALIZED;
      } else if(e->review_score >= TA_TRUST_REVIEW_SCORE_UNDER) {
        e->review_state = TA_REVIEW_STATE_UNDER;
      } else {
        e->review_state = TA_REVIEW_STATE_NORMAL;
      }

      if(e->review_state != prev_review_state) {
        printf("CSV,VAL_STATE,%u,%u,%lu,%u,%u,%u,%u,%u\n",
               (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
               (unsigned)e->node_id,
               (unsigned long)clock_time(),
               (unsigned)prev_review_state,
               (unsigned)e->review_state,
               (unsigned)e->review_score,
               (unsigned)e->review_bad_windows,
               (unsigned)e->blacklisted);
      }

      if(e->review_windows_seen < TA_TRUST_VALIDATION_MIN_WINDOWS &&
         e->review_score > 0) {
        e->review_score--;
      }
    }

    if(e->node_id == current_parent_id &&
       e->fwd_sent_new >= 2 &&
       e->trust_fwd < TA_TRUST_TAU_JOIN) {
      if(e->low_trust_updates < 0xff) {
        e->low_trust_updates++;
      }
    } else {
      e->low_trust_updates = 0;
    }
    e->fwd_observed_new = 0;
    e->fwd_sent_new     = 0;

    check_blacklist(e);

    if(e->release_active) {
      clock_time_t now = clock_time();
      clock_time_t cooldown = (clock_time_t)TA_TRUST_RELEASE_COOLDOWN_SECONDS * CLOCK_SECOND;
      uint16_t penalty_scale = penalty_scale_for_entry(e);

      if(now - e->release_started_at >= cooldown) {
        e->release_active = 0;
        e->release_redrop_armed = 0;
        printf("CSV,TRUST_RECOVERY_DONE,%u,%lu,%u\n",
               e->node_id,
               (unsigned long)now,
               (unsigned)e->trust);
      } else {
        if(e->trust < TA_TRUST_TAU_JOIN && e->release_redrop_armed) {
          e->release_redrop_armed = 0;
          printf("CSV,TRUST_REDROP,%u,%lu,%u\n",
                 e->node_id,
                 (unsigned long)now,
                 (unsigned)e->trust);
        } else if(e->trust >= TA_TRUST_TAU_JOIN) {
          e->release_redrop_armed = 1;
        }

        printf("CSV,TRUST_RECOVERY,%u,%u,%lu,%u,%u\n",
               (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
               (unsigned)e->node_id,
               (unsigned long)now,
               (unsigned)e->trust,
               (unsigned)penalty_scale);
      }
    }

    if(e->node_id == current_parent_id || e->trust < TA_TRUST_TAU_WARN) {
      uint16_t penalty_scale = penalty_scale_for_entry(e);
      int escape = escape_mode_for_entry(e);
      int soft_release = soft_release_mode_for_entry(e);
      printf("CSV,TRUST_ROUTEGUARD,%u,%u,%lu,%u,%u,%u\n",
             (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
             (unsigned)e->node_id,
             (unsigned long)(current_parent_elapsed() / CLOCK_SECOND),
             (unsigned)e->trust,
             (unsigned)penalty_scale,
             (unsigned)(escape || soft_release));

      if(escape && e->node_id == current_parent_id && current_parent_escape_armed) {
        current_parent_escape_armed = 0;
        current_parent_escape_cooldown_until =
          clock_time() + (clock_time_t)TA_TRUST_ESCAPE_COOLDOWN_SECONDS * CLOCK_SECOND;
        if(admission_suspicion_level(e) >= 2 ||
           e->review_state >= TA_REVIEW_STATE_UNDER) {
          e->reentry_block_until =
            clock_time() + (clock_time_t)TA_TRUST_REENTRY_COOLDOWN_SECONDS * CLOCK_SECOND;
          printf("CSV,REENTRY_BLOCK_SET,%u,%u,%lu,%u\n",
                 (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
                 (unsigned)e->node_id,
                 (unsigned long)e->reentry_block_until,
                 (unsigned)TA_TRUST_REENTRY_COOLDOWN_SECONDS);
        }
        printf("CSV,TRUST_ESCAPE,%u,%u,%lu,%u\n",
               (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
               (unsigned)e->node_id,
               (unsigned long)clock_time(),
               (unsigned)e->trust);
        escape_triggered = 1;
      }
      if(soft_release && e->node_id == current_parent_id && current_parent_soft_release_armed) {
        current_parent_soft_release_armed = 0;
        current_parent_soft_release_cooldown_until =
          clock_time() + (clock_time_t)TA_TRUST_SOFT_RELEASE_COOLDOWN_SECONDS * CLOCK_SECOND;
        printf("CSV,TRUST_SOFT_RELEASE,%u,%u,%lu,%u,%u\n",
               (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
               (unsigned)e->node_id,
               (unsigned long)clock_time(),
               (unsigned)e->trust,
               (unsigned)e->trust_fwd);
      }
    }

    printf("CSV,TRUST,%u,%u,%u,%u,%u,%u,%u,%u\n",
           (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
           (unsigned)e->node_id,
           (unsigned)t_fwd,
           (unsigned)t_ctrl,
           (unsigned)t_hon,
           (unsigned)t_agg,
           (unsigned)e->trust,
           (unsigned)e->trust_fwd);

    {
      /* Policy-layer state log:
       *   - soft_penalized: suspicious, still routable
       *   - below_join: below join threshold (still soft in current policy)
       *   - hard_blocked: blacklisted (hard exclusion) */
      uint8_t soft_penalized = (!e->blacklisted && e->trust < TA_TRUST_TAU_WARN) ? 1 : 0;
      uint8_t below_join = (!e->blacklisted && e->trust < TA_TRUST_TAU_JOIN) ? 1 : 0;
      uint8_t hard_blocked = e->blacklisted ? 1 : 0;
      uint8_t policy_state = hard_blocked ? 3 : (below_join ? 2 : (soft_penalized ? 1 : 0));

      printf("CSV,TRUST_POLICY,%u,%u,%u,%u,%u,%u,%u,%u\n",
             (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
             (unsigned)e->node_id,
             (unsigned)e->trust,
             (unsigned)policy_state,
             (unsigned)soft_penalized,
             (unsigned)below_join,
             (unsigned)hard_blocked,
             (unsigned)e->review_state);
    }

    printf("CSV,ADMISSION,%u,%u,%u,%u,%u,%u,%u,%lu,%lu,%lu,%lu,%lu,%lu,%lu\n",
           (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
           (unsigned)e->node_id,
           (unsigned)(e->node_id == current_parent_id ? 1 : 0),
           (unsigned)admission_suspicion_level(e),
           (unsigned)e->trust,
           (unsigned)e->trust_fwd,
           (unsigned)e->review_state,
           (unsigned long)e->adm_new_eval,
           (unsigned long)e->adm_new_allow,
           (unsigned long)e->adm_new_block_blacklist,
           (unsigned long)e->adm_new_block_trust,
           (unsigned long)e->adm_new_block_review,
           (unsigned long)e->adm_new_block_severe,
           (unsigned long)clock_time());

    /* Halving decay instead of hard reset.
     *
     * Previously counters were zeroed each window, which caused
     * T_fwd = alpha/(alpha+beta) = 500 (neutral) whenever no packets
     * were sent in that window (e.g. for non-parent neighbour nodes).
     * Since T_agg(500, 1000, 1000) = 707 > T_INIT=500, trust drifted
     * upward for every unobserved node including active attackers.
     *
     * With halving, historical counts persist with exponential
     * forgetting (effective window ≈ 2 update periods).  A blackhole
     * that accumulates fwd_sent >> fwd_observed will converge to
     * T_fwd → alpha/(large_S + alpha + beta) → near 0, and the per-
     * window EWMA update will then pull trust below the thresholds. */
    e->fwd_sent          = e->fwd_sent      >> 1;
    e->fwd_observed      = e->fwd_observed  >> 1;
    e->ctrl_dio_count    = e->ctrl_dio_count >> 1;
    e->ctrl_rank_dev_count   = e->ctrl_rank_dev_count   >> 1;
    e->ctrl_version_mismatch = e->ctrl_version_mismatch >> 1;
    e->ctrl_dio_excess   = e->ctrl_dio_excess >> 1;
    e->ctrl_low_rank_count = e->ctrl_low_rank_count >> 1;
    if(e->ctrl_low_rank_streak > 0) {
      e->ctrl_low_rank_streak--;
    }
  }

  if(escape_triggered) {
    rpl_dag_t *dag = rpl_get_any_dag();
    if(dag != NULL && dag->instance != NULL) {
      rpl_reset_dio_timer(dag->instance);
    }
    dis_output(NULL);
  }
}

uint16_t
ta_trust_get(uint16_t node_id)
{
  ta_trust_entry_t *e = find_entry(node_id);
  if(e == NULL) {
    return TA_TRUST_INIT;
  }
  if(e->blacklisted) {
    return 0;
  }
  return e->trust;
}

ta_trust_status_t
ta_trust_get_status(uint16_t node_id)
{
  ta_trust_entry_t *e = find_entry(node_id);
  if(e == NULL) return TA_TRUST_NORMAL;
  if(e->blacklisted) return TA_TRUST_BLACKLISTED;
  if(e->trust >= TA_TRUST_TAU_WARN)   return TA_TRUST_NORMAL;
  if(e->trust >= TA_TRUST_TAU_JOIN)   return TA_TRUST_SUSPECT;
  if(e->trust >= TA_TRUST_TAU_BLACK)  return TA_TRUST_UNTRUSTED;
  return TA_TRUST_BLACKLISTED;
}

int
ta_trust_is_parent_candidate(uint16_t node_id)
{
  ta_trust_entry_t *e = find_entry(node_id);
  if(e == NULL) return 1; /* unknown: give benefit of the doubt        */
  return e->blacklisted ? 0 : 1;
}

void
ta_trust_log_all(void)
{
  for(uint8_t i = 0; i < trust_table_size; i++) {
    ta_trust_entry_t *e = &trust_table[i];
    if(!e->valid) continue;
    printf("CSV,TRUST_TABLE,%u,%u,%u,%s\n",
           (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
           (unsigned)e->node_id,
           (unsigned)e->trust,
           e->blacklisted ? "BL" : "OK");
  }
}

/* ------------------------------------------------------------------ */
/* Override BRPL weak symbol — used by rpl-brpl.c for parent scoring  */
/* ------------------------------------------------------------------ */
uint16_t
brpl_trust_get(uint16_t node_id)
{
  return ta_trust_get(node_id);
}

uint16_t
brpl_penalty_scale_get(uint16_t node_id)
{
  ta_trust_entry_t *e = find_entry(node_id);
  uint16_t scale = penalty_scale_for_entry(e);

  /* Policy v3: candidate-side admission pressure.
   * Keep current parent stable; only tighten admission for non-current
   * suspicious candidates to reduce attacker capture without re-adding churn. */
  if(e != NULL && node_id != current_parent_id) {
    uint8_t level = admission_suspicion_level(e);
    if(level >= 1 && scale < TA_ADMISSION_WARN_JOIN_PENALTY_SCALE) {
      scale = TA_ADMISSION_WARN_JOIN_PENALTY_SCALE;
    }
  }

  return scale;
}

uint16_t
brpl_validation_penalty_scale_get(uint16_t node_id)
{
  ta_trust_entry_t *e = find_entry(node_id);

  if(e == NULL) {
    return 1000;
  }
  if(e->blacklisted) {
    return 3000;
  }
  if(e->review_state == TA_REVIEW_STATE_PENALIZED) {
    return 2200;
  }
  if(e->review_state == TA_REVIEW_STATE_UNDER) {
    return 1600;
  }
  return 1000;
}

int
brpl_escape_mode_get(uint16_t node_id)
{
  ta_trust_entry_t *e = find_entry(node_id);
  return escape_mode_for_entry(e) || soft_release_mode_for_entry(e);
}

int
brpl_trust_parent_allowed(uint16_t node_id)
{
  ta_trust_entry_t *e = find_entry(node_id);
  uint8_t is_new_candidate = 0;
  uint8_t blocked = 0;
  uint8_t reason = 0; /* 1 blacklist, 2 trust, 3 review, 4 severe, 5 cond_evict, 6 reentry */

  if(e == NULL) {
    return 1;
  }
  is_new_candidate = (node_id != current_parent_id) ? 1 : 0;
  if(is_new_candidate) {
    e->adm_new_eval++;
  }
  /* Decision policy split:
   * - Hard exclusion: blacklist always blocks.
   * - Admission control: low-trust candidates are blocked only for
   *   new parent adoption; keep current parent eligible to avoid churn. */
  if(e->blacklisted) {
    blocked = 1;
    reason = 1;
  } else if(node_id != current_parent_id &&
            e->reentry_block_until != 0 &&
            clock_time() < e->reentry_block_until) {
    blocked = 1;
    reason = 6;
    printf("CSV,REENTRY_BLOCK_HIT,%u,%u,%lu\n",
           (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
           (unsigned)e->node_id,
           (unsigned long)e->reentry_block_until);
  } else if(node_id != current_parent_id && e->trust < TA_TRUST_TAU_JOIN) {
    blocked = 1;
    reason = 2;
  } else if(node_id != current_parent_id && e->review_state == TA_REVIEW_STATE_PENALIZED) {
    blocked = 1;
    reason = 3;
  } else if(node_id != current_parent_id && admission_suspicion_level(e) >= 2) {
    blocked = 1;
    reason = 4;
  } else if(node_id == current_parent_id && should_conditional_evict_current_parent(e)) {
    blocked = 1;
    reason = 5;
    current_parent_cond_evict_cooldown_until =
      clock_time() + (clock_time_t)TA_TRUST_COND_EVICT_COOLDOWN_SECONDS * CLOCK_SECOND;
    printf("CSV,TRUST_COND_EVICT,%u,%u,%lu,%u,%u,%u\n",
           (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
           (unsigned)e->node_id,
           (unsigned long)clock_time(),
           (unsigned)e->trust,
           (unsigned)e->trust_fwd,
           (unsigned)(current_parent_elapsed() / CLOCK_SECOND));
  }

  if(is_new_candidate) {
    if(blocked) {
      if(reason == 1) {
        e->adm_new_block_blacklist++;
      } else if(reason == 2) {
        e->adm_new_block_trust++;
      } else if(reason == 3) {
        e->adm_new_block_review++;
      } else if(reason == 4) {
        e->adm_new_block_severe++;
      }
    } else {
      e->adm_new_allow++;
    }
  }
  return blocked ? 0 : 1;
}

enum {
  TA_SWITCH_TYPE_NN = 1,
  TA_SWITCH_TYPE_NA = 2,
  TA_SWITCH_TYPE_AN = 3,
  TA_SWITCH_TYPE_AA = 4
};

enum {
  TA_SWITCH_REASON_OK = 0,
  TA_SWITCH_REASON_MISSING_IN_LOSS = 10,
  TA_SWITCH_REASON_BLACKLIST = 11,
  TA_SWITCH_REASON_REENTRY_COOLDOWN = 12,
  TA_SWITCH_REASON_REVIEW_CLEAN_REQ = 13,
  TA_SWITCH_REASON_SUSPICION_CLEAN_REQ = 14,
  TA_SWITCH_REASON_TFWD_MIN = 15,
  TA_SWITCH_REASON_LOSS_LOW_SUCCESS = 20,
  TA_SWITCH_REASON_LOSS_EVIDENCE_MISSING = 21,
  TA_SWITCH_REASON_NN_HOLD = 30,
  TA_SWITCH_REASON_REENTRY_GUARD = 31,
  TA_SWITCH_REASON_NA_GUARD = 32
};

static uint8_t
ta_switch_type(uint8_t pref_attacker_like, uint8_t cand_attacker_like)
{
  if(!pref_attacker_like && !cand_attacker_like) {
    return TA_SWITCH_TYPE_NN;
  }
  if(!pref_attacker_like && cand_attacker_like) {
    return TA_SWITCH_TYPE_NA;
  }
  if(pref_attacker_like && !cand_attacker_like) {
    return TA_SWITCH_TYPE_AN;
  }
  return TA_SWITCH_TYPE_AA;
}

static void
ta_build_switch_policy(uint16_t preferred_id,
                       uint16_t challenger_id,
                       uint8_t preferred_allowed,
                       brpl_switch_policy_decision_t *out)
{
  ta_trust_entry_t *pref = find_entry(preferred_id);
  ta_trust_entry_t *cand = find_entry(challenger_id);
  ta_trust_entry_t *cur = find_entry(current_parent_id);
  uint8_t loss_mode = (cur != NULL && cur->trust_fwd < TA_TRUST_TAU_WARN) ? 1 : 0;
  uint8_t severe_escape = is_current_parent_severe_attacker_like();
  uint8_t pref_attacker_like = is_attacker_like_entry(pref);
  uint8_t cand_attacker_like = is_attacker_like_entry(cand);
  uint8_t cand_recent_attacker_parent = 0;
  uint8_t rs_count = recent_switch_count_in_window();
  uint8_t sw_type = ta_switch_type(pref_attacker_like, cand_attacker_like);
  uint8_t relax_for_an = (sw_type == TA_SWITCH_TYPE_AN) ? 1 : 0;
  uint16_t extra = 0;
  uint8_t block_reason = TA_SWITCH_REASON_OK;
  clock_time_t now = clock_time();

  (void)preferred_allowed;

  if(out == NULL) {
    return;
  }
  out->extra_margin_abs = 0;
  out->block_switch = 0;
  out->bypass_dwell = 0;
  out->reason_code = TA_SWITCH_REASON_OK;

  if(cand == NULL) {
    if(loss_mode) {
      out->block_switch = 1;
      out->reason_code = TA_SWITCH_REASON_MISSING_IN_LOSS;
    }
    goto done;
  }

  if(cand->recent_attacker_parent_until != 0 &&
     now < cand->recent_attacker_parent_until) {
    cand_recent_attacker_parent = 1;
  }

  if(cand->blacklisted) {
    out->block_switch = 1;
    out->reason_code = TA_SWITCH_REASON_BLACKLIST;
    goto done;
  }
  if(cand->reentry_block_until != 0 && now < cand->reentry_block_until) {
    out->block_switch = 1;
    out->reason_code = TA_SWITCH_REASON_REENTRY_COOLDOWN;
    goto done;
  }
#if TA_TRUST_SWITCH_REQUIRE_CLEAN
  if(!relax_for_an && cand->review_state != TA_REVIEW_STATE_NORMAL) {
    out->block_switch = 1;
    out->reason_code = TA_SWITCH_REASON_REVIEW_CLEAN_REQ;
    goto done;
  }
  /* Do not bypass control-plane suspicion filtering even in AN mode.
   * Otherwise attacker challengers can pass through the relaxed path when
   * preferred parent is (possibly falsely) tagged attacker-like. */
  if(admission_suspicion_level(cand) > 0) {
    out->block_switch = 1;
    out->reason_code = TA_SWITCH_REASON_SUSPICION_CLEAN_REQ;
    goto done;
  }
#endif
  {
    /* Keep AN relaxation only in non-loss conditions.
     * In lossy phases, an attacker challenger can be misclassified as
     * non-attacker-like (AN path), so we keep the stricter tfwd floor. */
    uint16_t tfwd_min = TA_TRUST_SWITCH_CANDIDATE_TFWD_MIN;
    if(relax_for_an && !loss_mode) {
      tfwd_min = TA_TRUST_TAU_JOIN;
    }
    if(cand->trust_fwd < tfwd_min) {
      out->block_switch = 1;
      out->reason_code = TA_SWITCH_REASON_TFWD_MIN;
      goto done;
    }
  }

  if(loss_mode) {
    uint16_t success_pm = 1000;

    if(cand->val_sent_acc >= TA_TRUST_SWITCH_RECENT_SENT_MIN) {
      success_pm = (uint16_t)(((uint32_t)cand->val_obs_acc * 1000u) / cand->val_sent_acc);
      if(success_pm < TA_TRUST_SWITCH_RECENT_SUCCESS_MIN) {
        out->block_switch = 1;
        out->reason_code = TA_SWITCH_REASON_LOSS_LOW_SUCCESS;
        goto done;
      }
    } else if(cand->ctrl_dio_count < TA_TRUST_SWITCH_RECENT_MIN_DIO ||
              cand->trust < TA_TRUST_SWITCH_LOSS_MIN_TRUST) {
      out->block_switch = 1;
      out->reason_code = TA_SWITCH_REASON_LOSS_EVIDENCE_MISSING;
      goto done;
    }
  }

  if(!severe_escape &&
     sw_type == TA_SWITCH_TYPE_NN &&
     current_parent_elapsed() <
       (clock_time_t)TA_TRUST_NN_HOLD_SECONDS * CLOCK_SECOND) {
    out->block_switch = 1;
    out->reason_code = TA_SWITCH_REASON_NN_HOLD;
    goto done;
  }

  /* v13.1: stronger non-att -> attacker-like suppression.
   * If current parent is non-attacker-like, block transitions to
   * attacker-like challengers during hold/cooldown windows. */
  if(!severe_escape &&
     sw_type == TA_SWITCH_TYPE_NA &&
     (rs_count > 0 ||
      current_parent_elapsed() <
        (clock_time_t)TA_TRUST_NN_HOLD_SECONDS * CLOCK_SECOND)) {
    out->block_switch = 1;
    out->reason_code = TA_SWITCH_REASON_NA_GUARD;
    goto done;
  }

  if(!severe_escape &&
     rs_count >= TA_TRUST_RECENT_SWITCH_BLOCK_COUNT &&
     (cand_attacker_like || cand_recent_attacker_parent)) {
    out->block_switch = 1;
    out->reason_code = TA_SWITCH_REASON_REENTRY_GUARD;
    goto done;
  }

  if((pref != NULL && pref->trust_fwd < TA_TRUST_TAU_WARN) ||
     (cand->trust_fwd < TA_TRUST_TAU_WARN)) {
    uint32_t candidate = (uint32_t)extra + TA_TRUST_LOSS_ADAPTIVE_MARGIN;
    extra = (candidate > 65535u) ? 65535u : (uint16_t)candidate;
  }

  if(sw_type == TA_SWITCH_TYPE_NN) {
    uint32_t candidate = (uint32_t)extra + TA_TRUST_NN_EXTRA_MARGIN;
    extra = (candidate > 65535u) ? 65535u : (uint16_t)candidate;
    if(rs_count > 0) {
      candidate = (uint32_t)extra + TA_TRUST_NN_RECENT_SWITCH_MARGIN;
      extra = (candidate > 65535u) ? 65535u : (uint16_t)candidate;
    }
  } else if(sw_type == TA_SWITCH_TYPE_NA) {
    uint32_t candidate = (uint32_t)extra + TA_TRUST_NONATT_TO_ATT_EXTRA_MARGIN;
    extra = (candidate > 65535u) ? 65535u : (uint16_t)candidate;
  }

  if(!severe_escape && rs_count > 0) {
    uint32_t candidate = (uint32_t)extra + TA_TRUST_RECENT_SWITCH_MARGIN;
    extra = (candidate > 65535u) ? 65535u : (uint16_t)candidate;
  }
  if(!severe_escape && (cand_attacker_like || cand_recent_attacker_parent)) {
    uint32_t candidate = (uint32_t)extra + TA_TRUST_REENTRY_MARGIN;
    extra = (candidate > 65535u) ? 65535u : (uint16_t)candidate;
  }

  if(sw_type == TA_SWITCH_TYPE_AN) {
    /* v13.1: do not bypass dwell to avoid rapid AN<->NA oscillation. */
    out->bypass_dwell = 0;
    if(extra > TA_TRUST_ATT_TO_NONATT_MARGIN_RELAX) {
      extra -= TA_TRUST_ATT_TO_NONATT_MARGIN_RELAX;
    } else {
      extra = 0;
    }
  }

done:
  out->extra_margin_abs = extra;
  block_reason = out->reason_code;
  if(out->block_switch && block_reason == TA_SWITCH_REASON_NN_HOLD) {
    printf("CSV,NN_HOLD_BLOCK,%u,%u,%u,%u,%lu\n",
           (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
           (unsigned)challenger_id,
           (unsigned)rs_count,
           (unsigned)TA_TRUST_NN_HOLD_SECONDS,
           (unsigned long)now);
  } else if(out->block_switch && block_reason == TA_SWITCH_REASON_NA_GUARD) {
    printf("CSV,NA_GUARD_BLOCK,%u,%u,%u,%u,%lu\n",
           (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
           (unsigned)challenger_id,
           (unsigned)rs_count,
           (unsigned)TA_TRUST_NN_HOLD_SECONDS,
           (unsigned long)now);
  } else if(out->block_switch && block_reason == TA_SWITCH_REASON_REENTRY_GUARD) {
    printf("CSV,REENTRY_GUARD_BLOCK,%u,%u,%u,%u,%u,%u,%lu\n",
           (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
           (unsigned)challenger_id,
           (unsigned)rs_count,
           (unsigned)cand_attacker_like,
           (unsigned)cand_recent_attacker_parent,
           (unsigned)severe_escape,
           (unsigned long)now);
  } else if(out->block_switch &&
            (block_reason == TA_SWITCH_REASON_LOSS_LOW_SUCCESS ||
             block_reason == TA_SWITCH_REASON_LOSS_EVIDENCE_MISSING ||
             block_reason == TA_SWITCH_REASON_MISSING_IN_LOSS)) {
    uint16_t val_sent = cand != NULL ? cand->val_sent_acc : 0;
    uint16_t success_pm = 0;
    if(cand != NULL && cand->val_sent_acc > 0) {
      success_pm = (uint16_t)(((uint32_t)cand->val_obs_acc * 1000u) / cand->val_sent_acc);
    }
    printf("CSV,SWITCH_QUALITY,%u,%u,%u,%u,%u,%u,%u,%lu\n",
           (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
           (unsigned)challenger_id,
           (unsigned)loss_mode,
           (unsigned)(block_reason == TA_SWITCH_REASON_MISSING_IN_LOSS ? 0 :
                      (block_reason == TA_SWITCH_REASON_LOSS_LOW_SUCCESS ? 1 : 2)),
           (unsigned)val_sent,
           (unsigned)success_pm,
           (unsigned)(cand != NULL ? cand->ctrl_dio_count : 0),
           (unsigned long)now);
  }

  printf("CSV,SWITCH_POLICY,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%lu\n",
         (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
         (unsigned)preferred_id,
         (unsigned)challenger_id,
         (unsigned)sw_type,
         (unsigned)out->block_switch,
         (unsigned)out->reason_code,
         (unsigned)out->extra_margin_abs,
         (unsigned)out->bypass_dwell,
         (unsigned)rs_count,
         (unsigned)loss_mode,
         (unsigned)severe_escape,
         (unsigned long)now);
}

int
brpl_switch_policy_get(uint16_t preferred_id,
                       uint16_t challenger_id,
                       int32_t preferred_weight,
                       int32_t challenger_weight,
                       uint8_t preferred_allowed,
                       brpl_switch_policy_decision_t *out)
{
  (void)preferred_weight;
  (void)challenger_weight;
  ta_build_switch_policy(preferred_id, challenger_id, preferred_allowed, out);
  return 1;
}

int
brpl_switch_candidate_quality_ok(uint16_t node_id)
{
  brpl_switch_policy_decision_t d;
  ta_build_switch_policy(current_parent_id, node_id, 1, &d);
  return d.block_switch ? 0 : 1;
}

uint16_t
brpl_switch_extra_margin_get(uint16_t preferred_id, uint16_t challenger_id)
{
  brpl_switch_policy_decision_t d;
  ta_build_switch_policy(preferred_id, challenger_id, 1, &d);
  return d.extra_margin_abs;
}

void
brpl_preferred_parent_changed(uint16_t old_id, uint16_t new_id)
{
  clock_time_t now = clock_time();
  clock_time_t switch_window =
    (clock_time_t)TA_TRUST_RECENT_SWITCH_WINDOW_SECONDS * CLOCK_SECOND;

  if(old_id != 0xffff && new_id != 0xffff && old_id != new_id) {
    if(switch_window > 0) {
      if(recent_switch_window_started_at == 0 ||
         now <= recent_switch_window_started_at ||
         now - recent_switch_window_started_at >= switch_window) {
        recent_switch_window_started_at = now;
        recent_switch_count = 1;
      } else if(recent_switch_count < 0xff) {
        recent_switch_count++;
      }
    }

    /* Mark recently-detached attacker-like parent to suppress immediate
     * re-entry as challenger in the next switch window. */
    {
      ta_trust_entry_t *old_e = find_entry(old_id);
      if(old_e != NULL && is_attacker_like_entry(old_e)) {
        old_e->recent_attacker_parent_until =
          now + (clock_time_t)TA_TRUST_RECENT_ATTACKER_PARENT_WINDOW_SECONDS * CLOCK_SECOND;
        printf("CSV,REENTRY_RECENT_PARENT_SET,%u,%u,%u,%lu\n",
               (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
               (unsigned)old_id,
               (unsigned)TA_TRUST_RECENT_ATTACKER_PARENT_WINDOW_SECONDS,
               (unsigned long)old_e->recent_attacker_parent_until);
      }
    }
  }

  current_parent_id = new_id;
  current_parent_since = now;
  current_parent_escape_armed = 1;
  current_parent_escape_cooldown_until = 0;
  current_parent_cond_evict_cooldown_until = 0;
  current_parent_soft_release_armed = 1;
  current_parent_soft_release_cooldown_until = 0;
  printf("CSV,TRUST_PARENT,%u,%u,%lu\n",
         (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
         (unsigned)new_id,
         (unsigned long)current_parent_since);
}

void
brpl_parent_switch_callback(rpl_parent_t *old_p, rpl_parent_t *new_p)
{
  uint16_t old_id = 0xffff;
  uint16_t new_id = 0xffff;

  if(old_p != NULL) {
    const linkaddr_t *old_ll = rpl_get_parent_lladdr(old_p);
    if(old_ll != NULL) {
      old_id = old_ll->u8[LINKADDR_SIZE - 1];
    }
  }

  if(new_p != NULL) {
    const linkaddr_t *new_ll = rpl_get_parent_lladdr(new_p);
    if(new_ll != NULL) {
      new_id = new_ll->u8[LINKADDR_SIZE - 1];
    }
  }

  brpl_preferred_parent_changed(old_id, new_id);
}
