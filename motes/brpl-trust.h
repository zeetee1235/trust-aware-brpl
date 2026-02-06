#ifndef BRPL_TRUST_H_
#define BRPL_TRUST_H_

#include <stdint.h>

#ifndef TRUST_MAX_NODES
#define TRUST_MAX_NODES 256
#endif

#ifndef TRUST_SCALE
#define TRUST_SCALE 1000
#endif

#ifndef TRUST_PARENT_MIN
#define TRUST_PARENT_MIN 700
#endif

void brpl_trust_override(uint16_t node_id, uint16_t trust);
uint16_t brpl_trust_get(uint16_t node_id);
int brpl_trust_is_allowed(uint16_t node_id);

#endif /* BRPL_TRUST_H_ */
