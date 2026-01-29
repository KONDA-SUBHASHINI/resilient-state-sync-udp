"""
Reliable UDP Protocol Implementation
Provides reliability over UDP with:
- Packet sequencing
- Acknowledgements
- Retransmissions with exponential backoff
- Out-of-order delivery handling
"""
import socket
import json
import time
import threading
import hashlib
import struct
from typing import Dict, Callable, Optional, Tuple, Set
from collections import defaultdict
from queue import Queue, PriorityQueue
import logging

logger = logging.getLogger(__name__)


class PacketType:
    """Protocol packet types"""
    DATA = 0
    ACK = 1
    SYNC_REQUEST = 2
    SYNC_RESPONSE = 3
    HEARTBEAT = 4
    DISCOVERY = 5


class ReliableUDPPacket:
    """
    Packet structure:
    - Header: [version(1) | type(1) | seq(4) | checksum(4)]
    - Payload: JSON data
    """
    VERSION = 1
    HEADER_SIZE = 10
    MAX_PAYLOAD_SIZE = 65507 - HEADER_SIZE  # UDP max - header
    
    def __init__(self, packet_type: int, seq_num: int, payload: Dict):
        self.packet_type = packet_type
        self.seq_num = seq_num
        self.payload = payload
        self.timestamp = time.time()
    
    def serialize(self) -> bytes:
        """Serialize packet to bytes"""
        payload_bytes = json.dumps(self.payload).encode('utf-8')
        
        # Truncate if too large
        if len(payload_bytes) > self.MAX_PAYLOAD_SIZE:
            logger.warning(f"Payload too large ({len(payload_bytes)} bytes), truncating")
            payload_bytes = payload_bytes[:self.MAX_PAYLOAD_SIZE]
        
        # Calculate checksum
        checksum = self._calculate_checksum(payload_bytes)
        
        # Build header
        header = struct.pack('!BBII', 
                            self.VERSION, 
                            self.packet_type, 
                            self.seq_num, 
                            checksum)
        
        return header + payload_bytes
    
    @classmethod
    def deserialize(cls, data: bytes) -> Optional['ReliableUDPPacket']:
        """Deserialize bytes to packet"""
        if len(data) < cls.HEADER_SIZE:
            return None
        
        try:
            # Parse header
            version, pkt_type, seq_num, checksum = struct.unpack('!BBII', data[:cls.HEADER_SIZE])
            
            if version != cls.VERSION:
                logger.warning(f"Unknown packet version: {version}")
                return None
            
            # Parse payload
            payload_bytes = data[cls.HEADER_SIZE:]
            
            # Verify checksum
            if cls._calculate_checksum(payload_bytes) != checksum:
                logger.warning("Checksum mismatch, packet corrupted")
                return None
            
            payload = json.loads(payload_bytes.decode('utf-8'))
            
            packet = cls(pkt_type, seq_num, payload)
            return packet
            
        except Exception as e:
            logger.error(f"Packet deserialization error: {e}")
            return None
    
    @staticmethod
    def _calculate_checksum(data: bytes) -> int:
        """Calculate simple checksum"""
        return int(hashlib.md5(data).hexdigest()[:8], 16)


