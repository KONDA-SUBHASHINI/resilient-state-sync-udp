#!/usr/bin/env python3
"""
Multi-Node Simulation
Simulates multiple nodes with automatic data generation and visualization
"""
import time
import logging
import random
import threading
from mesh_node import MeshSyncNode

# Configure logging
logging.basicConfig(
    level=logging.WARNING,  # Reduce noise
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class NodeSimulator:
    """Simulates a node with automatic data generation"""
    
    def __init__(self, node: MeshSyncNode):
        self.node = node
        self.running = False
        self.thread = None
        self.operations_count = 0
    
    def start(self):
        """Start automatic operations"""
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Stop automatic operations"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
    
    def _run(self):
        """Run loop with random operations"""
        while self.running:
            time.sleep(random.uniform(3, 8))
            
            try:
                # Random operation
                op = random.choice(['set', 'delete'])
                
                if op == 'set':
                    key = f"key_{random.randint(1, 10)}"
                    value = f"{self.node.node_id}_{int(time.time())}"
                    self.node.set(key, value)
                    self.operations_count += 1
                    logger.info(f"[{self.node.node_id}] AUTO SET: {key} = {value}")
                
                elif op == 'delete' and random.random() < 0.3:  # Delete less frequently
                    data = self.node.get_all_data()
                    if data:
                        key = random.choice(list(data.keys()))
                        self.node.delete(key)
                        self.operations_count += 1
                        logger.info(f"[{self.node.node_id}] AUTO DELETE: {key}")
            
            except Exception as e:
                logger.error(f"Simulator error: {e}")


def print_cluster_state(nodes, simulators):
    """Print the current state of all nodes"""
    print("\n" + "="*80)
    print(f"CLUSTER STATE - {time.strftime('%H:%M:%S')}")
    print("="*80)
    
    all_keys = set()
    for node in nodes:
        all_keys.update(node.get_all_data().keys())
    
    # Header
    print(f"{'Key':<15}", end='')
    for node in nodes:
        print(f"{node.node_id:<20}", end='')
    print()
    print("-" * 80)
    
    # Data rows
    for key in sorted(all_keys):
        print(f"{key:<15}", end='')
        for node in nodes:
            value = node.get(key)
            display = str(value)[:18] if value else '---'
            print(f"{display:<20}", end='')
        print()
    
    print("-" * 80)
    
    # Statistics
    print("\nNode Statistics:")
    for i, node in enumerate(nodes):
        status = node.get_status()
        sim = simulators[i]
        print(f"  {node.node_id:8} | Version: {status['state_version']:4} | "
              f"Keys: {status['data_keys']:3} | Peers: {status['peers']['alive_peers']}/{status['peers']['total_peers']} | "
              f"Pending: {status['pending_acks']:3} | Ops: {sim.operations_count:3}")
    
    # Convergence check
    data_sets = [node.get_all_data() for node in nodes]
    key_sets = [set(d.keys()) for d in data_sets]
    
    if len(set(map(frozenset, key_sets))) == 1:
        print("\n✓ CONVERGED: All nodes have the same keys")
        
        # Check if values also match
        all_match = True
        for key in all_keys:
            values = [d.get(key) for d in data_sets]
            if len(set(values)) > 1:
                all_match = False
                break
        
        if all_match:
            print("✓ FULLY CONSISTENT: All values match across nodes")
        else:
            print("⚠ KEYS MATCH but some values differ (convergence in progress)")
    else:
        print("\n⚠ NOT CONVERGED: Nodes have different keys")
        for i, keys in enumerate(key_sets):
            print(f"    {nodes[i].node_id}: {len(keys)} keys")


def main():
    """Run multi-node simulation"""
    print("="*80)
    print("MESH SYNC - MULTI-NODE SIMULATION")
    print("="*80)
    print("\nStarting 5-node cluster with automatic operations...")
    print("Press Ctrl+C to stop\n")
    
    # Create 5 nodes
    num_nodes = 5
    base_port = 8000
    nodes = []
    
    for i in range(num_nodes):
        node_id = f"node{i+1}"
        port = base_port + i
        node = MeshSyncNode(node_id, port, sync_interval=3.0, heartbeat_interval=2.0)
        nodes.append(node)
    
    # Set up mesh topology (each node knows about 2-3 others)
    nodes[1].add_bootstrap_peer('localhost', base_port)
    nodes[2].add_bootstrap_peer('localhost', base_port)
    nodes[2].add_bootstrap_peer('localhost', base_port + 1)
    nodes[3].add_bootstrap_peer('localhost', base_port + 1)
    nodes[3].add_bootstrap_peer('localhost', base_port + 2)
    nodes[4].add_bootstrap_peer('localhost', base_port + 2)
    nodes[4].add_bootstrap_peer('localhost', base_port + 3)
    
    # Start all nodes
    for node in nodes:
        node.start()
        print(f"Started {node.node_id} on port {node.port}")
    
    print("\nWaiting for nodes to discover each other...")
    time.sleep(5)
    
    # Create simulators
    simulators = []
    for node in nodes:
        sim = NodeSimulator(node)
        sim.start()
        simulators.append(sim)
    
    print("Simulators started - nodes will perform random operations\n")
    
    try:
        iteration = 0
        while True:
            time.sleep(10)
            iteration += 1
            
            print_cluster_state(nodes, simulators)
            
            if iteration % 3 == 0:
                print("\n>>> Monitoring continues... (Ctrl+C to stop)")
    
    except KeyboardInterrupt:
        print("\n\nStopping simulation...")
    
    finally:
        # Stop simulators
        for sim in simulators:
            sim.stop()
        
        # Stop nodes
        for node in nodes:
            node.stop()
        
        print("\nFinal state:")
        print_cluster_state(nodes, simulators)
        
        print("\nSimulation completed!")


if __name__ == '__main__':
    main()
