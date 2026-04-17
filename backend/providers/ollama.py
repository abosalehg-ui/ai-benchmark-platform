"""مزود Ollama (نماذج محلية)."""
from __future__ import annotations

import httpx

from backend.providers.base import BaseProvider, ModelResponse, measure_latency


class OllamaProvider(BaseProvider):
    name = "ollama"
    # Ollama تكتشف النماذج ديناميكياً
    available_models: list[str] = []

    def __init__(self, api_key: str = "", base_url: str = "http://localhost:11434"):
        super().__init__(api_key=api_key, base_url=base_url)

    async def list_local_models(self) -> dict:
        """جلب قائمة بالنماذج المثبتة محلياً.

        يرجع dict فيه models (قائمة) + error (نص أو None).
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                r.raise_for_status()
                data = r.json()
                models = [m["name"] for m in data.get("models", [])]
                return {"models": models, "error": None}
        except httpx.ConnectError as e:
            return {
                "models": [],
                "error": f"ما قدرنا نتصل بـ Ollama على {self.base_url}. تأكد إنه شغّال: 'ollama serve' أو من تطبيق Ollama. ({e})",
            }
        except httpx.TimeoutException:
            return {
                "models": [],
                "error": f"انتهى الوقت (15s) عند الاتصال بـ {self.base_url}. Ollama قد يكون بطيئاً جداً أو محظوراً بجدار الحماية.",
            }
        except httpx.HTTPStatusError as e:
            return {
                "models": [],
                "error": f"Ollama رجّع خطأ HTTP {e.response.status_code}: {e.response.text[:200]}",
            }
        except Exception as e:
            return {
                "models": [],
                "error": f"{type(e).__name__}: {e}",
            }

    async def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        system: str | None = None,
    ) -> ModelResponse:
        url = f"{self.base_url}/api/chat"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        with measure_latency() as t:
            try:
                async with httpx.AsyncClient(timeout=300.0) as client:
                    r = await client.post(url, json=body)
                    r.raise_for_status()
                    data = r.json()
            except httpx.HTTPStatusError as e:
                return ModelResponse(
                    text="",
                    model_id=model,
                    error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                )
            except httpx.ConnectError:
                return ModelResponse(
                    text="",
                    model_id=model,
                    error=f"Cannot connect to Ollama at {self.base_url}. هل Ollama شغّال؟",
                )
            except Exception as e:
                return ModelResponse(
                    text="", model_id=model, error=f"{type(e).__name__}: {e}"
                )

        text = data.get("message", {}).get("content", "")
        in_tok = data.get("prompt_eval_count", 0)
        out_tok = data.get("eval_count", 0)

        return ModelResponse(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=t.elapsed_ms,
            cost_usd=0.0,  # محلي = مجاني
            model_id=model,
            raw=data,
        )
