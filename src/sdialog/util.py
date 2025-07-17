"""
util: Utility Functions for sdialog

This module provides helper functions for the sdialog package, including serialization utilities to ensure
objects can be safely converted to JSON for storage or transmission.
"""
# SPDX-FileCopyrightText: Copyright © 2025 Idiap Research Institute <contact@idiap.ch>
# SPDX-FileContributor: Sergio Burdisso <sergio.burdisso@idiap.ch>
# SPDX-License-Identifier: MIT
import re
import json
import time
import torch
import logging
import subprocess
import transformers
import pandas as pd

from typing import Union
from pydantic import BaseModel
from sklearn.neighbors import NearestNeighbors
from langchain_ollama.chat_models import ChatOllama

logger = logging.getLogger(__name__)


class KNNModel:
    def __init__(self, items, k=3):
        # items = (item, vector) pair list
        self.model = NearestNeighbors(algorithm='auto',
                                      metric="cosine",
                                      n_jobs=-1)
        self.k = k
        self.model.ix2id = {ix: item for ix, (item, _) in enumerate(items)}
        self.model.fit([vec for _, vec in items])

    def neighbors(self, target_emb, k=None):
        k = k or self.k
        dists, indexes = self.model.kneighbors([target_emb],
                                               min(k, len(self.model.ix2id)),
                                               return_distance=True)
        dists, indexes = dists[0], indexes[0]
        return [(self.model.ix2id[indexes[ix]], dist) for ix, dist in enumerate(dists)]

    __call__ = neighbors


def softmax(values, temperature=0.05, as_list=True):
    probs = torch.nn.functional.softmax(torch.tensor(values, dtype=float) / temperature, dim=0)
    return probs.tolist() if as_list else probs


def get_universal_id() -> str:
    """
    Generates a unique identifier for a dialog or persona using a universal ID generator.

    :return: A unique identifier as a string.
    :rtype: str
    """
    return int(time.time() * 1000)


def remove_newlines(s: str) -> str:
    """
    Removes all newline (\n and \r) characters from a string, replacing them with a single space.

    :param s: The input string.
    :type s: str
    :return: The string with all newlines replaced by spaces.
    :rtype: str
    """
    if type(s) is not str:
        return s
    return re.sub(r'\s+', ' ', s)


def get_timestamp() -> str:
    """
    Returns the current UTC timestamp as an ISO 8601 string (e.g., "2025-01-01T12:00:00Z").

    :return: Current UTC timestamp in ISO 8601 format with 'Z' suffix.
    :rtype: str
    """
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def set_ollama_model_defaults(model_name: str, llm_params: dict) -> float:
    """ Set default parameters for an Ollama model if not already specified in llm_params."""
    if not is_ollama_model_name(model_name):
        return llm_params

    defaults = {}
    try:
        result = subprocess.run(
            ["ollama", "show", "--parameters", model_name],
            capture_output=True,
            text=True,
            check=True
        )
        # Look for a line like: "temperature: 0.7"
        for line in result.stdout.splitlines():
            m = re.match(r'(\w+)\s+([0-9]*\.?[0-9]+)', line)  # For now only with numbers
            # TODO: check support strings leter, gives Ollama ValidationError (probably the stop tokens?)
            # m = re.match(r'(\w+)\s+(.+)', line)
            if m:
                param, value = m.groups()
                if value.startswith('"'):
                    if param not in defaults:
                        defaults[param] = value.strip('"')
                    else:
                        if type(defaults[param]) is not list:
                            defaults[param] = [defaults[param]]
                        defaults[param].append(value.strip('"'))
                else:
                    try:
                        defaults[param] = float(value) if "." in value else int(value)
                    except ValueError:
                        logger.warning(f"Could not convert value '{value}' for parameter '{param}' "
                                       "to float or int. Skipping...")
        if "temperature" not in defaults:
            defaults["temperature"] = 0.8
    except Exception as e:
        logger.error(f"Error getting default parameters for model '{model_name}': {e}")

    for k, v in list(defaults.items()):
        if k in llm_params and llm_params[k] is not None:
            continue
        llm_params[k] = v
    return llm_params


