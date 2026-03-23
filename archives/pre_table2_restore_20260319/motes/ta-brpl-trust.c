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

#include <string.h>
#include <stdio.h>
#include <math.h>

#define LOG_MODULE "TA-TRUST"
#define LOG_LEVEL  LOG_LEVEL_WARN

/* ------------------------------------------------------------------ */
/* Per-neighbour record                                                */
/* ------------------------------------------------------------------ */
typedef struct {
  uint16_t node_id;
  uint8_t  valid;

  /* T_fwd */
  uint32_t fwd_sent;         /* S_ij: packets sent to this neighbour     */
  uint32_t fwd_observed;     /* F_ij: forwarding observations (EWMA acc) */
  uint8_t  fwd_window_head;  /* next insertion index for recent send set */
  uint8_t  fwd_window_count; /* active slots in recent send set          */
  uint8_t  fwd_window_success[TA_TRUST_FWD_WINDOW_SIZE];

  /* T_ctrl */
  uint16_t ctrl_rank_last;         /* last advertised rank              */
  uint16_t ctrl_rank_dev_count;    /* rank deviation events             */
  uint16_t ctrl_dio_count;         /* DIO count in current window       */
  uint16_t ctrl_dio_excess;        /* excess DIO events (> normal rate) */
  uint8_t  ctrl_version_last;      /* last seen RPL version             */
  uint8_t  ctrl_version_seen;      /* whether we have a baseline        */
  uint16_t ctrl_version_mismatch;  /* version inconsistency count       */

  /* T_hon */
  uint16_t hon_q_adv;      /* advertised backlog (0..q_max)            */
  uint16_t hon_q_max;      /* max queue size as reported               */
  uint8_t  hon_valid;      /* whether backlog data is available        */

  /* Aggregated trust (0..TA_TRUST_SCALE) */
  uint16_t trust;
  uint16_t last_t_fwd;
  uint16_t last_t_ctrl;
  uint16_t last_t_hon;
  uint16_t last_t_agg;

  /* Blacklist */
  uint8_t       blacklisted;
  clock_time_t  blacklist_until;
  uint8_t       release_active;
  uint8_t       release_redrop_armed;
  clock_time_t  release_started_at;
  uint8_t       low_trust_updates;
  uint8_t       below_join_updates;
  uint8_t       below_black_updates;
  uint8_t       below_join_ever;   /* set when trust first drops below tau_join; never cleared */

} ta_trust_entry_t;

/* ------------------------------------------------------------------ */
/* State                                                               */
/* ------------------------------------------------------------------ */
static ta_trust_entry_t trust_table[TA_TRUST_MAX_NEIGHBORS];
static uint8_t trust_table_size;
static uint16_t current_parent_id = 0xffff;
static clock_time_t current_parent_since;
static uint8_t current_parent_escape_armed;
static clock_time_t current_parent_escape_cooldown_until;

static ta_trust_entry_t *find_entry(uint16_t node_id);

