# Architecture Deep Dive

## System Architecture Overview

```
                         MESH NETWORK TOPOLOGY
                                                    
         Node 1                    Node 2                    Node 3
    ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
    │ MeshSyncNode│◄────────►│ MeshSyncNode│◄────────►│ MeshSyncNode│
    │             │          │             │          │             │
    │  Port 5001  │          │  Port 5002  │          │  Port 5003  │
    └─────────────┘          └─────────────┘          └─────────────┘
         ▲                        ▲                        ▲
         │                        │                        │
         └────────────────────────┴────────────────────────┘
                    All nodes can communicate
                       (mesh connectivity)
```

## Component Interaction Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                      MeshSyncNode                              │
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │                    User API                           │    │
│  │   set(key, val) | get(key) | delete(key)            │    │
│  └────────────────┬─────────────────────────────────────┘    │
│                   │                                           │
│  ┌────────────────▼──────────────────────────────────────┐   │
│  │               State Manager (CRDT)                    │   │
│  │  ┌────────────────────────────────────────────┐      │   │
│  │  │ Data Store (LWW-Register)                  │      │   │
│  │  │ key -> (value, timestamp, node_id)         │      │   │
│  │  └────────────────────────────────────────────┘      │   │
│  │  ┌────────────────────────────────────────────┐      │   │
│  │  │ Tombstones (Deletions)                     │      │   │
│  │  │ key -> (timestamp, node_id)                │      │   │
│  │  └────────────────────────────────────────────┘      │   │
│  │  ┌────────────────────────────────────────────┐      │   │
│  │  │ Vector Clock                                │      │   │
│  │  │ node_id -> sequence_number                  │      │   │
│  │  └────────────────────────────────────────────┘      │   │
│  └───────────────────┬──────────────────────────────────┘   │
│                      │                                       │
│  ┌───────────────────▼──────────────────────────────────┐   │
│  │          Synchronization Logic                       │   │
│  │                                                       │   │
│  │  Sync Loop ──┐    Heartbeat Loop ──┐                │   │
│  │  (10s)       │    (5s)             │                │   │
│  │              ▼                     ▼                │   │
│  └──────────────┬──────────────────────┬───────────────┘   │
│                 │                      │                   │
│  ┌──────────────▼──────────────────────▼───────────────┐   │
│  │            ReliableUDP Protocol                     │   │
│  │                                                      │   │
│  │  ┌──────────────────────────────────────────┐      │   │
│  │  │ Packet Builder/Parser                    │      │   │
│  │  │ [Header: 10 bytes] + [Payload: JSON]     │      │   │
│  │  └──────────────────────────────────────────┘      │   │
│  │  ┌──────────────────────────────────────────┐      │   │
│  │  │ ACK Tracker                              │      │   │
│  │  │ seq -> (packet, time, retries, addr)     │      │   │
│  │  └──────────────────────────────────────────┘      │   │
│  │  ┌──────────────────────────────────────────┐      │   │
│  │  │ Retry Logic (Exponential Backoff)        │      │   │
│  │  └──────────────────────────────────────────┘      │   │
│  └──────────────┬───────────────────────────────────┘   │
│                 │                                       │
│  ┌──────────────▼───────────────────────────────────┐   │
│  │             UDP Socket                           │   │
│  │         (bind to 0.0.0.0:port)                   │   │
│  └──────────────┬───────────────────────────────────┘   │
│                 │                                       │
│  ┌──────────────▼───────────────────────────────────┐   │
│  │          Peer Manager                            │   │
│  │                                                   │   │
│  │  ┌─────────────────────────────────────────┐    │   │
│  │  │ Peer Registry                            │    │   │
│  │  │ node_id -> PeerInfo                      │    │   │
│  │  │   (address, last_seen, version, alive)   │    │   │
│  │  └─────────────────────────────────────────┘    │   │
│  │  ┌─────────────────────────────────────────┐    │   │
│  │  │ Health Monitor (timeout detection)       │    │   │
│  │  └─────────────────────────────────────────┘    │   │
│  │  ┌─────────────────────────────────────────┐    │   │
│  │  │ Bootstrap Peers (seed addresses)         │    │   │
│  │  └─────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────┘
```

## Packet Flow: Reliable Send

```
Node A                                    Node B
  │                                         │
  │  1. send_reliable(data)                │
  ├────┐                                    │
  │    │ Generate seq_num                  │
  │    │ Build packet                      │
  │    │ Add to pending_acks                │
  │◄───┘                                    │
  │                                         │
  │  2. UDP sendto(packet) ────────────────►│
  │                                         │
  │                                    ┌────┤
  │                                    │    │ Verify checksum
  │                                    │    │ Process packet
  │                                    │    │ Add to received_seqs
  │                                    └───►│
  │                                         │
  │  3. ◄───────────────── ACK(seq_num) ───│
  │                                         │
  ├────┐                                    │
  │    │ Remove from pending_acks           │
  │◄───┘                                    │
  │                                         │
  
  If ACK not received:
  │                                         │
  │  Wait timeout (0.5s, 1s, 2s, 4s, 8s)   │
  │                                         │
  │  4. Retry sendto(packet) ──────────────►│
  │                                         │
  │     (up to MAX_RETRIES = 5)            │
