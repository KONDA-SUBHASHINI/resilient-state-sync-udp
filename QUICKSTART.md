# Quick Start Guide

Get up and running with the mesh sync system in 5 minutes!

## Prerequisites

- Python 3.7 or higher
- Multiple terminal windows (or tmux/screen)
- No external dependencies needed!

## Installation

```bash
# Clone or download the project
cd mesh-sync

# Make scripts executable (Linux/Mac)
chmod +x *.py

# Verify Python version
python3 --version
```

## Quick Test: 2-Node Cluster

### Terminal 1: Start First Node

```bash
python3 example_basic.py node1 5001
```

You should see:
```
Node node1 started on port 5001
Commands: set <key> <value>, get <key>, delete <key>, list, status, quit
[node1]>
```

### Terminal 2: Start Second Node (Connected)

```bash
python3 example_basic.py node2 5002 localhost 5001
```

Output:
```
Added bootstrap peer: localhost:5001
Node node2 started on port 5002
...
[node2]>
```

### Try It Out!

**In Terminal 1 (node1):**
```bash
[node1]> set message "Hello from node1"
Set message = Hello from node1

[node1]> set counter 42
Set counter = 42

[node1]> list
Current data:
  counter = 42
  message = Hello from node1
```

**In Terminal 2 (node2):**

Wait ~10 seconds for automatic sync, then:

```bash
[node2]> list
Current data:
  counter = 42
  message = Hello from node1

[node2]> get message
message = Hello from node1
```

🎉 **Success!** Node2 automatically received data from Node1!

### Test Bidirectional Sync

**In Terminal 2 (node2):**
```bash
[node2]> set response "Hello from node2"
Set response = Hello from node2
```

**Wait ~10 seconds, then in Terminal 1 (node1):**
```bash
[node1]> list
Current data:
  counter = 42
  message = Hello from node1
  response = Hello from node2
```

Both nodes now have all data!

### Test Conflict Resolution

**In Terminal 1:**
```bash
[node1]> set shared "Version A"
```

**In Terminal 2 (immediately after):**
```bash
[node2]> set shared "Version B"
```

**Wait for sync, then check both:**
```bash
[node1]> get shared
[node2]> get shared
```

Both will show the same value (the "winner" based on timestamp and node_id)!

### View Status

```bash
[node1]> status
Node Status:
  Node ID: node1
  Port: 5001
  State Version: 5
  Data Keys: 3
  Peers: 1/1 alive
  Pending ACKs: 0
```

## Quick Test: Reliability Under Packet Loss

Run the automated reliability tests:

```bash
python3 test_reliability.py
```

This will:
1. Start 3 nodes
2. Simulate 30% packet loss
3. Write different data to each node
4. Verify they all converge
5. Test network partition recovery

Expected output:
```
TEST: Convergence Under Packet Loss
====================================
Started node1
Started node2
Started node3

Phase 1: Writing different data to each node
...
Phase 2: Checking convergence

node1 data:
  key1 = value1_from_node1
  key2 = value2_from_node2
  key3 = value3_from_node3
  shared = node2_version

✓ SUCCESS: All nodes have the same keys
✓ LWW conflict resolution working: shared = node2_version
```

## Quick Test: Multi-Node Simulation

Watch 5 nodes sync automatically:

```bash
python3 test_simulation.py
```

This starts 5 nodes that:
- Discover each other automatically
- Perform random set/delete operations
- Display cluster state every 10 seconds
- Show convergence status

Example output:
```
CLUSTER STATE - 14:23:45
================================================================================
Key            node1               node2               node3               ...
--------------------------------------------------------------------------------
key_1          node2_1738162980    node2_1738162980    node2_1738162980    ...
key_3          node1_1738162982    node1_1738162982    node1_1738162982    ...
key_7          node5_1738162975    node5_1738162975    node5_1738162975    ...
--------------------------------------------------------------------------------

Node Statistics:
  node1    | Version:   12 | Keys:   8 | Peers: 4/4 | Pending:   0 | Ops:   5
  node2    | Version:   12 | Keys:   8 | Peers: 4/4 | Pending:   1 | Ops:   4
  ...

✓ CONVERGED: All nodes have the same keys
✓ FULLY CONSISTENT: All values match across nodes
```

Press Ctrl+C to stop.

## Troubleshooting

### Problem: "Address already in use"

**Solution**: Port is taken. Use a different port:
```bash
python3 example_basic.py node1 5101  # Instead of 5001
```

### Problem: Nodes don't sync

**Checklist**:
1. ✓ Did you add bootstrap peer? (`python3 example_basic.py node2 5002 localhost 5001`)
2. ✓ Wait at least 10 seconds (default sync interval)
3. ✓ Check firewall (allow UDP on your ports)
4. ✓ Use `status` command to verify peers are alive

**Debug**:
```bash
# Enable debug logging
python3 -c "import logging; logging.basicConfig(level=logging.DEBUG)"
```

### Problem: "Connection refused" or "No route to host"

**Solution**: 
- Use `localhost` or `127.0.0.1` for local testing
- For network testing, use actual IP addresses
- Check firewalls allow UDP traffic

## Next Steps

1. **Read the Architecture**: Check `ARCHITECTURE.md` for system design details
2. **Explore the Code**: Start with `mesh_node.py` for the main logic
3. **Customize**: Adjust `sync_interval`, `heartbeat_interval` in node creation
4. **Experiment**: Try creating 4-5 nodes and see how they form a mesh

## Common Commands Reference

```bash
# Start a node
python3 example_basic.py <node_id> <port> [bootstrap_host] [bootstrap_port]

# Interactive commands once running:
set <key> <value>     # Set a value
get <key>             # Get a value
delete <key>          # Delete a key
list                  # Show all data
status                # Show node statistics
quit                  # Stop node
```

## Performance Tips

For faster sync:
```python
node = MeshSyncNode(
    node_id='node1',
    port=5001,
    sync_interval=3.0,      # Sync every 3s instead of 10s
    heartbeat_interval=2.0  # Heartbeat every 2s instead of 5s
)
```

For lower network usage:
```python
node = MeshSyncNode(
    node_id='node1', 
    port=5001,
    sync_interval=30.0,     # Sync every 30s
    heartbeat_interval=10.0 # Heartbeat every 10s
)
```

## What to Try Next

1. **Kill a node** and watch others detect the failure
2. **Restart a killed node** and watch it catch up
3. **Write conflicting data** and observe LWW resolution
4. **Monitor network traffic** with Wireshark (filter: udp.port == 5001)
5. **Scale up** to 10+ nodes and measure convergence time

Happy meshing! 🚀