static void
log_parent_candidate_summary(void)
{
  rpl_dag_t *dag = rpl_get_any_dag();

  if(dag != NULL) {
    uint16_t total = 0;
    uint16_t allowed = 0;
    uint16_t blacklisted = 0;
    uint16_t suspect_or_worse = 0;
    rpl_parent_t *p;
    extern nbr_table_t *rpl_parents;

    for(p = nbr_table_head(rpl_parents); p != NULL;
        p = nbr_table_next(rpl_parents, p)) {
      const linkaddr_t *ll = rpl_get_parent_lladdr(p);
      ta_trust_entry_t *e;
      uint16_t node_id;

      if(ll == NULL) {
        continue;
      }

      total++;
      node_id = ll->u8[LINKADDR_SIZE - 1];
      e = find_entry(node_id);

      if(e != NULL && e->blacklisted) {
        blacklisted++;
      }
      if(e != NULL && e->trust < TA_TRUST_TAU_WARN) {
        suspect_or_worse++;
      }
      if(brpl_trust_parent_allowed(node_id)) {
        allowed++;
      }
    }

    printf("CSV,TRUST_CANDIDATES,%u,%lu,%u,%u,%u,%u\n",
           (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
           (unsigned long)clock_time(),
           (unsigned)allowed,
           (unsigned)total,
           (unsigned)blacklisted,
           (unsigned)suspect_or_worse);
  }
}

static clock_time_t
current_parent_elapsed(void)
{
  if(current_parent_id == 0xffff || current_parent_since == 0) {
    return 0;
  }
  return clock_time() - current_parent_since;
}

static uint16_t
attack_persistence_penalty_scale(uint16_t node_id, uint16_t trust)
{
  uint16_t scale = TA_TRUST_SCALE;

  /* Apply persistence penalty to any node whose trust has fallen to
   * SUSPECT or worse — not just a hardcoded attacker ID set.
   * This makes the detection ID-agnostic and generalizable. */
  if(trust >= TA_TRUST_TAU_WARN) {
    return scale;
  }

  scale = TA_TRUST_ATTACK_PARENT_PENALTY_SCALE;

  if(node_id == current_parent_id) {
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
       trust < TA_TRUST_ESCAPE_TRUST_THRESHOLD &&
       scale < TA_TRUST_ESCAPE_PENALTY_SCALE) {
      scale = TA_TRUST_ESCAPE_PENALTY_SCALE;
    }
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

static void
ta_fwd_window_note_sent(ta_trust_entry_t *e)
{
#if TA_TRUST_FWD_WINDOW_ENABLE
  e->fwd_window_success[e->fwd_window_head] = 0;
  e->fwd_window_head = (uint8_t)((e->fwd_window_head + 1) % TA_TRUST_FWD_WINDOW_SIZE);
  if(e->fwd_window_count < TA_TRUST_FWD_WINDOW_SIZE) {
    e->fwd_window_count++;
  }
#else
  (void)e;
#endif
}

static void
ta_fwd_window_note_credit(ta_trust_entry_t *e)
{
#if TA_TRUST_FWD_WINDOW_ENABLE
  if(e->fwd_window_count == 0) {
    return;
  }

  for(uint8_t age = 0; age < e->fwd_window_count; age++) {
    uint8_t idx = (uint8_t)((e->fwd_window_head + TA_TRUST_FWD_WINDOW_SIZE
                           - e->fwd_window_count + age) % TA_TRUST_FWD_WINDOW_SIZE);
    if(e->fwd_window_success[idx] == 0) {
      e->fwd_window_success[idx] = 1;
      return;
    }
  }
#else
  (void)e;
#endif
}

static int
ta_has_better_parent_candidate(uint16_t current_node_id, uint16_t current_trust)
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
      if(!brpl_trust_parent_allowed(node_id)) {
        continue;
      }
      if(trust + TA_TRUST_ESCAPE_BETTER_TRUST_MARGIN < current_trust) {
        continue;
      }

      path_cost = (uint32_t)rpl_get_parent_link_metric(p) + (uint32_t)p->rank;
      if(current_path_cost != 0xffffffff &&
         path_cost > current_path_cost + TA_TRUST_ESCAPE_BETTER_PATH_MARGIN) {
        continue;
      }

      return 1;
    }
  }

  return 0;
#else
  (void)current_node_id;
  (void)current_trust;
  return 1;
#endif
}

static int
escape_mode_for_entry(const ta_trust_entry_t *e)
{
  clock_time_t now = clock_time();
  uint8_t fwd_driven;
  uint8_t congestion_likely;

  if(e == NULL || e->node_id != current_parent_id) {
    return 0;
  }
  if(e->trust >= TA_TRUST_ESCAPE_TRUST_THRESHOLD) {
    return 0;
  }
  if(current_parent_elapsed() < (clock_time_t)TA_TRUST_ESCAPE_TRIGGER_SECONDS * CLOCK_SECOND) {
    return 0;
  }
  if(current_parent_escape_cooldown_until != 0 && now < current_parent_escape_cooldown_until) {
    return 0;
  }
  if(e->low_trust_updates < TA_TRUST_ESCAPE_CONSECUTIVE_UPDATES) {
    return 0;
  }
  if(!ta_has_better_parent_candidate(e->node_id, e->trust)) {
    return 0;
  }

  fwd_driven = (e->last_t_fwd < TA_TRUST_ESCAPE_FWD_SUSPECT_THRESHOLD)
            && (e->last_t_hon > TA_TRUST_ESCAPE_HON_HEALTHY_THRESHOLD);
  congestion_likely = (e->last_t_fwd < TA_TRUST_ESCAPE_FWD_SUSPECT_THRESHOLD)
                   && (e->last_t_hon <= TA_TRUST_ESCAPE_HON_HEALTHY_THRESHOLD);
  if(!fwd_driven || congestion_likely) {
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
    uint32_t combined = ((uint32_t)scale * attack_persistence_penalty_scale(e->node_id, e->trust))
                        / TA_TRUST_SCALE;
    if(combined > 0xffff) {
      combined = 0xffff;
    }
    scale = (uint16_t)combined;
  }

  return scale;
}

