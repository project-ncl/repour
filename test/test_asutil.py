import asyncio
import io
import os
import types
import unittest

import aiohttp
import aiohttp.web

import repour.asutil

loop = asyncio.get_event_loop()

class TestDownload(unittest.TestCase):
    foo_bar = io.BytesIO(b"just read the instructions")

    @classmethod
    def setUpClass(cls):
        app = aiohttp.web.Application(loop=loop)

        def write(stream):
            @asyncio.coroutine
            def handler(request):
                resp = aiohttp.web.StreamResponse()
                resp.start(request)

                stream.seek(0)
                while True:
                    buf = stream.read(4096)
                    if not buf:
                        break
                    resp.write(buf)
                    yield from resp.drain()
                yield from resp.write_eof()

                return resp

            return handler

        app.router.add_route("GET", "/foo_bar", write(cls.foo_bar))

        host = "localhost"
        port = 51854
        cls.url = "http://{host}:{port}".format(**locals())
        cls.handler = app.make_handler()
        cls.server = loop.run_until_complete(loop.create_server(cls.handler, host, port))

    @classmethod
    def tearDownClass(cls):
        loop.run_until_complete(cls.handler.finish_connections(0.25))
        cls.server.close()
        loop.run_until_complete(cls.server.wait_closed())

    @staticmethod
    def fake_resp(suggest_filename=None):
        first_call = True
        @asyncio.coroutine
        def fake_read(l):
            nonlocal first_call
            first_call = False
            return b"hello" if first_call else None

        if suggest_filename is None:
            headers = {}
        else:
            headers = {
                aiohttp.hdrs.CONTENT_DISPOSITION: 'attachment; filename="{}"'.format(suggest_filename),
            }

        return types.SimpleNamespace(
            content=types.SimpleNamespace(read=fake_read),
            headers=headers,
        )

    def test_content_disposition(self):
        fake_resp = self.fake_resp(suggest_filename="foo.tar")
        self.assertEqual(repour.asutil._find_filename("bar.zip", fake_resp), "foo.tar")

    def test_basename(self):
        fake_resp = self.fake_resp()
        self.assertEqual(repour.asutil._find_filename("bar.zip", fake_resp), "bar.zip")

    def test_download(self):
        buf = io.BytesIO()
        buf.sync = lambda: None

        loop.run_until_complete(repour.asutil.download(self.url + "/foo_bar", buf))

        self.assertEqual(buf.getvalue(), self.foo_bar.getvalue())
