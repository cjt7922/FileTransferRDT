import argparse
import errno
import pickle
import random
import socket
import threading
import time

from util import PrintType, print_info
from receiver import TCPReceiver
from sender import TCPClient


class Intermediary:
    def __init__(self,
                 sender_client: TCPClient,
                 receiver_client: TCPReceiver,
                 drop_prob: float | None = None,
                 delay_range: tuple[float] | None = None,
                 corrupt_pkts: float | None = None):

        # Network simulation params
        self.drop_prob = drop_prob
        self.delay_range = delay_range
        self.corrupt_pkts = corrupt_pkts
        print_info(f"[Drop Prob: {self.drop_prob}, Delay Range: {self.delay_range}, Corrupt Prob: {self.corrupt_pkts}]", PrintType.INFO)

        self.sender_client = sender_client
        self.receiver_client = receiver_client

        # Ports
        self.sender_recv_port = sender_client.recv_port
        self.sender_send_port = sender_client.send_port
        self.receiver_recv_port = receiver_client.recv_port
        self.receiver_send_port = receiver_client.send_port

        print(f"Ports | Receiver: [Recv: {self.receiver_recv_port}, Send: {self.receiver_send_port}] "
              f"| Sender: [Recv: {self.sender_recv_port}, Send: {self.sender_send_port}]")

        # Threading and shutdown
        self.shutdown_event = threading.Event()
        self.lock = threading.Lock()

        # Sockets
        self.sender_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sender_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.receiver_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.receiver_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Threads
        self.sending_thread = threading.Thread(target=self.sender_listener, daemon=True)
        self.receiving_thread = threading.Thread(target=self.receiver_listener, daemon=True)

    def start(self):
        """Start the intermediary"""
        try:
            # Bind sockets safely
            self.sender_socket.bind(("127.0.0.1", self.sender_send_port))
            self.receiver_socket.bind(("127.0.0.1", self.receiver_send_port))

            print_info(f"Listening for sender on port {self.sender_send_port}", PrintType.INFO)
            print_info(f"Listening for receiver on port {self.receiver_send_port}", PrintType.INFO)

            # Start listener threads
            self.sending_thread.start()
            self.receiving_thread.start()
            return True

        except Exception as e:
            print_info(f"Failed to start intermediary: {e}", PrintType.ERROR)
            self.shutdown()
            return False

    def sender_listener(self):
        """Listen for data from sender and forward to receiver"""
        print("Sender listener started")
        while not self.shutdown_event.is_set():
            try:
                # Add timeout to allow checking shutdown event
                self.sender_socket.settimeout(1.0)
                pkt, addr = self.sender_socket.recvfrom(2048)

                if not pkt:
                    print_info("Empty packet from sender", PrintType.INFO)
                    continue

                print_info(f"Received data packet from {addr}", PrintType.INFO)

                if self.drop_prob and random.random() < self.drop_prob:
                    print_info("Dropping Packet!", PrintType.CONDITION)
                    continue

                if self.corrupt_pkts and random.random() < self.corrupt_pkts:
                    data = pickle.loads(pkt)
                    if "checksum" in data:
                        data["checksum"] += 1
                    pkt = pickle.dumps(data)

                # Simulate packet delay
                if self.delay_range:
                    delay = random.uniform(self.delay_range[0], self.delay_range[1])
                    time.sleep(delay)

                # Forward to receiver
                if not self.shutdown_event.is_set():
                    self.receiver_socket.sendto(pkt, ("127.0.0.1", self.receiver_recv_port))
                    print_info(f"Forwarded data to receiver port {self.receiver_recv_port}", PrintType.INFO)

            except socket.timeout:
                continue  # Normal - check shutdown event
            except socket.error as e:
                if e.errno in [10054, 10053, 10022]:  # Connection errors
                    print_info(f"Receiver closed connection!", PrintType.INFO)
                    break
            except Exception as e:
                print_info(f"Error in sender listener: {e}", PrintType.ERROR)
                break

        self.sender_client.terminate_connection()
        print("Sender listener stopped")

    def receiver_listener(self):
        print("Receiver listener started")
        while not self.shutdown_event.is_set():
            try:
                # Add timeout to allow checking shutdown event
                self.receiver_socket.settimeout(1.0)
                ack_pkt, addr = self.receiver_socket.recvfrom(4096)

                if not ack_pkt:
                    print_info("Empty ACK from receiver", PrintType.INFO)
                    continue

                print_info(f"Received ACK from {addr}", PrintType.INFO)

                # Simulate ACK loss
                if self.drop_prob and random.random() < self.drop_prob:
                    print_info("Dropping ACK!", PrintType.CONDITION)
                    continue

                # Simulate ACK delay
                if self.delay_range:
                    delay = random.uniform(self.delay_range[0], self.delay_range[1])
                    time.sleep(delay)

                # Forward ACK to sender
                if not self.shutdown_event.is_set():
                    self.sender_socket.sendto(ack_pkt, ("127.0.0.1", self.sender_recv_port))
                    print_info(f"Forwarded ACK to sender port {self.sender_recv_port}", PrintType.INFO)

            except socket.timeout:
                continue  # Normal - check shutdown event
            except socket.error as e:
                if e.errno in [10054, 10053, 10022]:  # Connection errors
                    print_info(f"Receiver connection error: {e}", PrintType.INFO)
                    #self.sender_client.terminate_connection()
                    self.shutdown_event.set()  # Just set the event, don't call shutdown
                    break
            except Exception as e:
                print_info(f"Error in receiver listener: {e}", PrintType.ERROR)
                self.shutdown_event.set()  # Just set the event, don't call shutdown
                break

        print("Receiver listener stopped")

    def shutdown(self):
        """Gracefully shutdown the intermediary"""
        if self.shutdown_event.is_set():
            return  # Already shutting down

        print_info("Intermediary shutting down...", PrintType.INFO)
        self.shutdown_event.set()

        # Close sockets to unblock recvfrom()
        try:
            self.sender_socket.close()
            print("Sender socket closed")
        except Exception as e:
            print_info(f"Error closing sender socket: {e}", PrintType.ERROR)

        try:
            self.receiver_socket.close()
            print("Receiver socket closed")
        except Exception as e:
            print_info(f"Error closing receiver socket: {e}", PrintType.ERROR)

        # Join threads safely
        current_thread = threading.current_thread()

        if current_thread != self.receiving_thread and self.receiving_thread.is_alive():
            self.receiving_thread.join(timeout=2.0)

        if current_thread != self.sending_thread and self.receiving_thread.is_alive():
            self.receiving_thread.join(timeout=2.0)

        print_info("Intermediary shutdown complete", PrintType.INFO)


