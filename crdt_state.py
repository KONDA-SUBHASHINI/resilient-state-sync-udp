"""
CRDT (Conflict-free Replicated Data Type) State Manager
Implements LWW (Last-Write-Wins) and counter-based CRDTs for eventual consistency
"""
import time
import threading
from typing import Dict, Any, Tuple, Set
from collections import defaultdict


class CRDTState:
    """
    Manages replicated state using CRDT principles:
    - LWW-Register for key-value pairs
    - Vector clocks for causality tracking
    - Tombstones for deletions
    """
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.lock = threading.RLock()
        
        # LWW-Register: key -> (value, timestamp, node_id)
        self.data: Dict[str, Tuple[Any, float, str]] = {}
        
        # Vector clock: node_id -> sequence_number
        self.vector_clock: Dict[str, int] = defaultdict(int)
        
        # Tombstones for deletions: key -> (timestamp, node_id)
        self.tombstones: Dict[str, Tuple[float, str]] = {}
        
        # Version tracking for sync optimization
        self.version = 0
        
    def set(self, key: str, value: Any) -> None:
        """Set a key-value pair with current timestamp"""
        with self.lock:
            timestamp = time.time()
            self.data[key] = (value, timestamp, self.node_id)
            self.vector_clock[self.node_id] += 1
            self.version += 1
            
            # Remove tombstone if it exists
            if key in self.tombstones:
                del self.tombstones[key]
    
    def get(self, key: str) -> Any:
        """Get value for key, returns None if not found or deleted"""
        with self.lock:
            if key in self.tombstones:
                return None
            if key in self.data:
                return self.data[key][0]
            return None
    
    def delete(self, key: str) -> None:
        """Delete a key using tombstone"""
        with self.lock:
            timestamp = time.time()
            self.tombstones[key] = (timestamp, self.node_id)
            self.vector_clock[self.node_id] += 1
            self.version += 1
    
    def merge_remote_state(self, remote_data: Dict, remote_tombstones: Dict, 
                          remote_vector_clock: Dict) -> bool:
        """
        Merge remote state using LWW conflict resolution
        Returns True if local state was modified
        """
        modified = False
        
        with self.lock:
            # Merge data
            for key, (value, timestamp, node_id) in remote_data.items():
                should_update = False
                
                # Check if we have this key
                if key in self.data:
                    local_value, local_ts, local_node = self.data[key]
                    # LWW: update if remote timestamp is newer
                    # Use node_id as tiebreaker for deterministic resolution
                    if timestamp > local_ts or (timestamp == local_ts and node_id > local_node):
                        should_update = True
                else:
                    should_update = True
                
                # Check against tombstones
                if key in self.tombstones:
                    tomb_ts, tomb_node = self.tombstones[key]
                    # Don't restore if tombstone is newer
                    if tomb_ts > timestamp or (tomb_ts == timestamp and tomb_node > node_id):
                        should_update = False
                
                if should_update:
                    self.data[key] = (value, timestamp, node_id)
                    modified = True
            
            # Merge tombstones
            for key, (timestamp, node_id) in remote_tombstones.items():
                should_update = False
                
                if key in self.tombstones:
                    local_ts, local_node = self.tombstones[key]
                    if timestamp > local_ts or (timestamp == local_ts and node_id > local_node):
                        should_update = True
                else:
                    should_update = True
                
                if should_update:
                    self.tombstones[key] = (timestamp, node_id)
                    # Remove from data if tombstone is newer
                    if key in self.data:
                        data_ts = self.data[key][1]
                        data_node = self.data[key][2]
                        if timestamp > data_ts or (timestamp == data_ts and node_id > data_node):
                            del self.data[key]
                    modified = True
            
            # Merge vector clocks
            for node, seq in remote_vector_clock.items():
                if seq > self.vector_clock[node]:
                    self.vector_clock[node] = seq
            
            if modified:
                self.version += 1
        
        return modified
    
    def get_state_snapshot(self) -> Dict:
        """Get complete state for synchronization"""
        with self.lock:
            return {
                'data': dict(self.data),
                'tombstones': dict(self.tombstones),
                'vector_clock': dict(self.vector_clock),
                'version': self.version,
                'node_id': self.node_id
            }
    
    def get_keys(self) -> Set[str]:
        """Get all active keys (excluding tombstoned ones)"""
        with self.lock:
            active_keys = set(self.data.keys()) - set(self.tombstones.keys())
            return active_keys
    
    def __repr__(self) -> str:
        with self.lock:
            active = {k: v[0] for k, v in self.data.items() if k not in self.tombstones}
            return f"CRDTState(node={self.node_id}, version={self.version}, data={active})"
