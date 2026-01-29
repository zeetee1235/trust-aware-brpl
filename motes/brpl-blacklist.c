/*
 * brpl-blacklist.c
 * - Blacklist implementation for trust-aware BRPL
 * - Network-layer packet filtering based on trust
 */

#include "brpl-blacklist.h"
#include "sys/log.h"
#include <string.h>

#define LOG_MODULE "BLACKLIST"
#define LOG_LEVEL LOG_LEVEL_INFO

static uint16_t blacklist[BLACKLIST_MAX_NODES];
static uint8_t blacklist_size = 0;

/*---------------------------------------------------------------------------*/
void
brpl_blacklist_init(void)
{
  memset(blacklist, 0, sizeof(blacklist));
  blacklist_size = 0;
  LOG_INFO("initialized (max %d nodes)\n", BLACKLIST_MAX_NODES);
#if CSV_VERBOSE_LOGGING
  printf("CSV,BLACKLIST_INIT,%d\n", BLACKLIST_MAX_NODES);
#endif
}
/*---------------------------------------------------------------------------*/
int
brpl_blacklist_add(uint16_t node_id)
{
  /* Check if already in list */
  for(uint8_t i = 0; i < blacklist_size; i++) {
    if(blacklist[i] == node_id) {
      return 0; /* Already blacklisted */
    }
  }
  
  /* Add if space available */
  if(blacklist_size < BLACKLIST_MAX_NODES) {
    blacklist[blacklist_size++] = node_id;
    LOG_WARN("added node %u (total: %u)\n", node_id, blacklist_size);
#if CSV_VERBOSE_LOGGING
    printf("CSV,BLACKLIST_ADD,%u,%u\n", node_id, blacklist_size);
#endif
    return 1;
  }
  
  LOG_WARN("failed to add node %u (list full)\n", node_id);
  return 0;
}
/*---------------------------------------------------------------------------*/
int
brpl_blacklist_remove(uint16_t node_id)
{
  for(uint8_t i = 0; i < blacklist_size; i++) {
    if(blacklist[i] == node_id) {
      /* Shift remaining entries */
      for(uint8_t j = i; j < blacklist_size - 1; j++) {
        blacklist[j] = blacklist[j + 1];
      }
      blacklist_size--;
      LOG_INFO("removed node %u (total: %u)\n", node_id, blacklist_size);
#if CSV_VERBOSE_LOGGING
      printf("CSV,BLACKLIST_REMOVE,%u,%u\n", node_id, blacklist_size);
#endif
      return 1;
    }
  }
  return 0;
}
/*---------------------------------------------------------------------------*/
int
brpl_blacklist_contains(uint16_t node_id)
{
  for(uint8_t i = 0; i < blacklist_size; i++) {
    if(blacklist[i] == node_id) {
      return 1;
    }
  }
  return 0;
}
/*---------------------------------------------------------------------------*/
static uint16_t
extract_node_id_from_ipaddr(const uip_ipaddr_t *ipaddr)
{
  if(ipaddr == NULL) {
    return 0xFFFF;
  }
  
  /* For link-local addresses (fe80::201:1:1:X), extract last byte */
  /* For global addresses, extract from IID */
  uint16_t node_id = ipaddr->u8[15];
  
  return node_id;
}
/*---------------------------------------------------------------------------*/
int
brpl_blacklist_contains_ipaddr(const uip_ipaddr_t *ipaddr)
{
  if(ipaddr == NULL) {
    return 0;
  }
  
  uint16_t node_id = extract_node_id_from_ipaddr(ipaddr);
  if(node_id == 0xFFFF) {
    return 0;
  }
  
  return brpl_blacklist_contains(node_id);
}
/*---------------------------------------------------------------------------*/
int
brpl_blacklist_contains_lladdr(const linkaddr_t *lladdr)
{
  if(lladdr == NULL) {
    return 0;
  }
  
  uint16_t node_id = lladdr->u8[LINKADDR_SIZE - 1];
  return brpl_blacklist_contains(node_id);
}
/*---------------------------------------------------------------------------*/
void
brpl_blacklist_clear(void)
{
  uint8_t old_size = blacklist_size;
  memset(blacklist, 0, sizeof(blacklist));
  blacklist_size = 0;
  LOG_INFO("cleared (%u entries removed)\n", old_size);
  printf("CSV,BLACKLIST_CLEAR,%u\n", old_size);
}
/*---------------------------------------------------------------------------*/
uint8_t
brpl_blacklist_count(void)
{
  return blacklist_size;
}
/*---------------------------------------------------------------------------*/
void
brpl_blacklist_print(void)
{
  if(blacklist_size == 0) {
    LOG_INFO("empty\n");
    return;
  }
  
  LOG_INFO("contains %u nodes:", blacklist_size);
  for(uint8_t i = 0; i < blacklist_size; i++) {
    printf(" %u", blacklist[i]);
  }
  printf("\n");
}
/*---------------------------------------------------------------------------*/
int
brpl_blacklist_should_drop_packet(const uip_ipaddr_t *dest_ipaddr,
                                  const uip_ipaddr_t *src_ipaddr)
{
  /* Check destination */
  if(dest_ipaddr != NULL && brpl_blacklist_contains_ipaddr(dest_ipaddr)) {
    LOG_DBG("drop: dest blacklisted\n");
#if CSV_VERBOSE_LOGGING
    printf("CSV,PKT_DROP_DEST,%u\n", extract_node_id_from_ipaddr(dest_ipaddr));
#endif
    return 1;
  }
  
  /* Check source */
  if(src_ipaddr != NULL && brpl_blacklist_contains_ipaddr(src_ipaddr)) {
    LOG_DBG("drop: src blacklisted\n");
#if CSV_VERBOSE_LOGGING
    printf("CSV,PKT_DROP_SRC,%u\n", extract_node_id_from_ipaddr(src_ipaddr));
#endif
    return 1;
  }
  
  return 0;
}
/*---------------------------------------------------------------------------*/
