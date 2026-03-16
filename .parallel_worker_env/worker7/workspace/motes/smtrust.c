/*
 * smtrust.c
 * SMTrust implementation for Contiki-NG / Cooja.
 *
 * Trust formation:
 *   TMSR     — packet success rate via passive overhearing
 *   TM(H0)   — previous TrustIndex
 *   TMEL     — residual energy from energest
 *   TMLLS    — RSSI-normalised link stability
 *   TMMobility — 1.0 (static topology in our experiment)
 *   TMRT     — recommended trust from DIO-carried neighbour opinions
 *
 * Attack detection:
 *   Rank attack  — rank change without corresponding DIO sequence bump
 *   Blackhole    — TMSR drops below SUCCESS_THRESHOLD
 *
 * Trust propagation:
 *   Each node embeds its current TrustIndex for neighbours inside the
 *   DIO's remaining extension bytes, which is intercepted in the IP
 *   input hook (ICMPv6 RPL DIO parsing).
 *
 *   For simplicity the DIO extension carries:
 *     [1 byte] trust_node_id   — which neighbour is being reported
 *     [1 byte] trust_value_x100 — TrustIndex × 100 (0–100)
 *   appended after the standard DIO body (after the DODAGID).
 *   This is a custom non-standard extension; it is ignored by standard
 *   RPL implementations.
 */

#include "smtrust.h"

#include "contiki.h"
#include "sys/log.h"
#include "sys/energest.h"
#include "net/netstack.h"
#include "net/ipv6/uip.h"
#include "net/ipv6/uipbuf.h"
#include "net/ipv6/uip-icmp6.h"
#include "net/routing/rpl-classic/rpl.h"
#include "net/routing/rpl-classic/rpl-private.h"
#include "net/linkaddr.h"
#include "packetbuf.h"

#include <string.h>
#include <stdio.h>
#include <math.h>

#define LOG_MODULE "SMTRUST"
#define LOG_LEVEL  LOG_LEVEL_WARN

/* ------------------------------------------------------------------ */
/* State                                                               */
/* ------------------------------------------------------------------ */
static smtrust_entry_t trust_table[SMTRUST_MAX_NODES];
static uint8_t trust_table_size;

/* Energest baseline at init (for TMEL) */
static uint64_t energy_baseline_cpu;
static uint64_t energy_baseline_tx;
static uint64_t energy_baseline_rx;

static uint16_t
preferred_parent_id(void)
{
  rpl_dag_t *dag = rpl_get_any_dag();
  if(dag == NULL || dag->preferred_parent == NULL) {
    return 0xffff;
  }
  {
    const linkaddr_t *ll = rpl_get_parent_lladdr(dag->preferred_parent);
    return ll != NULL ? ll->u8[LINKADDR_SIZE - 1] : 0xffff;
  }
}

