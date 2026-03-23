/*
 * sender.c
 * UDP sensor sender for Contiki-NG / Cooja
 *
 * Protocol variants (compile-time flags):
 *   RPL_BASELINE_MODE=1  : Pure RPL (MRHOF, no trust, no BRPL)
 *   BRPL_MODE=1          : BRPL congestion-aware, no trust
 *   TABRPL_MODE=1        : TA-BRPL (BRPL + on-node trust model)
 *
 * CSV output lines:
 *   CSV,LLADDR,<id>,<hex>
 *   CSV,TX,<id>,<seq>,<t0>,<joined>
 *   CSV,RTT,<seq>,<t0>,<t_ack>,<rtt_ticks>,<len>
 *   CSV,PARENT,<id>,<ip|none>
 *   CSV,ROUTING,<id>,<joined>,<parent_ip>,<rank>
 *   CSV,TRUST,<self>,<nbr>,<t_fwd>,<t_ctrl>,<t_hon>,<t_agg>,<t_ewma>  [TA-BRPL only]
 */

#include "contiki.h"
#include "sys/log.h"
#include "sys/etimer.h"
#include "net/ipv6/uip.h"
#include "net/ipv6/uiplib.h"
#include "net/ipv6/uip-ds6.h"
#include "net/ipv6/uip-ds6-route.h"
#include "net/routing/routing.h"
#include "net/routing/rpl-classic/rpl.h"
#include "net/routing/rpl-classic/rpl-private.h"
#include "net/ipv6/simple-udp.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#ifdef TABRPL_MODE
#include "ta-brpl-trust.h"
#endif

#ifdef SMTRUST_MODE
#include "smtrust.h"
#endif

#define LOG_MODULE "SENDER"
#define LOG_LEVEL  LOG_LEVEL_WARN

#define UDP_PORT 8765

#ifndef SEND_INTERVAL_SECONDS
#define SEND_INTERVAL_SECONDS 30
#endif
#define SEND_INTERVAL (SEND_INTERVAL_SECONDS * CLOCK_SECOND)

#ifndef CONGESTION_INDUCTION_ENABLE
#define CONGESTION_INDUCTION_ENABLE 1
#endif

#ifndef CONGESTION_START_SECONDS
#define CONGESTION_START_SECONDS 200
#endif

#ifndef CONGESTION_END_SECONDS
#define CONGESTION_END_SECONDS 300
#endif

#ifndef CONGESTION_SEND_INTERVAL_SECONDS
#define CONGESTION_SEND_INTERVAL_SECONDS 15
#endif

#define CONGESTION_SEND_INTERVAL (CONGESTION_SEND_INTERVAL_SECONDS * CLOCK_SECOND)

/* Routing readiness limits */
#ifndef ROUTING_WAIT_MAX
#define ROUTING_WAIT_MAX (300 * CLOCK_SECOND)
#endif
#ifndef ROUTING_POLL_INT
#define ROUTING_POLL_INT (2 * CLOCK_SECOND)
#endif
#ifndef ROUTING_DIS_INT
#define ROUTING_DIS_INT (20 * CLOCK_SECOND)
#endif

/* ------------------------------------------------------------------ */
/* State                                                               */
/* ------------------------------------------------------------------ */
static struct simple_udp_connection udp_conn;
static uip_ipaddr_t root_ipaddr;
static uint16_t last_parent_id;
static uint32_t parent_switch_count;

#ifdef TABRPL_MODE
#define TX_PARENT_HISTORY_SIZE 64
typedef struct {
  uint32_t seq;
  uint16_t parent_id;
  uint8_t valid;
} tx_parent_hist_t;

static tx_parent_hist_t tx_parent_hist[TX_PARENT_HISTORY_SIZE];
static uint8_t tx_parent_hist_next;
#endif

