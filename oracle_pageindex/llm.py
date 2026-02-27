import httpx
import json
import logging
import asyncio
import time

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, base_url="http://localhost:11434", model="llama3.1", temperature=0):
        self.base_url = base_url
        self.model = model
        self.temperature = temperature

    def chat(self, prompt, chat_history=None, max_retries=10):
        messages = list(chat_history) if chat_history else []
        messages.append({"role": "user", "content": prompt})

        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=120.0) as client:
                    response = client.post(
                        f"{self.base_url}/api/chat",
                        json={
                            "model": self.model,
                            "messages": messages,
                            "stream": False,
                            "options": {"temperature": self.temperature},
                        },
                    )
                    response.raise_for_status()
                    return response.json()["message"]["content"]
            except Exception as e:
                logger.error(f"Ollama API error (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                else:
                    logger.error(f"Max retries reached for prompt: {prompt[:100]}...")
                    return "Error"

    async def chat_async(self, prompt, max_retries=10):
        messages = [{"role": "user", "content": prompt}]

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(
                        f"{self.base_url}/api/chat",
                        json={
                            "model": self.model,
                            "messages": messages,
                            "stream": False,
                            "options": {"temperature": self.temperature},
                        },
                    )
                    response.raise_for_status()
                    return response.json()["message"]["content"]
            except Exception as e:
                logger.error(f"Ollama API error (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                else:
                    logger.error(f"Max retries reached for prompt: {prompt[:100]}...")
                    return "Error"

    def chat_with_finish_info(self, prompt, chat_history=None, max_retries=10):
        messages = list(chat_history) if chat_history else []
        messages.append({"role": "user", "content": prompt})

        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=120.0) as client:
                    response = client.post(
                        f"{self.base_url}/api/chat",
                        json={
                            "model": self.model,
                            "messages": messages,
                            "stream": False,
                            "options": {"temperature": self.temperature},
                        },
                    )
                    response.raise_for_status()
                    data = response.json()
                    content = data["message"]["content"]
                    done_reason = data.get("done_reason", "stop")
                    status = "max_output_reached" if done_reason == "length" else "finished"
                    return content, status
            except Exception as e:
                logger.error(f"Ollama API error (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
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
