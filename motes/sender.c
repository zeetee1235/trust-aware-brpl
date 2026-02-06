/*
 * sender.c
 * - UDP sensor sender for Contiki-NG (Cooja)
 * - Sends seq + local clock after warmup
 * - RTT measured via receiver echo
 */

#include "contiki.h"
#include "sys/log.h"

#include "net/ipv6/uip.h"
#include "net/ipv6/uiplib.h"
#include "net/ipv6/uip-ds6-route.h"
#include "net/nbr-table.h"
#include "net/routing/routing.h"
#include "net/routing/rpl-classic/rpl.h"
#include "net/routing/rpl-classic/rpl-private.h"
#include "net/ipv6/simple-udp.h"
#include "dev/serial-line.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "brpl-trust.h"
#include "brpl-blacklist.h"

#define LOG_MODULE "SENDER"
#define LOG_LEVEL LOG_LEVEL_INFO

#define UDP_PORT 8765
#ifndef SEND_INTERVAL_SECONDS
#define SEND_INTERVAL_SECONDS 10
#endif
#ifndef WARMUP_SECONDS
#define WARMUP_SECONDS 60
#endif
#ifndef TRUST_SCALE
#define TRUST_SCALE 1000
#endif
#define SEND_INTERVAL (SEND_INTERVAL_SECONDS * CLOCK_SECOND)

static struct simple_udp_connection udp_conn;
static uip_ipaddr_t root_ipaddr;
static uip_ipaddr_t forwarder_ipaddr;

#ifndef ATTACKER_NODE_ID
#define ATTACKER_NODE_ID 2
#endif
#ifndef RELAY_NODE_ID
#define RELAY_NODE_ID 4
#endif
#define TRUST_SWITCH_THRESHOLD 700

static uint16_t trust_attacker = TRUST_SCALE;
static uint16_t trust_relay = TRUST_SCALE;

static void
set_forwarder(uint16_t node_id)
{
  uip_lladdr_t lladdr;
  uip_ipaddr_t lladdr_ip;
  memset(&lladdr, 0, sizeof(lladdr));
  for(uint8_t i = 0; i < UIP_LLADDR_LEN; i++) {
    lladdr.addr[i] = (i % 2 == 0) ? 0x00 : (uint8_t)node_id;
  }

  uip_ip6addr(&lladdr_ip, 0xfe80, 0, 0, 0, 0, 0, 0, 0);
  uip_ds6_set_addr_iid(&lladdr_ip, &lladdr);
  uip_ds6_nbr_add(&lladdr_ip, &lladdr, 1, NBR_REACHABLE, NBR_TABLE_REASON_ROUTE, NULL);

  uip_ipaddr_copy(&forwarder_ipaddr, &lladdr_ip);
  printf("CSV,FORWARDER,%u\n", (unsigned)node_id);
}

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

static int
parse_payload(const uint8_t *data, uint16_t len, uint32_t *seq_out, uint32_t *t0_out)
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
    *t0_out = (uint32_t)t0;
    return 1;
  }
  return 0;
}

static void
echo_rx_callback(struct simple_udp_connection *c,
                 const uip_ipaddr_t *sender_addr,
                 uint16_t sender_port,
                 const uip_ipaddr_t *receiver_addr,
                 uint16_t receiver_port,
                 const uint8_t *data,
                 uint16_t datalen)
{
  (void)c; (void)sender_addr; (void)sender_port; (void)receiver_addr; (void)receiver_port;

  uint32_t seq = 0;
  uint32_t t0 = 0;
  if(!parse_payload(data, datalen, &seq, &t0)) {
    return;
  }

  uint32_t t_ack = (uint32_t)clock_time();
  uint32_t rtt_ticks = t_ack - t0;

  LOG_INFO("echo rx seq=%lu rtt_ticks=%lu len=%u\n",
           (unsigned long)seq,
           (unsigned long)rtt_ticks,
           (unsigned)datalen);
  printf("CSV,RTT,%lu,%lu,%lu,%lu,%u\n",
         (unsigned long)seq,
         (unsigned long)t0,
         (unsigned long)t_ack,
         (unsigned long)rtt_ticks,
         (unsigned)datalen);
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
      /* Remove from blacklist if trust recovers */
      brpl_blacklist_remove((uint16_t)node_id);
    }

    if(node_id == ATTACKER_NODE_ID) {
      trust_attacker = trust;
      if(trust_attacker < TRUST_SWITCH_THRESHOLD) {
        set_forwarder(RELAY_NODE_ID);
      } else {
        set_forwarder(ATTACKER_NODE_ID);
      }
    }
    if(node_id == RELAY_NODE_ID) {
      trust_relay = trust;
      if(trust_attacker < TRUST_SWITCH_THRESHOLD && trust_relay >= TRUST_SWITCH_THRESHOLD) {
        set_forwarder(RELAY_NODE_ID);
      }
    }
  }
}

