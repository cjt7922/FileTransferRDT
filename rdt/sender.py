import datetime
import pickle
import socket
import threading
import time

from rdt.util import PrintType, print_info, calculate_checksum


class RDTSender:
    def __init__(self, port: int, timeout=8, dst_address="127.0.0.1"):
        self.src_address = "127.0.0.1"
        self.dst_address = dst_address
        self.recv_port = port
        self.send_port = self.recv_port + 1
        print(f"Sender Ports: [Recv: {self.recv_port}, Send: {self.send_port}]")
        self.recv_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.window_size = 100
        self.seq_num = 0
        self.seq_base = 0
        self.window = {}
        self.received_acks = {}
        self.listener = threading.Thread(target=self.receive_acks)

        self.lock = threading.Lock()
        self.is_sending = False
        self.is_terminated = False

        self.timeout = timeout

    def send_data(self, data: list[bytes]):
        if not self.listener.is_alive():
            self.listener.start()

        self.is_sending = True
        data_list = data.copy()

        try:
            while (len(data_list) > 0 or any(not ack for ack in self.received_acks.values())) and self.is_sending:
                while self.seq_num < self.seq_base + self.window_size and len(data_list) > 0 and self.is_sending:
                    chunk = data_list.pop(0)
                    self.send_packet(self.seq_num, chunk)

                    print(f"Sender: Sent {self.seq_num}")
                    with self.lock:
                        self.window[self.seq_num] = (chunk, datetime.datetime.now())
                        self.received_acks[self.seq_num] = False
                    self.seq_num += 1

                with self.lock:
                    while self.seq_base in self.window and self.received_acks.get(self.seq_base, False) and self.is_sending:
                        del self.received_acks[self.seq_base]
                        del self.window[self.seq_base]
                        self.seq_base += 1

                if self.is_sending:
                    with self.lock:
                        current_time = datetime.datetime.now()
                        for seq in list(self.window.keys()):
                            if (not self.received_acks[seq] and
                                    current_time - self.window[seq][1] > datetime.timedelta(seconds=self.timeout) and
                                    self.is_sending):
                                print(f"Sender: Retransmitting {seq}")
                                self.window[seq] = (self.window[seq][0], datetime.datetime.now())
                                self.send_packet(seq, self.window[seq][0])

                time.sleep(0.1)

            print("Sender: All data sent and acknowledged or connection terminated")
            self.is_sending = False

        except Exception as e:
            print(f"Sender Error: {str(e)}")
        finally:
            self.initiate_termination()

    def send_packet(self, seq_num, data, terminate=False):
        payload = {
            "terminate": terminate,
            "seq": seq_num,
            "data": data,
        }
        initial_payload = pickle.dumps(payload)
        payload["checksum"] = calculate_checksum(initial_payload)
        final_payload = pickle.dumps(payload)

        try:
            self.send_socket.sendto(final_payload, (self.dst_address, self.send_port))
        except Exception as e:
            print(f"Failed to send packet: {e}")
            self.is_sending = False
            self.is_terminated = True

    def receive_acks(self):
        try:
            self.recv_socket.bind((self.src_address, self.recv_port))
            self.recv_socket.settimeout(self.timeout + 5)
        except Exception as e:
            print(e)
            self.recv_socket.close()
            self.is_terminated = True
            self.is_sending = False
            return

        while self.is_sending or not self.is_terminated:
            try:
                data, _ = self.recv_socket.recvfrom(2048)
                if not data:
                    continue
                pkt = pickle.loads(data)

                if "fin_ack" in pkt and pkt["fin_ack"]:
                    print("Sender: Received FIN ACK!")
                    self.is_terminated = True
                    break

                if "ack" in pkt:
                    self.received_acks[pkt["ack"]] = True
                    print(f"Sender: Received ACK {pkt['ack']}")

            except socket.timeout:
                continue
            except OSError as e:
                print(f"Sender: Socket closed or error: {e}")
                break
            except Exception as e:
                print(f"Sender: Exception in receive_acks: {e}")
                break

    def initiate_termination(self):
        if not self.listener.is_alive():
            self.terminate_connection()
            return

        retries = 5
        attempt = 0

        while not self.is_terminated and attempt <= retries:
            print(f"Sender: Sent FIN with SEQ ({self.seq_num}) | Attempt: ({attempt}), awaiting final ACK!")
            try:
                self.send_packet(self.seq_num, b"Connection Termination", True)
            except:
                print("Sender: Error while sending FIN packet.")

            waited = 0.0
            step = 0.1
            while waited < self.timeout and not self.is_terminated:
                time.sleep(step)
                waited += step

            attempt += 1

        self.terminate_connection()

    def terminate_connection(self):
        print("Sender: Closing connection!")
        self.is_sending = False

        try:
            self.send_socket.close()
            self.recv_socket.close()
        except:
            pass

        if self.listener.is_alive() and threading.current_thread() is not self.listener:
            self.listener.join()

        self.is_terminated = True
