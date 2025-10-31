import pickle
import socket

from util import PrintType, print_info, calculate_checksum


class TCPReceiver:
    def __init__(self, port: int, dst_address="127.0.0.1"):
        self.src_address = "127.0.0.1"
        self.dst_address = dst_address
        self.send_port = port
        self.recv_port = self.send_port + 1
        print(f"Receiver Ports: [Send: {self.send_port}, Recv: {self.recv_port}]")
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.is_receiving = False
        self.received_end = False

        self.window_size = 4
        self.recv_base = 0
        self.window = {}

        self.ordered_chunks = []

    def receive_packet(self):
        pkt, _ = self.socket.recvfrom(2048)
        if not pkt:
            return None

        # length = int.from_bytes(pkt_len, "big")
        # data = b""
        # while len(data) < length:
        #     payload = conn.recv(length - len(data))
        #     if not payload:
        #         return None
        #     data += payload

        return pkt

    def verify_packet(self, data):
        pkt = pickle.loads(data)

        if "terminate" not in pkt:
            print_info("Receiver: Terminate flag is not in packet!", PrintType.ERROR)
            return False
        if "seq" not in pkt:
            print_info("Receiver: Sequence number not in packet!", PrintType.ERROR)
            return False
        if "data" not in pkt:
            print_info("Receiver: Data payload not in packet!", PrintType.ERROR)
            return False
        if "checksum" not in pkt or pkt["checksum"] is None:
            print_info("Receiver: Checksum in packet is missing or None!", PrintType.ERROR)
            return False

        valid_checksum = pkt["checksum"] == calculate_checksum(pickle.dumps({
            "terminate": pkt["terminate"],
            "seq": pkt["seq"],
            "data": pkt["data"]
        }))
        print(f"Receiver: Valid Checksum {pkt["seq"]}: {valid_checksum}")
        return valid_checksum

    def accept_client(self):
        print(self.src_address)
        self.socket.bind((self.src_address, self.recv_port))

        self.is_receiving = True
        termination_received = False

        while self.is_receiving:
            data = self.receive_packet()
            # try:
            if data is None:
                print("Receiver: Received Nothing... Quitting")
                break

            if self.verify_packet(data):
                pkt = pickle.loads(data)
                seq_num = pkt["seq"]
                print(f"Received SEQ: {seq_num} | Expected SEQ: {self.recv_base}")

                # Check for termination flag
                if "terminate" in pkt and pkt["terminate"]:
                    termination_received = True
                    print(f"Receiver: Received termination packet at SEQ {seq_num}")
                    self.socket.sendto(pickle.dumps({"fin_ack": True}), (self.dst_address, self.send_port))
                    print("Receiver: Re-sent FIN-ACK")

                if self.recv_base <= seq_num <= self.recv_base + self.window_size - 1:
                    print(f"Sent ACK {seq_num}")
                    self.socket.sendto(
                        pickle.dumps({"ack": seq_num}),
                        (self.dst_address, self.send_port)
                    )

                    self.window[seq_num] = pkt

                    # Process all available packets in order
                    while self.recv_base in self.window:
                        current_pkt = self.window[self.recv_base]
                        self.ordered_chunks.append(current_pkt["data"])
                        del self.window[self.recv_base]
                        self.recv_base += 1

                elif self.recv_base - self.window_size <= seq_num <= self.recv_base - 1:
                    print(f"Sent ACK {seq_num}")
                    self.socket.sendto(
                        pickle.dumps({"ack": seq_num}),
                        (self.dst_address, self.send_port)
                    )
                else:
                    print(f"ACK {seq_num} ignored.")

                # Only break after processing all data and receiving termination
                if termination_received and len(self.window) == 0:
                    print("Receiver: All data received, terminating connection!")
                    break

            # except Exception as e:
            #     print("Receiver Error: " + str(e))
            #     break

        try:
            self.socket.settimeout(5)
            while True:
                data, _ = self.socket.recvfrom(2048)
                pkt = pickle.loads(data)
                if "terminate" in pkt and pkt["terminate"]:
                    # If sender retransmits FIN, resend FIN-ACK
                    self.socket.sendto(pickle.dumps({"fin_ack": True}), (self.dst_address, self.send_port))
                    print("Receiver: Re-sent FIN-ACK")
        except socket.timeout:
            pass

        print("Receiver: Terminating connection!")
        self.socket.close()
        self.is_receiving = False
