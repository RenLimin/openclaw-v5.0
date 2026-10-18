"""
Video document parser: extract frames from video and run OCR on each frame
Supports: mp4, avi, mov, mkv, webm
"""
import os
import cv2
import pytesseract
from PIL import Image
from typing import Optional, List
from dataclasses import dataclass

from ai_kb.parsers.base import BaseParser
from ai_kb.quality import PIIDetector


@dataclass
class VideoFrameResult:
    frame_num: int
    timestamp: float
    text: str
    pii_found: bool


@dataclass
class VideoParseResult:
    success: bool
    text: str = ""
    frames: List[VideoFrameResult] = None
    error: str = None


class VideoParser(BaseParser):
    """Extract text from video by sampling frames and running OCR"""

    SUPPORTED_EXTS = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}

    def __init__(
        self,
        fps: float = 0.5,
        lang: str = 'chi_sim+eng',
        min_text_length: int = 10,
        lang_config: str = None
    ):
        """
        Initialize video parser.
        Args:
            fps: frames per second to sample (0.5 = 1 frame every 2 seconds)
            lang: tesseract language code
            min_text_length: skip frames with less text than this
            lang_config: optional config path for tesseract lang data
        """
        super().__init__()
        self.fps = fps
        self.lang = lang
        self.min_text_length = min_text_length
        self.lang_config = lang_config
        self.pii_detector = PIIDetector()

    def parse(self, file_path: str) -> VideoParseResult:
        """Parse video file, sample frames, run OCR, aggregate text"""
        if not self._is_supported(file_path):
            return VideoParseResult(
                success=False,
                error=f"Unsupported video format: {os.path.splitext(file_path)[1]}"
            )

        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return VideoParseResult(
                success=False,
                error=f"Could not open video file: {file_path}"
            )

        try:
            video_fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / video_fps if video_fps > 0 else 0
            sample_interval = 1.0 / self.fps

            results: List[VideoFrameResult] = []
            full_text = []
            current_time = 0.0

            while current_time < duration:
                # Seek to frame at current_time
                cap.set(cv2.CAP_PROP_POS_MSEC, current_time * 1000)
                ret, frame = cap.read()
                if not ret:
                    break

                # Convert to grayscale for better OCR
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                pil_img = Image.fromarray(gray)

                # Run OCR
                text = pytesseract.image_to_string(pil_img, lang=self.lang)
                text = text.strip()

                if len(text) >= self.min_text_length:
                    # Check for PII
                    pii_found, _ = self.pii_detector.detect(text)
                    results.append(VideoFrameResult(
                        frame_num=int(current_time * video_fps),
                        timestamp=current_time,
                        text=text,
                        pii_found=pii_found
                    ))
                    full_text.append(text)

                current_time += sample_interval

            cap.release()

            return VideoParseResult(
                success=True,
                text="\n\n---\n\n".join(full_text),
                frames=results
            )
        except Exception as e:
            cap.release()
            return VideoParseResult(
                success=False,
                error=f"Video parsing failed: {str(e)}"
            )

    def _is_supported(self, file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext in self.SUPPORTED_EXTS
