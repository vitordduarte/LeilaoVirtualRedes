import socket
import json
import threading
import time
import logging

PORTA_TCP = 12346
PORTA_UDP = 12347

IP_SERVIDOR = "127.0.0.1"


# Socket TCP
cliente_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Socket UDP
cliente_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)