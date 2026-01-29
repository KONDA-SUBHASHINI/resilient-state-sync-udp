#!/usr/bin/env python3
"""
Example: Basic Mesh Sync Usage
Demonstrates starting a node and performing basic operations
"""
import sys
import time
import logging
from mesh_node import MeshSyncNode

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def main():
    if len(sys.argv) < 3:
        print("Usage: python example_basic.py <node_id> <port> [bootstrap_host bootstrap_port]")
        print("Example: python example_basic.py node1 5001")
        print("Example: python example_basic.py node2 5002 localhost 5001")
        sys.exit(1)
    
    node_id = sys.argv[1]
    port = int(sys.argv[2])
    
    # Create node
    node = MeshSyncNode(node_id, port, sync_interval=5.0)
    
    # Add bootstrap peer if provided
    if len(sys.argv) >= 5:
        bootstrap_host = sys.argv[3]
        bootstrap_port = int(sys.argv[4])
        node.add_bootstrap_peer(bootstrap_host, bootstrap_port)
        print(f"Added bootstrap peer: {bootstrap_host}:{bootstrap_port}")
    
    # Start node
    node.start()
    print(f"Node {node_id} started on port {port}")
    print("Commands: set <key> <value>, get <key>, delete <key>, list, status, quit")
    
    try:
        while True:
            try:
                cmd = input(f"[{node_id}]> ").strip()
                
                if not cmd:
                    continue
                
                parts = cmd.split()
                command = parts[0].lower()
                
                if command == 'quit' or command == 'exit':
                    break
                
                elif command == 'set' and len(parts) >= 3:
                    key = parts[1]
                    value = ' '.join(parts[2:])
                    node.set(key, value)
                    print(f"Set {key} = {value}")
                
                elif command == 'get' and len(parts) >= 2:
                    key = parts[1]
                    value = node.get(key)
                    print(f"{key} = {value}")
                
                elif command == 'delete' and len(parts) >= 2:
                    key = parts[1]
                    node.delete(key)
                    print(f"Deleted {key}")
                
                elif command == 'list':
                    data = node.get_all_data()
                    if data:
                        print("Current data:")
                        for k, v in data.items():
                            print(f"  {k} = {v}")
                    else:
                        print("No data")
                
                elif command == 'status':
                    status = node.get_status()
                    print(f"Node Status:")
                    print(f"  Node ID: {status['node_id']}")
                    print(f"  Port: {status['port']}")
                    print(f"  State Version: {status['state_version']}")
                    print(f"  Data Keys: {status['data_keys']}")
                    print(f"  Peers: {status['peers']['alive_peers']}/{status['peers']['total_peers']} alive")
                    print(f"  Pending ACKs: {status['pending_acks']}")
                
                else:
                    print("Unknown command. Available: set, get, delete, list, status, quit")
            
            except KeyboardInterrupt:
                print()
                break
            except Exception as e:
                print(f"Error: {e}")
    
    finally:
        print("Stopping node...")
        node.stop()
        print("Node stopped")


if __name__ == '__main__':
    main()
