#!/usr/bin/env python2
# -*- coding: utf-8
from __future__ import absolute_import, print_function

import itertools
import os
import re
import socket
import sys
import time
from datetime import datetime
from subprocess import check_output

import mice

SYSTEMD_FIRST_SOCKET_FD = 3

sock = socket.fromfd(
    SYSTEMD_FIRST_SOCKET_FD, socket.AF_INET, socket.SOCK_STREAM
)
while True:
    sock.sendall(b"test\n")
    time.sleep(1)
