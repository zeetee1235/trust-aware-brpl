#include "brpl-trust.h"
#include "../project-conf.h"
#include "net/linkaddr.h"

#include <stdio.h>

static uint16_t trust_values[TRUST_MAX_NODES];
static uint8_t trust_valid[TRUST_MAX_NODES];

uint16_t
brpl_trust_get(uint16_t node_id)
{
  if(node_id < TRUST_MAX_NODES && trust_valid[node_id]) {
    return trust_values[node_id];
  }
  return TRUST_SCALE;
}

int
brpl_trust_is_allowed(uint16_t node_id)
{
  uint16_t trust = brpl_trust_get(node_id);
  return trust >= TRUST_PARENT_MIN;
}

/* Trust override function for external trust value injection */
void brpl_trust_override(uint16_t node_id, uint16_t trust)
{
  if(node_id >= TRUST_MAX_NODES) {
    return;
  }

  trust_values[node_id] = trust;
  trust_valid[node_id] = 1;

#if CSV_VERBOSE_LOGGING
  {
    uint16_t self_id = (uint16_t)linkaddr_node_addr.u8[LINKADDR_SIZE - 1];
    printf("CSV,TRUST_SET,%u,%u,%u\n", self_id, node_id, trust);
  }
#endif

}