static uint16_t
ta_trust_median_snapshot(void)
{
#if TA_TRUST_RELATIVE_FILTER_ENABLE || TA_TRUST_RELATIVE_PENALTY_ENABLE
  uint16_t vals[TA_TRUST_MAX_NEIGHBORS];
  uint8_t n = 0;

  for(uint8_t i = 0; i < trust_table_size && n < TA_TRUST_MAX_NEIGHBORS; i++) {
    if(!trust_table[i].valid || trust_table[i].blacklisted) {
      continue;
    }
    vals[n++] = trust_table[i].trust;
  }

  if(n == 0) {
    return TA_TRUST_TAU_JOIN;
  }

  for(uint8_t i = 1; i < n; i++) {
    uint16_t key = vals[i];
    int8_t j = (int8_t)i - 1;
    while(j >= 0 && vals[j] > key) {
      vals[j + 1] = vals[j];
      j--;
    }
    vals[j + 1] = key;
  }

  return vals[n / 2];
#else
  return TA_TRUST_TAU_JOIN;
#endif
}

static uint16_t
ta_trust_relative_floor(uint16_t median)
{
#if TA_TRUST_RELATIVE_FILTER_ENABLE
  uint16_t floor = median > TA_TRUST_REL_MARGIN ? (uint16_t)(median - TA_TRUST_REL_MARGIN) : 0;
  if(floor < TA_TRUST_TAU_BLACK) {
    floor = TA_TRUST_TAU_BLACK;
  }
  return floor;
#else
  (void)median;
  return TA_TRUST_TAU_JOIN;
#endif
}

static uint16_t __attribute__((unused))
ta_trust_relative_penalty(uint16_t trust, uint16_t median)
{
#if TA_TRUST_RELATIVE_PENALTY_ENABLE
  if(trust >= median) {
    return 0;
  }

  uint32_t gap = (uint32_t)(median - trust);
  uint32_t penalty = (gap * TA_TRUST_REL_PENALTY_SCALE) / TA_TRUST_SCALE;
  if(penalty > TA_TRUST_REL_MAX_SOFT_PENALTY) {
    penalty = TA_TRUST_REL_MAX_SOFT_PENALTY;
  }
  return (uint16_t)penalty;
#else
  (void)trust;
  (void)median;
  return 0;
#endif
}

static uint16_t
ta_trust_effective_for_penalty(uint16_t node_id)
{
  uint16_t trust = ta_trust_get(node_id);

#if TA_TRUST_RELATIVE_PENALTY_ENABLE
  {
    uint16_t median = ta_trust_median_snapshot();
    uint16_t penalty = ta_trust_relative_penalty(trust, median);
    if(penalty >= TA_TRUST_SCALE) {
      return 0;
    }
    return (uint16_t)(TA_TRUST_SCALE - penalty);
  }
#else
  return trust;
#endif
}

static uint8_t
ta_join_min_updates_required(void)
{
  uint8_t updates =
    (TA_TRUST_JOIN_MIN_DURATION_SECONDS + TA_TRUST_UPDATE_INTERVAL - 1)
    / TA_TRUST_UPDATE_INTERVAL;
  return updates == 0 ? 1 : updates;
}