/* Root-adjacent senders used to induce temporary congestion. */
static int
is_congestion_node(uint16_t node_id)
{
  switch(node_id) {
  case 17:
  case 18:
  case 22:
  case 27:
  case 28:
    return 1;
  default:
    return 0;
  }
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */
static void
update_root_ipaddr(void)
{
  if(!NETSTACK_ROUTING.get_root_ipaddr(&root_ipaddr)) {
    uip_ip6addr(&root_ipaddr, 0xaaaa, 0, 0, 0, 0, 0, 0, 1);
  }
}

static void
log_preferred_parent(void)
{
  rpl_dag_t *dag = rpl_get_any_dag();
  unsigned id = (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
  if(dag == NULL || dag->preferred_parent == NULL) {
    printf("CSV,PARENT,%u,none\n", id);
    return;
  }
  const uip_ipaddr_t *paddr = rpl_parent_get_ipaddr(dag->preferred_parent);
  printf("CSV,PARENT,%u,", id);
  if(paddr != NULL) {
    uiplib_ipaddr_print(paddr);
  } else {
    printf("unknown");
  }
  printf("\n");
}

static void
log_routing_status(void)
{
  rpl_dag_t *dag = rpl_get_any_dag();
  unsigned id     = (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
  unsigned joined = NETSTACK_ROUTING.node_has_joined() ? 1 : 0;
  printf("CSV,ROUTING,%u,%u,", id, joined);
  if(dag != NULL && dag->preferred_parent != NULL) {
    const uip_ipaddr_t *paddr = rpl_parent_get_ipaddr(dag->preferred_parent);
    if(paddr != NULL) {
      uiplib_ipaddr_print(paddr);
      printf(",%u\n", (unsigned)dag->rank);
      return;
    }
  }
  printf("none,0\n");
}

static uint16_t
preferred_parent_id(void)
{
  rpl_dag_t *dag = rpl_get_any_dag();
  if(dag == NULL || dag->preferred_parent == NULL) {
    return 0xffff;
  }

  {
    const linkaddr_t *pll = rpl_get_parent_lladdr(dag->preferred_parent);
    if(pll == NULL) {
      return 0xffff;
    }
    return pll->u8[LINKADDR_SIZE - 1];
  }
}

static void
log_route_snapshot(uint16_t self_id)
{
  rpl_dag_t *dag = rpl_get_any_dag();
  uint16_t parent_id = preferred_parent_id();
  uint16_t hop_est = 0xffff;
  uint16_t rank = 0;
  uint8_t joined = NETSTACK_ROUTING.node_has_joined() ? 1 : 0;
  uint8_t parent_is_sink = 0;
  uint8_t parent_is_attacker = 0;

  if(parent_id != last_parent_id) {
    if(last_parent_id != 0xffff) {
      parent_switch_count++;
    }
    last_parent_id = parent_id;
  }

  if(parent_id == 18) {
    parent_is_sink = 1;
  } else if(parent_id == 2 || parent_id == 3 || parent_id == 4) {
    parent_is_attacker = 1;
  }

  if(dag != NULL && dag->instance != NULL) {
    rank = dag->rank;
    if(dag->instance->min_hoprankinc > 0 && rank > 0) {
      hop_est = DAG_RANK(rank, dag->instance);
    }
  }

  printf("CSV,ROUTE,%u,%lu,%u,%u,%u,%lu,%u,%u,%u\n",
         (unsigned)self_id,
         (unsigned long)clock_time(),
         (unsigned)parent_id,
         (unsigned)rank,
         (unsigned)hop_est,
         (unsigned long)parent_switch_count,
         (unsigned)parent_is_sink,
         (unsigned)parent_is_attacker,
         (unsigned)joined);
}

static int
parse_echo(const uint8_t *data, uint16_t len,
           uint32_t *seq_out, uint32_t *t0_out)
{
  char buf[64];
  if(len >= sizeof(buf)) len = sizeof(buf) - 1;
  memcpy(buf, data, len);
  buf[len] = '\0';
  unsigned long seq = 0, t0 = 0;
  return (sscanf(buf, "seq=%lu t0=%lu", &seq, &t0) == 2)
    ? (*seq_out = (uint32_t)seq, *t0_out = (uint32_t)t0, 1)
    : 0;
}

#ifdef TABRPL_MODE
static void
remember_tx_parent(uint32_t seq, uint16_t parent_id)
{
  tx_parent_hist[tx_parent_hist_next].seq = seq;
  tx_parent_hist[tx_parent_hist_next].parent_id = parent_id;
  tx_parent_hist[tx_parent_hist_next].valid = 1;
  tx_parent_hist_next = (uint8_t)((tx_parent_hist_next + 1) % TX_PARENT_HISTORY_SIZE);
}

static uint16_t
take_tx_parent(uint32_t seq)
{
  for(uint8_t i = 0; i < TX_PARENT_HISTORY_SIZE; i++) {
    if(tx_parent_hist[i].valid && tx_parent_hist[i].seq == seq) {
      uint16_t parent_id = tx_parent_hist[i].parent_id;
      tx_parent_hist[i].valid = 0;
      return parent_id;
    }
  }
  return 0xffff;
}
#endif

#if CONGESTION_INDUCTION_ENABLE
static void
schedule_congestion_timer(struct etimer *timer, uint16_t node_id)
{
  clock_time_t now_t;
  clock_time_t start_t;
  clock_time_t end_t;

  if(!is_congestion_node(node_id)) {
    return;
  }

  now_t = clock_time();
  start_t = (clock_time_t)CONGESTION_START_SECONDS * CLOCK_SECOND;
  end_t = (clock_time_t)CONGESTION_END_SECONDS * CLOCK_SECOND;

  if(now_t < start_t) {
    etimer_set(timer, start_t - now_t);
  } else if(now_t < end_t) {
    clock_time_t to_end = end_t - now_t;
    etimer_set(timer, to_end < CONGESTION_SEND_INTERVAL ? to_end
                                                        : CONGESTION_SEND_INTERVAL);
  }
}
#endif

static void
send_data_packet(uint16_t self_id)
{
  char buf[64];
  uint32_t t0;
  uint8_t joined;
  static uint32_t seq;
  uint16_t tx_parent_id = 0xffff;

  log_preferred_parent();
  log_routing_status();
  log_route_snapshot(self_id);

  joined = NETSTACK_ROUTING.node_has_joined();

#if defined(TABRPL_MODE) || defined(SMTRUST_MODE)
  {
    rpl_dag_t *dag = rpl_get_any_dag();
    if(dag != NULL && dag->preferred_parent != NULL) {
      const linkaddr_t *pll = rpl_get_parent_lladdr(dag->preferred_parent);
      if(pll != NULL) {
        uint16_t pid = pll->u8[LINKADDR_SIZE - 1];
        tx_parent_id = pid;
#ifdef TABRPL_MODE
        ta_trust_notify_sent(pid);
#endif
#ifdef SMTRUST_MODE
        smtrust_notify_sent(pid);
#endif
      }
    }
  }
#endif

  t0 = (uint32_t)clock_time();
  seq++;
#ifdef TABRPL_MODE
  if(tx_parent_id != 0xffff) {
    remember_tx_parent(seq, tx_parent_id);
  }
#endif
  snprintf(buf, sizeof(buf), "seq=%lu t0=%lu",
           (unsigned long)seq, (unsigned long)t0);

  update_root_ipaddr();
  simple_udp_sendto(&udp_conn, buf, strlen(buf), &root_ipaddr);

  printf("CSV,TX,%u,%lu,%lu,%u\n",
         (unsigned)self_id,
         (unsigned long)seq,
         (unsigned long)t0,
         (unsigned)joined);
}

/* ------------------------------------------------------------------ */
/* Echo (RTT) callback                                                 */
/* ------------------------------------------------------------------ */
static void
echo_rx_callback(struct simple_udp_connection *c,
                 const uip_ipaddr_t *sender_addr,
                 uint16_t sender_port,
                 const uip_ipaddr_t *receiver_addr,
                 uint16_t receiver_port,
                 const uint8_t *data, uint16_t datalen)
{
  (void)c; (void)sender_addr; (void)sender_port;
  (void)receiver_addr; (void)receiver_port;

  uint32_t seq = 0, t0 = 0;
  uint32_t t_ack    = (uint32_t)clock_time();
  /* Log any UDP packet received on our port (diagnostic for echo routing) */
  printf("CSV,ECHORECV,%u,%lu\n",
         (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
         (unsigned long)t_ack);
  if(!parse_echo(data, datalen, &seq, &t0)) {
    return;
  }
  uint32_t rtt_ticks = t_ack - t0;
  printf("CSV,RTT,%lu,%lu,%lu,%lu,%u\n",
         (unsigned long)seq,
         (unsigned long)t0,
         (unsigned long)t_ack,
         (unsigned long)rtt_ticks,
         (unsigned)datalen);

#ifdef TABRPL_MODE
  /* Echo reply received: credit the parent that actually carried the
   * original TX for this seq, not the current parent at reply time. */
  {
    uint16_t pid = take_tx_parent(seq);
    if(pid != 0xffff) {
      ta_trust_notify_forwarded(pid);
    }
  }
#endif
}

/* ------------------------------------------------------------------ */
/* Process                                                             */
/* ------------------------------------------------------------------ */
PROCESS(sender_process, "UDP sensor sender");
AUTOSTART_PROCESSES(&sender_process);

PROCESS_THREAD(sender_process, ev, data)
{
  static struct etimer tx_timer;
  static struct etimer dis_timer;
  static struct etimer routing_timer;
#if defined(TABRPL_MODE) || defined(SMTRUST_MODE)
  static struct etimer trust_timer;
#endif
#if CONGESTION_INDUCTION_ENABLE
  static struct etimer congestion_tx_timer;
#endif
  static uint8_t  last_reachable;
  static uint8_t  routing_ready;
  static uint8_t  congestion_active;
  static uint16_t self_id;
  static clock_time_t routing_start;
  static clock_time_t last_dis;

  (void)ev; (void)data;

  PROCESS_BEGIN();

  /* Protocol banner */
#if defined(TABRPL_FWD_MODE)
  printf("CSV,PROTOCOL,%u,TABRPL_FWD\n",
         (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1]);
#elif defined(TABRPL_FWDCTRL_MODE)
  printf("CSV,PROTOCOL,%u,TABRPL_FWDCTRL\n",
         (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1]);
#elif defined(TABRPL_MODE)
  printf("CSV,PROTOCOL,%u,TABRPL\n",
         (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1]);
#elif defined(SMTRUST_MODE)
  printf("CSV,PROTOCOL,%u,SMTRUST\n",
         (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1]);
#elif defined(BRPL_MODE)
  printf("CSV,PROTOCOL,%u,BRPL\n",
         (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1]);
#else
  printf("CSV,PROTOCOL,%u,RPL\n",
         (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1]);
#endif

  /* Link-layer address log */
  {
    unsigned id = (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
    printf("CSV,LLADDR,%u,", id);
    for(uint8_t i = 0; i < LINKADDR_SIZE; i++) {
      printf("%02x", linkaddr_node_addr.u8[i]);
      if(i + 1 < LINKADDR_SIZE) printf(":");
    }
    printf("\n");
  }

  self_id = (uint16_t)linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
  last_parent_id = 0xffff;
  parent_switch_count = 0;
#ifdef TABRPL_MODE
  memset(tx_parent_hist, 0, sizeof(tx_parent_hist));
  tx_parent_hist_next = 0;
#endif

  update_root_ipaddr();
  simple_udp_register(&udp_conn, UDP_PORT, NULL, UDP_PORT, echo_rx_callback);

#ifdef TABRPL_MODE
  ta_trust_init();
  etimer_set(&trust_timer,
             (clock_time_t)(TA_TRUST_UPDATE_INTERVAL * CLOCK_SECOND));
#endif
#ifdef SMTRUST_MODE
  smtrust_init();
  etimer_set(&trust_timer,
             (clock_time_t)(SMTRUST_UPDATE_INTERVAL * CLOCK_SECOND));
#endif

  /* Routing readiness barrier */
  last_reachable = 0;
  routing_ready  = 0;
  congestion_active = 0;
  routing_start  = clock_time();
  last_dis       = 0;
  etimer_set(&routing_timer, 0);
  etimer_set(&tx_timer,      SEND_INTERVAL);
  etimer_set(&dis_timer,     30 * CLOCK_SECOND);
#if CONGESTION_INDUCTION_ENABLE
  schedule_congestion_timer(&congestion_tx_timer, self_id);
#endif
  dis_output(NULL);

  while(1) {
    PROCESS_WAIT_EVENT();

    /* ---- Periodic trust update ---- */
#ifdef TABRPL_MODE
    if(etimer_expired(&trust_timer)) {
      ta_trust_update_all();
      ta_trust_log_all();
      etimer_reset(&trust_timer);
    }
#endif
#ifdef SMTRUST_MODE
    if(etimer_expired(&trust_timer)) {
      smtrust_periodic_update();
      smtrust_log_all();
      etimer_reset(&trust_timer);
    }
#endif

    /* ---- Routing readiness poll ---- */
    if(!routing_ready) {
      if(etimer_expired(&routing_timer)) {
        if(last_dis == 0 ||
           (clock_time() - last_dis) > ROUTING_DIS_INT) {
          dis_output(NULL);
          last_dis = clock_time();
        }
        if(clock_time() - routing_start > ROUTING_WAIT_MAX) {
          routing_ready = 1; /* proceed on timeout */
        } else if(NETSTACK_ROUTING.node_is_reachable()) {
          routing_ready = 1;
          printf("ROUTING_READY joined=1 reachable=1\n");
        } else {
          etimer_set(&routing_timer, ROUTING_POLL_INT);
        }
      }
      if(!routing_ready) continue;
    }

    /* ---- DIS keep-alive ---- */
    if(etimer_expired(&dis_timer)) {
      if(!NETSTACK_ROUTING.node_has_joined()) {
        dis_output(NULL);
      }
      etimer_reset(&dis_timer);
    }

#if CONGESTION_INDUCTION_ENABLE
    {
      uint8_t now_active = is_congestion_node(self_id)
        && clock_time() >= (clock_time_t)CONGESTION_START_SECONDS * CLOCK_SECOND
        && clock_time() < (clock_time_t)CONGESTION_END_SECONDS * CLOCK_SECOND;
      if(now_active != congestion_active) {
        congestion_active = now_active;
        printf("CSV,CONGESTION,%u,%u\n",
               (unsigned)self_id,
               (unsigned)congestion_active);
      }
    }

    if(etimer_expired(&congestion_tx_timer)) {
      if(routing_ready) {
        send_data_packet(self_id);
      }
      schedule_congestion_timer(&congestion_tx_timer, self_id);
      continue;
    }
#endif

    /* ---- Periodic send ---- */
    if(!etimer_expired(&tx_timer)) continue;

    etimer_reset(&tx_timer);

    uint8_t reachable = NETSTACK_ROUTING.node_is_reachable();
    if(reachable != last_reachable) {
      last_reachable = reachable;
    }

#if CONGESTION_INDUCTION_ENABLE
    if(congestion_active && is_congestion_node(self_id)) {
      continue;
    }
#endif

    send_data_packet(self_id);
  }

  PROCESS_END();
}
