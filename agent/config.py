import os


DEFAULT_MODEL = "gemini-3.5-flash"
MAX_REVIEW_LINES = 500
DEFAULT_RETRIES = 2
DEFAULT_RETRY_DELAY = 2.0


def get_bounded_int_env(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return default

    return max(minimum, min(parsed, maximum))


class ConfigurationError(Exception):
    """Raised when the agent cannot be configured safely."""


class DependencyError(Exception):
    """Raised when a required package is not installed."""


class DiffParseError(Exception):
    """Raised when the unified diff cannot be parsed."""


def load_environment():
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError as exc:
        raise DependencyError(
            "python-dotenv paketi eksik. `pip install -r requirements.txt` calistirin."
        ) from exc

    load_dotenv()


def get_api_key():
    load_environment()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ConfigurationError(
            "'GEMINI_API_KEY' veya 'GOOGLE_API_KEY' bulunamadi. .env dosyasini kontrol edin."
        )
    return api_key

