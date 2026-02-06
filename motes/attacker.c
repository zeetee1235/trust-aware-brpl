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
#include "net/ipv6/simple-udp.h"
#include "net/linkaddr.h"
#include "random.h"
#include "net/routing/routing.h"
#include "net/routing/rpl-classic/rpl.h"
#include "net/routing/rpl-classic/rpl-private.h"
#include "dev/serial-line.h"
#include "net/nbr-table.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

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

#ifndef ROUTING_DIS_INT
#define ROUTING_DIS_INT (20 * CLOCK_SECOND)
#endif

static uint8_t effective_drop_pct;

static uip_ipaddr_t root_ipaddr;
static uint8_t attack_enabled;
static uint32_t fwd_total;
static uint32_t fwd_udp_root;
static uint32_t fwd_udp_root_dropped;
static uint32_t last_seq[256];

#define ROOT_NODE_ID 1


static void
log_preferred_parent(void)
{
  rpl_dag_t *dag = rpl_get_any_dag();
  unsigned node_id = (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
  if(dag == NULL || dag->preferred_parent == NULL) {
    printf("CSV,PARENT,%u,none\n", node_id);
    return;
  }
  const uip_ipaddr_t *paddr = rpl_parent_get_ipaddr(dag->preferred_parent);
  printf("CSV,PARENT,%u,", node_id);
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
  unsigned node_id = (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
  unsigned joined = NETSTACK_ROUTING.node_has_joined() ? 1 : 0;
  printf("CSV,ROUTING,%u,%u,", node_id, joined);
  if(dag != NULL && dag->preferred_parent != NULL) {
    const uip_ipaddr_t *paddr = rpl_parent_get_ipaddr(dag->preferred_parent);
    if(paddr != NULL) {
      uiplib_ipaddr_print(paddr);
      printf("\n");
      return;
    }
  }
  printf("none\n");
}

static uint8_t
should_attack_drop(void)
{
  if(effective_drop_pct == 0) {
    return 0;
  }
  if(effective_drop_pct >= 100) {
    return 1;
  }
  return (random_rand() % 100) < effective_drop_pct;
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
    brpl_trust_override((uint16_t)node_id, (uint16_t)trust);
#if CSV_VERBOSE_LOGGING
    uint16_t self_id = (uint16_t)linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
    printf("CSV,TRUST_IN,%u,%u,%u\n", self_id, node_id, trust);
#endif
    
    /* Auto-blacklist if trust is below threshold */
    if(trust < BLACKLIST_TRUST_THRESHOLD) {
      brpl_blacklist_add((uint16_t)node_id);
    } else {
      brpl_blacklist_remove((uint16_t)node_id);
    }
  }
}

static int
parse_payload(const uint8_t *data, uint16_t len, uint32_t *seq_out)
{
  char buf[64];
  if(len >= sizeof(buf)) len = sizeof(buf) - 1;
  memcpy(buf, data, len);
  buf[len] = '\0';

  unsigned long seq = 0;
  unsigned long t0 = 0;
  int matched = sscanf(buf, "seq=%lu t0=%lu", &seq, &t0);
  if(matched == 2) {
    *seq_out = (uint32_t)seq;
    return 1;
  }
  return 0;
}

static struct simple_udp_connection udp_conn;

static void
udp_rx_callback(struct simple_udp_connection *c,
                const uip_ipaddr_t *sender_addr,
                uint16_t sender_port,
                const uip_ipaddr_t *receiver_addr,
                uint16_t receiver_port,
                const uint8_t *data,
                uint16_t datalen)
{
  (void)c; (void)sender_addr; (void)sender_port;
  (void)receiver_addr; (void)receiver_port;

  fwd_total++;
  fwd_udp_root++;

  uint32_t seq = 0;
  uint16_t sender_id = uip_ntohs(sender_addr->u16[7]);
  if(parse_payload(data, datalen, &seq)) {
    if(seq <= last_seq[sender_id]) {
      return;
    }
    last_seq[sender_id] = seq;
  }

  if(attack_enabled && should_attack_drop()) {
    fwd_udp_root_dropped++;
    LOG_WARN("drop fwd UDP to root\n");
    return;
  }

  if(seq > 0) {
    printf("CSV,FWD_PKT,%u,%u,%lu\n",
           (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
           (unsigned)sender_id,
           (unsigned long)seq);
  }

  /* Echo back to sender to enable RTT logging (proxy delay). */
  simple_udp_sendto(&udp_conn, data, datalen, sender_addr);

  simple_udp_sendto(&udp_conn, data, datalen, &root_ipaddr);
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
  serial_line_init();
  brpl_blacklist_init();
  
  /* Effective drop rate for this node */
  effective_drop_pct = ATTACK_DROP_PCT;
  LOG_INFO("=== ATTACKER NODE INITIALIZED === (Node ID: %u)\n", 
           (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1]);
  LOG_INFO("attack will start after %u second warmup\n", ATTACK_WARMUP_SECONDS);
  LOG_INFO("routing driver: %s\n", NETSTACK_ROUTING.name);
  {
    unsigned node_id = (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
    printf("CSV,LLADDR,%u,", node_id);
    for(uint8_t i = 0; i < LINKADDR_SIZE; i++) {
      printf("%02x", linkaddr_node_addr.u8[i]);
      if(i + 1 < LINKADDR_SIZE) {
        printf(":");
      }
    }
    printf("\n");
  }
  simple_udp_register(&udp_conn, UDP_PORT, NULL, UDP_PORT, udp_rx_callback);

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
        dis_output(NULL);
      }
      etimer_reset(&dis_timer);
    }
    if(etimer_expired(&parent_timer)) {
      log_preferred_parent();
      log_routing_status();
      etimer_reset(&parent_timer);
    }
    if(etimer_expired(&stats_timer)) {
      unsigned node_id = (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
      printf("CSV,FWD,%u,%lu,%lu,%lu\n",
             node_id,
             (unsigned long)fwd_total,
             (unsigned long)fwd_udp_root,
             (unsigned long)fwd_udp_root_dropped);
      etimer_reset(&stats_timer);
    }
  }

  PROCESS_END();
}
