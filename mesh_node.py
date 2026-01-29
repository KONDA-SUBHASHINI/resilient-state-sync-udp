"""
Mesh Sync Node
Main node implementation that coordinates CRDT state, reliable UDP, and peer management
"""
import time
import threading
import logging
import random
from typing import Optional, Tuple, Dict, Callable

from crdt_state import CRDTState
from reliable_udp import ReliableUDPSocket, PacketType
from peer_manager import PeerManager

logger = logging.getLogger(__name__)


class MeshSyncNode:
    """
    Main mesh synchronization node
    Coordinates state replication across unreliable mesh network
    """
    
    def __init__(self, node_id: str, port: int, 
                 sync_interval: float = 10.0,
                 heartbeat_interval: float = 5.0):
        """
        Initialize mesh sync node
        
        Args:
            node_id: Unique identifier for this node
            port: UDP port to listen on
            sync_interval: How often to sync with peers (seconds)
            heartbeat_interval: How often to send heartbeats (seconds)
        """
        self.node_id = node_id
        self.port = port
        self.sync_interval = sync_interval
        self.heartbeat_interval = heartbeat_interval
        
        # Core components
        self.state = CRDTState(node_id)
        self.udp = ReliableUDPSocket(port, node_id)
        self.peer_mgr = PeerManager(node_id, heartbeat_interval)
        
        # Register packet handlers
        self._register_handlers()
        
        # Background threads
        self.running = False
        self.sync_thread = None
        self.heartbeat_thread = None
        self.discovery_thread = None
        
        # Callbacks
        self.on_state_change = None
        
        logger.info(f"MeshSyncNode initialized: {node_id} on port {port}")
    
    def start(self):
        """Start the mesh sync node"""
        self.running = True
        
        # Start components
        self.udp.start()
        self.peer_mgr.start()
        
        # Start background threads
        self.sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.sync_thread.start()
        
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        
        self.discovery_thread = threading.Thread(target=self._discovery_loop, daemon=True)
        self.discovery_thread.start()
        
        logger.info(f"Node {self.node_id} started")
    
    def stop(self):
        """Stop the mesh sync node"""
        self.running = False
        
        # Stop threads
        if self.sync_thread:
            self.sync_thread.join(timeout=1.0)
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=1.0)
        if self.discovery_thread:
            self.discovery_thread.join(timeout=1.0)
        
        # Stop components
        self.udp.stop()
        self.peer_mgr.stop()
        
        logger.info(f"Node {self.node_id} stopped")
    
    def add_bootstrap_peer(self, host: str, port: int):
        """Add a bootstrap peer for discovery"""
        self.peer_mgr.add_bootstrap_peer((host, port))
    
    # ========== State Operations ==========
    
    def set(self, key: str, value):
        """Set a key-value pair in the replicated state"""
        self.state.set(key, value)
        logger.info(f"[{self.node_id}] Set {key} = {value}")
        
        if self.on_state_change:
            self.on_state_change(key, value, 'set')
    
    def get(self, key: str):
        """Get a value from the replicated state"""
        return self.state.get(key)
    
    def delete(self, key: str):
        """Delete a key from the replicated state"""
        self.state.delete(key)
        logger.info(f"[{self.node_id}] Deleted {key}")
        
        if self.on_state_change:
            self.on_state_change(key, None, 'delete')
    
    def get_all_data(self) -> Dict:
        """Get all active data"""
        snapshot = self.state.get_state_snapshot()
        return {k: v[0] for k, v in snapshot['data'].items() 
                if k not in snapshot['tombstones']}
    
    # ========== Protocol Handlers ==========
    
    def _register_handlers(self):
        """Register packet type handlers"""
        self.udp.register_handler(PacketType.SYNC_REQUEST, self._handle_sync_request)
        self.udp.register_handler(PacketType.SYNC_RESPONSE, self._handle_sync_response)
        self.udp.register_handler(PacketType.HEARTBEAT, self._handle_heartbeat)
        self.udp.register_handler(PacketType.DISCOVERY, self._handle_discovery)
    
    def _handle_sync_request(self, payload: Dict, addr: Tuple[str, int]):
        """Handle incoming sync request"""
        remote_node_id = payload.get('node_id')
        remote_version = payload.get('version', 0)
        
        logger.debug(f"Sync request from {remote_node_id} at {addr}")
        
        # Update peer info
        self.peer_mgr.add_or_update_peer(remote_node_id, addr, remote_version)
        
        # Send our full state back
        snapshot = self.state.get_state_snapshot()
        response = {
            'node_id': self.node_id,
            'state': snapshot
        }
        
        self.udp.send_reliable(addr, PacketType.SYNC_RESPONSE, response)
    
    def _handle_sync_response(self, payload: Dict, addr: Tuple[str, int]):
        """Handle incoming sync response"""
        remote_node_id = payload.get('node_id')
        remote_state = payload.get('state')
        
        if not remote_state:
            return
        
        logger.debug(f"Sync response from {remote_node_id}")
        
        # Update peer
        remote_version = remote_state.get('version', 0)
        self.peer_mgr.add_or_update_peer(remote_node_id, addr, remote_version)
        
        # Merge remote state
        modified = self.state.merge_remote_state(
            remote_state.get('data', {}),
            remote_state.get('tombstones', {}),
            remote_state.get('vector_clock', {})
        )
        
        if modified:
            logger.info(f"State updated from {remote_node_id}")
            if self.on_state_change:
                self.on_state_change(None, None, 'sync')
        
        # Mark peer as synced
        self.peer_mgr.mark_peer_synced(remote_node_id)
    
    def _handle_heartbeat(self, payload: Dict, addr: Tuple[str, int]):
        """Handle incoming heartbeat"""
        remote_node_id = payload.get('node_id')
        remote_version = payload.get('version', 0)
        
        # Update peer info
        self.peer_mgr.add_or_update_peer(remote_node_id, addr, remote_version)
        
        logger.debug(f"Heartbeat from {remote_node_id}")
    
    def _handle_discovery(self, payload: Dict, addr: Tuple[str, int]):
        """Handle discovery message"""
        remote_node_id = payload.get('node_id')
        remote_port = payload.get('port')
        remote_peers = payload.get('peers', [])
        
        logger.debug(f"Discovery from {remote_node_id} at {addr}")
        
        # Add the sender
        self.peer_mgr.add_or_update_peer(remote_node_id, (addr[0], remote_port))
        
        # Add any peers they know about
        for peer_info in remote_peers:
            peer_id = peer_info.get('node_id')
            peer_host = peer_info.get('host')
            peer_port = peer_info.get('port')
            if peer_id and peer_host and peer_port:
                self.peer_mgr.add_or_update_peer(peer_id, (peer_host, peer_port))
        
        # Respond with our peer list
        our_peers = []
        for peer in self.peer_mgr.get_alive_peers():
            our_peers.append({
                'node_id': peer.node_id,
                'host': peer.address[0],
                'port': peer.address[1]
            })
        
        response = {
            'node_id': self.node_id,
            'port': self.port,
            'peers': our_peers
        }
        
        self.udp.send_unreliable(addr, PacketType.DISCOVERY, response)
    
    # ========== Background Loops ==========
    
    def _sync_loop(self):
        """Periodically sync with peers"""
        while self.running:
            time.sleep(self.sync_interval)
            
            # Get peers that need syncing
            peers_to_sync = self.peer_mgr.get_peers_needing_sync(self.sync_interval)
            
            if not peers_to_sync:
                # Try to sync with random alive peer
                alive_peers = self.peer_mgr.get_alive_peers()
                if alive_peers:
                    peers_to_sync = [random.choice(alive_peers)]
            
            for peer in peers_to_sync:
                try:
                    logger.debug(f"Syncing with {peer.node_id}")
                    
                    # Send sync request
                    request = {
                        'node_id': self.node_id,
                        'version': self.state.version
                    }
                    
                    self.udp.send_reliable(peer.address, PacketType.SYNC_REQUEST, request)
                    
                except Exception as e:
                    logger.error(f"Sync error with {peer.node_id}: {e}")
    
    def _heartbeat_loop(self):
        """Send periodic heartbeats to all peers"""
        while self.running:
            time.sleep(self.heartbeat_interval)
            
            alive_peers = self.peer_mgr.get_alive_peers()
            
            for peer in alive_peers:
                try:
                    heartbeat = {
                        'node_id': self.node_id,
                        'version': self.state.version,
                        'timestamp': time.time()
                    }
                    
                    self.udp.send_unreliable(peer.address, PacketType.HEARTBEAT, heartbeat)
                    
                except Exception as e:
                    logger.error(f"Heartbeat error to {peer.node_id}: {e}")
    
    def _discovery_loop(self):
        """Periodically send discovery messages to bootstrap peers"""
        # Initial discovery
        time.sleep(1.0)  # Wait for everything to start
        self._send_discovery()
        
        # Periodic rediscovery
        while self.running:
            time.sleep(30.0)  # Rediscover every 30 seconds
            self._send_discovery()
    
    def _send_discovery(self):
        """Send discovery messages"""
        # Discovery to bootstrap peers
        for addr in self.peer_mgr.get_bootstrap_addresses():
            try:
                # Gather our known peers
                our_peers = []
                for peer in self.peer_mgr.get_alive_peers():
                    our_peers.append({
                        'node_id': peer.node_id,
                        'host': peer.address[0],
                        'port': peer.address[1]
                    })
                
                discovery = {
                    'node_id': self.node_id,
                    'port': self.port,
                    'peers': our_peers
                }
                
                self.udp.send_unreliable(addr, PacketType.DISCOVERY, discovery)
                logger.debug(f"Sent discovery to {addr}")
                
            except Exception as e:
                logger.error(f"Discovery error to {addr}: {e}")
    
    def get_status(self) -> Dict:
        """Get node status information"""
        peer_stats = self.peer_mgr.get_stats()
        return {
            'node_id': self.node_id,
            'port': self.port,
            'state_version': self.state.version,
            'data_keys': len(self.state.get_keys()),
            'peers': peer_stats,
            'pending_acks': self.udp.get_pending_count()
        }
    
    def __repr__(self) -> str:
        return f"MeshSyncNode(id={self.node_id}, port={self.port}, peers={len(self.peer_mgr.get_alive_peers())})"
