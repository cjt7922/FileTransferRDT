import pickle
import time
import threading

from sender import TCPClient
from receiver import TCPReceiver
def main():
    simulate_loss()


def simulate_loss():
    receiver_threads = {}

    host_sender = TCPClient(41729)
    test_receiver = TCPReceiver(41729)
    create_connection(host_sender, test_receiver, "test", receiver_threads)
    host_sender.send_data([bytes(f"Message {s}", "utf-8") for s in range(10)])
    host_sender.send_data([bytes(f"Cont. {s}", "utf-8") for s in range(10)])
    host_sender.initiate_termination()
    print(test_receiver.ordered_chunks)

    # test_sender = TCPClient(41730)
    # host_recevier = TCPReceiver(41730)


def create_connection(sender: TCPClient, receiver: TCPReceiver, receiver_name: str, receiver_threads: dict):
    print("Starting Receiver: \"" + receiver_name + "\"")
    receiving_thread = threading.Thread(target=receiver.accept_client)
    receiving_thread.start()
    receiver_threads[receiver_name] = receiving_thread
    time.sleep(1)

    print("Connecting sender to receiver")
    sender.connect_to_receiver()


def send_data(data: list[bytes]):
    sender = TCPClient(41729)
    receiver = TCPReceiver(41729)

    receiving_thread = threading.Thread(target=receiver.accept_client)
    receiving_thread.start()
    time.sleep(1)

    print("Connecting sender to receiver")
    sender.connect_to_receiver()

    print("Sending First Messages!")
    sender.send_data(data)
    print("Receiver has received: " + str(receiver.ordered_chunks))

    sender.initiate_termination()
    receiving_thread.join()





if __name__ == "__main__":
    main()