import pickle
import socket
import time

from rdt.util import PrintType, print_info, calculate_checksum


class RDTReceiver:
    def __init__(self, port: int, dst_address="127.0.0.1"):
        self.src_address = "127.0.0.1"
        self.dst_address = dst_address
        self.send_port = port
        self.recv_port = self.send_port + 1
        print(f"Receiver Ports: [Send: {self.send_port}, Recv: {self.recv_port}]")
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.is_receiving = False
        self.received_files = False
        self.window_size = 100
        self.recv_base = 0
        self.window = {}
        self.ordered_chunks = []

    def receive_packet(self):
        try:
            pkt, _ = self.socket.recvfrom(2048)
            return pkt if pkt else None
        except Exception:
            return None

    def verify_packet(self, data):
        pkt = pickle.loads(data)
        if "terminate" not in pkt or "seq" not in pkt or "data" not in pkt or "checksum" not in pkt:
            print_info("Receiver: Packet missing required fields!", PrintType.ERROR)
            return False

        valid_checksum = pkt["checksum"] == calculate_checksum(pickle.dumps({
            "terminate": pkt["terminate"],
            "seq": pkt["seq"],
            "data": pkt["data"]
        }))
        print(f"Receiver: Valid Checksum {pkt['seq']}: {valid_checksum}")
        return valid_checksum

    def accept_client(self):
        try:
            self.socket.bind((self.src_address, self.recv_port))
        except OSError:
            print("[Receiver] Socket already in use or closed.")
            return

        self.is_receiving = True
        termination_received = False

        while self.is_receiving:
            data = self.receive_packet()
            if data is None:
                continue

            if not self.verify_packet(data):
                continue

            pkt = pickle.loads(data)
            seq_num = pkt["seq"]

            if pkt.get("terminate"):
                termination_received = True
                self.socket.sendto(pickle.dumps({"fin_ack": True}), (self.dst_address, self.send_port))
                print(f"Receiver: Received termination packet at SEQ {seq_num}, sent FIN-ACK")

            if self.recv_base <= seq_num < self.recv_base + self.window_size:
                self.socket.sendto(pickle.dumps({"ack": seq_num}), (self.dst_address, self.send_port))
                self.window[seq_num] = pkt

                while self.recv_base in self.window:
                    current_pkt = self.window.pop(self.recv_base)
                    self.ordered_chunks.append(current_pkt["data"])
                    self.recv_base += 1

            elif self.recv_base - self.window_size <= seq_num < self.recv_base:
                self.socket.sendto(pickle.dumps({"ack": seq_num}), (self.dst_address, self.send_port))

            if termination_received and not self.window:
                break

        # Handle any late retransmitted termination packets
        self.socket.settimeout(5)
        try:
            while True:
                data, _ = self.socket.recvfrom(2048)
                pkt = pickle.loads(data)
                if pkt.get("terminate"):
                    self.socket.sendto(pickle.dumps({"fin_ack": True}), (self.dst_address, self.send_port))
                    print("Receiver: Re-sent FIN-ACK")
        except socket.timeout:
            pass

        print("Receiver: Terminating connection!")
        self.terminate_connection()

    def terminate_connection(self):
        self.received_files = True
        self.socket.close()
        self.is_receiving = False
