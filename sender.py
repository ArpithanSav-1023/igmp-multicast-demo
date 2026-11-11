import socket
import time
import sys

GROUP = sys.argv[1]
PORT = 5000
SENDER_NAME = sys.argv[2]

INTERFACE = "192.168.1.10"

sock = socket.socket(
    socket.AF_INET,
    socket.SOCK_DGRAM,
    socket.IPPROTO_UDP
)

sock.setsockopt(
    socket.IPPROTO_IP,
    socket.IP_MULTICAST_IF,
    socket.inet_aton(INTERFACE)
)

sock.setsockopt(
    socket.IPPROTO_IP,
    socket.IP_MULTICAST_TTL,
    1
)

counter = 0

print(f"{SENDER_NAME} transmitting to {GROUP}:{PORT}")

try:
    while True:
        message = f"{SENDER_NAME} | Group={GROUP} | Packet={counter}"

        sock.sendto(message.encode(), (GROUP, PORT))

        print(f"Sent: {message}")

        counter += 1
        time.sleep(1)

except KeyboardInterrupt:
    print("\nSender stopped.")
finally:
    sock.close()
