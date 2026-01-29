"""
Peer Discovery and Management
Handles peer discovery, heartbeats, and failure detection
"""
import time
import threading
import logging
from typing import Dict, Set, Tuple, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PeerInfo:
    """Information about a peer node"""
    node_id: str
    address: Tuple[str, int]
    last_seen: float = field(default_factory=time.time)
    last_sync: float = 0.0
    version: int = 0
    is_alive: bool = True
    failed_pings: int = 0
    
    def update_seen(self):
        """Update last seen timestamp"""
        self.last_seen = time.time()
        self.is_alive = True
        self.failed_pings = 0
    
    def mark_dead(self):
        """Mark peer as dead"""
        self.is_alive = False
    
    def needs_sync(self, sync_interval: float) -> bool:
        """Check if peer needs synchronization"""
        return (time.time() - self.last_sync) > sync_interval


class PeerManager:
    """
    Manages peer discovery and health monitoring
    """
    
    def __init__(self, node_id: str, heartbeat_interval: float = 5.0, 
                 peer_timeout: float = 15.0):
        self.node_id = node_id
        self.heartbeat_interval = heartbeat_interval
        self.peer_timeout = peer_timeout
        
        # Peers: node_id -> PeerInfo
        self.peers: Dict[str, PeerInfo] = {}
        self.lock = threading.RLock()
        
        # Bootstrap peers (seed addresses)
        self.bootstrap_peers: Set[Tuple[str, int]] = set()
        
        # Callbacks
        self.on_peer_discovered = None
        self.on_peer_failed = None
        
        # Health check thread
        self.running = False
        self.health_thread = None
    
    def start(self):
        """Start peer health monitoring"""
        self.running = True
        self.health_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self.health_thread.start()
        logger.info("PeerManager started")
    
    def stop(self):
        """Stop peer monitoring"""
        self.running = False
        if self.health_thread:
            self.health_thread.join(timeout=1.0)
        logger.info("PeerManager stopped")
    
    def add_bootstrap_peer(self, address: Tuple[str, int]):
        """Add a bootstrap peer address"""
        self.bootstrap_peers.add(address)
        logger.info(f"Added bootstrap peer: {address}")
    
    def add_or_update_peer(self, node_id: str, address: Tuple[str, int], 
                          version: int = 0) -> bool:
        """
        Add or update peer information
        Returns True if this is a new peer
        """
        with self.lock:
            # Don't add ourselves
            if node_id == self.node_id:
                return False
            
            is_new = node_id not in self.peers
            
            if is_new:
                self.peers[node_id] = PeerInfo(
                    node_id=node_id,
                    address=address,
                    version=version
                )
                logger.info(f"Discovered new peer: {node_id} at {address}")
                
                if self.on_peer_discovered:
                    self.on_peer_discovered(node_id, address)
            else:
                peer = self.peers[node_id]
                peer.update_seen()
                peer.address = address  # Update in case it changed
                if version > peer.version:
                    peer.version = version
            
            return is_new
    
    def update_peer_version(self, node_id: str, version: int):
        """Update peer's version number"""
        with self.lock:
            if node_id in self.peers:
                peer = self.peers[node_id]
                if version > peer.version:
                    peer.version = version
    
    def mark_peer_synced(self, node_id: str):
        """Mark that we just synced with this peer"""
        with self.lock:
            if node_id in self.peers:
                self.peers[node_id].last_sync = time.time()
    
    def get_peer(self, node_id: str) -> Optional[PeerInfo]:
        """Get peer information"""
        with self.lock:
            return self.peers.get(node_id)
    
    def get_all_peers(self) -> List[PeerInfo]:
        """Get all known peers"""
        with self.lock:
            return list(self.peers.values())
    
    def get_alive_peers(self) -> List[PeerInfo]:
        """Get all alive peers"""
        with self.lock:
            return [p for p in self.peers.values() if p.is_alive]
    
    def get_peers_needing_sync(self, sync_interval: float) -> List[PeerInfo]:
        """Get peers that need synchronization"""
        with self.lock:
            return [p for p in self.peers.values() 
                   if p.is_alive and p.needs_sync(sync_interval)]
    
    def mark_peer_failed(self, node_id: str):
        """Mark a peer as failed"""
        with self.lock:
            if node_id in self.peers:
                peer = self.peers[node_id]
                peer.failed_pings += 1
                
                if peer.failed_pings >= 3 and peer.is_alive:
                    peer.mark_dead()
                    logger.warning(f"Peer {node_id} marked as dead")
                    
                    if self.on_peer_failed:
                        self.on_peer_failed(node_id)
    
    def get_bootstrap_addresses(self) -> List[Tuple[str, int]]:
        """Get bootstrap peer addresses"""
        return list(self.bootstrap_peers)
    
    def _health_check_loop(self):
        """Periodically check peer health"""
        while self.running:
            time.sleep(self.heartbeat_interval)
            
            now = time.time()
            with self.lock:
                for node_id, peer in list(self.peers.items()):
                    if peer.is_alive and (now - peer.last_seen) > self.peer_timeout:
                        self.mark_peer_failed(node_id)
    
    def get_stats(self) -> Dict:
        """Get peer statistics"""
        with self.lock:
            alive = sum(1 for p in self.peers.values() if p.is_alive)
            return {
                'total_peers': len(self.peers),
                'alive_peers': alive,
                'dead_peers': len(self.peers) - alive,
                'bootstrap_peers': len(self.bootstrap_peers)
            }
    
    def __repr__(self) -> str:
        with self.lock:
            alive = [p.node_id for p in self.peers.values() if p.is_alive]
            return f"PeerManager(node={self.node_id}, peers={len(alive)} alive)"