static void
trigger_reevaluation(const char *reason, uint16_t node_id)
{
  rpl_dag_t *dag = rpl_get_any_dag();
  printf("CSV,SMTRUST_REEVAL,%u,%u,%s\n",
         (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
         (unsigned)node_id,
         reason);
  if(dag != NULL && dag->instance != NULL) {
    rpl_reset_dio_timer(dag->instance);
  }
  dis_output(NULL);
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */
static smtrust_entry_t *
find_entry(uint16_t node_id)
{
  for(uint8_t i = 0; i < trust_table_size; i++) {
    if(trust_table[i].valid && trust_table[i].node_id == node_id) {
      return &trust_table[i];
    }
  }
  return NULL;
}

static smtrust_entry_t *
get_or_create(uint16_t node_id)
{
  smtrust_entry_t *e = find_entry(node_id);
  if(e) return e;
  if(trust_table_size >= SMTRUST_MAX_NODES) {
    LOG_WARN("trust table full\n");
    return NULL;
  }
  e = &trust_table[trust_table_size++];
  memset(e, 0, sizeof(*e));
  e->node_id     = node_id;
  e->valid       = 1;
  e->tmsr        = 1.0;
  e->tm_h0       = 0.5;
  e->tmel        = 1.0;
  e->tmlls       = 0.5;
  e->tm_mobility = 1.0;
  e->tmrt        = 0.5;
  e->trust_index = 0.5;
  e->rssi_last   = SMTRUST_RSSI_MAX; /* default: good link */
  return e;
}

/* ------------------------------------------------------------------ */
/* TMSR: success rate                                                   */
/* ------------------------------------------------------------------ */
static double
compute_tmsr(const smtrust_entry_t *e)
{
  if(e->pkts_sent == 0) {
    return 1.0; /* initial trust: assume perfect */
  }
  /* Bayesian smoothing avoids collapsing trust after a single missed
   * overhearing observation in the lossless Cooja model. */
  double ratio = (double)(e->pkts_observed + 1U)
               / (double)(e->pkts_sent + 2U);
  return (ratio > 1.0) ? 1.0 : ratio;
}

/* ------------------------------------------------------------------ */
/* TMEL: energy level                                                  */
/* Energy consumed / max energy: lower consumed → higher trust         */
/* ------------------------------------------------------------------ */
static double
compute_tmel(void)
{
  energest_flush();
  uint64_t cpu = energest_type_time(ENERGEST_TYPE_CPU);
  uint64_t tx  = energest_type_time(ENERGEST_TYPE_TRANSMIT);
  uint64_t rx  = energest_type_time(ENERGEST_TYPE_LISTEN);

  /* Total active time since baseline */
  uint64_t total = (cpu  - energy_baseline_cpu)
                 + (tx   - energy_baseline_tx)
                 + (rx   - energy_baseline_rx);

  /* Clock ticks up time since system start */
  uint64_t uptime = (uint64_t)clock_seconds() * RTIMER_SECOND;
  if(uptime == 0) return 1.0;

  /* Fraction of time spent in high-power modes (proxy for battery drain) */
  double drain_ratio = (double)total / (double)uptime;
  double tmel = 1.0 - drain_ratio;
  if(tmel < 0.0) tmel = 0.0;
  if(tmel > 1.0) tmel = 1.0;
  return tmel;
}

/* ------------------------------------------------------------------ */
/* TMLLS: link/location stability from RSSI                            */
/* ------------------------------------------------------------------ */
static double
compute_tmlls(const smtrust_entry_t *e)
{
  int32_t rssi;
  if(e->rssi_count > 0) {
    rssi = e->rssi_sum / (int32_t)e->rssi_count;
  } else {
    rssi = e->rssi_last;
  }

  double norm = (double)(rssi - SMTRUST_RSSI_MIN)
              / (double)(SMTRUST_RSSI_MAX - SMTRUST_RSSI_MIN);
  if(norm < 0.0) norm = 0.0;
  if(norm > 1.0) norm = 1.0;
  return norm;
}

/* ------------------------------------------------------------------ */
/* TMRT: recommended trust (average from neighbours)                   */
/* ------------------------------------------------------------------ */
static double
compute_tmrt(const smtrust_entry_t *e)
{
  if(e->tmrt_count == 0) {
    return 0.5; /* neutral initial value */
  }
  return e->tmrt_sum / (double)e->tmrt_count;
}

/* ------------------------------------------------------------------ */
/* TrustIndex: weighted sum                                            */
/* ------------------------------------------------------------------ */
static double
compute_trust_index(smtrust_entry_t *e)
{
  double ti = SMTRUST_W1 * e->tmsr
            + SMTRUST_W2 * e->tm_h0
            + SMTRUST_W3 * e->tmel
            + SMTRUST_W4 * e->tmlls
            + SMTRUST_W5 * e->tm_mobility
            + SMTRUST_W6 * e->tmrt;
  if(ti < 0.0) ti = 0.0;
  if(ti > 1.0) ti = 1.0;
  return ti;
}

/* ------------------------------------------------------------------ */
/* Attack detection                                                    */
/* ------------------------------------------------------------------ */
static void
detect_rank_attack(smtrust_entry_t *e, uint16_t new_rank, uint8_t new_seq)
{
  rpl_dag_t *dag = rpl_get_any_dag();

  if(!e->dio_seq_seen) {
    e->prev_rank    = new_rank;
    e->prev_dio_seq = new_seq;
    e->dio_seq_seen = 1;
    return;
  }

  /* Contiki's DIO version is a DODAG-wide counter, not a per-neighbour
   * sequence number, so natural rank updates with the same version are
   * common. The previous heuristic falsely marked most stable parents as
   * attackers and collapsed the network. We only flag physically
   * impossible advertisements here: a non-root claiming rank below the
   * root's own minimum rank. */
  if(dag != NULL && dag->instance != NULL &&
     new_rank != 0 && new_rank < dag->instance->min_hoprankinc) {
    e->is_suspicious = 1;
    printf("CSV,SMTRUST_RANK_ATTACK,%u,%u,%u\n",
           (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
           (unsigned)e->node_id,
           (unsigned)new_rank);
    if(e->node_id == preferred_parent_id()) {
      trigger_reevaluation("rank", e->node_id);
    }
  }

  e->prev_rank    = new_rank;
  e->prev_dio_seq = new_seq;
}

static void
detect_blackhole(smtrust_entry_t *e)
{
  if(e->pkts_sent >= SMTRUST_MIN_FWD_SAMPLES &&
     e->tmsr < SMTRUST_SUCCESS_THRESHOLD &&
     e->trust_index < SMTRUST_THRESHOLD) {
    if(!e->is_suspicious) {
      e->is_suspicious = 1;
      printf("CSV,SMTRUST_BLACKHOLE,%u,%u,tmsr=%.3f,trust=%.3f\n",
             (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
             (unsigned)e->node_id,
             e->tmsr,
             e->trust_index);
      if(e->node_id == preferred_parent_id()) {
        trigger_reevaluation("blackhole", e->node_id);
      }
    }
  } else if(e->tmsr >= SMTRUST_SUCCESS_THRESHOLD + 0.1 &&
            e->trust_index >= SMTRUST_THRESHOLD + 0.1) {
    /* Recovery: clear suspicious flag with hysteresis */
    e->is_suspicious = 0;
  }
}

/* ------------------------------------------------------------------ */
/* IP input hook — overhearing + DIO interception + RSSI              */
/* ------------------------------------------------------------------ */
static enum netstack_ip_action
smtrust_ip_input(void)
{
  if(uip_ds6_is_my_addr(&UIP_IP_BUF->srcipaddr)) {
    return NETSTACK_IP_PROCESS;
  }

  const linkaddr_t *mac_sender = packetbuf_addr(PACKETBUF_ADDR_SENDER);
  if(mac_sender == NULL) {
    return NETSTACK_IP_PROCESS;
  }
  uint16_t mac_id = mac_sender->u8[LINKADDR_SIZE - 1];
  smtrust_entry_t *e = get_or_create(mac_id);
  if(e == NULL) return NETSTACK_IP_PROCESS;

  /* RSSI sample */
  int16_t rssi = (int16_t)packetbuf_attr(PACKETBUF_ATTR_RSSI);
  if(rssi != 0) {
    e->rssi_sum  += rssi;
    e->rssi_count++;
    e->rssi_last  = rssi;
  }

  /* Forwarding observation for TMSR */
  uint8_t ip_src_id = UIP_IP_BUF->srcipaddr.u8[15];
  if(ip_src_id != mac_id) {
    /* mac_id is forwarding on behalf of ip_src_id */
    smtrust_entry_t *fwd = get_or_create(mac_id);
    if(fwd) fwd->pkts_observed++;
  }

  /* DIO: rank attack detection + TMRT extraction */
  if(UIP_IP_BUF->proto == UIP_PROTO_ICMP6) {
    struct uip_icmp_hdr *icmp6 = UIP_ICMP_BUF;

#ifndef RPL_CODE_DIO
#define RPL_CODE_DIO 0x02
#endif
    if(icmp6->type == ICMP6_RPL && icmp6->icode == RPL_CODE_DIO) {
      uint8_t *dio = ((uint8_t *)icmp6) + sizeof(struct uip_icmp_hdr);
      /* DIO body: [RPLInstanceID][Version][Rank(2B)][flags][DTSN][...] */
      uint8_t  seq  = dio[1]; /* version used as seq proxy */
      uint16_t rank = ((uint16_t)dio[2] << 8) | dio[3];

      detect_rank_attack(e, rank, seq);

      /* Custom trust options start after fixed 24-byte DIO base header.
       * Format: [0xFE][2][node_id][trust_x100] */
      {
        uint16_t dio_len = uip_len - UIP_IPH_LEN - 4;
        uint16_t off = 24;
        while(off + 2 <= dio_len) {
          uint8_t opt_type = dio[off];
          uint8_t opt_len;
          if(opt_type == 0) {
            off += 1;
            continue;
          }
          if(off + 2 > dio_len) {
            break;
          }
          opt_len = dio[off + 1];
          if(off + 2 + opt_len > dio_len) {
            break;
          }
          if(opt_type == 0xFE && opt_len == 2) {
            uint16_t rep_node = dio[off + 2];
            double rep_trust = (double)dio[off + 3] / 100.0;
            smtrust_entry_t *target = get_or_create(rep_node);
            if(target != NULL) {
              target->tmrt_sum += rep_trust;
              target->tmrt_count++;
            }
          }
          off += 2 + opt_len;
        }
      }
    }
  }

  return NETSTACK_IP_PROCESS;
}

static struct netstack_ip_packet_processor smtrust_proc = {
  .process_input  = smtrust_ip_input,
  .process_output = NULL
};

/* ------------------------------------------------------------------ */
/* Public API                                                          */
/* ------------------------------------------------------------------ */
void
smtrust_init(void)
{
  memset(trust_table, 0, sizeof(trust_table));
  trust_table_size = 0;

  energest_flush();
  energy_baseline_cpu = energest_type_time(ENERGEST_TYPE_CPU);
  energy_baseline_tx  = energest_type_time(ENERGEST_TYPE_TRANSMIT);
  energy_baseline_rx  = energest_type_time(ENERGEST_TYPE_LISTEN);

  netstack_ip_packet_processor_add(&smtrust_proc);
  LOG_INFO("SMTrust initialised\n");
}

void
smtrust_notify_sent(uint16_t node_id)
{
  smtrust_entry_t *e = get_or_create(node_id);
  if(e) e->pkts_sent++;
}

void
smtrust_periodic_update(void)
{
  double local_tmel = compute_tmel();

  for(uint8_t i = 0; i < trust_table_size; i++) {
    smtrust_entry_t *e = &trust_table[i];
    if(!e->valid) continue;

    /* Save previous TrustIndex for TM(H0) */
    e->tm_h0 = e->trust_index;

    /* Recompute all metrics */
    e->tmsr        = compute_tmsr(e);
    e->tmel        = local_tmel;
    e->tmlls       = compute_tmlls(e);
    e->tm_mobility = 1.0; /* static topology */
    e->tmrt        = compute_tmrt(e);

    /* TrustIndex */
    e->trust_index = compute_trust_index(e);

    /* Attack detection */
    detect_blackhole(e);

    printf("CSV,SMTRUST,%u,%u,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%s\n",
           (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
           (unsigned)e->node_id,
           e->tmsr,
           e->tm_h0,
           e->tmel,
           e->tmlls,
           e->tm_mobility,
           e->tmrt,
           e->trust_index,
           e->is_suspicious ? "SUSP" : "OK");

    /* Reset per-window counters */
    e->pkts_sent     = 0;
    e->pkts_observed = 0;
    e->rssi_sum      = 0;
    e->rssi_count    = 0;
    e->tmrt_sum      = 0.0;
    e->tmrt_count    = 0;
  }
}

double
smtrust_get(uint16_t node_id)
{
  smtrust_entry_t *e = find_entry(node_id);
  if(e == NULL) return 0.5;
  if(e->is_suspicious) return 0.0;
  return e->trust_index;
}

smtrust_level_t
smtrust_level(uint16_t node_id)
{
  double ti = smtrust_get(node_id);
  if(ti <= 0.20) return SMTRUST_L1_NO_TRUST;
  if(ti <= 0.45) return SMTRUST_L2_POOR;
  if(ti <= 0.70) return SMTRUST_L3_FAIR;
  if(ti <= 0.90) return SMTRUST_L4_GOOD;
  return SMTRUST_L5_FULL;
}

int
smtrust_is_parent_candidate(uint16_t node_id)
{
  smtrust_entry_t *e = find_entry(node_id);
  if(e == NULL) return 1; /* unknown → optimistic */
  if(e->is_suspicious) return 0;
  return e->trust_index >= SMTRUST_THRESHOLD;
}

void
smtrust_log_all(void)
{
  for(uint8_t i = 0; i < trust_table_size; i++) {
    smtrust_entry_t *e = &trust_table[i];
    if(!e->valid) continue;
    printf("CSV,SMTRUST_TABLE,%u,%u,%.3f,%s\n",
           (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
           (unsigned)e->node_id,
           e->trust_index,
           e->is_suspicious ? "SUSP" : "OK");
  }
}

/*
 * Override brpl_trust_get() weak symbol.
 * SMTrust runs on pure MRHOF (no BRPL backpressure), but the symbol
 * must be defined to avoid linker errors when BRPL is compiled in.
 * Returns TrustIndex scaled to [0, 1000].
 */
uint16_t
brpl_trust_get(uint16_t node_id)
{
  double ti = smtrust_get(node_id);
  uint16_t scaled = (uint16_t)(ti * 1000.0);
  return scaled;
}

int
smtrust_append_dio_options(uint8_t *buffer, int pos, int max_len)
{
  int added = 0;
  uint16_t self_id = linkaddr_node_addr.u8[LINKADDR_SIZE - 1];

  for(uint8_t i = 0; i < trust_table_size && added < 4; i++) {
    smtrust_entry_t *e = &trust_table[i];
    uint8_t trust_x100;
    if(!e->valid || e->node_id == self_id) {
      continue;
    }
    if(pos + 4 > max_len) {
      break;
    }
    trust_x100 = (uint8_t)(e->trust_index * 100.0);
    buffer[pos++] = 0xFE;
    buffer[pos++] = 2;
    buffer[pos++] = (uint8_t)e->node_id;
    buffer[pos++] = trust_x100;
    added++;
  }

  return pos;
}

int
smtrust_compare_parents(uint16_t p1_id, uint16_t p2_id,
                        uint16_t p1_rank, uint16_t p2_rank,
                        uint16_t self_rank,
                        uint16_t p1_metric, uint16_t p2_metric)
{
  smtrust_level_t l1 = smtrust_level(p1_id);
  smtrust_level_t l2 = smtrust_level(p2_id);
  double t1 = smtrust_get(p1_id);
  double t2 = smtrust_get(p2_id);
  int p1_rank_ok = p1_rank <= self_rank;
  int p2_rank_ok = p2_rank <= self_rank;
  uint16_t metric_gap = p1_metric > p2_metric
                      ? (p1_metric - p2_metric)
                      : (p2_metric - p1_metric);
  double trust_gap = t1 > t2 ? (t1 - t2) : (t2 - t1);
  double strong_gap = (double)SMTRUST_TRUST_DIFF_STRONG_X100 / 100.0;
  double weak_gap = (double)SMTRUST_TRUST_DIFF_WEAK_X100 / 100.0;

  if(p1_rank_ok != p2_rank_ok) {
    return p1_rank_ok ? -1 : 1;
  }

  /* Let MRHOF dominate when route quality is clearly different. */
  if(metric_gap > SMTRUST_METRIC_NEAR_TIE) {
    return 0;
  }

  /* Only near-ties are reordered by trust. Prefer a clearly higher
   * trust level among otherwise similar candidates. */
  if(l1 >= SMTRUST_L4_GOOD && l2 <= SMTRUST_L3_FAIR &&
     t1 >= t2 + strong_gap) {
    return -1;
  }
  if(l2 >= SMTRUST_L4_GOOD && l1 <= SMTRUST_L3_FAIR &&
     t2 >= t1 + strong_gap) {
    return 1;
  }

  if(l1 != l2 && trust_gap >= strong_gap) {
    return l1 > l2 ? -1 : 1;
  }

  if(trust_gap >= weak_gap) {
    return t1 > t2 ? -1 : 1;
  }

  return 0;
}
