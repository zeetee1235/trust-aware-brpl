/*
 * brpl-blacklist.h
 * - Blacklist management for trust-aware BRPL
 * - Filters packets from/to blacklisted nodes at network layer
 */

#ifndef BRPL_BLACKLIST_H_
#define BRPL_BLACKLIST_H_

#include "net/linkaddr.h"
#include "net/ipv6/uip.h"
#include <stdint.h>

#ifndef BLACKLIST_MAX_NODES
#define BLACKLIST_MAX_NODES 32
#endif

/* Blacklist threshold - nodes below this trust are blacklisted */
#ifndef BLACKLIST_TRUST_THRESHOLD
#define BLACKLIST_TRUST_THRESHOLD 700
#endif

/**
 * Initialize blacklist module
 */
void brpl_blacklist_init(void);

/**
 * Add a node to the blacklist
 * @param node_id Node ID (last byte of link-layer address)
 * @return 1 if added, 0 if already in list or list full
 */
int brpl_blacklist_add(uint16_t node_id);

/**
 * Remove a node from the blacklist
 * @param node_id Node ID to remove
 * @return 1 if removed, 0 if not found
 */
int brpl_blacklist_remove(uint16_t node_id);

/**
 * Check if a node is blacklisted
 * @param node_id Node ID to check
 * @return 1 if blacklisted, 0 otherwise
 */
int brpl_blacklist_contains(uint16_t node_id);

/**
 * Check if an IPv6 address is blacklisted
 * @param ipaddr IPv6 address to check
 * @return 1 if blacklisted, 0 otherwise
 */
int brpl_blacklist_contains_ipaddr(const uip_ipaddr_t *ipaddr);

/**
 * Check if a link-layer address is blacklisted
 * @param lladdr Link-layer address to check
 * @return 1 if blacklisted, 0 otherwise
 */
int brpl_blacklist_contains_lladdr(const linkaddr_t *lladdr);

/**
 * Clear all entries from the blacklist
 */
void brpl_blacklist_clear(void);

/**
 * Get number of blacklisted nodes
 * @return Count of blacklisted nodes
 */
uint8_t brpl_blacklist_count(void);

/**
 * Print blacklist contents
 */
void brpl_blacklist_print(void);

/**
 * Packet filter hook - call this before forwarding
 * @param dest_ipaddr Destination IPv6 address
 * @param src_ipaddr Source IPv6 address (can be NULL)
 * @return 1 if packet should be dropped, 0 if allowed
 */
int brpl_blacklist_should_drop_packet(const uip_ipaddr_t *dest_ipaddr,
                                      const uip_ipaddr_t *src_ipaddr);

#endif /* BRPL_BLACKLIST_H_ */
