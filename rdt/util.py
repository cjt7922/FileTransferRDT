from enum import Enum


class PrintType(Enum):
    INFO = '\033[93m'
    ERROR = '\033[91m'
    CONDITION = '\033[33m'


def print_info(message: str, print_type: PrintType):
    print(f"{print_type.value}{message}\033[0m")


def calculate_checksum(data: bytes) -> int:
    if len(data) % 2 == 1:
        data += b'\x00'

    checksum = 0
    for i in range(0, len(data), 2):
        word = (data[i] << 8) + data[i + 1]
        checksum += word
        checksum = (checksum & 0xFFFF) + (checksum >> 16)  # carry around

    return ~checksum & 0xFFFF