static int
ta_parent_exclusion_ready(const ta_trust_entry_t *e, uint16_t floor)
{
  if(e == NULL) {
    return 0;
  }
  if(e->blacklisted) {
    return 1;
  }
  if(e->trust < TA_TRUST_TAU_BLACK) {
    return 1;
  }
  if(e->trust >= floor) {
    return 0;
  }
  return e->below_join_updates >= ta_join_min_updates_required();
}

/* ------------------------------------------------------------------ */
/* Internal helpers                                                    */
/* ------------------------------------------------------------------ */
static ta_trust_entry_t *
find_entry(uint16_t node_id)
{
  for(uint8_t i = 0; i < trust_table_size; i++) {
    if(trust_table[i].valid && trust_table[i].node_id == node_id) {
      return &trust_table[i];
    }
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
  if(trust_table_size >= TA_TRUST_MAX_NEIGHBORS) {
    LOG_WARN("trust table full, dropping node %u\n", node_id);
    return NULL;
  }
  e = &trust_table[trust_table_size++];
  memset(e, 0, sizeof(*e));
  e->node_id    = node_id;
  e->valid      = 1;
  e->trust      = TA_TRUST_INIT;
  return e;
}

/* ------------------------------------------------------------------ */
/* T_fwd  = (F + alpha) / (E + alpha + beta)                          */
/* E = expected forwarding events = sent * PRR (channel-loss-aware)   */
/* PRR is estimated from Contiki-NG link-stats ETX for the neighbour. */
/* ------------------------------------------------------------------ */
static const linkaddr_t *
find_lladdr_by_node_id(uint16_t node_id) __attribute__((unused));

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
ta_estimate_prr(const linkaddr_t *lladdr) __attribute__((unused));

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
  if(prr > TA_PRR_MAX) {
    prr = TA_PRR_MAX;
  }
  if(prr > TA_TRUST_SCALE) {
    prr = TA_TRUST_SCALE;
  }
  if(prr < TA_PRR_MIN) {
    prr = TA_PRR_MIN;
  }

  return prr;
}

static uint16_t
compute_t_fwd_window(const ta_trust_entry_t *e) __attribute__((unused));

static uint16_t
compute_t_fwd_window(const ta_trust_entry_t *e)
{
#if TA_TRUST_FWD_WINDOW_ENABLE
  uint32_t successes = 0;

  for(uint8_t i = 0; i < e->fwd_window_count; i++) {
    uint8_t idx = (uint8_t)((e->fwd_window_head + TA_TRUST_FWD_WINDOW_SIZE
                           - e->fwd_window_count + i) % TA_TRUST_FWD_WINDOW_SIZE);
    successes += e->fwd_window_success[idx] ? 1u : 0u;
  }

  {
    uint32_t num = successes + TA_TRUST_FWD_ALPHA;
    uint32_t den = e->fwd_window_count + TA_TRUST_FWD_ALPHA + TA_TRUST_FWD_BETA;
    uint32_t val = (num * TA_TRUST_SCALE) / den;
    if(val > TA_TRUST_SCALE) {
      val = TA_TRUST_SCALE;
    }
    return ta_sharpen_tfwd((uint16_t)val);
  }
#else
  (void)e;
  return TA_TRUST_INIT;
#endif
}

