"""Real Meta Responses streaming through the official Python SAM parser."""

import asyncio
import base64
from io import BytesIO
from pathlib import Path
import warnings

from meta_sam_parser import image_segmentation_format, parse_responses_stream
from openai import AsyncOpenAI
from PIL import Image, ImageOps

from backend.agent.config import MetaConfig, META_BASE_URL
from backend.agent.errors import MuseConfigurationError
from backend.vision.errors import SamConfigurationError, SamImageError, SamParsingError, SamProviderError
from backend.vision.models import (
    ComponentBox, ConceptRequest, MaskMetadata, SAM_MODEL, SamDiagnostic, SegmentationResult,
)

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
IMAGE_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


def read_image(path: Path) -> tuple[str, int, int]:
    """Bound reads, verify raster contents, and use displayed EXIF dimensions."""
    try:
        with path.open("rb") as handle:
            content = handle.read(MAX_IMAGE_BYTES + 1)
        if not content or len(content) > MAX_IMAGE_BYTES:
            raise ValueError("Invalid size")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                media_type = IMAGE_TYPES.get(image.format)
                if media_type is None or image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("Unsupported image")
                image.verify()
            with Image.open(BytesIO(content)) as image:
                width, height = ImageOps.exif_transpose(image).size
        return f"data:{media_type};base64,{base64.b64encode(content).decode('ascii')}", width, height
    except Exception:
        raise SamImageError("Image is missing, unreadable, unsupported, or exceeds the image limits.") from None


class SamProvider:
    """Sync runtime adapter over an async SDK stream; injected clients are caller-owned.

    No client/key is constructed until an image has passed local validation.
    Async callers can await segment_async instead of using the sync adapter.
    """

    def __init__(self, *, client: AsyncOpenAI | None = None) -> None:
        self._client = client

    def segment(self, image_path: Path, concept: str) -> SegmentationResult:
        return asyncio.run(self.segment_async(image_path, concept))

    async def segment_async(self, image_path: Path, concept: str) -> SegmentationResult:
        concept = ConceptRequest(concept=concept).concept
        data_url, width, height = read_image(Path(image_path))
        client = self._client
        owned = client is None
        if owned:
            try:
                config = MetaConfig.from_env()
                client = AsyncOpenAI(api_key=config.api_key.get_secret_value(), base_url=META_BASE_URL,
                                     timeout=60, max_retries=0)
            except MuseConfigurationError:
                raise SamConfigurationError("Set a valid META_API_KEY on the server to use SAM.") from None
            except Exception:
                raise SamConfigurationError("SAM client configuration could not be initialized.") from None
        try:
            stream = await client.responses.create(model=SAM_MODEL, stream=True, input=[{
                "role": "user", "type": "message", "content": [
                    {"type": "input_text", "text": concept},
                    {"type": "input_image", "image_url": data_url},
                ],
            }])
            async with stream:
                parsed = await parse_responses_stream(stream, image_segmentation_format()).final_result()
            if parsed.outcome.status != "completed" or any(d.severity == "error" for d in parsed.diagnostics):
                raise SamParsingError("SAM did not return a complete, valid segmentation.")
            boxes = [ComponentBox(object_id=r.object_id, left=r.left, top=r.top,
                                  right=r.right, bottom=r.bottom) for r in parsed.records if r.kind == "box"]
            masks = [MaskMetadata(object_id=r.object_id, encoding=r.mask.encoding,
                                  width=r.mask.width, height=r.mask.height)
                     for r in parsed.records if r.kind == "mask"]
            if any(b.right <= b.left or b.bottom <= b.top or b.right > width or b.bottom > height for b in boxes):
                raise SamParsingError("SAM returned geometry outside the image bounds.")
            return SegmentationResult(concept=concept, objects_found=len({r.object_id for r in parsed.records
                                      if r.kind in {"box", "mask"}}), boxes=boxes, masks=masks,
                                      image_width=width, image_height=height,
                                      diagnostics=[SamDiagnostic(severity=d.severity, line=d.line)
                                                   for d in parsed.diagnostics])
        except SamParsingError:
            raise
        except Exception:
            raise SamProviderError("SAM request or streamed segmentation could not be completed.") from None
        finally:
            if owned:
                try:
                    await client.close()
                except Exception:
                    pass  # Cleanup must not replace a sanitized result/error with transport details.
