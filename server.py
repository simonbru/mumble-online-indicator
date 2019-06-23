#!/usr/bin/env python3

import argparse
import json
import logging
import socket
import socketserver
import time
from collections import deque
from queue import Queue
from threading import Thread

import Ice


logger = logging.getLogger(__name__)


def retrieve_server_state():
    try:
        import mice3 as mice
        server = mice.s
        users = server.getUsers()
    except Ice.SocketException:
        return {"error": "offline"}

    final_users = {}
    for session_id, user in users.items():
        final_user = {
            'name': user.name
        }
        if user.deaf or user.selfDeaf:
            final_user['status'] = 'deaf'
        elif user.mute or user.selfMute or user.suppress:
            final_user['status'] = 'mute'
        final_users[session_id] = final_user
    return {
        "users": final_users
    }


def create_request_handler(client_queues, max_interval):
    class RequestHandler(socketserver.StreamRequestHandler):
        disable_nagle_algorithm = True

        def setup(self):
            super().setup()
            self.queue = Queue()
            client_queues.append(self.queue)

        def finish(self):
            super().finish()
            client_queues.remove(self.queue)

        def handle(self):
            message = {'params': {
                'max_interval': max_interval,
            }}
            self._send_message(message)

            state = retrieve_server_state()
            while True:
                self._send_message(state)
                state = self.queue.get()

        def _send_message(self, message):
            data = json.dumps(message)
            self.wfile.write(data.encode() + b'\n')

    return RequestHandler


class TCPServer(socketserver.ThreadingTCPServer):
    address_family = socket.AF_INET6
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        logging.debug("User disconnected: %s", client_address)


def mumble_thread(queues, max_interval, polling_interval):
    max_skips = max_interval // polling_interval
    state = None
    skip_count = 0
    while True:
        old_state = state
        state = retrieve_server_state()
        if skip_count < max_skips and state == old_state:
            skip_count += 1
        else:
            skip_count = 0
            for q in queues.copy():
                q.put(state)
        time.sleep(polling_interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-l', '--host', default='::',
        help="Listening address"
    )
    parser.add_argument('-p', '--port', type=int, default=43223,
        help="Listening port"
    )
    parser.add_argument(
        '-i', '--interval', type=float, default=0.5,
        help="Interval between polls (in seconds)",
    )
    parser.add_argument(
        '--max', type=float, default=30,
        help="Maximum interval in seconds between updates (keep-alive interval)",
    )
    parser.add_argument('-d', '--debug', action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(message)s'
    )

    client_queues = deque()

    thread = Thread(
        target=mumble_thread,
        name="mumble_thread",
        args=(client_queues, args.max, args.interval)
    )
    thread.start()

    request_handler = create_request_handler(
        client_queues, args.max
    )
    with TCPServer((args.host, args.port), request_handler) as server:
        logging.info(
            f"Listening for connections on [{args.host}]:{args.port}"
        )
        server.serve_forever()
