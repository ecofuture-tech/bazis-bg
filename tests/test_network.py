# Copyright 2026 EcoFuture Technology Services LLC and contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The health check server of the background processes (`bazis.contrib.bg.network`)."""

import socket
import subprocess
import sys
import textwrap

import pytest

from bazis.contrib.bg.network import check_port, healthcheck_server


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def test_check_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        sock.listen()
        port = sock.getsockname()[1]
        assert not check_port(port, host='127.0.0.1')
    assert check_port(port, host='127.0.0.1')


def test_healthcheck_server():
    # in a process of its own: the server sets the event loop policy of the process
    port = free_port()
    script = textwrap.dedent(
        f"""
        import time
        from urllib.request import urlopen

        from aiohttp import web

        from bazis.contrib.bg.network import healthcheck_server

        async def pid(request):
            return web.Response(text='42')

        healthcheck_server('127.0.0.1', {port}, pid=pid)
        for _ in range(50):
            try:
                assert urlopen('http://127.0.0.1:{port}/healthcheck').status == 200
                break
            except OSError:
                time.sleep(0.1)
        print(urlopen('http://127.0.0.1:{port}/pid').read().decode())
        """
    )
    result = subprocess.run(
        [sys.executable, '-c', script], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '42'


def test_healthcheck_server_on_a_busy_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        sock.listen()
        with pytest.raises(Exception, match='is busy'):
            healthcheck_server('127.0.0.1', sock.getsockname()[1])


def test_the_module_of_the_core_is_deprecated():
    sys.modules.pop('bazis.core.utils.network', None)
    with pytest.warns(DeprecationWarning, match='bazis.contrib.bg.network'):
        from bazis.core.utils import network
    assert network.healthcheck_server is healthcheck_server
