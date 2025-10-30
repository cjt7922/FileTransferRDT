import datetime
import pickle
import threading
import time
from enum import Enum
import socket
from tcp_packet import construct_tcp_packet


class TCPClient:
    def __init__(self, port: int, timeout=3, dst_address="127.0.0.1"):
        self.src_address = "127.0.0.1"  # socket.gethostbyname(socket.gethostname())
        self.dst_address = dst_address
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # self.socket.settimeout(1)

        self.window_size = 4
        self.seq_num = 0
        self.seq_base = 0
        self.seq_max = self.window_size + 1
        self.window = {}
        self.received_acks = {}
        self.listener = threading.Thread(target=self.receive_acks)

        self.lock = threading.Lock()
        self.is_sending = False
        self.is_terminated = False

        self.timeout = timeout
        self.data = None
        self.chunk_number = 1

    def initialize_sending_parameters(self):
        self.window_size = 4
        self.seq_num = 0
        self.seq_base = 0
        self.window = {}
        self.received_acks = {}

    def connect_to_receiver(self):
        self.socket.connect((self.dst_address, self.port))
        if not self.listener.is_alive():
            self.listener.start()
        self.is_sending = True

    def send_data(self, data: list[bytes]):
        try:
            while self.seq_base < len(data) or any(not ack for ack in self.received_acks.values()):
                while self.seq_num < self.seq_base + self.window_size and self.seq_num < len(data):
                    print(f"Sender: Sent {self.seq_num}")
                    self.send_packet(self.seq_num, data[self.seq_num])
                    with self.lock:
                        self.window[self.seq_num] = (data[self.seq_num], datetime.datetime.now())
                        self.received_acks[self.seq_num] = False
                    self.seq_num += 1
                    # time.sleep(0.1)

                with self.lock:
                    while self.seq_base in self.window and self.received_acks.get(self.seq_base, False):
                        del self.received_acks[self.seq_base]
                        del self.window[self.seq_base]
                        self.seq_base += 1

                with self.lock:
                    for seq in self.window.keys():
                        if not self.received_acks[seq] and datetime.datetime.now() - self.window[seq][1] > datetime.timedelta(seconds=self.timeout):
                            print(f"Sender: Retransmitting {seq}")
                            self.send_packet(seq, self.window[seq][0])

                time.sleep(0.05)

        except Exception as e:
            print("Sender Error" + str(e))

    def send_packet(self, seq_num, data, terminate=False):
        payload = {
            "fin": terminate,
            "seq": seq_num,
            "data": data
        }
        serialized_pl = pickle.dumps(payload)
        try:
            pkt_len = len(serialized_pl).to_bytes(4, "big")
            self.socket.sendall(pkt_len + serialized_pl)
        except Exception as e:
            print(f"Failed to send packet: {e}")
            return

    def receive_acks(self):
        while self.is_sending or not self.is_terminated:
            try:
                data = self.socket.recv(2048)
                if len(data) == 0:
                    break
                pkt = pickle.loads(data)

                if "fin_ack" in pkt and pkt["fin_ack"]:
                    print("Sender: Received FIN ACK!")
                    self.__terminate_connection()
                    break

                self.received_acks[pkt["ack"]] = True
                print("Sender: Received ACK " + str(pkt["ack"]))

            except socket.timeout:
                continue
            except (ConnectionResetError, ConnectionAbortedError):
                break

    def initiate_termination(self):
        if self.listener.is_alive():
            print(f"Sender: Sent FIN with SEQ ({self.seq_num}), awaiting final ACK!")
            self.send_packet(self.seq_num, b"Connection Termination", True)
            while not self.is_terminated:
                time.sleep(1)
            self.listener.join()
        else:
            raise threading.ThreadError("Listener thread is not running!")

    def __terminate_connection(self):
        print("Sender: Closing connection!")
        self.is_sending = False
        self.is_terminated = True
        self.socket.close()
