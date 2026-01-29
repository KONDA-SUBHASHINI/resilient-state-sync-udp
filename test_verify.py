#!/usr/bin/env python3
"""
Quick Verification Test
Verifies that all components work correctly
"""
import sys
import time
import logging

# Suppress logging for clean output
logging.basicConfig(level=logging.ERROR)

def test_imports():
    """Test all imports work"""
    print("Testing imports...", end=' ')
    try:
        from crdt_state import CRDTState
        from reliable_udp import ReliableUDPSocket, PacketType
        from peer_manager import PeerManager
        from mesh_node import MeshSyncNode
        print("✓")
        return True
    except Exception as e:
        print(f"✗ {e}")
        return False

def test_crdt_basic():
    """Test basic CRDT operations"""
    print("Testing CRDT state...", end=' ')
    try:
        from crdt_state import CRDTState
        
        state = CRDTState('test_node')
        state.set('key1', 'value1')
        assert state.get('key1') == 'value1'
        
        state.delete('key1')
        assert state.get('key1') is None
        
        print("✓")
        return True
    except Exception as e:
        print(f"✗ {e}")
        return False

def test_crdt_merge():
    """Test CRDT merge logic"""
    print("Testing CRDT merge...", end=' ')
    try:
        from crdt_state import CRDTState
        import time
        
        state1 = CRDTState('node1')
        state2 = CRDTState('node2')
        
        # Node1 writes
        state1.set('key1', 'value1')
        time.sleep(0.01)
        
        # Node2 writes to same key
        state2.set('key1', 'value2')
        
        # Merge state2 into state1
        snapshot = state2.get_state_snapshot()
        state1.merge_remote_state(
            snapshot['data'],
            snapshot['tombstones'],
            snapshot['vector_clock']
        )
        
        # Should have newer value (value2)
        assert state1.get('key1') == 'value2'
        
        print("✓")
        return True
    except Exception as e:
        print(f"✗ {e}")
        return False

def test_udp_packet():
    """Test UDP packet serialization"""
    print("Testing UDP packets...", end=' ')
    try:
        from reliable_udp import ReliableUDPPacket, PacketType
        
        # Create packet
        packet = ReliableUDPPacket(
            PacketType.DATA,
            seq_num=42,
            payload={'test': 'data'}
        )
        
        # Serialize
        data = packet.serialize()
        
        # Deserialize
        recovered = ReliableUDPPacket.deserialize(data)
        
        assert recovered is not None
        assert recovered.seq_num == 42
        assert recovered.payload['test'] == 'data'
        
        print("✓")
        return True
    except Exception as e:
        print(f"✗ {e}")
        return False

def test_peer_manager():
    """Test peer management"""
    print("Testing peer manager...", end=' ')
    try:
        from peer_manager import PeerManager
        
        mgr = PeerManager('node1')
        
        # Add peer
        is_new = mgr.add_or_update_peer('node2', ('127.0.0.1', 5000))
        assert is_new == True
        
        # Add same peer again
        is_new = mgr.add_or_update_peer('node2', ('127.0.0.1', 5000))
        assert is_new == False
        
        # Get peers
        peers = mgr.get_all_peers()
        assert len(peers) == 1
        assert peers[0].node_id == 'node2'
        
        print("✓")
        return True
    except Exception as e:
        print(f"✗ {e}")
        return False

def test_node_creation():
    """Test node creation and basic operations"""
    print("Testing node creation...", end=' ')
    try:
        from mesh_node import MeshSyncNode
        
        node = MeshSyncNode('test_node', 9999)
        
        # Test set/get
        node.set('test_key', 'test_value')
        assert node.get('test_key') == 'test_value'
        
        # Test delete
        node.delete('test_key')
        assert node.get('test_key') is None
        
        # Get all data
        node.set('key1', 'value1')
        node.set('key2', 'value2')
        data = node.get_all_data()
        assert 'key1' in data
        assert 'key2' in data
        
        print("✓")
        return True
    except Exception as e:
        print(f"✗ {e}")
        return False

def test_two_node_sync():
    """Test actual synchronization between two nodes"""
    print("Testing two-node sync...", end=' ')
    try:
        from mesh_node import MeshSyncNode
        
        # Create nodes
        node1 = MeshSyncNode('node1', 19001, sync_interval=1.0, heartbeat_interval=0.5)
        node2 = MeshSyncNode('node2', 19002, sync_interval=1.0, heartbeat_interval=0.5)
        
        # Connect node2 to node1
        node2.add_bootstrap_peer('localhost', 19001)
        
        # Start both
        node1.start()
        node2.start()
        
        # Give time to discover
        time.sleep(2)
        
        # Write to node1
        node1.set('sync_test', 'hello_world')
        
        # Wait for sync
        time.sleep(3)
        
        # Check node2 has the data
        value = node2.get('sync_test')
        
        # Stop nodes
        node1.stop()
        node2.stop()
        
        assert value == 'hello_world', f"Expected 'hello_world', got '{value}'"
        
        print("✓")
        return True
    except Exception as e:
        print(f"✗ {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("="*60)
    print("MESH SYNC - VERIFICATION TEST")
    print("="*60)
    print()
    
    tests = [
        test_imports,
        test_crdt_basic,
        test_crdt_merge,
        test_udp_packet,
        test_peer_manager,
        test_node_creation,
        test_two_node_sync,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        if test():
            passed += 1
        else:
            failed += 1
    
    print()
    print("="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60)
    
    if failed == 0:
        print("\n✓ All tests passed! System is ready to use.")
        print("\nNext steps:")
        print("  1. Read QUICKSTART.md for usage examples")
        print("  2. Try: python3 example_basic.py node1 5001")
        print("  3. Try: python3 test_simulation.py")
        return 0
    else:
        print("\n✗ Some tests failed. Please check the errors above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
