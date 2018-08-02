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


def simple_formatter(state, filters):
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


def emoji_formatter(state, filters):
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
        nb_away = nb_total - nb_online
        return f'✔️ {nb_online} | 🕘 {nb_away}'
    else:
        return "Error"


FORMATTERS = {
    'emoji': emoji_formatter,
    'simple': simple_formatter,
}


class FileStatusView:
    def __init__(self, fpath, filters=[], formatter=simple_formatter):
        self.fpath = fpath
        self.filters = filters
        self.formatter = formatter
        self.old_state = 'INITIAL_STATE'

    def _writeline(self, text):
        self.file.seek(0)
        self.file.truncate()
        self.file.write(text + '\n')

    def update(self, state):
        if self.old_state != state:
            self.old_state = state
            text = self.formatter(state, self.filters)
            self._writeline(text)

    def __enter__(self):
        self.file = open(self.fpath, 'w', buffering=1)
        self._writeline('-')
        return self

    def __exit__(self, type, value, traceback):
        self._writeline('-')
        self.file.close()


async def mumble_online_client(host, port, status_view):
    timeout = 30
    reader, writer = await wait_for(
        asyncio.open_connection(host, port), timeout
    )
    try:
        data = await wait_for(reader.readline(), timeout)
        params = json.loads(data).get('params')
        logger.debug('Received params: %r' % params)
        timeout = params['max_interval'] + 5

        while True:
            data = await wait_for(reader.readline(), timeout)
            if not data:
                break
            state = json.loads(data)
            status_view.update(state)
            logger.debug('Received: %r' % state)
    finally:
        logger.debug('Close the socket')
        writer.close()


async def reconnect_agent(host, port, status_view):
    status_view.update(None)
    while True:
        logger.debug("Try connecting...")
        try:
            await mumble_online_client(host, port, status_view)
        except (socket.error, asyncio.TimeoutError):
            pass
        status_view.update(None)
        await asyncio.sleep(3)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('host')
    parser.add_argument('port', type=int)
    parser.add_argument('-d', '--debug', action="store_true")
    parser.add_argument(
        '--filters', nargs='+', default=[],
        help="List of ignored pseudonyms"
    )
    parser.add_argument(
        '--formatter', choices=FORMATTERS.keys(), default='emoji'
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(message)s'
    )

    formatter = FORMATTERS[args.formatter]

    base_dir = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp'))
    fpath = base_dir / 'mumble-online-users.txt'
    logger.info(f"Write state in: {fpath}")    

    loop = asyncio.get_event_loop()
    if args.debug:
        loop.set_debug(True)
    with FileStatusView(
        fpath, args.filters, formatter
    ) as status_view:
        loop.run_until_complete(
            reconnect_agent(args.host, args.port, status_view)
        )
    loop.close()
