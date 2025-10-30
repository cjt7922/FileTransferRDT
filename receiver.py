import pickle
import socket


class TCPReceiver:
    def __init__(self, port: int, dst_address="127.0.0.1"):
        self.src_address = "127.0.0.1"  # socket.gethostbyname(socket.gethostname())
        self.dst_address = dst_address
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.window_size = 4
        self.recv_base = 0
        self.window = {}

        self.ordered_chunks = []

    def receive_packet(self, conn):
        pkt_len = conn.recv(4)
        if not pkt_len:
            return None

        length = int.from_bytes(pkt_len, "big")
        data = b""
        while len(data) < length:
            payload = conn.recv(length - len(data))
            if not payload:
                return None
            data += payload

        return pickle.loads(data)

    def accept_client(self):
        print(self.src_address)
        self.socket.bind((self.src_address, self.port))
        self.socket.listen(1)

        conn, addr = self.socket.accept()
        with conn:
            print(f"Receiver: Sender connected: {addr} | Port: {self.port}")
            while True:
                try:
                    pkt = self.receive_packet(conn)
                    if pkt is None:
                        print("Receiver: Received Nothing... Quitting")
                        break

                    seq_num = pkt["seq"]
                    print(f"Received SEQ: {seq_num} | Expected SEQ: {self.recv_base}")

                    if "fin" in pkt and pkt["fin"]:
                        print(f"Receiver: Received FIN with SEQ {seq_num}, sending final ACK!")
                        conn.sendall(pickle.dumps({"fin_ack": True}))
                        break

                    if self.recv_base <= seq_num <= self.recv_base + self.window_size - 1:
                        print(f"Sent ACK {seq_num}")
                        conn.sendall(pickle.dumps({
                            "ack": seq_num
                        }))

                        self.window[seq_num] = pkt["data"]
                        while self.recv_base in self.window:
                            self.ordered_chunks.append(self.window[self.recv_base])
                            del self.window[self.recv_base]
                            self.recv_base += 1

                    elif self.recv_base - self.window_size <= seq_num <= self.recv_base - 1:
                        print(f"Sent ACK {seq_num}")
                        conn.sendall(pickle.dumps({
                            "ack": seq_num
                        }))
                    else:
                        print(f"ACK {seq_num} ignored.")

                except Exception as e:
                    print("Receiver Error: " + str(e))
                    break

            print("Receiver: Terminating connection!")
            conn.close()
