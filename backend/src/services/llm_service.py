"""Utility helpers for loading and using the local LLM."""

from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from typing import Any, Dict

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

logger = logging.getLogger(__name__)

DEFAULT_LOCATION = "Jakarta"
DEFAULT_RADIUS_METERS = 3000
DEFAULT_MODEL_NAME = "sshleifer/tiny-gpt2"


def _model_name() -> str:
    return os.getenv("LOCAL_LLM_MODEL_NAME", DEFAULT_MODEL_NAME).strip() or DEFAULT_MODEL_NAME


@lru_cache(maxsize=1)
def _get_pipeline() -> Any:
    model_name = _model_name()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    device_index = 0 if torch.cuda.is_available() else -1
    logger.info("Loading local LLM model '%s' on %s", model_name, device.upper())

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(model_name)
    text_generator = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        device=device_index,
        pad_token_id=tokenizer.pad_token_id,
        return_full_text=False,
    )
    return text_generator


def ensure_model_loaded() -> None:
    """Trigger the lazy loader to make sure the model is cached."""

    _get_pipeline()


def _default_intent(prompt: str) -> Dict[str, Any]:
    clean_prompt = prompt.strip()
    fallback_query = clean_prompt if clean_prompt else "places"
    return {
        "query": fallback_query,
        "location": DEFAULT_LOCATION,
        "radius_m": DEFAULT_RADIUS_METERS,
    }


def _coerce_radius(value: Any) -> int:
    try:
        radius = int(float(value))
    except (TypeError, ValueError):
        return DEFAULT_RADIUS_METERS
    return max(100, radius)


def _heuristic_from_prompt(prompt: str) -> Dict[str, Any]:
    intent = _default_intent(prompt)

    working_prompt = prompt

    radius_pattern = re.compile(r"radius\s*(\d+(?:\.\d+)?)\s*(km|m|meter|meters)?", re.IGNORECASE)
    match = radius_pattern.search(prompt)
    if match:
        value = float(match.group(1))
        unit = (match.group(2) or "m").lower()
        radius = int(value * 1000) if unit.startswith("km") else int(value)
        intent["radius_m"] = max(100, radius)
        working_prompt = working_prompt.replace(match.group(0), "")

    location_pattern = re.compile(r"(?:di|dekat|near|sekitar)\s+([\w\s]+)", re.IGNORECASE)
    loc_match = location_pattern.search(prompt)
    if loc_match:
        location_value = loc_match.group(1).strip()
        if location_value:
            intent["location"] = location_value
        working_prompt = working_prompt.replace(loc_match.group(0), "")

    cleaned_query = re.sub(r"\s+", " ", working_prompt).strip(" ,.-")
    if cleaned_query:
        intent["query"] = cleaned_query

    return intent


def _extract_from_text(text: str, prompt: str) -> Dict[str, Any]:
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        candidate = text[start:end]
        data = json.loads(candidate)
    except (ValueError, json.JSONDecodeError):
        logger.debug("LLM output was not valid JSON: %s", text)
        return _heuristic_from_prompt(prompt)

    intent = _default_intent(prompt)
    if isinstance(data, dict):
        query = data.get("query")
        location = data.get("location")
        radius = data.get("radius_m") or data.get("radius")

        if isinstance(query, str) and query.strip():
            intent["query"] = query.strip()
        if isinstance(location, str) and location.strip():
            intent["location"] = location.strip()
        if radius is not None:
            intent["radius_m"] = _coerce_radius(radius)

    return intent


def extract_intent_from_prompt(prompt: str) -> Dict[str, Any]:
    """Use the local LLM to extract a structured place intent from a prompt."""

    if not isinstance(prompt, str) or len(prompt.strip()) < 3:
        return _default_intent(prompt)

    generator = _get_pipeline()
    instruction = (
        "Anda adalah asisten yang mengekstrak niat pencarian tempat. "
        "Berikan hasil dalam JSON dengan kunci: query (string), location (string), radius_m (integer)."
        "\nPrompt pengguna: "
        f"{prompt.strip()}\nJSON:"
    )

    try:
        output = generator(
            instruction,
            max_new_tokens=200,
            do_sample=False,
            temperature=0.2,
            top_p=0.9,
            eos_token_id=generator.tokenizer.eos_token_id,
        )
        if isinstance(output, list) and output:
            text = output[0].get("generated_text") or ""
        else:
            text = ""
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.exception("LLM intent extraction failed: %s", exc)
        return _heuristic_from_prompt(prompt)

    return _extract_from_text(text, prompt)


__all__ = ["extract_intent_from_prompt", "ensure_model_loaded"]