def is_ollama_model_name(model_name: str) -> bool:
    return (
        model_name.startswith("ollama:")
        or not is_huggingface_model_name(model_name)
        and not is_openai_model_name(model_name)
        and not is_google_genai_model_name(model_name)
    )


def is_openai_model_name(model_name: str) -> bool:
    return model_name.startswith("openai:")


def is_google_genai_model_name(model_name: str) -> bool:
    return re.match(r"^google(-genai)?:", model_name, re.IGNORECASE)


def is_huggingface_model_name(model_name: str) -> bool:
    return model_name.startswith("huggingface:") or "/" in model_name


def get_llm_model(model_name: str,
                  output_format: Union[dict, BaseModel] = None,
                  **llm_kwargs):
    # If model name has a slash, assume it's a Hugging Face model
    # Otherwise, assume it's an Ollama model
    if is_openai_model_name(model_name):
        # If the model name is a string, assume it's an OpenAI model
        from langchain_openai import ChatOpenAI
        if ":" in model_name:
            model_name = model_name.split(":", 1)[-1]
        logger.info(f"Loading OpenAI model: {model_name}")

        if output_format and not issubclass(output_format, BaseModel):
            logger.warning("Output format should be a pydantic's BaseModel for ChatOpenAI models.")
        llm = ChatOpenAI(model=model_name,
                         response_format=output_format,
                         **llm_kwargs)
    elif is_google_genai_model_name(model_name):
        from langchain_google_genai import ChatGoogleGenerativeAI
        if ":" in model_name:
            model_name = model_name.split(":", 1)[-1]
        logger.info(f"Loading Google GenAI model: {model_name}")

        llm = ChatGoogleGenerativeAI(model=model_name, **llm_kwargs)

        if output_format and issubclass(output_format, BaseModel):
            llm = llm.with_structured_output(output_format)
        else:
            logger.warning("Output format should be a pydantic's BaseModel for ChatGoogleGenerativeAI models.")
    elif is_ollama_model_name(model_name):
        if model_name.startswith("ollama:"):
            model_name = model_name.split(":", 1)[-1]
        logger.info(f"Loading ChatOllama model: {model_name}")

        if output_format and issubclass(output_format, BaseModel):
            output_format = output_format.model_json_schema()

        ollama_check_and_pull_model(model_name)  # Ensure the model is available locally
        llm_kwargs = set_ollama_model_defaults(model_name, llm_kwargs)
        llm = ChatOllama(model=model_name,
                         format=output_format,
                         **llm_kwargs)
    else:
        if model_name.startswith("huggingface:"):
            model_name = model_name.split(":", 1)[-1]
        logger.info(f"Loading Hugging Face model: {model_name}")
        from langchain_huggingface import ChatHuggingFace, HuggingFacePipeline

        # Remove 'seed' from llm_kwargs if present (not supported by HuggingFace pipeline)
        llm_kwargs = {k: v for k, v in llm_kwargs.items() if k != "seed"}
        llm_kwargs["model"] = model_name

        # Default HuggingFace parameters
        hf_defaults = dict(
            torch_dtype=torch.bfloat16,
            device_map="auto",
            max_new_tokens=2048,
            do_sample=True,
            repetition_penalty=1.03,
            return_full_text=False,
        )
        hf_params = {**hf_defaults, **llm_kwargs}

        pipe = transformers.pipeline("text-generation", **hf_params)

        llm = ChatHuggingFace(llm=HuggingFacePipeline(pipeline=pipe))

    return llm


