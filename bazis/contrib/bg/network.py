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

"""
The health check server of the background processes (bg_handler, bg_scheduler); it moved
here from bazis.core.utils.network (bazis 2.16) with the dependency aiohttp.
"""

import asyncio
import socket
import threading

import uvloop
from aiohttp import web


def check_port(port, host='localhost') -> bool:
    """
    Check if a given port on the specified host is free.

    Tags: RAG, EXPORT
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex((host, port))
    is_free = result != 0
    sock.close()
    return is_free


def healthcheck_server(host, port, **endpoints):
    """
    Start a simple healthcheck server with custom endpoints in a separate thread.

    Tags: RAG, EXPORT
    """

    async def healthcheck(r):
        return web.Response()

    app = web.Application()
    app.router.add_get('/healthcheck', healthcheck)

    for ep_name, ep_func in endpoints.items():
        app.router.add_get(f'/{ep_name}', ep_func)

    async def thead_worker():
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()

    if not check_port(port, host=host):
        raise Exception(f'Handler cannot run. Address [{host}, {port}] is busy.')

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = asyncio.new_event_loop()
    loop.create_task(thead_worker())

    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()
