#!/usr/bin/env python3
"""
Test: Network Reliability Simulation
Tests the mesh sync system under packet loss and high latency
"""
import time
import logging
import random
import sys
from mesh_node import MeshSyncNode

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


class UnreliableNetworkSimulator:
    """
    Simulates network unreliability by randomly dropping packets
    This wraps the socket sendto method
    """
    def __init__(self, original_socket, packet_loss_rate=0.0, latency_ms=0):
        self.original_socket = original_socket
        self.packet_loss_rate = packet_loss_rate
        self.latency_ms = latency_ms
        self.original_sendto = original_socket.sendto
        self.packets_sent = 0
        self.packets_dropped = 0
        
        # Monkey patch the socket
        original_socket.sendto = self._unreliable_sendto
    
    def _unreliable_sendto(self, data, addr):
        """Simulate unreliable network"""
        self.packets_sent += 1
        
        # Simulate packet loss
        if random.random() < self.packet_loss_rate:
            self.packets_dropped += 1
            logger.debug(f"DROPPED packet to {addr} (loss rate: {self.packet_loss_rate})")
            return len(data)  # Pretend it was sent
        
        # Simulate latency (simplified - doesn't actually delay)
        if self.latency_ms > 0:
            # In a real implementation, you'd queue and delay
            # For testing purposes, we just log it
            pass
        
        return self.original_sendto(data, addr)
    
    def get_stats(self):
        """Get network statistics"""
        return {
            'packets_sent': self.packets_sent,
            'packets_dropped': self.packets_dropped,
            'drop_rate': self.packets_dropped / max(1, self.packets_sent)
        }


def test_convergence_under_packet_loss():
    """
    Test that nodes converge to the same state despite packet loss
    """
    print("\n" + "="*60)
    print("TEST: Convergence Under Packet Loss")
    print("="*60)
    
    # Create 3 nodes
    nodes = []
    for i in range(3):
        node_id = f"node{i+1}"
        port = 6000 + i
        node = MeshSyncNode(node_id, port, sync_interval=2.0, heartbeat_interval=1.0)
        nodes.append(node)
    
    # Set up bootstrap relationships (mesh topology)
    nodes[1].add_bootstrap_peer('localhost', 6000)  # node2 -> node1
    nodes[2].add_bootstrap_peer('localhost', 6000)  # node3 -> node1
    nodes[2].add_bootstrap_peer('localhost', 6001)  # node3 -> node2
    
    # Add network unreliability (30% packet loss)
    simulators = []
    for node in nodes:
        sim = UnreliableNetworkSimulator(node.udp.socket, packet_loss_rate=0.3)
        simulators.append(sim)
    
    # Start all nodes
    for node in nodes:
        node.start()
        print(f"Started {node.node_id}")
    
    time.sleep(2)
    
    # Each node writes different data
    print("\nPhase 1: Writing different data to each node")
    nodes[0].set('key1', 'value1_from_node1')
    nodes[0].set('shared', 'node1_version')
    
    nodes[1].set('key2', 'value2_from_node2')
    nodes[1].set('shared', 'node2_version')
    
    nodes[2].set('key3', 'value3_from_node3')
    nodes[2].set('shared', 'node3_version')
    
    print("\nWaiting for convergence (20 seconds)...")
    for i in range(20):
        time.sleep(1)
        sys.stdout.write('.')
        sys.stdout.flush()
    print()
    
    # Check convergence
    print("\nPhase 2: Checking convergence")
    for i, node in enumerate(nodes):
        data = node.get_all_data()
        print(f"\n{node.node_id} data:")
        for k, v in sorted(data.items()):
            print(f"  {k} = {v}")
        
        status = node.get_status()
        print(f"  Version: {status['state_version']}, Peers: {status['peers']['alive_peers']}")
        
        net_stats = simulators[i].get_stats()
        print(f"  Network: {net_stats['packets_sent']} sent, {net_stats['packets_dropped']} dropped ({net_stats['drop_rate']:.1%})")
    
    # Verify all nodes have the same keys
    print("\nConvergence Check:")
    data_sets = [set(node.get_all_data().keys()) for node in nodes]
    
    if len(set(map(frozenset, data_sets))) == 1:
        print("✓ SUCCESS: All nodes have the same keys")
    else:
        print("✗ FAILURE: Nodes have different keys")
        for i, keys in enumerate(data_sets):
            print(f"  {nodes[i].node_id}: {keys}")
    
    # Check for 'shared' key - should have the same value (LWW)
    shared_values = [node.get('shared') for node in nodes]
    if len(set(shared_values)) == 1:
        print(f"✓ LWW conflict resolution working: shared = {shared_values[0]}")
    else:
        print(f"✗ LWW conflict resolution issue: {shared_values}")
    
    # Cleanup
    for node in nodes:
        node.stop()
    
    print("\nTest completed!")


def test_partition_recovery():
    """
    Test that nodes recover after a network partition
    """
    print("\n" + "="*60)
    print("TEST: Network Partition Recovery")
    print("="*60)
    
    # Create 2 nodes
    node1 = MeshSyncNode('node1', 7000, sync_interval=2.0)
    node2 = MeshSyncNode('node2', 7001, sync_interval=2.0)
    
    node2.add_bootstrap_peer('localhost', 7000)
    
    # Start both nodes
    node1.start()
    node2.start()
    print("Started node1 and node2")
    
    time.sleep(3)
    
    # Write data before partition
    print("\nPhase 1: Before partition")
    node1.set('before', 'partition_data')
    time.sleep(2)
    
    print(f"node1 data: {node1.get_all_data()}")
    print(f"node2 data: {node2.get_all_data()}")
    
    # Simulate partition (100% packet loss)
    print("\nPhase 2: Simulating network partition (100% packet loss)")
    sim1 = UnreliableNetworkSimulator(node1.udp.socket, packet_loss_rate=1.0)
    sim2 = UnreliableNetworkSimulator(node2.udp.socket, packet_loss_rate=1.0)
    
    # Write different data during partition
    node1.set('partition1', 'data_from_node1')
    node2.set('partition2', 'data_from_node2')
    
    time.sleep(3)
    
    print(f"node1 data (partitioned): {node1.get_all_data()}")
    print(f"node2 data (partitioned): {node2.get_all_data()}")
    
    # Heal partition
    print("\nPhase 3: Healing partition (removing packet loss)")
    sim1.packet_loss_rate = 0.0
    sim2.packet_loss_rate = 0.0
    
    print("Waiting for recovery (10 seconds)...")
    time.sleep(10)
    
    print(f"node1 data (recovered): {node1.get_all_data()}")
    print(f"node2 data (recovered): {node2.get_all_data()}")
    
    # Check convergence
    keys1 = set(node1.get_all_data().keys())
    keys2 = set(node2.get_all_data().keys())
    
    if keys1 == keys2:
        print("✓ SUCCESS: Nodes recovered and converged after partition")
    else:
        print("✗ FAILURE: Nodes did not converge")
        print(f"  node1 keys: {keys1}")
        print(f"  node2 keys: {keys2}")
    
    # Cleanup
    node1.stop()
    node2.stop()
    
    print("\nTest completed!")


def main():
    """Run all tests"""
    try:
        test_convergence_under_packet_loss()
        time.sleep(2)
        test_partition_recovery()
        
        print("\n" + "="*60)
        print("ALL TESTS COMPLETED")
        print("="*60)
        
    except KeyboardInterrupt:
        print("\nTests interrupted")
    except Exception as e:
        logger.error(f"Test error: {e}", exc_info=True)


if __name__ == '__main__':
    main()
