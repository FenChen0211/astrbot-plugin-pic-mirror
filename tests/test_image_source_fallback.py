"""Regression tests for per-image source fallback handling."""

import asyncio
import logging
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "picmirror_test_package"


def install_astrbot_stubs():
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    components = types.ModuleType("astrbot.api.message_components")
    star = types.ModuleType("astrbot.api.star")

    class Image:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class Reply:
        def __init__(self, chain=None):
            self.chain = chain or []

    class At:
        pass

    class Plain:
        def __init__(self, text=""):
            self.text = text

    components.Image = Image
    components.Reply = Reply
    components.At = At
    components.Plain = Plain
    api.logger = logging.getLogger("picmirror-test")
    api.message_components = components
    star.StarTools = type("StarTools", (), {})

    sys.modules.update(
        {
            "astrbot": astrbot,
            "astrbot.api": api,
            "astrbot.api.message_components": components,
            "astrbot.api.star": star,
        }
    )


install_astrbot_stubs()
package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE_NAME] = package

from picmirror_test_package.core.image_handler import ImageHandler
from picmirror_test_package.utils.message_utils import MessageUtils
import picmirror_test_package.utils.message_utils as message_utils_module


class FakeEvent:
    def __init__(self, image):
        self.image = image

    def get_messages(self):
        return [self.image]

    def get_sender_id(self):
        return "test-user"

    def plain_result(self, message):
        return ("plain", message)


class ImageSourceFallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.local_source = "/missing/astrbot/media_image_preview.jpg"
        self.url_source = "https://example.com/original.png"
        self.image = message_utils_module.Comp.Image(
            path=self.local_source,
            url=self.url_source,
        )

    def make_handler(self, prepared_sources, processed_sources):
        handler = ImageHandler.__new__(ImageHandler)
        handler.config = SimpleNamespace(enable_at_avatar=False, silent_mode=True)
        handler.message_utils = MessageUtils()
        handler._processing_semaphore = asyncio.Semaphore(1)
        handler._last_prepare_error = None

        async def check_rate_limit(_user_id):
            return True, None

        async def prepare_image_file(source, _trusted_paths):
            prepared_sources.append(source)
            if source == self.local_source and self.fail_local_source:
                handler._last_prepare_error = "local cache missing"
                return None
            return Path(f"prepared-{len(prepared_sources)}.png")

        async def process_single_image(_event, _input_path, _mode, source):
            processed_sources.append(source)
            yield ("processed", source)

        handler.check_rate_limit = check_rate_limit
        handler._prepare_image_file = prepare_image_file
        handler._process_single_image = process_single_image
        handler._get_error_message = lambda _event, message, detail=None: (
            "error",
            message,
            detail,
        )
        return handler

    async def test_falls_back_to_url_when_local_candidate_cannot_prepare(self):
        self.fail_local_source = True
        prepared_sources = []
        processed_sources = []
        handler = self.make_handler(prepared_sources, processed_sources)

        results = [
            result
            async for result in handler.process_mirror(FakeEvent(self.image), "left")
        ]

        self.assertEqual(prepared_sources, [self.local_source, self.url_source])
        self.assertEqual(processed_sources, [self.url_source])
        self.assertEqual(results, [("processed", self.url_source)])

    async def test_does_not_process_url_after_local_candidate_prepares(self):
        self.fail_local_source = False
        prepared_sources = []
        processed_sources = []
        handler = self.make_handler(prepared_sources, processed_sources)

        results = [
            result
            async for result in handler.process_mirror(FakeEvent(self.image), "left")
        ]

        self.assertEqual(prepared_sources, [self.local_source])
        self.assertEqual(processed_sources, [self.local_source])
        self.assertEqual(results, [("processed", self.local_source)])


if __name__ == "__main__":
    unittest.main()
