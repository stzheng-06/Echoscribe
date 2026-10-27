"""Application-level exceptions for EchoScribe."""


class EchoScribeError(Exception):
    """Base class for all application errors."""


class ConfigurationError(EchoScribeError):
    """Invalid or missing configuration."""


class AudioValidationError(EchoScribeError):
    """Imported audio file failed validation."""


class AudioConversionError(EchoScribeError):
    """Audio conversion or probing failed."""


class AudioCaptureError(EchoScribeError):
    """Windows system-audio capture could not start or finalize."""


class ProviderAuthenticationError(EchoScribeError):
    """ASR/LLM provider rejected credentials."""


class ProviderRateLimitError(EchoScribeError):
    """ASR/LLM provider rate limit hit."""


class ProviderTimeoutError(EchoScribeError):
    """ASR/LLM provider request timed out."""


class ProviderResponseError(EchoScribeError):
    """Unexpected or invalid response from provider."""


class ProviderAudioDurationError(ProviderResponseError):
    """Provider rejected an audio file because it exceeded a duration limit."""


class JobStateError(EchoScribeError):
    """Invalid job state transition or missing job data."""


class OperationCancelled(EchoScribeError):
    """A cooperative background operation was cancelled."""


class SummaryParseError(EchoScribeError):
    """Failed to parse structured summary output."""