```

## State Synchronization Flow

```
Node A wants to sync with Node B:

Node A                                    Node B
  │                                         │
  │  1. SYNC_REQUEST                       │
  │     {node_id, version} ────────────────►│
  │                                         │
  │                                    ┌────┤
  │                                    │    │ Check version
  │                                    │    │ Prepare full state:
  │                                    │    │  - data
  │                                    │    │  - tombstones
  │                                    │    │  - vector_clock
  │                                    └───►│
  │                                         │
  │  2. ◄────────────── SYNC_RESPONSE ─────│
  │     {node_id, state}                    │
  │                                         │
  ├────┐                                    │
  │    │ Merge remote state:               │
  │    │  - Compare timestamps             │
  │    │  - Apply LWW resolution           │
  │    │  - Update vector clock            │
  │    │  - Handle tombstones              │
  │◄───┘                                    │
  │                                         │
  │  State now consistent!                 │
```

## Conflict Resolution: LWW Example

```
Initial State:
  Node A: {}
  Node B: {}

Time t=1000:
  Node A: set('x', 'A')  →  x=(A, 1000, node_a)
  Node B: set('x', 'B')  →  x=(B, 1000, node_b)

Sync at t=1005:
  Node A sends: x=(A, 1000, node_a)
  Node B has:   x=(B, 1000, node_b)

Conflict Resolution:
  Timestamps equal: 1000 == 1000
  Use node_id tiebreaker: 'node_b' > 'node_a' (lexicographic)
  Winner: Node B's value 'B'

After sync:
  Node A: x=(B, 1000, node_b)
  Node B: x=(B, 1000, node_b)
  ✓ Consistent!
```

## Network Partition Scenario

```
Initial: All nodes connected

      Node A ◄─────► Node B ◄─────► Node C
        │                             │
        └─────────────────────────────┘

Partition Occurs (network split):

      Node A ◄─────► Node B         Node C
                                    (isolated)

