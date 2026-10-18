"""
Audio document parser: use OpenAI Whisper ASR to extract text from audio files
Supports: mp3, wav, flac, m4a, ogg, opus
"""
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass

from ai_kb.parsers.base import BaseParser


@dataclass
class AudioParseResult:
    success: bool
    text: str = ""
    segments: list = None
    error: str = None


class AudioParser(BaseParser):
    """Parse audio files to text using Whisper ASR"""

    SUPPORTED_EXTS = {'.mp3', '.wav', '.flac', '.m4a', '.ogg', '.opus'}

    def __init__(self, model_name: str = "base", language: Optional[str] = None):
        """
        Initialize Whisper parser.
        Args:
            model_name: whisper model name (tiny/base/small/medium/large)
            language: optional language code (auto-detect if None)
        """
        super().__init__()
        self.model_name = model_name
        self.language = language
        self._model = None

    @property
    def model(self):
        """Lazy load whisper model"""
        if self._model is None:
            try:
                import whisper
                self._model = whisper.load_model(self.model_name)
            except ImportError as e:
                raise RuntimeError(f"Whisper not installed: {e}\nInstall with: pip install openai-whisper") from e
        return self._model

    def parse(self, file_path: str) -> AudioParseResult:
        """Parse audio file and return transcribed text"""
        if not self._is_supported(file_path):
            return AudioParseResult(
                success=False,
                error=f"Unsupported audio format: {os.path.splitext(file_path)[1]}"
            )

        try:
            result = self.model.transcribe(
                file_path,
                language=self.language,
                verbose=False
            )
            text = result.get("text", "")
            segments = result.get("segments", [])
            return AudioParseResult(
                success=True,
                text=text.strip(),
                segments=segments
            )
        except Exception as e:
            return AudioParseResult(
                success=False,
                error=f"Transcription failed: {str(e)}"
            )

    def _is_supported(self, file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext in self.SUPPORTED_EXTS