class ReliableUDPSocket:
    """
    Reliable UDP socket with automatic retransmissions and ACKs
    """
    
    def __init__(self, port: int, node_id: str):
        self.port = port
        self.node_id = node_id
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(('0.0.0.0', port))
        
        # Sequence numbers
        self.send_seq = 0
        self.seq_lock = threading.Lock()
        
        # Pending ACKs: seq_num -> (packet, send_time, retries, addr)
        self.pending_acks: Dict[int, Tuple[ReliableUDPPacket, float, int, Tuple]] = {}
        self.ack_lock = threading.Lock()
        
        # Received sequence tracking per peer
        self.received_seqs: Dict[Tuple, Set[int]] = defaultdict(set)
        
        # Message handlers
        self.handlers: Dict[int, Callable] = {}
        
        # Threads
        self.running = False
        self.recv_thread = None
        self.retry_thread = None
        
        # Configuration
        self.MAX_RETRIES = 5
        self.INITIAL_TIMEOUT = 0.5
        self.MAX_TIMEOUT = 8.0
        
    def start(self):
        """Start socket threads"""
        self.running = True
        
        self.recv_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.recv_thread.start()
        
        self.retry_thread = threading.Thread(target=self._retry_loop, daemon=True)
        self.retry_thread.start()
        
        logger.info(f"ReliableUDP started on port {self.port}")
    
    def stop(self):
        """Stop socket threads"""
        self.running = False
        if self.recv_thread:
            self.recv_thread.join(timeout=1.0)
        if self.retry_thread:
            self.retry_thread.join(timeout=1.0)
        self.socket.close()
        logger.info("ReliableUDP stopped")
    
    def register_handler(self, packet_type: int, handler: Callable):
        """Register handler for packet type"""
        self.handlers[packet_type] = handler
    
    def send_reliable(self, addr: Tuple[str, int], packet_type: int, payload: Dict) -> int:
        """Send packet with reliability (will retry until ACK or max retries)"""
        with self.seq_lock:
            seq_num = self.send_seq
            self.send_seq += 1
        
        packet = ReliableUDPPacket(packet_type, seq_num, payload)
        data = packet.serialize()
        
        # Send packet
        self.socket.sendto(data, addr)
        
        # Track for retransmission
        with self.ack_lock:
            self.pending_acks[seq_num] = (packet, time.time(), 0, addr)
        
        return seq_num
    
    def send_unreliable(self, addr: Tuple[str, int], packet_type: int, payload: Dict):
        """Send packet without reliability (fire and forget)"""
        with self.seq_lock:
            seq_num = self.send_seq
            self.send_seq += 1
        
        packet = ReliableUDPPacket(packet_type, seq_num, payload)
        data = packet.serialize()
        self.socket.sendto(data, addr)
    
    def _send_ack(self, addr: Tuple[str, int], seq_num: int):
        """Send ACK packet"""
        packet = ReliableUDPPacket(PacketType.ACK, seq_num, {'ack': seq_num})
        data = packet.serialize()
        self.socket.sendto(data, addr)
    
    def _receive_loop(self):
        """Main receive loop"""
        self.socket.settimeout(0.1)  # Non-blocking with timeout
        
        while self.running:
            try:
                data, addr = self.socket.recvfrom(65535)
                packet = ReliableUDPPacket.deserialize(data)
                
                if packet is None:
                    continue
                
                # Handle ACK packets
                if packet.packet_type == PacketType.ACK:
                    self._handle_ack(packet, addr)
                    continue
                
                # Check for duplicates (already received)
                if packet.seq_num in self.received_seqs[addr]:
                    # Duplicate, send ACK again but don't process
                    self._send_ack(addr, packet.seq_num)
                    continue
                
                # Mark as received
                self.received_seqs[addr].add(packet.seq_num)
                
                # Send ACK
                self._send_ack(addr, packet.seq_num)
                
                # Handle packet
                handler = self.handlers.get(packet.packet_type)
                if handler:
                    try:
                        handler(packet.payload, addr)
                    except Exception as e:
                        logger.error(f"Handler error for packet type {packet.packet_type}: {e}")
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Receive error: {e}")
    
    def _handle_ack(self, packet: ReliableUDPPacket, addr: Tuple):
        """Handle ACK packet"""
        ack_seq = packet.payload.get('ack')
        if ack_seq is None:
            return
        
        with self.ack_lock:
            if ack_seq in self.pending_acks:
                del self.pending_acks[ack_seq]
                logger.debug(f"Received ACK for seq {ack_seq} from {addr}")
    
    def _retry_loop(self):
        """Retry loop for unacknowledged packets"""
        while self.running:
            time.sleep(0.1)
            
            now = time.time()
            to_retry = []
            
            with self.ack_lock:
                for seq_num, (packet, send_time, retries, addr) in list(self.pending_acks.items()):
                    timeout = min(self.INITIAL_TIMEOUT * (2 ** retries), self.MAX_TIMEOUT)
                    
                    if now - send_time > timeout:
                        if retries >= self.MAX_RETRIES:
                            # Give up
                            logger.warning(f"Max retries reached for seq {seq_num} to {addr}")
                            del self.pending_acks[seq_num]
                        else:
                            to_retry.append((seq_num, packet, retries, addr))
            
            # Retry outside lock
            for seq_num, packet, retries, addr in to_retry:
                logger.debug(f"Retrying seq {seq_num} to {addr} (attempt {retries + 1})")
                data = packet.serialize()
                self.socket.sendto(data, addr)
                
                with self.ack_lock:
                    if seq_num in self.pending_acks:
                        self.pending_acks[seq_num] = (packet, time.time(), retries + 1, addr)
    
    def get_pending_count(self) -> int:
        """Get count of pending acknowledgements"""
        with self.ack_lock:
            return len(self.pending_acks)
