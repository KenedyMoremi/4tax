import hashlib
import io
import warnings
from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 3 * 1024 * 1024
MAX_PIXELS = 16_000_000


def prepare_images(files):
    if not 1 <= len(files) <= 3 or sum(f.size for f in files) > MAX_BYTES:
        raise ValidationError('Upload 1–3 screenshots, no more than 3 MB in total.')
    images, digests = [], []
    for upload in files:
        raw = upload.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValidationError('Screenshots must total no more than 3 MB.')
        digests.append(hashlib.sha256(raw).hexdigest())
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as source:
                    if source.format not in {'PNG', 'JPEG', 'WEBP'} or getattr(source, 'n_frames', 1) != 1:
                        raise ValidationError('Use a static PNG, JPEG or WebP screenshot.')
                    if source.width * source.height > MAX_PIXELS:
                        raise ValidationError('Each screenshot must be no larger than 16 megapixels.')
                    source.verify()
                with Image.open(io.BytesIO(raw)) as source:
                    source.load()
                    image = ImageOps.exif_transpose(source).convert('RGB')
                    image.thumbnail((2400, 4000))
                    output = io.BytesIO()
                    image.save(output, format='JPEG', quality=90)
                    images.append(output.getvalue())
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise ValidationError('One of the screenshots is invalid or too large. Use PNG, JPEG or WebP.') from None
    if len(set(digests)) != len(digests):
        raise ValidationError('The same screenshot was selected twice. Remove the duplicate.')
    if sum(map(len, images)) > MAX_BYTES:
        raise ValidationError('The decoded screenshots are too large. Crop them to the item list and try again.')
    return images, hashlib.sha256('|'.join(sorted(digests)).encode()).hexdigest()
