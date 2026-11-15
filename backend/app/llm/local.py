"""Local Qwen backend that satisfies the same `LLM` protocol as GeminiClient.

Intended for the fine-tuned intake model (see training/). torch, transformers and peft are imported only when a model is first
used, so the base install (fastapi, uvicorn, pydantic, httpx, pytest) is unchanged and nothing here runs at import time.

    llm = LocalLLM("Qwen/Qwen2.5-3B-Instruct", adapter="training/outputs/intake-lora/final")
    text = llm.generate(system, user, json_mode=True)

Greedy decoding (the intake answer is a fixed JSON shape, so sampling only adds noise). LocalLLM is text only: snapshots reach it
as a transcript from the vision stage (LocalVisionLLM below, or Gemini), see llm/vision.py and llm/factory.py.
"""
from __future__ import annotations

import importlib.util
import threading
import time

from .gemini import LLMError
from .intake import LOCAL_INTAKE_SYSTEM

_DEPS = ("torch", "transformers")


class LocalLLM:
    intake_prompt = LOCAL_INTAKE_SYSTEM   # run_intake uses this instead of the long Gemini prompt (the adapter was trained on it)

    def __init__(self, model: str = "Qwen/Qwen2.5-3B-Instruct", adapter: str | None = None, *, max_new_tokens: int = 512,
                 load_in_4bit: bool = False, device: str | None = None):
        self.model_id, self.adapter = model, adapter
        self.max_new_tokens, self.load_in_4bit, self.device = max_new_tokens, load_in_4bit, device
        self.last_model: str | None = None
        self.attempts: list[dict] = []
        self._tok = self._model = None
        self._lock = threading.Lock()   # one generation at a time; the model object is not thread-safe

    @property
    def name(self) -> str:
        return self.last_model or self.model_id

    @property
    def available(self) -> bool:
        return all(importlib.util.find_spec(m) is not None for m in _DEPS)

    def for_model(self, model: str | None) -> "LocalLLM":
        return self   # one loaded model serves every request; the UI model choice does not apply to it

    # ------------------------------------------------------------------ loading
    def _load(self) -> None:
        if self._model is not None:
            return
        if not self.available:
            raise LLMError("local model unavailable: install torch and transformers (and peft for an adapter)")
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        kw: dict = {}
        if self.load_in_4bit:
            from transformers import BitsAndBytesConfig
            kw["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16)
            kw["device_map"] = "auto"
        else:
            kw["torch_dtype"] = torch.float16 if torch.cuda.is_available() else torch.float32
        tok = AutoTokenizer.from_pretrained(self.adapter or self.model_id)
        model = AutoModelForCausalLM.from_pretrained(self.model_id, **kw)
        if self.adapter:
            try:
                from peft import PeftModel
            except ImportError as e:
                raise LLMError("local adapter needs peft: pip install peft") from e
            model = PeftModel.from_pretrained(model, self.adapter)
        if not self.load_in_4bit:
            model.to(self.device or ("cuda" if torch.cuda.is_available() else "cpu"))
        model.eval()
        self._tok, self._model = tok, model

    # ------------------------------------------------------------------ generate
    def generate(self, system: str, user: str, *, json_mode: bool = False, images: list[dict] | None = None) -> str:
        if images:
            raise LLMError("the local model does not read images; use Gemini for briefs with images")
        t0 = time.monotonic()
        try:
            with self._lock:
                self._load()
                import torch
                msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
                # render to text, then tokenise: the return type of apply_chat_template(tokenize=True) changed between transformers 4 and 5
                prompt = self._tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
                enc = self._tok(prompt, return_tensors="pt").to(self._model.device)
                n = enc["input_ids"].shape[-1]
                with torch.no_grad():
                    out = self._model.generate(**enc, max_new_tokens=self.max_new_tokens, do_sample=False,
                                               pad_token_id=self._tok.eos_token_id)
                text = self._tok.decode(out[0][n:], skip_special_tokens=True).strip()
        except LLMError:
            self._note("error", t0)
            raise
        except Exception as e:   # a failed load or CUDA error must surface as the same error type the pipeline already handles
            self._note("error", t0)
            raise LLMError(f"local model failed: {type(e).__name__}: {str(e)[:200]}") from e
        if not text:
            self._note("empty", t0)
            raise LLMError("local model returned an empty response")
        self.last_model = self.model_id + ("+lora" if self.adapter else "")
        self._note("ok", t0)
        return text

    def _note(self, outcome: str, t0: float) -> None:
        self.attempts.append({"model": self.model_id, "outcome": outcome, "ms": int((time.monotonic() - t0) * 1000)})
        del self.attempts[:-60]


class LocalVisionLLM:
    """Qwen2.5-VL as a snapshot reader. Same generate() contract as the other backends, but it requires images.

    Used by the two-stage intake (backend/app/llm/vision.py): it transcribes, the fine-tuned text model extracts. Not fine-tuned;
    the stock instruct model is asked to copy what it sees. Needs torch, transformers (with Qwen2.5-VL support) and pillow."""
    def __init__(self, model: str = "Qwen/Qwen2.5-VL-3B-Instruct", *, max_new_tokens: int = 600, device: str | None = None):
        self.model_id, self.max_new_tokens, self.device = model, max_new_tokens, device
        self.last_model: str | None = None
        self.attempts: list[dict] = []
        self._proc = self._model = None
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self.last_model or self.model_id

    @property
    def available(self) -> bool:
        return all(importlib.util.find_spec(m) is not None for m in (*_DEPS, "PIL"))

    def for_model(self, model: str | None) -> "LocalVisionLLM":
        return self

    def _load(self) -> None:
        if self._model is not None:
            return
        if not self.available:
            raise LLMError("local vision model unavailable: install torch, transformers and pillow")
        import torch
        from transformers import AutoProcessor
        try:
            from transformers import AutoModelForImageTextToText as Auto
        except ImportError:   # older transformers
            from transformers import AutoModelForVision2Seq as Auto
        dev = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._proc = AutoProcessor.from_pretrained(self.model_id)
        self._model = Auto.from_pretrained(self.model_id, torch_dtype=torch.float16 if dev == "cuda" else torch.float32).to(dev).eval()

    def generate(self, system: str, user: str, *, json_mode: bool = False, images: list[dict] | None = None) -> str:
        if not images:
            raise LLMError("the local vision model needs at least one image")
        t0 = time.monotonic()
        try:
            with self._lock:
                self._load()
                import base64
                import io

                import torch
                from PIL import Image
                pics = [Image.open(io.BytesIO(base64.b64decode(i["data"]))).convert("RGB") for i in images]
                content = [{"type": "image"} for _ in pics] + [{"type": "text", "text": user}]
                msgs = [{"role": "system", "content": system}, {"role": "user", "content": content}]
                prompt = self._proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
                enc = self._proc(text=[prompt], images=pics, return_tensors="pt").to(self._model.device)
                with torch.no_grad():
                    out = self._model.generate(**enc, max_new_tokens=self.max_new_tokens, do_sample=False)
                text = self._proc.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)[0].strip()
        except LLMError:
            self._note("error", t0)
            raise
        except Exception as e:
            self._note("error", t0)
            raise LLMError(f"local vision model failed: {type(e).__name__}: {str(e)[:200]}") from e
        if not text:
            self._note("empty", t0)
            raise LLMError("local vision model returned an empty response")
        self.last_model = self.model_id
        self._note("ok", t0)
        return text

    def _note(self, outcome: str, t0: float) -> None:
        self.attempts.append({"model": self.model_id, "outcome": outcome, "ms": int((time.monotonic() - t0) * 1000)})
        del self.attempts[:-60]
