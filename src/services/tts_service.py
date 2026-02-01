"""
TTS (Text-to-Speech) Service

Supports:
- Edge TTS (Microsoft) - Fast, cloud-based (recommended)
- Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice - High quality, local
"""

import os
import re
import hashlib
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor
from loguru import logger

# TTS executor for async operations
_tts_executor = ThreadPoolExecutor(max_workers=2)


class TTSService:
    """Text-to-Speech service supporting multiple backends"""

    # Available TTS models
    AVAILABLE_MODELS = {
        "edge-tts": {
            "name": "Edge TTS (Fast)",
            "description": "Microsoft Edge TTS - 빠른 실시간 음성 합성",
            "sample_rate": 24000,
            "language": ["ko", "en", "zh", "ja", "de", "fr", "es", "pt", "ru", "it"],
            "model_type": "edge",
        },
        "Qwen/Qwen3-TTS-12Hz-0.6B-Base": {
            "name": "Qwen3 TTS 0.6B (Fast Local)",
            "description": "Qwen3 TTS 0.6B - 빠른 로컬 음성 합성 (Voice Clone)",
            "sample_rate": 24000,
            "language": ["ko", "en", "zh", "ja", "de", "fr", "es", "pt", "ru", "it"],
            "model_type": "base",
        },
        "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice": {
            "name": "Qwen3 TTS 0.6B CustomVoice (Fast)",
            "description": "Qwen3 TTS 0.6B CustomVoice - 빠른 로컬 음성 합성",
            "sample_rate": 24000,
            "language": ["ko", "en", "zh", "ja", "de", "fr", "es", "pt", "ru", "it"],
            "model_type": "custom_voice",
        },
        "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice": {
            "name": "Qwen3 TTS 1.7B (High Quality)",
            "description": "Qwen3 TTS 1.7B - 고품질 로컬 음성 합성 (느림)",
            "sample_rate": 24000,
            "language": ["ko", "en", "zh", "ja", "de", "fr", "es", "pt", "ru", "it"],
            "model_type": "custom_voice",
        },
    }

    # Edge TTS voice mapping
    EDGE_VOICES = {
        "ko": "ko-KR-SunHiNeural",
        "en": "en-US-JennyNeural",
        "zh": "zh-CN-XiaoxiaoNeural",
        "ja": "ja-JP-NanamiNeural",
        "de": "de-DE-KatjaNeural",
        "fr": "fr-FR-DeniseNeural",
        "es": "es-ES-ElviraNeural",
        "pt": "pt-BR-FranciscaNeural",
        "ru": "ru-RU-SvetlanaNeural",
        "it": "it-IT-ElsaNeural",
    }

    # Qwen speakers
    QWEN_SPEAKERS = {
        "ko": ["sohee"],
        "en": ["ryan", "serena", "aiden", "dylan", "eric"],
        "zh": ["uncle_fu", "vivian"],
        "ja": ["ono_anna"],
        "default": ["sohee"],
    }

    # Language code mapping for Qwen
    LANGUAGE_MAP = {
        "ko": "korean",
        "en": "english",
        "zh": "chinese",
        "ja": "japanese",
        "de": "german",
        "fr": "french",
        "es": "spanish",
        "pt": "portuguese",
        "ru": "russian",
        "it": "italian",
    }

    @staticmethod
    def _split_by_language(text: str) -> List[Tuple[str, str]]:
        """
        Split text into segments by language (Korean vs English).
        Returns list of (text, language_code) tuples.

        Handles mixed text like "안녕하세요 Hello World 반갑습니다"
        -> [("안녕하세요 ", "ko"), ("Hello World ", "en"), ("반갑습니다", "ko")]
        """
        segments = []

        # Pattern to match Korean characters (including spaces attached to Korean)
        # and English/Latin characters (including numbers and common punctuation)
        # Korean: Hangul syllables (AC00-D7AF), Hangul Jamo (1100-11FF, 3130-318F)
        korean_pattern = r'[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F]+'
        english_pattern = r'[a-zA-Z0-9]+'

        current_pos = 0
        current_segment = ""
        current_lang = None

        while current_pos < len(text):
            char = text[current_pos]

            # Determine character's language
            if re.match(r'[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F]', char):
                char_lang = "ko"
            elif re.match(r'[a-zA-Z]', char):
                char_lang = "en"
            else:
                # Punctuation, numbers, spaces - attach to current segment
                char_lang = current_lang if current_lang else "ko"

            # If language changed and we have content, save segment
            if current_lang is not None and char_lang != current_lang and current_segment.strip():
                # Check if current segment has meaningful content
                if re.search(r'[\uAC00-\uD7AFa-zA-Z]', current_segment):
                    segments.append((current_segment, current_lang))
                    current_segment = ""

            current_segment += char
            current_lang = char_lang
            current_pos += 1

        # Add remaining segment
        if current_segment.strip() and re.search(r'[\uAC00-\uD7AFa-zA-Z]', current_segment):
            segments.append((current_segment, current_lang or "ko"))

        # If no segments found, return original text with default language
        if not segments:
            return [(text, "ko")]

        # Merge consecutive segments of same language
        merged = []
        for seg_text, seg_lang in segments:
            if merged and merged[-1][1] == seg_lang:
                merged[-1] = (merged[-1][0] + seg_text, seg_lang)
            else:
                merged.append((seg_text, seg_lang))

        return merged

    @staticmethod
    def _has_mixed_language(text: str) -> bool:
        """Check if text contains both Korean and English"""
        has_korean = bool(re.search(r'[\uAC00-\uD7AF]', text))
        has_english = bool(re.search(r'[a-zA-Z]{2,}', text))  # At least 2 consecutive letters
        return has_korean and has_english

    def __init__(
        self,
        model_id: str = "edge-tts",
        cache_dir: Optional[str] = None,
        device: str = "auto",
    ):
        self.model_id = model_id
        self.cache_dir = cache_dir or os.path.join(
            os.path.dirname(__file__), "..", "..", "cache", "tts"
        )
        self.device = device
        self.model = None
        self.sample_rate = 24000
        self._initialized = False

        # Ensure cache directory exists
        Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
        Path(os.path.join(self.cache_dir, "audio")).mkdir(parents=True, exist_ok=True)

        logger.info(f"TTS Service initialized with model: {model_id}")

    def _load_model(self):
        """Load TTS model (lazy loading) - only for Qwen models"""
        if self._initialized:
            return

        # Edge TTS doesn't need model loading
        if self.model_id == "edge-tts":
            self._initialized = True
            return

        try:
            import torch
            from qwen_tts import Qwen3TTSModel

            logger.info(f"Loading TTS model: {self.model_id}")

            # Determine device
            if self.device == "auto":
                if torch.cuda.is_available():
                    self.device = "cuda:0"
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    self.device = "mps"
                else:
                    self.device = "cpu"

            logger.info(f"TTS using device: {self.device}")

            # Determine dtype based on device
            if self.device == "cpu":
                dtype = torch.float32
            else:
                dtype = torch.bfloat16

            # Load model
            self.model = Qwen3TTSModel.from_pretrained(
                self.model_id,
                device_map=self.device,
                dtype=dtype,
            )

            self._initialized = True
            logger.success(f"TTS model loaded successfully: {self.model_id}")

        except ImportError as e:
            logger.error(f"Required package not installed for TTS: {e}")
            raise RuntimeError(
                "TTS requires qwen-tts package. Install with: pip install qwen-tts"
            )
        except Exception as e:
            logger.error(f"Failed to load TTS model: {e}")
            raise

    def _generate_cache_key(self, text: str, voice_id: str, speed: float, language: str) -> str:
        """Generate cache key for audio file"""
        content = f"{text}:{voice_id}:{speed}:{language}:{self.model_id}"
        return hashlib.md5(content.encode()).hexdigest()

    def _get_cached_audio(self, cache_key: str) -> Optional[str]:
        """Get cached audio file path if exists"""
        audio_path = os.path.join(self.cache_dir, "audio", f"{cache_key}.mp3")
        if os.path.exists(audio_path):
            return audio_path
        audio_path = os.path.join(self.cache_dir, "audio", f"{cache_key}.wav")
        if os.path.exists(audio_path):
            return audio_path
        return None

    async def _synthesize_edge_tts(
        self,
        text: str,
        voice_id: str,
        speed: float,
        language: str,
        cache_key: str,
    ) -> str:
        """Synthesize using Edge TTS (async, fast)"""
        import edge_tts

        # Calculate rate string (e.g., "+20%" or "-10%")
        rate_percent = int((speed - 1.0) * 100)
        rate_str = f"+{rate_percent}%" if rate_percent >= 0 else f"{rate_percent}%"

        audio_path = os.path.join(self.cache_dir, "audio", f"{cache_key}.mp3")

        # Check if text has mixed Korean and English
        if self._has_mixed_language(text):
            # Split text by language and synthesize each segment
            segments = self._split_by_language(text)
            logger.info(f"Edge TTS: Mixed language detected, {len(segments)} segments")

            if len(segments) > 1:
                # Synthesize each segment with appropriate voice
                temp_files = []
                for i, (seg_text, seg_lang) in enumerate(segments):
                    if not seg_text.strip():
                        continue

                    seg_voice = self.EDGE_VOICES.get(seg_lang, "ko-KR-SunHiNeural")
                    temp_path = os.path.join(self.cache_dir, "audio", f"{cache_key}_seg{i}.mp3")

                    logger.debug(f"Edge TTS segment {i}: lang={seg_lang}, voice={seg_voice}, text='{seg_text[:30]}...'")

                    communicate = edge_tts.Communicate(seg_text, seg_voice, rate=rate_str)
                    await communicate.save(temp_path)
                    temp_files.append(temp_path)

                # Concatenate audio files
                if temp_files:
                    await self._concatenate_audio_files(temp_files, audio_path)

                    # Clean up temp files
                    for temp_file in temp_files:
                        try:
                            os.remove(temp_file)
                        except Exception:
                            pass

                    logger.info(f"Edge TTS: Mixed language audio generated: {audio_path}")
                    return audio_path

        # Single language - use standard synthesis
        if voice_id == "default":
            voice = self.EDGE_VOICES.get(language, "ko-KR-SunHiNeural")
        else:
            voice = voice_id

        logger.info(f"Edge TTS: voice={voice}, rate={rate_str}, text_len={len(text)}")

        communicate = edge_tts.Communicate(text, voice, rate=rate_str)
        await communicate.save(audio_path)

        logger.info(f"Edge TTS audio generated: {audio_path}")
        return audio_path

    async def _concatenate_audio_files(self, input_files: List[str], output_file: str) -> None:
        """Concatenate multiple audio files into one using pydub (async)"""
        try:
            from pydub import AudioSegment

            def _concat_sync():
                combined = AudioSegment.empty()
                for file_path in input_files:
                    if os.path.exists(file_path):
                        audio = AudioSegment.from_mp3(file_path)
                        combined += audio
                combined.export(output_file, format="mp3")

            # pydub은 동기 라이브러리이므로 스레드에서 실행
            await asyncio.get_event_loop().run_in_executor(_tts_executor, _concat_sync)
            logger.debug(f"Concatenated {len(input_files)} audio files to {output_file}")

        except ImportError:
            logger.warning("pydub not installed, falling back to ffmpeg concatenation")
            await self._concatenate_with_ffmpeg(input_files, output_file)

    async def _concatenate_with_ffmpeg(self, input_files: List[str], output_file: str) -> None:
        """Concatenate audio files using ffmpeg as fallback"""
        import tempfile

        # Create a file list for ffmpeg
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            list_file = f.name
            for file_path in input_files:
                f.write(f"file '{file_path}'\n")

        try:
            # Run ffmpeg to concatenate
            process = await asyncio.create_subprocess_exec(
                'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                '-i', list_file, '-c', 'copy', output_file,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await process.wait()
            logger.debug(f"FFmpeg concatenated {len(input_files)} files to {output_file}")
        finally:
            try:
                os.remove(list_file)
            except Exception:
                pass

    async def _get_or_create_reference_audio(self, language: str) -> str:
        """Get or create reference audio for voice cloning using Edge TTS"""
        import edge_tts

        ref_dir = os.path.join(self.cache_dir, "reference")
        Path(ref_dir).mkdir(parents=True, exist_ok=True)

        ref_path = os.path.join(ref_dir, f"ref_{language}.mp3")

        # Return existing reference audio if available
        if os.path.exists(ref_path):
            return ref_path

        # Generate reference audio using Edge TTS
        ref_texts = {
            "ko": "안녕하세요. 저는 음성 합성을 위한 참조 음성입니다.",
            "en": "Hello. This is a reference voice for speech synthesis.",
            "zh": "你好。这是用于语音合成的参考音频。",
            "ja": "こんにちは。これは音声合成のための参照音声です。",
            "de": "Hallo. Dies ist eine Referenzstimme für die Sprachsynthese.",
            "fr": "Bonjour. Ceci est une voix de référence pour la synthèse vocale.",
            "es": "Hola. Esta es una voz de referencia para la síntesis de voz.",
            "pt": "Olá. Esta é uma voz de referência para síntese de fala.",
            "ru": "Здравствуйте. Это референсный голос для синтеза речи.",
            "it": "Ciao. Questa è una voce di riferimento per la sintesi vocale.",
        }

        ref_text = ref_texts.get(language, ref_texts["ko"])
        voice = self.EDGE_VOICES.get(language, "ko-KR-SunHiNeural")

        logger.info(f"Creating reference audio for {language} using Edge TTS")

        communicate = edge_tts.Communicate(ref_text, voice)
        await communicate.save(ref_path)

        logger.info(f"Reference audio created: {ref_path}")
        return ref_path

    def _synthesize_qwen_base_sync(
        self,
        text: str,
        voice_id: str,
        speed: float,
        language: str,
        cache_key: str,
        ref_audio_path: str,
    ) -> str:
        """Synthesize using Qwen TTS 0.6B Base model (voice clone)"""
        import soundfile as sf
        import numpy as np

        # Load model if not loaded
        self._load_model()

        # Map language code to full name
        lang_full = self.LANGUAGE_MAP.get(language, "korean")

        logger.info(f"Qwen TTS Base: lang={lang_full}, text_len={len(text)}, ref_audio={ref_audio_path}")

        # Generate audio using voice clone
        try:
            wavs, sr = self.model.generate_voice_clone(
                text=text,
                language=lang_full,
                ref_audio=ref_audio_path,
                x_vector_only_mode=True,  # Only use speaker embedding (simpler, faster)
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Qwen TTS Base error: {error_msg}")
            # Check if it's a numerical error that Edge TTS can handle
            if "probability tensor" in error_msg or "inf" in error_msg or "nan" in error_msg:
                logger.warning(f"Qwen TTS numerical error, will fallback to Edge TTS")
                raise RuntimeError(f"FALLBACK_TO_EDGE:{error_msg}")
            raise RuntimeError(f"TTS synthesis failed: {e}")

        # Get waveform
        waveform = wavs[0] if isinstance(wavs, list) else wavs

        # Convert to numpy if tensor
        if hasattr(waveform, 'cpu'):
            waveform = waveform.cpu().numpy()

        # Apply speed adjustment if needed
        if speed != 1.0:
            new_length = int(len(waveform) / speed)
            indices = np.linspace(0, len(waveform) - 1, new_length).astype(int)
            waveform = waveform[indices]

        # Save to WAV file
        audio_path = os.path.join(self.cache_dir, "audio", f"{cache_key}.wav")
        sf.write(audio_path, waveform, sr)

        logger.info(f"Qwen TTS Base audio generated: {audio_path}")
        return audio_path

    def _synthesize_qwen_custom_voice_sync(
        self,
        text: str,
        voice_id: str,
        speed: float,
        language: str,
        cache_key: str,
    ) -> str:
        """Synthesize using Qwen TTS CustomVoice model (predefined speakers)"""
        import soundfile as sf
        import numpy as np

        # Load model if not loaded
        self._load_model()

        # Map language code to full name
        lang_full = self.LANGUAGE_MAP.get(language, "korean")

        # Get speaker for the language
        if voice_id == "default":
            speakers = self.QWEN_SPEAKERS.get(language, self.QWEN_SPEAKERS["default"])
            speaker = speakers[0]
        else:
            speaker = voice_id.lower()

        logger.info(f"Qwen TTS CustomVoice: lang={lang_full}, speaker={speaker}, text_len={len(text)}")

        # Generate audio
        try:
            wavs, sr = self.model.generate_custom_voice(
                text=text,
                language=lang_full,
                speaker=speaker,
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Qwen TTS CustomVoice error: {error_msg}")
            # Check if it's a numerical error that Edge TTS can handle
            if "probability tensor" in error_msg or "inf" in error_msg or "nan" in error_msg:
                logger.warning(f"Qwen TTS numerical error, will fallback to Edge TTS")
                raise RuntimeError(f"FALLBACK_TO_EDGE:{error_msg}")
            raise RuntimeError(f"TTS synthesis failed: {e}")

        # Get waveform
        waveform = wavs[0] if isinstance(wavs, list) else wavs

        # Convert to numpy if tensor
        if hasattr(waveform, 'cpu'):
            waveform = waveform.cpu().numpy()

        # Apply speed adjustment if needed
        if speed != 1.0:
            new_length = int(len(waveform) / speed)
            indices = np.linspace(0, len(waveform) - 1, new_length).astype(int)
            waveform = waveform[indices]

        # Save to WAV file
        audio_path = os.path.join(self.cache_dir, "audio", f"{cache_key}.wav")
        sf.write(audio_path, waveform, sr)

        logger.info(f"Qwen TTS CustomVoice audio generated: {audio_path}")
        return audio_path

    async def synthesize(
        self,
        text: str,
        voice_id: str = "default",
        speed: float = 1.0,
        language: str = "ko",
    ) -> str:
        """
        Synthesize speech from text

        Args:
            text: Text to synthesize
            voice_id: Voice/speaker identifier
            speed: Playback speed (0.5-2.0)
            language: Language code (ko, en, ja, zh, etc.)

        Returns:
            Path to generated audio file
        """
        # Check cache
        cache_key = self._generate_cache_key(text, voice_id, speed, language)
        cached_path = self._get_cached_audio(cache_key)
        if cached_path:
            logger.debug(f"Using cached audio: {cache_key}")
            return cached_path

        # Use appropriate backend based on model type
        if self.model_id == "edge-tts":
            return await self._synthesize_edge_tts(text, voice_id, speed, language, cache_key)

        # Get model type from AVAILABLE_MODELS
        model_info = self.AVAILABLE_MODELS.get(self.model_id, {})
        model_type = model_info.get("model_type", "custom_voice")

        try:
            if model_type == "base":
                # Qwen 0.6B Base model - requires voice cloning with reference audio
                ref_audio_path = await self._get_or_create_reference_audio(language)
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    _tts_executor,
                    self._synthesize_qwen_base_sync,
                    text,
                    voice_id,
                    speed,
                    language,
                    cache_key,
                    ref_audio_path,
                )
            else:
                # Qwen CustomVoice model - uses predefined speakers
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    _tts_executor,
                    self._synthesize_qwen_custom_voice_sync,
                    text,
                    voice_id,
                    speed,
                    language,
                    cache_key,
                )
        except RuntimeError as e:
            error_msg = str(e)
            # Check if this is a fallback request to Edge TTS
            if error_msg.startswith("FALLBACK_TO_EDGE:"):
                original_error = error_msg.replace("FALLBACK_TO_EDGE:", "")
                logger.warning(f"Qwen TTS failed with numerical error, falling back to Edge TTS: {original_error}")
                # Generate new cache key for Edge TTS fallback
                fallback_cache_key = self._generate_cache_key(text, "edge-fallback", speed, language)
                return await self._synthesize_edge_tts(text, voice_id, speed, language, fallback_cache_key)
            # Re-raise other runtime errors
            raise

    def load_model(self):
        """Eagerly load the TTS model (public method for startup loading)"""
        if self._initialized:
            logger.info(f"TTS model already loaded: {self.model_id}")
            return

        logger.info(f"Eagerly loading TTS model: {self.model_id}")
        self._load_model()

    def reload_model(self, model_id: str, eager_load: bool = True):
        """Reload with a different model

        Args:
            model_id: New model ID to load
            eager_load: If True, load the model immediately. If False, defer to lazy loading.
        """
        if model_id != self.model_id:
            self.model_id = model_id
            self.model = None
            self._initialized = False
            logger.info(f"TTS model changed to: {model_id}")

            if eager_load:
                logger.info(f"Eagerly loading new TTS model: {model_id}")
                self._load_model()
        elif eager_load and not self._initialized:
            # Same model but not initialized - load it
            logger.info(f"Loading TTS model: {model_id}")
            self._load_model()

    def get_model_info(self) -> Dict[str, Any]:
        """Get current model information"""
        return {
            "model_id": self.model_id,
            "initialized": self._initialized,
            "device": self.device if self._initialized and self.model_id != "edge-tts" else None,
            "sample_rate": self.sample_rate,
            "cache_dir": self.cache_dir,
        }

    def get_available_models(self) -> List[Dict[str, Any]]:
        """Get list of available models"""
        return [
            {
                "id": model_id,
                "name": info["name"],
                "description": info["description"],
                "sample_rate": info["sample_rate"],
                "languages": info["language"],
            }
            for model_id, info in self.AVAILABLE_MODELS.items()
        ]

    def clear_cache(self) -> int:
        """Clear audio cache, returns number of files deleted"""
        audio_dir = os.path.join(self.cache_dir, "audio")
        count = 0
        if os.path.exists(audio_dir):
            for f in Path(audio_dir).glob("*.*"):
                if f.suffix in [".wav", ".mp3"]:
                    try:
                        f.unlink()
                        count += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete cache file {f}: {e}")
        logger.info(f"Cleared {count} cached audio files")
        return count
