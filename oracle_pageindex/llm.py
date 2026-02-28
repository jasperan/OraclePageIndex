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


def _backoff_sleep(attempt):
    """Exponential backoff: 2s, 4s, 8s, 16s, 32s, 60s, 60s, ..."""
    wait = min(_BACKOFF_BASE ** (attempt + 1), _BACKOFF_MAX)
    logger.info(f"Retrying in {wait:.0f}s...")
    time.sleep(wait)


async def _backoff_sleep_async(attempt):
    wait = min(_BACKOFF_BASE ** (attempt + 1), _BACKOFF_MAX)
    logger.info(f"Retrying in {wait:.0f}s...")
    await asyncio.sleep(wait)


class OllamaClient:
    def __init__(self, base_url="http://localhost:11434", model="llama3.1", temperature=0, num_ctx=16384):
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.num_ctx = num_ctx

    def _maybe_no_think(self, prompt):
        """Append /no_think for qwen3 models to disable internal reasoning."""
        if "qwen3" in self.model.lower():
            return prompt + "\n/no_think"
        return prompt

    def chat(self, prompt, chat_history=None, max_retries=_DEFAULT_MAX_RETRIES):
        messages = list(chat_history) if chat_history else []
        messages.append({"role": "user", "content": self._maybe_no_think(prompt)})

        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
                    response = client.post(
                        f"{self.base_url}/api/chat",
                        json={
                            "model": self.model,
                            "messages": messages,
                            "stream": False,
                            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
                        },
                    )
                    response.raise_for_status()
                    return response.json()["message"]["content"]
            except Exception as e:
                logger.error(f"Ollama API error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    _backoff_sleep(attempt)
                else:
                    logger.error(f"Max retries ({max_retries}) reached for prompt: {prompt[:100]}...")
                    return "Error"

    async def chat_async(self, prompt, max_retries=_DEFAULT_MAX_RETRIES):
        messages = [{"role": "user", "content": self._maybe_no_think(prompt)}]

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                    response = await client.post(
                        f"{self.base_url}/api/chat",
                        json={
                            "model": self.model,
                            "messages": messages,
                            "stream": False,
                            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
                        },
                    )
                    response.raise_for_status()
                    return response.json()["message"]["content"]
            except Exception as e:
                logger.error(f"Ollama API error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await _backoff_sleep_async(attempt)
                else:
                    logger.error(f"Max retries ({max_retries}) reached for prompt: {prompt[:100]}...")
                    return "Error"

    def chat_with_finish_info(self, prompt, chat_history=None, max_retries=_DEFAULT_MAX_RETRIES):
        messages = list(chat_history) if chat_history else []
        messages.append({"role": "user", "content": self._maybe_no_think(prompt)})

        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
                    response = client.post(
                        f"{self.base_url}/api/chat",
                        json={
                            "model": self.model,
                            "messages": messages,
                            "stream": False,
                            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
                        },
                    )
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
                else:
                    return "Error", "error"

    @staticmethod
    def extract_json(content):
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
