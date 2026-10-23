"""Bound decoded image resources without rewriting source evidence bytes."""
from io import BytesIO

from PIL import Image, UnidentifiedImageError

MAX_PIXELS = 20_000_000
MAX_SIDE = 10_000


def validate_image(data, mime_type):
    try:
        with Image.open(BytesIO(data), formats=['PNG', 'JPEG']) as image:
            expected = 'PNG' if mime_type == 'image/png' else 'JPEG'
            if image.format != expected:
                raise ValueError('Image format does not match declared MIME type')
            if (image.width > MAX_SIDE or image.height > MAX_SIDE or
                    image.width * image.height > MAX_PIXELS):
                raise ValueError('Image exceeds 20 megapixels or 10000 pixels per side')
            if getattr(image, 'n_frames', 1) != 1:
                raise ValueError('Animated images are not supported')
            image.verify()
        # verify checks structure/PNG CRC; load also forces decompression of pixel data.
        with Image.open(BytesIO(data), formats=['PNG', 'JPEG']) as image:
            image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError('Invalid, truncated or unsafe PNG/JPEG image') from exc
