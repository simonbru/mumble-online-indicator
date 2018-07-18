#!/usr/bin/env python3

import json
import socket
import socketserver
import time
from collections import deque
from queue import Queue
from threading import Thread

import Ice

import mice3 as mice


LISTEN_ADDRESS = ("::", 43223)
POLLING_TIME = 0.5
MAX_SKIP_TIME = 30


def retrieve_server_state():
    try:
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


def create_request_handler(client_queues):
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
            data = {'params': {
                'max_skip_time': MAX_SKIP_TIME,
            }}
            params_output = json.dumps(data).encode() + b'\n'
            self.wfile.write(params_output)

            state = retrieve_server_state()
            while True:
                output = json.dumps(state).encode() + b'\n'
                self.wfile.write(output)
                state = self.queue.get()

    return RequestHandler


class TCPServer(socketserver.ThreadingTCPServer):
    address_family = socket.AF_INET6
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        print("User disconnected:", client_address)


def mumble_thread(queues):
    max_skips = MAX_SKIP_TIME // POLLING_TIME
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
        time.sleep(POLLING_TIME)


if __name__ == "__main__":
    client_queues = deque()

    thread = Thread(
        target=mumble_thread,
        name="mumble_thread",
        args=(client_queues,)
    )
    thread.start()

    request_handler = create_request_handler(client_queues)
    with TCPServer(LISTEN_ADDRESS, request_handler) as server:
        address, port = LISTEN_ADDRESS
        print(f"Listening for connections on: {port}")
        server.serve_forever()
