/*
 * receiver_root.c
 * - RPL root + UDP receiver/logger for Contiki-NG (Cooja)
 *
 * CSV output:
 * CSV,RX,src_ip,seq,t_recv,len
 *
 * Sensor payload expected: "seq=<n> t0=<clock>"
 */

#include "contiki.h"
#include "sys/log.h"

#include "net/ipv6/uip.h"
#include "net/ipv6/uiplib.h"
#include "net/ipv6/uip-ds6.h"
#include "net/routing/routing.h"
#include "net/ipv6/uip-sr.h"
#include "net/ipv6/simple-udp.h"
#include "net/ipv6/uip-nd6.h"
#include "net/linkaddr.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define LOG_MODULE "RECVROOT"
#define LOG_LEVEL LOG_LEVEL_INFO

#define UDP_PORT 8765
#define ROOT_START_RETRY_SECONDS 2
#define ROOT_START_RETRY (ROOT_START_RETRY_SECONDS * CLOCK_SECOND)

/* Trust calculation is delegated to external trust_engine */

static struct simple_udp_connection udp_conn;
static struct etimer root_timer;
static uip_ipaddr_t root_ipaddr;
static uint8_t root_started;


static void
set_root_address_and_prefix(void)
{
  uip_ipaddr_t prefix;

  /* Root global address: aaaa::1 */
  uip_ip6addr(&root_ipaddr, 0xaaaa,0,0,0,0,0,0,1);
  uip_ds6_addr_t *addr = uip_ds6_addr_add(&root_ipaddr, 0, ADDR_MANUAL);
  if(addr != NULL) {
    addr->state = ADDR_PREFERRED;
  }

  /* Prefix: aaaa::/64 */
  uip_ip6addr(&prefix, 0xaaaa,0,0,0,0,0,0,0);
  uip_ds6_prefix_add(&prefix, 64,
                     1, /* advertise */
                     UIP_ND6_RA_FLAG_ONLINK | UIP_ND6_RA_FLAG_AUTONOMOUS,
                     UIP_ND6_INFINITE_LIFETIME,
                     UIP_ND6_INFINITE_LIFETIME);

  LOG_INFO("root ip = ");
  LOG_INFO_6ADDR(&root_ipaddr);
  LOG_INFO_("\n");
}

static int
root_start_if_ready(void)
{
  uip_ds6_addr_t *addr = uip_ds6_addr_lookup(&root_ipaddr);
  if(addr == NULL || addr->state != ADDR_PREFERRED) {
    return 0;
  }
  if(NETSTACK_ROUTING.root_start() == 0) {
    LOG_INFO("root_start() ok\n");
    if(uip_sr_update_node(NULL, &root_ipaddr, NULL, UIP_SR_INFINITE_LIFETIME) == NULL) {
      LOG_ERR("failed to register SR root node\n");
    }
    root_started = 1;
    return 1;
  }
  LOG_ERR("root_start() failed\n");
  return 0;
}

static int
parse_payload(const uint8_t *data, uint16_t len, uint32_t *seq_out, uint32_t *t_out)
{
  char buf[96];
  if(len >= sizeof(buf)) len = sizeof(buf) - 1;
  memcpy(buf, data, len);
  buf[len] = '\0';

  unsigned long seq = 0, t = 0;
  int matched = sscanf(buf, "seq=%lu t0=%lu", &seq, &t);
  if(matched == 2) {
    *seq_out = (uint32_t)seq;
    *t_out   = (uint32_t)t;
    return 1;
  }
  return 0;
}

/* Not needed anymore - trust is calculated externally
static uint16_t
node_id_from_addr(const uip_ipaddr_t *addr)
{
  return (uint16_t)uip_ntohs(addr->u16[7]);
}
*/

/*
 * Trust calculation is now handled by external trust_engine.
 * The root only reports packet reception via CSV,RX output.
 * Trust values are injected back from trust_engine via TRUST input.
 */

static void
udp_rx_callback(struct simple_udp_connection *c,
                const uip_ipaddr_t *sender_addr,
                uint16_t sender_port,
                const uip_ipaddr_t *receiver_addr,
                uint16_t receiver_port,
                const uint8_t *data,
                uint16_t datalen)
{
  (void)c; (void)receiver_addr; (void)receiver_port;
  (void)sender_port;

  uint32_t seq = 0, t0 = 0;
  uint32_t t_recv = (uint32_t)clock_time();

  int ok = parse_payload(data, datalen, &seq, &t0);
  if(ok) {
    char buf[64];
    uip_ipaddr_t reply_addr;
    uip_ipaddr_copy(&reply_addr, sender_addr);
    if(uip_sr_update_node(NULL, &reply_addr, &root_ipaddr, UIP_SR_INFINITE_LIFETIME) == NULL) {
      LOG_WARN("failed to update SR route for sender\n");
    }
    /* Trust calculation delegated to external trust_engine */
    printf("CSV,RX,");
    uiplib_ipaddr_print(&reply_addr);
    printf(",%lu,%lu,%u\n",
           (unsigned long)seq,
           (unsigned long)t_recv,
           (unsigned)datalen);

    snprintf(buf, sizeof(buf), "seq=%lu t0=%lu",
             (unsigned long)seq, (unsigned long)t0);
    simple_udp_sendto(&udp_conn, buf, strlen(buf), &reply_addr);
    LOG_INFO("echo sent to ");
    LOG_INFO_6ADDR(&reply_addr);
    LOG_INFO_(" seq=%lu\n", (unsigned long)seq);
  } else {
    LOG_WARN("payload parse failed\n");
  }
}

PROCESS(receiver_root_process, "Receiver Root (RPL root + UDP logger)");
AUTOSTART_PROCESSES(&receiver_root_process);

PROCESS_THREAD(receiver_root_process, ev, data)
{
  (void)ev; (void)data;

  PROCESS_BEGIN();

  LOG_INFO("boot\n");
#ifdef BRPL_MODE
  printf("CSV,BRPL_MODE,%u,1\n", (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1]);
#else
  printf("CSV,BRPL_MODE,%u,0\n", (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1]);
#endif

  /* Establish RPL root and prefix so sensors can auto-configure. */
  set_root_address_and_prefix();
  root_started = 0;
  etimer_set(&root_timer, ROOT_START_RETRY);

  /* UDP receiver for sensor traffic. */
  simple_udp_register(&udp_conn, UDP_PORT, NULL, UDP_PORT, udp_rx_callback);
  LOG_INFO("UDP receiver listening on %u\n", UDP_PORT);

  while(1) {
    PROCESS_WAIT_EVENT();
    if(!root_started && etimer_expired(&root_timer)) {
      if(!root_start_if_ready()) {
        etimer_reset(&root_timer);
      }
    }
  }

  PROCESS_END();
}
