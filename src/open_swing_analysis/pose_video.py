"""Annotated pose-video rendering from stored raw observations.

Rendering is deliberately downstream of extraction: it never changes or smooths
the raw landmark table and can be rerun without another model invocation.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from statistics import median

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from open_swing_analysis.contracts import DecodeStatus, Frame, PoseObservation
from open_swing_analysis.ingestion import FrameSelection, VideoReader
from open_swing_analysis.pose import (
    LANDMARK_NAMES,
    POSE_CONNECTIONS,
    map_inference_timestamps,
)
from open_swing_analysis.storage import DataIntegrityError, ImmutableDataError


class PoseVideoError(RuntimeError):
    """Raised when annotated-video encoding or validation fails."""


@dataclass(frozen=True)
class AnnotatedVideoResult:
    path: Path
    frame_count: int
    width_px: int
    height_px: int
    side_by_side: bool
    codec: str


def _pixel(row: PoseObservation, width: int, height: int) -> tuple[int, int] | None:
    if (
        row.x is None
        or row.y is None
        or not (0.0 <= row.x <= 1.0 and 0.0 <= row.y <= 1.0)
    ):
        return None
    return round(row.x * (width - 1)), round(row.y * (height - 1))


def _annotate_frame(
    image_rgb: np.ndarray,
    observations: Sequence[PoseObservation],
    *,
    frame_index: int,
    timestamp_s: float,
    show_landmark_names: bool,
    left_wrist_trace: Sequence[tuple[int, int]],
    right_wrist_trace: Sequence[tuple[int, int]],
) -> np.ndarray:
    image = Image.fromarray(image_rgb, mode="RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    width, height = image.size
    indexed = {row.landmark_index: row for row in observations}
    points = {
        index: point
        for index, row in indexed.items()
        if (point := _pixel(row, width, height)) is not None
    }

    for start, end in POSE_CONNECTIONS:
        if start in points and end in points:
            draw.line(
                (points[start], points[end]),
                fill=(80, 220, 255),
                width=max(2, width // 320),
            )
    radius = max(2, width // 180)
    for index, point in points.items():
        x, y = point
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius), fill=(255, 210, 45)
        )
        if show_landmark_names:
            draw.text(
                (x + radius + 1, y - radius),
                LANDMARK_NAMES[index],
                fill=(255, 255, 255),
                font=font,
            )

    if len(left_wrist_trace) > 1:
        draw.line(
            tuple(left_wrist_trace), fill=(255, 90, 170), width=max(2, width // 240)
        )
    if len(right_wrist_trace) > 1:
        draw.line(
            tuple(right_wrist_trace), fill=(110, 255, 100), width=max(2, width // 240)
        )

    visibility = [row.visibility for row in observations if row.visibility is not None]
    detected = bool(points)
    quality = (
        f"pose detected; mean visibility={sum(visibility) / len(visibility):.3f}"
        if detected and visibility
        else (
            "pose detected; visibility unavailable" if detected else "pose not detected"
        )
    )
    lines = (f"frame {frame_index}   timestamp {timestamp_s:.6f} s", quality)
    y = 6
    for text in lines:
        box = draw.textbbox((6, y), text, font=font)
        draw.rectangle((box[0] - 3, box[1] - 2, box[2] + 3, box[3] + 2), fill=(0, 0, 0))
        draw.text((6, y), text, fill=(255, 255, 255), font=font)
        y = box[3] + 6
    return np.asarray(image)


def _rate_from_frames(frames: Sequence[Frame]) -> Fraction:
    deltas = [
        later.timestamp_s - earlier.timestamp_s
        for earlier, later in zip(frames, frames[1:])
        if later.timestamp_s > earlier.timestamp_s
    ]
    if not deltas:
        return Fraction(30, 1)
    return Fraction(1.0 / median(deltas)).limit_denominator(1001)


def write_annotated_video(
    video_path: str | Path,
    frames: Sequence[Frame],
    observations: Sequence[PoseObservation],
    output_path: str | Path,
    *,
    side_by_side: bool = False,
    show_landmark_names: bool = False,
    wrist_trace_length: int = 45,
    codec: str = "libx264",
) -> AnnotatedVideoResult:
    """Render and validate an annotated video from one raw observation revision."""
    if wrist_trace_length <= 0:
        raise ValueError("wrist_trace_length must be positive")
    source_frames = tuple(frames)
    if not source_frames:
        raise DataIntegrityError("annotated video requires Frame records")
    frame_lookup = {frame.frame_index: frame for frame in source_frames}
    if len(frame_lookup) != len(source_frames):
        raise DataIntegrityError("annotated video frame indexes must be unique")
    observation_lookup: dict[int, list[PoseObservation]] = {}
    for observation in observations:
        frame = frame_lookup.get(observation.frame_index)
        if frame is None or abs(frame.timestamp_s - observation.timestamp_s) > 1e-9:
            raise DataIntegrityError(
                "annotated-video observation has an invalid frame reference"
            )
        observation_lookup.setdefault(observation.frame_index, []).append(observation)

    decoded_frames = [
        frame for frame in source_frames if frame.decode_status == DecodeStatus.DECODED
    ]
    if not decoded_frames:
        raise DataIntegrityError("annotated video has no decoded frames")
    destination = Path(output_path)
    if destination.exists():
        raise ImmutableDataError(
            f"refusing to overwrite annotated video: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    selection = FrameSelection(
        indices=frozenset(frame.frame_index for frame in decoded_frames)
    )
    mapped_timestamps = {
        frame.frame_index: mapped
        for frame, mapped in zip(
            decoded_frames,
            (
                value[0]
                for value in map_inference_timestamps(
                    [frame.timestamp_s for frame in decoded_frames]
                )
            ),
            strict=True,
        )
    }
    left_trace: deque[tuple[int, int]] = deque(maxlen=wrist_trace_length)
    right_trace: deque[tuple[int, int]] = deque(maxlen=wrist_trace_length)
    output: av.container.OutputContainer | None = None
    stream: av.VideoStream | None = None
    written = 0
    output_width = 0
    output_height = 0
    try:
        output = av.open(str(destination), mode="w")
        for decoded in VideoReader(video_path).iter_frames(selection):
            frame = frame_lookup[decoded.frame_index]
            rows = observation_lookup.get(frame.frame_index, [])
            row_by_index = {row.landmark_index: row for row in rows}
            left_point = (
                _pixel(
                    row_by_index[15],
                    decoded.display_width_px,
                    decoded.display_height_px,
                )
                if 15 in row_by_index
                else None
            )
            right_point = (
                _pixel(
                    row_by_index[16],
                    decoded.display_width_px,
                    decoded.display_height_px,
                )
                if 16 in row_by_index
                else None
            )
            if left_point is not None:
                left_trace.append(left_point)
            if right_point is not None:
                right_trace.append(right_point)
            annotated = _annotate_frame(
                decoded.image,
                rows,
                frame_index=frame.frame_index,
                timestamp_s=frame.timestamp_s,
                show_landmark_names=show_landmark_names,
                left_wrist_trace=tuple(left_trace),
                right_wrist_trace=tuple(right_trace),
            )
            rendered = (
                np.concatenate((decoded.image, annotated), axis=1)
                if side_by_side
                else annotated
            )
            if stream is None:
                output_height, output_width = rendered.shape[:2]
                try:
                    stream = output.add_stream(
                        codec, rate=_rate_from_frames(decoded_frames)
                    )
                except (ValueError, av.FFmpegError) as exc:
                    raise PoseVideoError(
                        f"could not open {codec!r} video encoder: {exc}"
                    ) from exc
                stream.width = output_width
                stream.height = output_height
                stream.pix_fmt = "yuv420p"
                stream.time_base = Fraction(1, 1000)
            video_frame = av.VideoFrame.from_ndarray(rendered, format="rgb24")
            video_frame.pts = mapped_timestamps[frame.frame_index]
            video_frame.time_base = Fraction(1, 1000)
            for packet in stream.encode(video_frame):
                output.mux(packet)
            written += 1
        if stream is None or written == 0:
            raise PoseVideoError("annotated writer received no frames")
        for packet in stream.encode():
            output.mux(packet)
    except Exception:
        if destination.exists() and destination.stat().st_size == 0:
            destination.unlink()
        raise
    finally:
        if output is not None:
            output.close()

    validated_count = 0
    validated_dimensions: tuple[int, int] | None = None
    previous_timestamp = -1.0
    try:
        for decoded in VideoReader(destination).iter_frames():
            dimensions = (decoded.display_width_px, decoded.display_height_px)
            validated_dimensions = validated_dimensions or dimensions
            if dimensions != validated_dimensions:
                raise PoseVideoError(
                    "annotated video dimensions change during playback"
                )
            if decoded.original_timestamp_s is not None:
                if decoded.original_timestamp_s <= previous_timestamp:
                    raise PoseVideoError(
                        "annotated video timestamps are not increasing"
                    )
                previous_timestamp = decoded.original_timestamp_s
            validated_count += 1
    except Exception as exc:
        if isinstance(exc, PoseVideoError):
            raise
        raise PoseVideoError(f"annotated video validation failed: {exc}") from exc
    if validated_count != written:
        raise PoseVideoError(
            f"annotated video validation decoded {validated_count} frames; expected {written}"
        )
    if validated_dimensions != (output_width, output_height):
        raise PoseVideoError(
            f"annotated video dimensions {validated_dimensions} differ from expected "
            f"{(output_width, output_height)}"
        )
    if not destination.is_file() or destination.stat().st_size == 0:
        raise PoseVideoError("annotated video writer produced no readable file")
    return AnnotatedVideoResult(
        path=destination,
        frame_count=written,
        width_px=output_width,
        height_px=output_height,
        side_by_side=side_by_side,
        codec=codec,
    )
