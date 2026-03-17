import httpx
import json
import logging
import asyncio
import time

logger = logging.getLogger(__name__)

# Retry configuration
_DEFAULT_MAX_RETRIES = 15
_DEFAULT_TIMEOUT = 600.0  # 10 minutes per request
_BACKOFF_BASE = 2.0       # exponential backoff base
_BACKOFF_MAX = 60.0       # cap wait at 60s


class OllamaError(Exception):
    """Raised when all LLM retry attempts are exhausted."""


def _backoff_sleep(attempt):
    """Exponential backoff: 2s, 4s, 8s, 16s, 32s, 60s, 60s, ..."""
    wait = min(_BACKOFF_BASE ** (attempt + 1), _BACKOFF_MAX)
    logger.info(f"Retrying in {wait:.0f}s...")
    time.sleep(wait)


async def _backoff_sleep_async(attempt):
    wait = min(_BACKOFF_BASE ** (attempt + 1), _BACKOFF_MAX)
    logger.info(f"Retrying in {wait:.0f}s...")
    await asyncio.sleep(wait)


def _build_request_body(model, messages, temperature, num_ctx):
    """Build the Ollama /api/chat request body (shared by sync/async)."""
    return {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }


class OllamaClient:
    def __init__(self, base_url="http://localhost:11434", model="llama3.1",
                 temperature=0, num_ctx=16384):
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.num_ctx = num_ctx

    def _maybe_no_think(self, prompt: str) -> str:
        """Append /no_think for qwen3 models to disable internal reasoning."""
        if "qwen3" in self.model.lower():
            return prompt + "\n/no_think"
        return prompt

    def _build_messages(self, prompt: str, chat_history: list | None = None) -> list:
        messages = list(chat_history) if chat_history else []
        messages.append({"role": "user", "content": self._maybe_no_think(prompt)})
        return messages

    def chat(self, prompt: str, chat_history: list | None = None,
             max_retries: int = _DEFAULT_MAX_RETRIES) -> str:
        messages = self._build_messages(prompt, chat_history)
        body = _build_request_body(self.model, messages, self.temperature, self.num_ctx)

        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
                    response = client.post(f"{self.base_url}/api/chat", json=body)
                    response.raise_for_status()
                    return response.json()["message"]["content"]
            except Exception as e:
                logger.error(f"Ollama API error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    _backoff_sleep(attempt)

        raise OllamaError(f"Max retries ({max_retries}) reached for prompt: {prompt[:100]}...")

    async def chat_async(self, prompt: str,
                         max_retries: int = _DEFAULT_MAX_RETRIES) -> str:
        messages = self._build_messages(prompt)
        body = _build_request_body(self.model, messages, self.temperature, self.num_ctx)

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                    response = await client.post(f"{self.base_url}/api/chat", json=body)
                    response.raise_for_status()
                    return response.json()["message"]["content"]
            except Exception as e:
                logger.error(f"Ollama API error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await _backoff_sleep_async(attempt)

        raise OllamaError(f"Max retries ({max_retries}) reached for prompt: {prompt[:100]}...")

    def chat_with_finish_info(self, prompt: str, chat_history: list | None = None,
                              max_retries: int = _DEFAULT_MAX_RETRIES) -> tuple[str, str]:
        messages = self._build_messages(prompt, chat_history)
        body = _build_request_body(self.model, messages, self.temperature, self.num_ctx)

        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
                    response = client.post(f"{self.base_url}/api/chat", json=body)
                    response.raise_for_status()
                    data = response.json()
                    content = data["message"]["content"]
                    done_reason = data.get("done_reason", "stop")
                    status = "max_output_reached" if done_reason == "length" else "finished"
                    return content, status
            except Exception as e:
                logger.error(f"Ollama API error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    _backoff_sleep(attempt)

        raise OllamaError(f"Max retries ({max_retries}) reached for prompt: {prompt[:100]}...")

    INTENT_CLASSIFICATION_PROMPT = """Classify the intent of this question and extract the key entities mentioned.

Intent types:
- LOOKUP: Direct question about a specific entity ("What is X?", "Tell me about X")
- RELATIONSHIP: How two or more entities relate ("How does X relate to Y?", "Connection between X and Y")
- EXPLORATION: Broad exploration of a topic ("What are the risks?", "Key findings")
- COMPARISON: Compare entities ("X vs Y", "Compare X and Y", "Differences between X and Y")
- HIERARCHICAL: Drill into document structure ("Details about section X", "Subsections of X")
- TEMPORAL: Changes over time or between versions ("What changed?", "Differences between 2023 and 2024")

Return ONLY valid JSON:
{"intent": "INTENT_TYPE", "entities": ["entity1", "entity2"]}

Question: """

    def classify_intent(self, question: str) -> tuple:
        """Classify query intent and extract key entities.

        Returns:
            tuple of (QueryIntent, list[str]) - the intent enum and extracted entity names
        """
        from oracle_pageindex.models import QueryIntent

        try:
            response = self.chat(self.INTENT_CLASSIFICATION_PROMPT + question, max_retries=3)
            parsed = self.extract_json(response)

            intent_str = parsed.get("intent", "EXPLORATION").upper()
            entities = parsed.get("entities", [])

            # Map string to enum, default to EXPLORATION
            try:
                intent = QueryIntent(intent_str)
            except ValueError:
                intent = QueryIntent.EXPLORATION

            # Ensure entities is a list of strings
            if not isinstance(entities, list):
                entities = []
            entities = [str(e) for e in entities if e]

            return intent, entities

        except Exception:
            return QueryIntent.EXPLORATION, []

    def embed(self, text: str, model: str | None = None) -> list[float]:
        """Get embedding vector for text via Ollama /api/embed endpoint.

        Args:
            text: The text to embed (typically an entity name).
            model: Optional embedding model override. Defaults to self.model.

        Returns:
            List of floats (the embedding vector), or empty list on error.
        """
        embed_model = model or self.model
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": embed_model, "input": text},
                )
                resp.raise_for_status()
                embeddings = resp.json().get("embeddings", [[]])
                return embeddings[0] if embeddings else []
        except Exception as e:
            logger.error(f"Embedding error: {e}")
            return []

    @staticmethod
    def extract_json(content: str):
        """Extract JSON from LLM output that may be wrapped in markdown fences."""
        try:
            start_idx = content.find("```json")
            if start_idx != -1:
                start_idx += 7
                end_idx = content.rfind("```")
                json_content = content[start_idx:end_idx].strip()
            else:
                json_content = content.strip()

            json_content = json_content.replace("None", "null")
            json_content = json_content.replace(",]", "]").replace(",}", "}")
            return json.loads(json_content)
        except json.JSONDecodeError:
            try:
                json_content = json_content.replace("\n", " ").replace("\r", " ")
                json_content = " ".join(json_content.split())
                return json.loads(json_content)
            except Exception:
                logger.error("Failed to parse JSON from LLM response")
                return {}
        except Exception:
            logger.error("Unexpected error extracting JSON")
            return {}
