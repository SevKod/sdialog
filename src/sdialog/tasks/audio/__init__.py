from .spoken_question_answering import SpokenQuestionAnsweringTask
from .automatic_speech_recognition import AutomaticSpeechRecognitionTask
from .spoken_language_understanding import SpokenLanguageUnderstandingTask
from .diarization import DiarizationTask
from .diarization_enhanced import DiarizationEnhancedTask
from .speaker_identification import SpeakerIdentificationTask
from .speech_separation import SpeechSeparationTask
from .speech_separation_enhanced import SpeechSeparationEnhancedTask

__all__ = [
    "SpokenQuestionAnsweringTask",
    "AutomaticSpeechRecognitionTask",
    "SpokenLanguageUnderstandingTask",
    "DiarizationTask",
    "SpeakerIdentificationTask",
    "DiarizationEnhancedTask",
    "SpeechSeparationTask",
    "SpeechSeparationEnhancedTask",
]