During Partition:
  - Node A sets x=1
  - Node B syncs with A, gets x=1
  - Node C sets x=2 (doesn't know about A/B)

After Partition Heals:

      Node A ◄─────► Node B ◄─────► Node C
        │                             │
        └─────────────────────────────┘

Sync:
  1. Node C discovers Node A/B
  2. C sends SYNC_REQUEST to A
  3. A sends full state including x=1
  4. C has x=2 with later timestamp
  5. C keeps x=2 (LWW)
  6. C sends SYNC_RESPONSE to A
  7. A merges, adopts x=2
  8. Eventually all nodes have x=2

Result: Convergence achieved!
```

## Thread Model

```
MeshSyncNode runs 5 concurrent threads:

1. Main Thread
   - User interaction
   - API calls (set/get/delete)

2. UDP Receive Thread (reliable_udp.py)
   - Continuously receives packets
   - Validates checksums
   - Sends ACKs
   - Calls packet handlers

3. UDP Retry Thread (reliable_udp.py)
   - Scans pending_acks
   - Retransmits unacknowledged packets
   - Exponential backoff

4. Sync Loop Thread (mesh_node.py)
   - Every sync_interval (10s)
   - Sends SYNC_REQUEST to peers
   - Triggers state synchronization

5. Heartbeat Loop Thread (mesh_node.py)
   - Every heartbeat_interval (5s)
   - Sends HEARTBEAT to all peers
   - Keeps connections alive

6. Discovery Loop Thread (mesh_node.py)
   - Every 30s
   - Sends DISCOVERY to bootstrap peers
   - Propagates peer information

7. Health Check Thread (peer_manager.py)
   - Every heartbeat_interval (5s)
   - Checks peer timeouts
   - Marks dead peers

Synchronization:
  - RLock on CRDTState for state access
  - Lock on pending_acks for ACK tracking
  - RLock on PeerManager for peer registry
```

## Performance Characteristics

### Time Complexity

| Operation | Complexity | Notes |
|-----------|-----------|-------|
| set(key, value) | O(1) | Direct dict insert |
| get(key) | O(1) | Direct dict lookup |
| delete(key) | O(1) | Add tombstone |
| merge_state(remote) | O(n) | n = number of keys |
| send_reliable() | O(1) | Async send |
| sync_with_peer() | O(n) | n = state size |

### Space Complexity

| Component | Space | Notes |
|-----------|-------|-------|
| State data | O(k) | k = number of keys |
| Tombstones | O(d) | d = deleted keys (grows unbounded*) |
| Vector clock | O(n) | n = number of nodes |
| Pending ACKs | O(p) | p = unacked packets (bounded) |
| Peer registry | O(n) | n = number of peers |

*Note: In production, tombstones should be garbage collected after sufficient time

### Network Bandwidth

Per node, per minute (5 peers, 10s sync interval):

- Heartbeats: 5 peers × 6 beats/min × 100 bytes = 3 KB/min
- Syncs: 6 syncs/min × 5 peers × (200 request + 10KB response) ≈ 300 KB/min
- ACKs: Variable, depends on reliability needs
- Total: ~300-500 KB/min baseline

Under heavy write load (10 writes/sec):
- State grows
- Sync payloads increase
- Can reach 1-5 MB/min per node

## Scalability Analysis

### Node Count

Current design scales to:
- **Tested**: 10 nodes
- **Practical**: 20-50 nodes
- **Limit factors**: 
  - O(n²) message complexity (all-to-all sync)
  - Vector clock grows with nodes
  - Bootstrap discovery overhead

For >50 nodes, consider:
- Hierarchical clustering
- Gossip with sampling
- Consistent hashing

### State Size

- **Optimal**: < 1000 keys, < 1 MB total
- **Maximum**: Limited by UDP packet size (64 KB per packet)
- **Large states**: Implement delta sync or compression

### Convergence Time

```
T_convergence ≈ sync_interval × network_diameter + retransmission_delays

Example (5 nodes, mesh topology):
  - sync_interval = 10s
  - diameter = 2 hops
  - Expected: 20-30s worst case
  - With 30% loss: 30-60s
```

## Failure Modes & Recovery

| Failure Mode | Detection | Recovery |
|--------------|-----------|----------|
| Packet Loss | ACK timeout | Automatic retransmission |
| Node Crash | Heartbeat timeout (15s) | Mark dead, stop syncing |
| Network Partition | Heartbeat timeout | Automatic reconciliation on heal |
| Clock Skew | Not detected | Use NTP in production |
| State Corruption | Checksum | Reject packet |
| Byzantine Node | Not handled | Out of scope (require BFT) |

## Future Optimizations

1. **Delta Sync**: Send only changed keys
2. **Merkle Trees**: Efficient difference detection
3. **Bloom Filters**: Quick "do you have X?" checks
4. **Compression**: Gzip large state transfers
5. **Multicast**: Efficient broadcast for discovery
6. **Vector Pruning**: Compact old vector clock entries
7. **Tombstone GC**: Remove old tombstones after time threshold