def ollama_check_and_pull_model(model_name: str) -> bool:
    """
    Check if an Ollama model is available locally, and if not, pull it from the hub.

    :param model_name: The name of the Ollama model to check/pull.
    :type model_name: str
    :return: True if the model is available (either was already local or successfully pulled), False otherwise.
    :rtype: bool
    """
    try:
        # First, check if the model is available locally
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=True
        )

        # Check if the model name is in the output
        if model_name in result.stdout:
            return True

        # If not available locally, try to pull it
        logger.info(f"Model '{model_name}' not found locally. Pulling it from the hub...")
        pull_result = subprocess.run(
            ["ollama", "pull", model_name],
            capture_output=True,
            text=True,
            check=True
        )

        if pull_result.returncode == 0:
            logger.info(f"Successfully pulled model '{model_name}'.")
            return True
        else:
            logger.error(f"Failed to pull model '{model_name}': {pull_result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Unexpected error while pulling model '{model_name}' from ollama hub: {e}")
        return False


def make_serializable(data: dict) -> dict:
    """
    Converts non-serializable values in a dictionary to strings so the dictionary can be safely serialized to JSON.

    :param data: The dictionary to process.
    :type data: dict
    :return: The dictionary with all values JSON-serializable.
    :rtype: dict
    """

    if type(data) is not dict:
        raise TypeError("Input must be a dictionary")

    for key, value in data.items():
        if hasattr(value, "json") and callable(value.json):
            data[key] = value.json()
        else:
            try:
                json.dumps(value)
            except (TypeError, OverflowError):
                data[key] = str(value)

    return data


def camel_or_snake_to_words(varname: str) -> str:
    """
    Converts a camelCase or snake_case variable name to a space-separated string of words.

    :param varname: The variable name in camelCase or snake_case.
    :type varname: str
    :return: The variable name as space-separated words.
    :rtype: str
    """
    # Replace underscores with spaces (snake_case)
    s = varname.replace('_', ' ')
    # Insert spaces before capital letters (camelCase, PascalCase)
    s = re.sub(r'(?<=[a-z0-9])([A-Z])', r' \1', s)
    # Normalize multiple spaces
    return ' '.join(s.split())


def remove_audio_tags(text: str) -> str:
    """
    Remove all the tags that use those formatting: <>, {}, (), []
    """
    return re.sub(r'<[^>]*>', '', text)


def dict_to_table(data: dict,
                  sort_by: str = None,
                  sort_ascending: bool = True,
                  markdown: bool = False,
                  format: str = ".2f",
                  show: bool = True) -> str:
    """
    Print a dictionary of dictionaries as a table (markdown or plain text).

    :param data: The dictionary to convert to a table.
    :type data: dict
    :param sort_by: The key to sort (column name) the table by. If None, no sorting is applied.
    :type sort_by: str, optional
    :param sort_ascending: If True, sort in ascending order; otherwise, descending.
    :type sort_ascending: bool
    :param markdown: If True, format the table as Markdown; otherwise, as plain text.
    :type markdown: bool
    :param format: The format string for floating-point numbers (e.g., ".2f").
    :type format: str
    :param show: If True, print the table to the console.
    :type show: bool
    :return: The formatted table as a string.
    :rtype: str
    """
    if not data:
        return "(empty table)"
    df = pd.DataFrame(data).T
    df.index.name = "dataset"
    if sort_by:
        df.sort_values(by=sort_by, ascending=sort_ascending, inplace=True)
    if markdown:
        table = df.to_markdown(floatfmt=format)
    else:
        table = df.to_markdown(tablefmt='fancy_grid', floatfmt=format)

    if show:
        print(table)

    return table


def upper_camel_to_dash(name: str) -> str:
    """
    Converts an UpperCamelCase class name to dash-case.

    :param name: The class name in UpperCamelCase.
    :type name: str
    :return: The class name in dash-case.
    :rtype: str
    """
    return re.sub(r'(?<!^)(?=[A-Z])', '-', name).lower()
