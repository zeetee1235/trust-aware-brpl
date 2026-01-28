/*
 * attacker.c
 * - Selective Forwarding attacker for Contiki-NG (Cooja)
 * - Drops forwarded UDP packets to the root with probability
 */

#include "contiki.h"
#include "sys/log.h"

#include "net/netstack.h"
#include "net/ipv6/uip.h"
#include "net/ipv6/uipbuf.h"
#include "net/ipv6/uip-ds6.h"
#include "net/ipv6/uiplib.h"
#include "net/linkaddr.h"
#include "random.h"
#include "net/routing/routing.h"
#include "net/routing/rpl-lite/rpl.h"
#include "net/routing/rpl-lite/rpl-icmp6.h"
#include "dev/serial-line.h"

#include <stdint.h>

#include "brpl-trust.h"
#include "brpl-blacklist.h"

#define LOG_MODULE "ATTACK"
#define LOG_LEVEL LOG_LEVEL_INFO

#define UDP_PORT 8765

#ifndef WARMUP_SECONDS
#define WARMUP_SECONDS 60
#endif

#ifndef ATTACK_DROP_PCT
#define ATTACK_DROP_PCT 50
#endif

#ifndef ATTACK_WARMUP_SECONDS
#define ATTACK_WARMUP_SECONDS WARMUP_SECONDS
#endif

static uip_ipaddr_t root_ipaddr;
static uint8_t attack_enabled;
static uint32_t fwd_total;
static uint32_t fwd_udp_root;
static uint32_t fwd_udp_root_dropped;

static void
log_preferred_parent(void)
{
  rpl_dag_t *dag = rpl_get_any_dag();
  unsigned node_id = (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
  if(dag == NULL || dag->preferred_parent == NULL) {
    printf("CSV,PARENT,%u,none\n", node_id);
    return;
  }
  const uip_ipaddr_t *paddr = rpl_neighbor_get_ipaddr(dag->preferred_parent);
  printf("CSV,PARENT,%u,", node_id);
  if(paddr != NULL) {
    uiplib_ipaddr_print(paddr);
  } else {
    printf("unknown");
  }
  printf("\n");
}

static uint8_t
should_attack_drop(void)
{
  if(ATTACK_DROP_PCT == 0) {
    return 0;
  }
  if(ATTACK_DROP_PCT >= 100) {
    return 1;
  }
  return (random_rand() % 100) < ATTACK_DROP_PCT;
}

static uint8_t
is_forwarded_udp_to_root(void)
{
  uint8_t proto = 0;

  if(uip_ds6_is_my_addr(&UIP_IP_BUF->srcipaddr)) {
    return 0;
  }

  uipbuf_get_last_header(uip_buf, uip_len, &proto);
  if(proto != UIP_PROTO_UDP) {
    return 0;
  }

  if(UIP_UDP_BUF->destport != UIP_HTONS(UDP_PORT)) {
    return 0;
  }

  return uip_ipaddr_cmp(&UIP_IP_BUF->destipaddr, &root_ipaddr);
}

static void
handle_trust_input(const char *line)
{
  unsigned node_id = 0;
  unsigned trust = 0;
  if(sscanf(line, "TRUST,%u,%u", &node_id, &trust) == 2) {
    uint16_t self_id = (uint16_t)linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
    brpl_trust_override((uint16_t)node_id, (uint16_t)trust);
    printf("CSV,TRUST_IN,%u,%u,%u\n", self_id, node_id, trust);
    
    /* Auto-blacklist if trust is below threshold */
    if(trust < BLACKLIST_TRUST_THRESHOLD) {
      brpl_blacklist_add((uint16_t)node_id);
    } else {
      brpl_blacklist_remove((uint16_t)node_id);
    }
  }
}

static enum netstack_ip_action
ip_output(const linkaddr_t *localdest)
{
  (void)localdest;

  /* Check blacklist first - drop packets to/from blacklisted nodes */
  if(brpl_blacklist_should_drop_packet(&UIP_IP_BUF->destipaddr, &UIP_IP_BUF->srcipaddr)) {
    return NETSTACK_IP_DROP;
  }

  if(!attack_enabled) {
    return NETSTACK_IP_PROCESS;
  }

  if(!uip_ds6_is_my_addr(&UIP_IP_BUF->srcipaddr)) {
    fwd_total++;
  }

  if(is_forwarded_udp_to_root() && should_attack_drop()) {
    fwd_udp_root++;
    fwd_udp_root_dropped++;
    LOG_WARN("drop fwd UDP to root\n");
    return NETSTACK_IP_DROP;
  }

  if(is_forwarded_udp_to_root()) {
    fwd_udp_root++;
  }

  return NETSTACK_IP_PROCESS;
}

static struct netstack_ip_packet_processor packet_processor = {
  .process_input = NULL,
  .process_output = ip_output
};

PROCESS(attacker_process, "Selective Forwarding attacker");
AUTOSTART_PROCESSES(&attacker_process);

PROCESS_THREAD(attacker_process, ev, data)
{
  static struct etimer warmup_timer;
  static struct etimer dis_timer;
  static struct etimer parent_timer;
  static struct etimer stats_timer;

  (void)ev; (void)data;

  PROCESS_BEGIN();

  uip_ip6addr(&root_ipaddr, 0xaaaa,0,0,0,0,0,0,1);

#ifdef BRPL_MODE
  printf("CSV,BRPL_MODE,%u,1\n", (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1]);
#else
  printf("CSV,BRPL_MODE,%u,0\n", (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1]);
#endif

  random_init();

  netstack_ip_packet_processor_add(&packet_processor);
  rpl_set_leaf_only(0);
  serial_line_init();
  brpl_blacklist_init();

  etimer_set(&dis_timer, 30 * CLOCK_SECOND);
  etimer_set(&parent_timer, 30 * CLOCK_SECOND);
  etimer_set(&stats_timer, 30 * CLOCK_SECOND);
  attack_enabled = 0;
  fwd_total = 0;
  fwd_udp_root = 0;
  fwd_udp_root_dropped = 0;
  if(ATTACK_WARMUP_SECONDS > 0) {
    etimer_set(&warmup_timer, ATTACK_WARMUP_SECONDS * CLOCK_SECOND);
  } else {
    attack_enabled = 1;
    LOG_INFO("attack enabled: drop=%u%%\n", (unsigned)ATTACK_DROP_PCT);
  }

  while(1) {
    PROCESS_WAIT_EVENT();
    if(ev == serial_line_event_message && data != NULL) {
      handle_trust_input((const char *)data);
    }
    if(!attack_enabled && ATTACK_WARMUP_SECONDS > 0 && etimer_expired(&warmup_timer)) {
      attack_enabled = 1;
      LOG_INFO("attack enabled: drop=%u%%\n", (unsigned)ATTACK_DROP_PCT);
    }
    if(etimer_expired(&dis_timer)) {
      if(!NETSTACK_ROUTING.node_has_joined()) {
        LOG_INFO("send DIS (not joined)\n");
        rpl_icmp6_dis_output(NULL);
      }
      etimer_reset(&dis_timer);
    }
    if(etimer_expired(&parent_timer)) {
      log_preferred_parent();
      etimer_reset(&parent_timer);
    }
    if(etimer_expired(&stats_timer)) {
      printf("CSV,FWD,3,%lu,%lu,%lu\n",
             (unsigned long)fwd_total,
             (unsigned long)fwd_udp_root,
             (unsigned long)fwd_udp_root_dropped);
      etimer_reset(&stats_timer);
    }
  }

  PROCESS_END();
}
