import base64
from io import BytesIO
import unittest
from unittest.mock import patch

from PIL import Image
from app.image_validation import validate_image


def encoded(fmt='PNG', size=(8, 8)):
    output = BytesIO()
    Image.new('RGB', size, 'red').save(output, format=fmt)
    return output.getvalue()


class ImageValidationTests(unittest.TestCase):
    def test_valid_evidence_remains_unchanged(self):
        for fmt, mime in [('PNG', 'image/png'), ('JPEG', 'image/jpeg')]:
            data = encoded(fmt)
            original = bytes(data)
            validate_image(data, mime)
            self.assertEqual(data, original)

    def test_corruption_truncation_and_mime_mismatch(self):
        bad_crc = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
        cases = [(bad_crc, 'image/png'), (b'\x89PNG\r\n\x1a\n' + b'fake', 'image/png'),
                 (encoded('JPEG')[:-20], 'image/jpeg'), (encoded(), 'image/jpeg')]
        for data, mime in cases:
            with self.subTest(mime=mime, size=len(data)), self.assertRaises(ValueError):
                validate_image(data, mime)

    def test_pixel_and_side_limits_checked_before_decode(self):
        data = encoded(size=(11, 10))
        with patch('app.image_validation.MAX_PIXELS', 100), self.assertRaises(ValueError):
            validate_image(data, 'image/png')
        with patch('app.image_validation.MAX_SIDE', 10), self.assertRaises(ValueError):
            validate_image(data, 'image/png')

    def test_animation_is_not_single_frame_evidence(self):
        out = BytesIO()
        Image.new('RGB', (8, 8), 'red').save(out, format='PNG', save_all=True,
            append_images=[Image.new('RGB', (8, 8), 'blue')], duration=100)
        with self.assertRaisesRegex(ValueError, 'Animated'):
            validate_image(out.getvalue(), 'image/png')