def parse_args():
    parser = argparse.ArgumentParser(
        prog="RDT Network Tester",
        description="Tests the RDT protocol against various network conditions."
    )

    # Optional float between 0 and 1
    parser.add_argument(
        "-d",
        "--drop",
        type=float,
        default=None,
        help="Packet drop probability (0.0 - 1.0). Default: 0.0",
    )

    # Optional tuple for delay range (two floats)
    parser.add_argument(
        "-w",
        "--delay",
        type=float,
        nargs=2,
        default=None,
        help="Range of artificial delay in seconds (e.g., --delay 0 3). Default: (0, 0)",
    )

    # Optional corruption flag
    parser.add_argument(
        "-c",
        "--corrupt",
        type=float,
        default=None,
        help="Enable packet corruption simulation (0.0 - 1.0). Default: 0.0",
    )

    args = parser.parse_args()
    print(args)

    # Validation
    if args.drop is not None and not (0.0 <= args.drop <= 1.0):
        parser.error("--drop must be between 0 and 1.")

    if args.corrupt is not None and not (0.0 <= args.corrupt <= 1.0):
        parser.error("--corrupt must be between 0 and 1.")

    if args.delay is not None and not (args.delay[0] >= 0 or args.delay[1] <= 0 or args.delay[0] < args.delay[1]):
        parser.error("--delay must be two non-negative numbers where MIN <= MAX.")

    return args

def main():
    args = parse_args()
    print(args)

    test_data = [
        b"LeBron James stepped onto the court with that familiar calm intensity, ",
        b"like a king surveying his kingdom before battle. ",
        b"The crowds roar swelled to a thunder as the ball hit his hands, one bounce, two bounces, ",
        b"and the game slowed down. ",
        b"With a quick crossover and a burst of power, he soared toward the rim, ",
        b"time itself pausing just long enough for everyone to realize ",
        b"they were witnessing greatness again. ",
        b"When the dunk landed, so did the cheers,",
        b"echoing through the arena like history being written in real time."
    ]

    # Start receiver
    receiver = TCPReceiver(41735)
    receiver_thread = threading.Thread(target=receiver.accept_client, daemon=True)
    receiver_thread.start()
    print_info("Receiver started", PrintType.INFO)

    time.sleep(1)

    # Create sender
    cont = sender = TCPClient(41729)
    if not cont:
        return
    print_info("Sender created", PrintType.INFO)

    # Start intermediary
    tester = Intermediary(
        sender_client=sender,
        receiver_client=receiver,
        drop_prob=args.drop,
        delay_range=args.delay,
        corrupt_pkts=args.corrupt
    )
    try:
        tester.start()
    except Exception as e:
        tester.shutdown()

    print_info("Intermediary started", PrintType.INFO)

    time.sleep(1)

    # Send data
    print("Starting data transfer...")
    sender.send_data(test_data)
    print("Sent Data!")

    max_wait = 5
    attempt = 0
    while (sender.is_sending or receiver.is_receiving) and max_wait >= attempt:
        time.sleep(1)
        attempt += 1

    # Cleanup
    tester.shutdown()

    # Reconstruct the message
    full_message = b''.join(receiver.ordered_chunks)
    print(f"\nFull reconstructed message: {full_message.decode()}")
    print("Test completed")


if __name__ == "__main__":
    main()