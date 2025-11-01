from rdt.sender import RDTSender

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    while True:
        try:
            user_in = input("Enter absolute path of file to transfer: ")
            chunks = []

            with open(user_in, "rb") as file:
                data = file.read()
                print(len(data))

                i, chunk_rate = 0, 1000
                while i < len(data):

                    chunk = i + chunk_rate
                    if chunk <= len(data):
                        print(i, len(data[i:chunk]), data[i:chunk])
                        chunks.append(data[i:chunk])
                    else:
                        print(i, len(data[i:]), data[i:])
                        chunks.append(data[i:])

                    i += chunk_rate

                print(len(chunks))

            sender = RDTSender(port=41729)
            sender.send_data(chunks)
            print("File transferred!")

        except KeyboardInterrupt:
            break
        except FileNotFoundError as e:
            print(e)
            continue







if __name__ == "__main__":
    main()