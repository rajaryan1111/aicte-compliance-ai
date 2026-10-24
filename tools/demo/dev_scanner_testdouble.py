#!/usr/bin/env python3
"""TEST DOUBLE — NOT A MALWARE SCANNER. NOT A SECURITY CONTROL.

    ############################################################
    #                                                          #
    #   THIS PROGRAM PERFORMS NO MALWARE SCANNING WHATSOEVER.  #
    #   It answers "clean" to every input. It exists only so a #
    #   LOCAL DEMO can exercise the document-intake pipeline    #
    #   when no real scanner is installed.                     #
    #                                                          #
    #   NEVER run this against anything but a local demo        #
    #   database, and never point production configuration at   #
    #   it. The product's real gate remains fail-closed: with   #
    #   no CLAMAV_HOST the backend quarantines every upload.    #
    #                                                          #
    ############################################################

It implements just enough of the clamd INSTREAM socket protocol for the backend's
ClamAVScanner client to receive an "OK" verdict:

    <zINSTREAM\0><len:uint32><chunk>...<0:uint32>   ->   "stream: OK\0"

USAGE (local demo only)
    python tools/demo/dev_scanner_testdouble.py --port 3310
    # then start the API with CLAMAV_HOST=127.0.0.1 CLAMAV_PORT=3310
"""
from __future__ import annotations

import argparse
import socket
import struct
import threading

BANNER = "*** TEST DOUBLE: performs NO scanning; returns OK to every input ***"


def _recv_exact(conn: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        part = conn.recv(n - len(buf))
        if not part:
            return buf
        buf += part
    return buf


def handle(conn: socket.socket) -> None:
    try:
        command = b""
        while not command.endswith(b"\0"):
            byte = conn.recv(1)
            if not byte:
                return
            command += byte

        if not command.startswith(b"zINSTREAM"):
            conn.sendall(b"UNKNOWN COMMAND\0")
            return

        while True:
            header = _recv_exact(conn, 4)
            if len(header) < 4:
                return
            (size,) = struct.unpack(">I", header)
            if size == 0:
                break
            if len(_recv_exact(conn, size)) < size:
                return

        conn.sendall(b"stream: OK\0")
    except OSError:
        pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="clamd-protocol test double. NO SCANNING.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3310)
    args = parser.parse_args()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(16)
    print(BANNER, flush=True)
    print(f"listening on {args.host}:{args.port} — answers 'stream: OK' to everything", flush=True)

    try:
        while True:
            conn, _ = server.accept()
            threading.Thread(target=handle, args=(conn,), daemon=True).start()
    except KeyboardInterrupt:
        print("\nstopped", flush=True)
    finally:
        server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
