"""Offline tests for the AniList cover cache."""

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aniyori.services.covers import MAX_COVER_BYTES, get_cached_cover, _prune_cache


class ImageResponse(io.BytesIO):
    def __init__(self, data, content_type="image/jpeg"):
        super().__init__(data)
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class CoverCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temp_dir.name) / "covers"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_downloads_and_caches_cover(self):
        payload = b"fake-image-data"
        with patch(
            "aniyori.services.covers.urlopen",
            return_value=ImageResponse(payload),
        ) as open_url:
            first = get_cached_cover(
                "https://s4.anilist.co/file/cover.jpg", cache_dir=self.cache_dir
            )
            second = get_cached_cover(
                "https://s4.anilist.co/file/cover.jpg", cache_dir=self.cache_dir
            )

        self.assertEqual(first, second)
        self.assertEqual(first.read_bytes(), payload)
        open_url.assert_called_once()

    def test_rejects_non_anilist_or_non_https_urls(self):
        for url in (
            "http://s4.anilist.co/file/cover.jpg",
            "https://example.com/cover.jpg",
            "https://anilist.co.example.com/cover.jpg",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                get_cached_cover(url, cache_dir=self.cache_dir)

    def test_rejects_non_image_response(self):
        with patch(
            "aniyori.services.covers.urlopen",
            return_value=ImageResponse(b"not-an-image", "text/html"),
        ):
            with self.assertRaisesRegex(ValueError, "did not return an image"):
                get_cached_cover(
                    "https://s4.anilist.co/file/cover.jpg", cache_dir=self.cache_dir
                )

    def test_rejects_oversized_response(self):
        with patch(
            "aniyori.services.covers.urlopen",
            return_value=ImageResponse(b"x" * (MAX_COVER_BYTES + 1)),
        ):
            with self.assertRaisesRegex(ValueError, "8 MiB"):
                get_cached_cover(
                    "https://s4.anilist.co/file/cover.jpg", cache_dir=self.cache_dir
                )

    def test_cover_cache_prunes_oldest_files_when_over_limit(self):
        first = self.cache_dir / "first.img"
        second = self.cache_dir / "second.img"
        first.parent.mkdir(parents=True)
        first.write_bytes(b"123456")
        second.write_bytes(b"abcdef")
        first.touch()
        second.touch()
        os.utime(first, (1, 1))
        os.utime(second, (2, 2))
        with patch("aniyori.services.covers.MAX_COVER_CACHE_BYTES", 8):
            _prune_cache(self.cache_dir)
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())

    def test_failed_download_does_not_leave_cache_file(self):
        with patch(
            "aniyori.services.covers.urlopen",
            return_value=ImageResponse(b"", "image/jpeg"),
        ):
            with self.assertRaisesRegex(ValueError, "empty cover"):
                get_cached_cover(
                    "https://s4.anilist.co/file/cover.jpg", cache_dir=self.cache_dir
                )
        self.assertFalse(list(self.cache_dir.glob("*.img")) if self.cache_dir.exists() else [])


if __name__ == "__main__":
    unittest.main()