static uint16_t
compute_t_fwd(const ta_trust_entry_t *e)
{
#if TA_TRUST_FWD_WINDOW_ENABLE
  return compute_t_fwd_window(e);
#else
  const linkaddr_t *lladdr = find_lladdr_by_node_id(e->node_id);
  uint32_t prr = ta_estimate_prr(lladdr);
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
#endif
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

  /* Weighted sum (weights sum to 10)                                  */
  uint32_t anomaly = ((uint32_t)TA_TRUST_CTRL_W_RANK * a_rank
                    + (uint32_t)TA_TRUST_CTRL_W_DIO  * a_dio
                    + (uint32_t)TA_TRUST_CTRL_W_VER  * a_ver) / 10;
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

/* ------------------------------------------------------------------ */
/* Blacklist management                                                */
/* ------------------------------------------------------------------ */
static void
check_blacklist(ta_trust_entry_t *e)
{
  clock_time_t now = clock_time();
  uint8_t black_min_updates =
    (TA_TRUST_BLACK_MIN_DURATION_SECONDS + TA_TRUST_UPDATE_INTERVAL - 1)
    / TA_TRUST_UPDATE_INTERVAL;

  if(e->blacklisted) {
    /* Release after quarantine period */
    if(now >= e->blacklist_until) {
      e->blacklisted = 0;
      e->trust = TA_TRUST_RESTORE_ON_RELEASE;
      e->below_join_updates = 0;
      e->below_black_updates = 0;
      e->low_trust_updates = 0;
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

  if(e->trust < TA_TRUST_TAU_BLACK) {
    if(e->below_black_updates < 0xff) {
      e->below_black_updates++;
    }
  } else {
    e->below_black_updates = 0;
  }

  if(e->trust < TA_TRUST_TAU_BLACK &&
     e->below_black_updates >= (black_min_updates == 0 ? 1 : black_min_updates)) {
    e->blacklisted = 1;
    e->release_active = 0;
    e->release_redrop_armed = 0;
    e->below_black_updates = 0;
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
  netstack_ip_packet_processor_add(&ta_ip_processor);
  LOG_INFO("TA-BRPL trust module initialised\n");
}

void
ta_trust_notify_sent(uint16_t node_id)
{
  ta_trust_entry_t *e = get_or_create(node_id);
  if(e == NULL) return;
  e->fwd_sent++;
  ta_fwd_window_note_sent(e);
}

void
ta_trust_notify_forwarded(uint16_t node_id)
{
  ta_trust_entry_t *e = get_or_create(node_id);
  if(e == NULL) return;
  e->fwd_observed++;
  ta_fwd_window_note_credit(e);
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
#if TA_TRUST_RELATIVE_FILTER_ENABLE || TA_TRUST_RELATIVE_PENALTY_ENABLE
  uint16_t median = ta_trust_median_snapshot();
  uint16_t rel_floor = ta_trust_relative_floor(median);
#endif

#if TA_TRUST_RELATIVE_FILTER_ENABLE || TA_TRUST_RELATIVE_PENALTY_ENABLE
  printf("CSV,TRUST_RELATIVE,%u,%lu,%u,%u\n",
         (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
         (unsigned long)clock_time(),
         (unsigned)median,
         (unsigned)rel_floor);
#endif

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

    e->last_t_fwd = t_fwd;
    e->last_t_ctrl = t_ctrl;
    e->last_t_hon = t_hon;
    e->last_t_agg = t_agg;

    uint16_t t_old = e->trust;
    e->trust = ewma_update(t_old, t_agg);
    if(e->trust < TA_TRUST_ESCAPE_TRUST_THRESHOLD) {
      if(e->low_trust_updates < 0xff) {
        e->low_trust_updates++;
      }
    } else {
      e->low_trust_updates = 0;
    }
    if(e->trust < TA_TRUST_TAU_JOIN) {
      if(e->below_join_updates < 0xff) {
        e->below_join_updates++;
      }
      e->below_join_ever = 1;
    } else {
      e->below_join_updates = 0;
    }

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
      printf("CSV,TRUST_ROUTEGUARD,%u,%u,%lu,%u,%u,%u\n",
             (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
             (unsigned)e->node_id,
             (unsigned long)(current_parent_elapsed() / CLOCK_SECOND),
             (unsigned)e->trust,
             (unsigned)penalty_scale,
             (unsigned)escape);

      if(escape && e->node_id == current_parent_id && current_parent_escape_armed) {
        current_parent_escape_armed = 0;
        current_parent_escape_cooldown_until =
          clock_time() + (clock_time_t)TA_TRUST_ESCAPE_COOLDOWN_SECONDS * CLOCK_SECOND;
        printf("CSV,TRUST_ESCAPE,%u,%u,%lu,%u\n",
               (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
               (unsigned)e->node_id,
               (unsigned long)clock_time(),
               (unsigned)e->trust);
        escape_triggered = 1;
      }
    }

    printf("CSV,TRUST,%u,%u,%u,%u,%u,%u,%u\n",
           (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
           (unsigned)e->node_id,
           (unsigned)t_fwd,
           (unsigned)t_ctrl,
           (unsigned)t_hon,
           (unsigned)t_agg,
           (unsigned)e->trust);

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
  }

  if(escape_triggered) {
    rpl_dag_t *dag = rpl_get_any_dag();
    if(dag != NULL && dag->instance != NULL) {
      rpl_reset_dio_timer(dag->instance);
    }
    dis_output(NULL);
  }

  log_parent_candidate_summary();
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
  uint16_t floor = ta_trust_relative_floor(ta_trust_median_snapshot());
  if(e == NULL) return TA_TRUST_NORMAL;
  if(e->blacklisted) return TA_TRUST_BLACKLISTED;
  if(e->trust >= TA_TRUST_TAU_WARN)   return TA_TRUST_NORMAL;
  if(e->trust >= floor)               return TA_TRUST_SUSPECT;
  if(!ta_parent_exclusion_ready(e, floor)) return TA_TRUST_SUSPECT;
  if(e->trust >= TA_TRUST_TAU_BLACK)  return TA_TRUST_UNTRUSTED;
  return TA_TRUST_BLACKLISTED;
}

int
ta_trust_is_parent_candidate(uint16_t node_id)
{
  ta_trust_entry_t *e = find_entry(node_id);
  uint16_t floor = ta_trust_relative_floor(ta_trust_median_snapshot());
  if(e == NULL) return 1; /* unknown: give benefit of the doubt        */
  if(e->blacklisted) return 0;
  if(e->trust < TA_TRUST_TAU_BLACK) {
    return 0;
  }
  /* Anti-oscillation gate: once a node's trust has dropped below tau_join
   * (below_join_ever=1), block re-admission while fwd evidence is stale
   * (fwd_sent halved to near 0 during exclusion).  Honest nodes remain
   * unaffected because they stay as active parents (fwd_sent stays high). */
  if(e->below_join_ever && e->fwd_sent < TA_TRUST_FWD_FRESH_THRESHOLD) {
    return 0;
  }
  if(e->trust >= floor) {
    return 1;
  }
  return !ta_parent_exclusion_ready(e, floor);
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
  return ta_trust_effective_for_penalty(node_id);
}

uint16_t
brpl_penalty_scale_get(uint16_t node_id)
{
  ta_trust_entry_t *e = find_entry(node_id);
  return penalty_scale_for_entry(e);
}

int
brpl_escape_mode_get(uint16_t node_id)
{
  ta_trust_entry_t *e = find_entry(node_id);
  return escape_mode_for_entry(e);
}

int
brpl_trust_parent_allowed(uint16_t node_id)
{
  ta_trust_entry_t *e = find_entry(node_id);
  uint16_t floor = ta_trust_relative_floor(ta_trust_median_snapshot());

  if(e == NULL) {
    return 1;
  }
  if(e->blacklisted) {
    return 0;
  }

  /* Anti-oscillation gate: once a node's trust has ever been below
   * tau_join (below_join_ever set), block re-admission while fwd
   * evidence is stale (fwd_sent halved toward 0 during exclusion).
   * When fwd_sent is stale, compute_t_fwd() returns ~500 (neutral
   * Bayesian prior), which would let trust drift above tau_join and
   * re-admit attackers.  This gate prevents that.  Honest nodes keep
   * fwd_sent high as long as they are used as parents, so they are
   * never blocked by this condition. */
  if(e->below_join_ever && e->fwd_sent < TA_TRUST_FWD_FRESH_THRESHOLD) {
    return 0;
  }

  /* Exclude nodes only after low trust persists long enough.
   * This keeps transient congestion/loss dips from pruning benign parents. */
  if(ta_parent_exclusion_ready(e, floor)) {
    return 0;
  }

  return 1;
}

void
brpl_preferred_parent_changed(uint16_t old_id, uint16_t new_id)
{
  (void)old_id;
  current_parent_id = new_id;
  current_parent_since = clock_time();
  current_parent_escape_armed = 1;
  current_parent_escape_cooldown_until = 0;
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
