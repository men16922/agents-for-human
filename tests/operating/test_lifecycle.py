import socket

import pytest

from rehearsal.operating.local import check_port


def test_restart_probe_accepts_time_wait_but_rejects_live_listener():
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.listen()
        with pytest.raises(OSError):
            check_port(port)
        with socket.create_connection(("127.0.0.1", port)) as client:
            accepted, _ = server.accept()
            accepted.close()  # Server actively closes, entering TIME_WAIT after the peer closes.
            assert client.recv(1) == b""
    check_port(port)
