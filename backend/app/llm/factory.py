"""Builds the optional local pieces from configuration. With no SDCV_* model settings this returns nothing and the pipeline
behaves exactly as before (Gemini for intake, images and narrative)."""
from __future__ import annotations

from .. import config


def build_local() -> dict:
    """Keyword arguments for Pipeline: intake_llm (a local text model or None), vision_mode and vision_llm."""
    kw: dict = {"intake_llm": None, "vision_mode": config.vision_backend() or None, "vision_llm": None}
    if config.intake_backend() == "local":
        from .local import LocalLLM   # imported here so a plain install never touches the module's optional dependencies
        kw["intake_llm"] = LocalLLM(config.local_model(), adapter=config.local_adapter(), load_in_4bit=config.local_4bit())
    if kw["vision_mode"] == "local":
        from .local import LocalVisionLLM
        kw["vision_llm"] = LocalVisionLLM(config.vision_model())
    return kw
