"""Writing an OME-TIFF: one file per acquisition, holding every plane of it.

OME-TIFF is an ordinary TIFF image with a description in OME-XML, the open
microscopy metadata standard, so any image program can open the pixels and
any OME-aware program also knows the pixel size and position. ZMART saves one
file per position: a z-stack is one file with one page per plane, which Fiji,
napari or QuPath open as one stack with the right pixel size.

The description also carries ZMART's note (namespace ``zmart/position``),
which other programs skip. It says that the stage position written for each
plane is that of the picture's corner, not its middle, so the ZMART interface
and viewer can use the file as a position just as it is.

This writer uses only the Python standard library: uncompressed 16-bit grey
images with the OME-XML stored in the first page's image description.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import struct
import sys
import uuid
from array import array
from pathlib import Path
from xml.sax.saxutils import quoteattr

# TIFF field types: 2 = text, 3 = 16-bit number, 4 = 32-bit number.
_TEXT, _SHORT, _LONG = 2, 3, 4

#: The namespace of ZMART's note, which the ZMART interface and viewer read.
ZMART_NOTE = "zmart/position"


def ome_xml(
    *,
    name: str,
    width: int,
    height: int,
    planes: int,
    pixel_size_um: float,
    z_step_um: float,
    position_um: dict[str, float],
    extra: dict[str, str],
) -> str:
    """The OME-XML description of a stack of ``planes`` planes, bottom plane first.

    ``position_um`` is the user position of the bottom plane's corner pixel;
    each plane above it is ``z_step_um`` higher.
    """
    annotations = "".join(
        f"<M K={quoteattr(key)}>{_escape(value)}</M>" for key, value in sorted(extra.items())
    )
    plane_entries = "".join(
        f'<Plane TheZ="{z}" TheC="0" TheT="0" '
        f'PositionX="{position_um["x"]}" PositionXUnit="µm" '
        f'PositionY="{position_um["y"]}" PositionYUnit="µm" '
        f'PositionZ="{position_um["z"] + z * z_step_um}" PositionZUnit="µm"/>'
        for z in range(planes)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06" '
        f'Creator="zmart_controller.mock" UUID="urn:uuid:{uuid.uuid4()}">'
        f'<Image ID="Image:0" Name={quoteattr(name)}>'
        f'<Pixels ID="Pixels:0" DimensionOrder="XYZCT" Type="uint16" '
        f'SizeX="{width}" SizeY="{height}" SizeZ="{planes}" SizeC="1" SizeT="1" '
        f'PhysicalSizeX="{pixel_size_um}" PhysicalSizeXUnit="µm" '
        f'PhysicalSizeY="{pixel_size_um}" PhysicalSizeYUnit="µm" '
        f'PhysicalSizeZ="{z_step_um}" PhysicalSizeZUnit="µm">'
        '<Channel ID="Channel:0:0" SamplesPerPixel="1"/>'
        f'<TiffData IFD="0" PlaneCount="{planes}"/>'
        f"{plane_entries}"
        "</Pixels>"
        '<AnnotationRef ID="Annotation:0"/>'
        '<AnnotationRef ID="Annotation:1"/>'
        "</Image>"
        "<StructuredAnnotations>"
        '<MapAnnotation ID="Annotation:0" Namespace="zmart/acquisition"><Value>'
        f"{annotations}"
        "</Value></MapAnnotation>"
        f'<MapAnnotation ID="Annotation:1" Namespace="{ZMART_NOTE}"><Value>'
        '<M K="position_origin">corner</M>'
        "</Value></MapAnnotation>"
        "</StructuredAnnotations>"
        "</OME>"
    )


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_ome_tiff(
    path: Path, planes: list[array], width: int, height: int, description: str
) -> None:
    """Write 16-bit ``planes`` as one TIFF file, one page each, with ``description`` as its OME-XML.

    The description is stored in the first page only, as OME-TIFF asks.
    """
    text = description.encode("utf-8") + b"\0"
    stream = bytearray(b"II*\0" + struct.pack("<I", 8))
    for index, plane in enumerate(planes):
        pixels = array("H", plane)
        if sys.byteorder == "big":
            pixels.byteswap()
        data = pixels.tobytes()
        first = index == 0
        tags = [
            (256, _LONG, 1, width),  # image width
            (257, _LONG, 1, height),  # image length
            (258, _SHORT, 1, 16),  # bits per sample
            (259, _SHORT, 1, 1),  # no compression
            (262, _SHORT, 1, 1),  # black is zero
            *([(270, _TEXT, len(text), None)] if first else []),  # the OME-XML
            (273, _LONG, 1, None),  # where the pixels start
            (277, _SHORT, 1, 1),  # one sample per pixel
            (278, _LONG, 1, height),  # all rows in one strip
            (279, _LONG, 1, len(data)),  # how many bytes of pixels
        ]
        ifd_offset = len(stream)
        text_offset = ifd_offset + 2 + 12 * len(tags) + 4
        data_offset = text_offset + (len(text) if first else 0)
        data_offset += data_offset % 2  # TIFF readers prefer the pixels on an even byte
        next_offset = data_offset + len(data)
        next_offset += next_offset % 2  # and every page's directory too
        entries = b""
        for tag, kind, count, value in tags:
            if tag == 270:
                value = text_offset
            elif tag == 273:
                value = data_offset
            if kind == _SHORT:
                entries += struct.pack("<HHIHH", tag, kind, count, value, 0)
            else:
                entries += struct.pack("<HHII", tag, kind, count, value)
        last = index == len(planes) - 1
        stream += struct.pack("<H", len(tags)) + entries
        stream += struct.pack("<I", 0 if last else next_offset)
        if first:
            stream += text
        stream += b"\0" * (data_offset - len(stream))
        stream += data
        stream += b"\0" * (next_offset - len(stream))
    path.write_bytes(bytes(stream))
