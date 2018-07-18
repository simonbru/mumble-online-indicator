#!/usr/bin/env python3

import argparse
import asyncio
import json
import logging
import os
import socket
import sys
import types
from asyncio import wait_for
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


def state_formatter(state, filters):
    if state is None:
        return 'Offline'
    elif 'error' in state:
        return 'Server down'
    elif 'users' in state:
        users = [
            user for user in state['users'].values()
            if user['name'] not in filters
        ]
        nb_total = len(users)
        nb_online = sum(
            1 for u in users
            if u.get('status') not in ('deaf', 'mute')
        )
        return f'Online: {nb_online}/{nb_total}'
    else:
        return "Error"


class StateWriter:
    def __init__(self, fpath, filters=[]):
        self.fpath = fpath
        self.filters = filters
        self.old_state = None

    def _writeline(self, text):
        self.file.seek(0)
        self.file.truncate()
        self.file.write(text + '\n')

    def update(self, state):
        if self.old_state != state:
            self.old_state = state
            text = state_formatter(state, self.filters)
            self._writeline(text)

    def __enter__(self):
        self.file = open(self.fpath, 'w', buffering=1)
        self._writeline('-')
        return self

    def __exit__(self, type, value, traceback):
        self._writeline('-')
        self.file.close()


async def mumble_online_client(host, port, state_writer):
    timeout = 30
    reader, writer = await wait_for(
        asyncio.open_connection(host, port), timeout
    )
    try:
        data = await wait_for(reader.readline(), timeout)
        params = json.loads(data).get('params')
        logger.debug('Received params: %r' % params)
        timeout = params['max_skip_time'] + 5

        while True:
            data = await wait_for(reader.readline(), timeout)
            if not data:
                break
            state = json.loads(data)
            state_writer.update(state)
            logger.debug('Received: %r' % state)
    finally:
        logger.debug('Close the socket')
        writer.close()


async def reconnect_agent(host, port, writer):
    writer.update(None)
    while True:
        logger.debug("Try connecting...")
        try:
            await mumble_online_client(host, port, writer)
        except (socket.error, asyncio.TimeoutError):
            pass
        writer.update(None)
        await asyncio.sleep(2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('host')
    parser.add_argument('port', type=int)
    parser.add_argument('-d', '--debug', action="store_true")
    parser.add_argument('--filters', nargs='+', default=[])
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(message)s'
    )
    
    base_dir = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp'))
    fpath = base_dir / 'mumble-online-users.txt'
    logger.info(f"Write state in: {fpath}")    

    loop = asyncio.get_event_loop()
    if args.debug:
        loop.set_debug(True)
    with StateWriter(fpath, args.filters) as state_writer:
        loop.run_until_complete(
            reconnect_agent(args.host, args.port, state_writer)
        )
    loop.close()