PROCESS(sender_process, "UDP sender (sensor)");
AUTOSTART_PROCESSES(&sender_process);

PROCESS_THREAD(sender_process, ev, data)
{
  static struct etimer periodic_timer;
  static struct etimer warmup_timer;
  static struct etimer dis_timer;
  static uint32_t seq;
  static uint8_t last_reachable;
  static uint8_t warmup_done;
  char buf[64];

  (void)ev; (void)data;

  PROCESS_BEGIN();

  /* Root is aaaa::1 as configured by receiver_root.c. */
  uip_ip6addr(&root_ipaddr, 0xaaaa,0,0,0,0,0,0,1);

#ifdef BRPL_MODE
  printf("CSV,BRPL_MODE,%u,1\n", (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1]);
#else
  printf("CSV,BRPL_MODE,%u,0\n", (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1]);
#endif

  serial_line_init();
  brpl_blacklist_init();

  simple_udp_register(&udp_conn, UDP_PORT, NULL, UDP_PORT, echo_rx_callback);
  etimer_set(&periodic_timer, SEND_INTERVAL);
  etimer_set(&dis_timer, 30 * CLOCK_SECOND);
  if(WARMUP_SECONDS > 0) {
    etimer_set(&warmup_timer, WARMUP_SECONDS * CLOCK_SECOND);
  } else {
    etimer_stop(&warmup_timer);
  }
  last_reachable = 0;
  warmup_done = (WARMUP_SECONDS == 0);
  if(warmup_done) {
    LOG_INFO("warmup complete, start sending\n");
  }

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
#if TRUST_ENABLED
  set_forwarder(RELAY_NODE_ID);
#else
  set_forwarder(ATTACKER_NODE_ID);
#endif

  while(1) {
    PROCESS_WAIT_EVENT();

    if(ev == serial_line_event_message && data != NULL) {
      handle_trust_input((const char *)data);
    }

    if(etimer_expired(&warmup_timer)) {
      warmup_done = 1;
      etimer_stop(&warmup_timer);
      LOG_INFO("warmup complete, start sending\n");
    }

    if(!etimer_expired(&periodic_timer)) {
      continue;
    }
    etimer_reset(&periodic_timer);

    uint8_t reachable = NETSTACK_ROUTING.node_is_reachable();
    uint8_t joined = NETSTACK_ROUTING.node_has_joined();
    if(reachable != last_reachable) {
      LOG_INFO("reachable changed: %u -> %u\n",
               (unsigned)last_reachable, (unsigned)reachable);
      last_reachable = reachable;
    }
    if(LOG_INFO_ENABLED) {
      const uip_ipaddr_t *defrt = uip_ds6_defrt_choose();
      int routes = uip_ds6_route_num_routes();
      LOG_INFO("routing state: joined=%d reachable=%u routes=%d defrt=%s",
               joined, (unsigned)reachable, routes, defrt ? "yes" : "no");
      if(defrt) {
        LOG_INFO_(" defrt=");
        LOG_INFO_6ADDR(defrt);
      }
      LOG_INFO_("\n");
    }
    log_preferred_parent();

    if(etimer_expired(&dis_timer) && !NETSTACK_ROUTING.node_has_joined()) {
      LOG_INFO("send DIS (not joined)\n");
      dis_output(NULL);
      etimer_reset(&dis_timer);
    }

    if(!warmup_done) {
      LOG_INFO("warmup in progress\n");
      continue;
    }

    uint32_t t0 = (uint32_t)clock_time();
    seq++;
    snprintf(buf, sizeof(buf), "seq=%lu t0=%lu",
             (unsigned long)seq, (unsigned long)t0);
    simple_udp_sendto(&udp_conn, buf, strlen(buf), &forwarder_ipaddr);
    LOG_INFO("TX id=%u seq=%lu t0=%lu joined=%u\n",
             (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
             (unsigned long)seq,
             (unsigned long)t0,
             (unsigned)joined);
    printf("CSV,TX,%u,%lu,%lu,%u\n",
           (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1],
           (unsigned long)seq,
           (unsigned long)t0,
           (unsigned)joined);
  }

  PROCESS_END();
}
