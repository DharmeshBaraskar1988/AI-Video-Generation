"""Language-model wrapper: Gemini free tier with rate limit, retry, JSON output and SQLite cache.

Keep calls batched (one call per job stage, never per sentence). Other providers
(Claude, OpenAI) can implement `LLMProvider` later without touching callers.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from collections import deque
from typing import Any, Protocol

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from sqlmodel import Session
from tenacity import before_sleep_log, retry, retry_if_exception, stop_after_attempt, wait_exponential

from ..config import settings
from ..db import LLMCache, engine
from . import jobcontrol

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    model: str
    last_model: str  # the model that answered the most recent call (after any fallback)

    def generate_json(
        self, prompt: str, *, system: str | None = None, temperature: float = 0.4, cache: bool = True,
        schema: dict | None = None,
    ) -> Any: ...


class RateLimiter:
    """Sliding one-minute window shared by all threads in this process."""

    def __init__(self, max_per_minute: int):
        self.max = max(1, max_per_minute)
        self.calls: deque[float] = deque()
        self.lock = threading.Lock()

    def wait(self) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                while self.calls and now - self.calls[0] >= 60:
                    self.calls.popleft()
                if len(self.calls) < self.max:
                    self.calls.append(now)
                    return
                delay = 60 - (now - self.calls[0]) + 0.1
            log.info("LLM rate limit reached, waiting %.1fs", delay)
            jobcontrol.sleep(delay)


class DailyQuotaExceeded(LLMError):
    def __init__(self, model: str, retry_seconds: float):
        super().__init__(f"Daily free-tier quota used up for {model}")
        self.model = model
        self.retry_seconds = retry_seconds


def _is_daily_quota(exc: BaseException) -> bool:
    return isinstance(exc, genai_errors.ClientError) and exc.code == 429 and "PerDay" in str(exc)


def _retry_seconds(exc: BaseException) -> float:
    m = re.search(r"retryDelay'?:\s*'(\d+)s", str(exc))
    return float(m.group(1)) if m else 3600.0


def _retryable(exc: BaseException) -> bool:
    """Retry server errors and per-minute rate limits. A daily quota will not clear by waiting."""
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError):
        return exc.code == 429 and not _is_daily_quota(exc)
    return False


def parse_json(text: str) -> Any:
    """Parse model output as JSON, tolerating ```json fences."""
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Model did not return valid JSON: {exc}; first 300 chars: {cleaned[:300]}") from exc


_EXHAUSTED: dict[str, float] = {}


class _CachedJSONProvider:
    """Shared JSON parsing + SQLite cache; subclasses implement `_call`."""

    model: str
    last_model: str

    def _call(self, prompt: str, system: str | None, temperature: float, schema: dict | None) -> str:
        raise NotImplementedError

    def _cache_key(self, prompt: str, system: str | None, temperature: float, schema: dict | None) -> str:
        raw = json.dumps([self.model, system or "", prompt, temperature, schema], ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def generate_json(
        self, prompt: str, *, system: str | None = None, temperature: float = 0.4, cache: bool = True,
        schema: dict | None = None,
    ) -> Any:
        key = self._cache_key(prompt, system, temperature, schema)
        if cache:
            with Session(engine) as s:
                hit = s.get(LLMCache, key)
                if hit:
                    log.info("LLM cache hit %s", key[:10])
                    return parse_json(hit.response)

        # Occasionally a reply is cut off or malformed; ask once more before giving up.
        for attempt in (1, 2):
            text = self._call(prompt, system, temperature, schema)
            try:
                data = parse_json(text)  # only cache responses that parse
                break
            except LLMError:
                if attempt == 2:
                    raise
                log.warning("LLM returned invalid JSON, retrying once")

        with Session(engine) as s:
            s.merge(LLMCache(key=key, model=self.last_model, response=text))
            s.commit()
        return data


def _openai_retryable(exc: BaseException) -> bool:
    import openai

    if isinstance(exc, openai.RateLimitError):
        return "insufficient_quota" not in str(exc)  # out of credit will not clear by waiting
    return isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError))


class OpenAIProvider(_CachedJSONProvider):
    """OpenAI chat completions in JSON mode. The schema is given in the system prompt (Gemini-style
    schemas are not always valid for OpenAI strict mode); callers validate the result anyway."""

    def __init__(self, model: str | None = None, api_key: str | None = None):
        import openai

        self.model = model or settings.openai_model
        self.last_model = self.model
        key = api_key or settings.openai_api_key
        if not key:
            raise LLMError("OPENAI_API_KEY is not set in .env")
        self.client = openai.OpenAI(api_key=key, timeout=180)
        self._no_temperature = False  # some reasoning models only accept the default temperature

    @retry(
        retry=retry_if_exception(_openai_retryable),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(5),
        before_sleep=before_sleep_log(log, logging.WARNING),
        sleep=jobcontrol.sleep,
        reraise=True,
    )
    def _call(self, prompt: str, system: str | None, temperature: float, schema: dict | None) -> str:
        import openai

        sys_text = (system or "").strip()
        sys_text += "\n\nReply with a single JSON object only."
        if schema:
            sys_text += " It must match this JSON schema:\n" + json.dumps(schema, ensure_ascii=False)
        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=[{"role": "system", "content": sys_text}, {"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        if not self._no_temperature:
            kwargs["temperature"] = temperature
        try:
            response = self.client.chat.completions.create(**kwargs)
        except openai.BadRequestError as exc:
            if "temperature" in str(exc) and not self._no_temperature:
                self._no_temperature = True
                kwargs.pop("temperature", None)
                response = self.client.chat.completions.create(**kwargs)
            else:
                raise LLMError(f"OpenAI rejected the request: {exc}") from exc
        except openai.AuthenticationError as exc:
            raise LLMError("OPENAI_API_KEY was rejected by OpenAI") from exc
        except openai.RateLimitError as exc:
            if "insufficient_quota" in str(exc):
                raise LLMError("OpenAI account has no remaining credit (insufficient_quota)") from exc
            raise
        text = response.choices[0].message.content if response.choices else None
        if not text:
            raise LLMError("Model returned an empty response")
        self.last_model = self.model
        return text


class GeminiProvider(_CachedJSONProvider):
    """Calls the configured model; when its free daily quota is used up, falls back to the next
    model in GEMINI_FALLBACK_MODELS (each model has its own free quota), then to OpenAI if a key is set."""

    def __init__(self, model: str | None = None, api_key: str | None = None, max_rpm: int | None = None):
        self.model = model or settings.gemini_model
        self.fallbacks = [m for m in settings.gemini_fallback_models if m and m != self.model]
        self.exhausted = _EXHAUSTED  # model -> time.time() when its daily quota resets (shared)
        self.last_model = self.model
        key = api_key or settings.gemini_api_key
        if not key:
            raise LLMError("GEMINI_API_KEY is not set in .env")
        if not self.model:
            raise LLMError("GEMINI_MODEL is not set in .env (run setup/pick_gemini_model.py)")
        self.client = genai.Client(api_key=key)
        self.limiter = RateLimiter(max_rpm or settings.gemini_max_rpm)
        self._openai: OpenAIProvider | None = None

    @retry(
        retry=retry_if_exception(_retryable),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(5),
        before_sleep=before_sleep_log(log, logging.WARNING),
        sleep=jobcontrol.sleep,
        reraise=True,
    )
    def _call_model(self, model: str, prompt: str, system: str | None, temperature: float, schema: dict | None) -> str:
        jobcontrol.check()
        self.limiter.wait()
        try:
            response = self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=temperature,
                    response_mime_type="application/json",
                    response_json_schema=schema,  # structured output: the reply must match this JSON schema
                ),
            )
        except genai_errors.ClientError as exc:
            if _is_daily_quota(exc):
                raise DailyQuotaExceeded(model, _retry_seconds(exc)) from exc
            raise
        if not response.text:
            raise LLMError("Model returned an empty response")
        return response.text

    def _call(self, prompt: str, system: str | None, temperature: float, schema: dict | None) -> str:
        now = time.time()
        chain = [m for m in [self.model, *self.fallbacks] if self.exhausted.get(m, 0) <= now]
        if not chain:
            if settings.openai_api_key:
                if self._openai is None:
                    self._openai = OpenAIProvider()
                    log.warning("All Gemini quotas used up, switching to OpenAI %s", self._openai.model)
                text = self._openai._call(prompt, system, temperature, schema)
                self.last_model = self._openai.last_model
                return text
            wait_h = (min(self.exhausted.values()) - now) / 3600
            raise LLMError(f"All Gemini models have used their free daily quota; the first resets in {wait_h:.1f} h")
        for model in chain:
            try:
                text = self._call_model(model, prompt, system, temperature, schema)
                self.last_model = model
                return text
            except DailyQuotaExceeded as exc:
                self.exhausted[model] = time.time() + exc.retry_seconds
                log.warning("%s: daily quota used up, falling back to the next model", model)
        return self._call(prompt, system, temperature, schema)  # all exhausted now -> OpenAI or raise


_provider: LLMProvider | None = None


def get_llm() -> LLMProvider:
    """LLM_PROVIDER=openai -> OPENAI_MODEL. Otherwise Gemini with the model chosen in Admin
    (llm_model setting), else GEMINI_MODEL from .env."""
    global _provider
    from .app_settings import get_setting

    if settings.llm_provider == "openai":
        if not isinstance(_provider, OpenAIProvider) or _provider.model != settings.openai_model:
            _provider = OpenAIProvider()
        return _provider
    wanted = get_setting("llm_model") or settings.gemini_model
    if not isinstance(_provider, GeminiProvider) or _provider.model != wanted:
        _provider = GeminiProvider(model=wanted)
    return _provider


def list_models() -> list[str]:
    """Gemini Flash models this API key can use (listing does not use generation quota)."""
    client = genai.Client(api_key=settings.gemini_api_key)
    names = []
    for m in client.models.list():
        name = (m.name or "").removeprefix("models/")
        actions = getattr(m, "supported_actions", None) or []
        if "flash" in name and "generateContent" in actions and not any(x in name for x in ("tts", "image", "live", "audio", "embedding")):
            names.append(name)
    return sorted(set(names), reverse=True)


def load_prompt(name: str) -> str:
    return (settings.prompts_dir / name).read_text(encoding="utf-8")
