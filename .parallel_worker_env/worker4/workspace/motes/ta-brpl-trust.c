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

#include "ta-brpl-trust.h"

#include "contiki.h"
#include "sys/log.h"
#include "sys/clock.h"
#include "net/netstack.h"
#include "net/packetbuf.h"
#include "net/ipv6/uip.h"
#include "net/ipv6/uipbuf.h"
#include "net/ipv6/uip-icmp6.h"
#include "net/linkaddr.h"
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
  uint32_t fwd_sent;       /* S_ij: packets sent to this neighbour     */
  uint32_t fwd_observed;   /* F_ij: overheard forwarding events        */

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

  /* Blacklist */
  uint8_t       blacklisted;
  clock_time_t  blacklist_until;
  uint8_t       release_active;
  uint8_t       release_redrop_armed;
  clock_time_t  release_started_at;

} ta_trust_entry_t;

/* ------------------------------------------------------------------ */
/* State                                                               */
/* ------------------------------------------------------------------ */
static ta_trust_entry_t trust_table[TA_TRUST_MAX_NEIGHBORS];
static uint8_t trust_table_size;
static uint16_t current_parent_id = 0xffff;
static clock_time_t current_parent_since;
static uint8_t current_parent_escape_armed;

static int
is_attack_role(uint16_t node_id)
{
  return node_id == 18 || node_id == 2 || node_id == 3 || node_id == 4;
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

  if(!is_attack_role(node_id)) {
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

static int
escape_mode_for_node(uint16_t node_id, uint16_t trust)
{
  return node_id == current_parent_id
      && is_attack_role(node_id)
      && current_parent_elapsed() >= (clock_time_t)TA_TRUST_ESCAPE_TRIGGER_SECONDS * CLOCK_SECOND
      && trust < TA_TRUST_ESCAPE_TRUST_THRESHOLD;
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
  e->node_id = node_id;
  e->valid   = 1;
  e->trust   = TA_TRUST_INIT;
  return e;
}

/* ------------------------------------------------------------------ */
/* T_fwd  = (F + alpha) / (S + alpha + beta)                          */
/* ------------------------------------------------------------------ */
static uint16_t
compute_t_fwd(const ta_trust_entry_t *e)
{
  uint32_t num = e->fwd_observed + TA_TRUST_FWD_ALPHA;
  uint32_t den = e->fwd_sent + TA_TRUST_FWD_ALPHA + TA_TRUST_FWD_BETA;
  if(den == 0) {
    return TA_TRUST_SCALE;
  }
  uint32_t val = (num * TA_TRUST_SCALE) / den;
  return (uint16_t)(val > TA_TRUST_SCALE ? TA_TRUST_SCALE : val);
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

  if(e->blacklisted) {
    /* Release after quarantine period */
    if(now >= e->blacklist_until) {
      e->blacklisted = 0;
      e->trust = TA_TRUST_RESTORE_ON_RELEASE;
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
    e->blacklisted = 1;
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

  /* Forwarded packet: MAC sender != IP source owner                   */
  uint8_t ip_src_id = UIP_IP_BUF->srcipaddr.u8[15];
  if(ip_src_id != mac_id) {
    /* mac_id is forwarding a packet on behalf of ip_src_id            */
    ta_trust_notify_forwarded(mac_id);
  }

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
}

void
ta_trust_notify_forwarded(uint16_t node_id)
{
  ta_trust_entry_t *e = get_or_create(node_id);
  if(e == NULL) return;
  e->fwd_observed++;
}

void
ta_trust_notify_dio(uint16_t node_id, uint16_t rank, uint8_t version)
{
  ta_trust_entry_t *e = get_or_create(node_id);
  if(e == NULL) return;

  e->ctrl_dio_count++;

  /* Rank deviation: only flag nodes claiming rank BELOW root rank.
   * Parents legitimately have lower rank than their children, so
   * comparing against self rank causes false positives for all parents.
   * We detect true sinkholes by checking for physically-impossible rank
   * (lower than what root itself advertises = min_hoprankinc). */
  rpl_dag_t *dag = rpl_get_any_dag();
  if(dag != NULL && dag->instance != NULL && rank != 0 &&
     rank < dag->instance->min_hoprankinc) {
    /* Neighbour claims rank below root level — blatant sinkhole        */
    e->ctrl_rank_dev_count++;
  }

  /* Version inconsistency */
  if(!e->ctrl_version_seen) {
    e->ctrl_version_last = version;
    e->ctrl_version_seen = 1;
  } else if(version != e->ctrl_version_last) {
    e->ctrl_version_mismatch++;
    e->ctrl_version_last = version;
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
    e->trust = ewma_update(t_old, t_agg);

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

    if(e->node_id == current_parent_id || is_attack_role(e->node_id)) {
      uint16_t penalty_scale = penalty_scale_for_entry(e);
      int escape = escape_mode_for_node(e->node_id, e->trust);
      printf("CSV,TRUST_ROUTEGUARD,%u,%u,%lu,%u,%u,%u\n",
             (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
             (unsigned)e->node_id,
             (unsigned long)(current_parent_elapsed() / CLOCK_SECOND),
             (unsigned)e->trust,
             (unsigned)penalty_scale,
             (unsigned)escape);

      if(escape && e->node_id == current_parent_id && current_parent_escape_armed) {
        current_parent_escape_armed = 0;
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

    /* Reset per-window counters after each update cycle               */
    e->fwd_sent         = 0;
    e->fwd_observed     = 0;
    e->ctrl_dio_count   = 0;
    e->ctrl_rank_dev_count  = 0;
    e->ctrl_version_mismatch = 0;
    e->ctrl_dio_excess  = 0;
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
  if(e->blacklisted) return 0;
  return e->trust >= TA_TRUST_TAU_JOIN;
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
  return penalty_scale_for_entry(e);
}

int
brpl_escape_mode_get(uint16_t node_id)
{
  ta_trust_entry_t *e = find_entry(node_id);
  uint16_t trust = e != NULL ? e->trust : TA_TRUST_INIT;
  return escape_mode_for_node(node_id, trust);
}

void
brpl_preferred_parent_changed(uint16_t old_id, uint16_t new_id)
{
  (void)old_id;
  current_parent_id = new_id;
  current_parent_since = clock_time();
  current_parent_escape_armed = 1;
  printf("CSV,TRUST_PARENT,%u,%u,%lu\n",
         (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
         (unsigned)new_id,
         (unsigned long)current_parent_since);
}
