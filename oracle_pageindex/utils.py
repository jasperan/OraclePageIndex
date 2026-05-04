"""
Utility functions for OraclePageIndex.

Adapted from PageIndex's utils.py — pure data helpers with no LLM calls.
All LLM interactions belong in llm.py and parser.py.
"""

import copy
import json
import logging
import os
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace as config

import PyPDF2
import pymupdf
import tiktoken
import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class ConfigLoader:
    """Load config.yaml, merge with user overrides, return SimpleNamespace.

    Nested dicts (e.g. ``oracle.*``, ``ollama.*``) are flattened into
    top-level keys (``oracle_user``, ``ollama_model``, ...) **and** kept
    as nested dicts so callers can use either access style.
    """

    def __init__(self, default_path: str = None):
        if default_path is None:
            default_path = Path(__file__).parent / "config.yaml"
        self._default_dict = self._load_yaml(default_path)

    @staticmethod
    def _load_yaml(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @staticmethod
    def _flatten(d: dict, parent_key: str = "", sep: str = "_") -> dict:
        """Recursively flatten nested dicts into ``parent_child`` keys."""
        items = {}
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(ConfigLoader._flatten(v, parent_key=k, sep=sep))
            else:
                items[new_key] = v
        return items

    @staticmethod
    def _deep_merge(defaults: dict, overrides: dict) -> dict:
        """Recursively merge user overrides into defaults."""
        merged = copy.deepcopy(defaults)
        for key, value in overrides.items():
            if (
                isinstance(value, dict)
                and isinstance(merged.get(key), dict)
            ):
                merged[key] = ConfigLoader._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _validate_keys(self, user_dict: dict):
        # Allow any key that already exists at the top level or as a
        # flattened variant so users can override ``ollama_model`` directly.
        flat_defaults = self._flatten(self._default_dict)
        known = set(self._default_dict) | set(flat_defaults)
        unknown = set(user_dict) - known
        if unknown:
            raise ValueError(f"Unknown config keys: {unknown}")

    def load(self, user_opt=None) -> config:
        """Merge *user_opt* into the default config and return a
        ``SimpleNamespace`` that supports both ``cfg.ollama_model`` and
        ``cfg.ollama`` (as a nested dict).

        Environment variables override config.yaml values:
          ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN
        """
        if user_opt is None:
            user_dict = {}
        elif isinstance(user_opt, config):
            user_dict = vars(user_opt)
        elif isinstance(user_opt, dict):
            user_dict = user_opt
        else:
            raise TypeError("user_opt must be dict, SimpleNamespace or None")

        self._validate_keys(user_dict)

        # Deep-merge: user values override defaults without deleting sibling keys.
        merged = self._deep_merge(self._default_dict, user_dict)

        # Apply environment variable overrides for Oracle credentials
        oracle = merged.get("oracle", {})
        if isinstance(oracle, dict):
            if os.environ.get("ORACLE_USER"):
                oracle["user"] = os.environ["ORACLE_USER"]
            if os.environ.get("ORACLE_PASSWORD"):
                oracle["password"] = os.environ["ORACLE_PASSWORD"]
            if os.environ.get("ORACLE_DSN"):
                oracle["dsn"] = os.environ["ORACLE_DSN"]
            merged["oracle"] = oracle

        # Flatten nested sections into top‑level keys
        flat = self._flatten(merged)
        merged.update(flat)

        return config(**merged)


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------

def count_tokens(text: str, model: str = None) -> int:
    """Return the token count of *text* for the given model.

    Falls back to ``cl100k_base`` when the model name is not recognised by
    tiktoken (which is common for Ollama / open‑source models).
    """
    if not text:
        return 0
    try:
        enc = tiktoken.encoding_for_model(model or "cl100k_base")
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


# ---------------------------------------------------------------------------
# PDF helpers
# ---------------------------------------------------------------------------

def get_page_tokens(pdf_path, model: str = None, pdf_parser: str = "PyMuPDF"):
    """Extract pages and per‑page token counts from a PDF.

    Returns a list of ``(page_text, token_count)`` tuples.
    """
    if model is None:
        model = "cl100k_base"

    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")

    if pdf_parser == "PyPDF2":
        pdf_reader = PyPDF2.PdfReader(pdf_path)
        page_list = []
        for page in pdf_reader.pages:
            page_text = page.extract_text() or ""
            page_list.append((page_text, len(enc.encode(page_text))))
        return page_list

    elif pdf_parser == "PyMuPDF":
        if isinstance(pdf_path, BytesIO):
            doc = pymupdf.open(stream=pdf_path, filetype="pdf")
        elif isinstance(pdf_path, str) and os.path.isfile(pdf_path):
            doc = pymupdf.open(pdf_path)
        else:
            raise ValueError(f"Cannot open PDF: {pdf_path}")
        page_list = []
        for page in doc:
            page_text = page.get_text() or ""
            page_list.append((page_text, len(enc.encode(page_text))))
        doc.close()
        return page_list

    else:
        raise ValueError(f"Unsupported PDF parser: {pdf_parser}")


def get_text_of_pdf_pages(pdf_pages, start_page: int, end_page: int) -> str:
    """Join the raw text of pages *start_page* .. *end_page* (1‑based, inclusive)."""
    total = len(pdf_pages)
    start_page = max(1, min(start_page, total))
    end_page = max(start_page, min(end_page, total))
    text = ""
    for page_num in range(start_page - 1, end_page):
        text += pdf_pages[page_num][0]
    return text


def get_text_of_pdf_pages_with_labels(pdf_pages, start_page: int, end_page: int) -> str:
    """Like :func:`get_text_of_pdf_pages` but wraps each page in
    ``<physical_index_N>`` tags.
    """
    text = ""
    for page_num in range(start_page - 1, end_page):
        idx = page_num + 1
        text += f"<physical_index_{idx}>\n{pdf_pages[page_num][0]}\n<physical_index_{idx}>\n"
    return text


def get_pdf_name(pdf_path) -> str:
    """Extract a human‑friendly document name from a path or BytesIO object."""
    if isinstance(pdf_path, str):
        return os.path.basename(pdf_path)
    elif isinstance(pdf_path, BytesIO):
        pdf_reader = PyPDF2.PdfReader(pdf_path)
        meta = pdf_reader.metadata
        name = meta.title if meta and meta.title else "Untitled"
        # Sanitise characters invalid in filenames
        return name.replace("/", "-")
    return "Untitled"


def get_number_of_pages(pdf_path) -> int:
    """Return the total page count of a PDF."""
    pdf_reader = PyPDF2.PdfReader(pdf_path)
    return len(pdf_reader.pages)


# ---------------------------------------------------------------------------
# Tree / structure helpers
# ---------------------------------------------------------------------------

def write_node_id(data, node_id: int = 0) -> int:
    """Assign sequential, zero‑padded 4‑digit ``node_id`` values to every
    node in *data* (dict or list) that represents a tree structure.

    Returns the next available *node_id* so the caller can continue
    numbering across multiple calls.
    """
    if isinstance(data, dict):
        data["node_id"] = str(node_id).zfill(4)
        node_id += 1
        for key in list(data.keys()):
            if "nodes" in key:
                node_id = write_node_id(data[key], node_id)
    elif isinstance(data, list):
        for item in data:
            node_id = write_node_id(item, node_id)
    return node_id


def get_nodes(structure):
    """Flatten a tree into a list of nodes **without** their ``nodes``
    children key (deep‑copied).
    """
    if isinstance(structure, dict):
        node = copy.deepcopy(structure)
        node.pop("nodes", None)
        nodes = [node]
        for key in list(structure.keys()):
            if "nodes" in key:
                nodes.extend(get_nodes(structure[key]))
        return nodes
    elif isinstance(structure, list):
        nodes = []
        for item in structure:
            nodes.extend(get_nodes(item))
        return nodes
    return []


def structure_to_list(structure):
    """Flatten a tree to a list **preserving** the ``nodes`` children on
    each item (references, not copies).
    """
    if isinstance(structure, dict):
        nodes = [structure]
        if "nodes" in structure:
            nodes.extend(structure_to_list(structure["nodes"]))
        return nodes
    elif isinstance(structure, list):
        nodes = []
        for item in structure:
            nodes.extend(structure_to_list(item))
        return nodes
    return []


def list_to_tree(data):
    """Convert a flat list of dicts with ``structure`` codes (e.g. ``"1.2.3"``)
    into a nested tree with ``nodes`` children.
    """

    def _parent_structure(structure_code):
        if not structure_code:
            return None
        parts = str(structure_code).split(".")
        return ".".join(parts[:-1]) if len(parts) > 1 else None

    nodes_map = {}
    root_nodes = []

    for item in data:
        structure_code = item.get("structure")
        node = {
            "title": item.get("title"),
            "start_index": item.get("start_index"),
            "end_index": item.get("end_index"),
            "nodes": [],
        }
        nodes_map[structure_code] = node

        parent = _parent_structure(structure_code)
        if parent and parent in nodes_map:
            nodes_map[parent]["nodes"].append(node)
        else:
            root_nodes.append(node)

    def _clean(node):
        if not node["nodes"]:
            del node["nodes"]
        else:
            for child in node["nodes"]:
                _clean(child)
        return node

    return [_clean(n) for n in root_nodes]


def post_processing(structure, end_physical_index: int):
    """Convert ``physical_index`` values to ``start_index`` / ``end_index``
    pairs, then build the nested tree.

    *structure* is expected to be a flat list coming from the LLM with
    ``physical_index`` on each item.
    """
    # Filter out items missing physical_index or with out-of-range values
    structure = [
        item for item in structure
        if item.get("physical_index") is not None
        and isinstance(item.get("physical_index"), int)
        and 1 <= item["physical_index"] <= end_physical_index
    ]

    if not structure:
        return []

    for i, item in enumerate(structure):
        item["start_index"] = item.get("physical_index")
        if i < len(structure) - 1:
            next_item = structure[i + 1]
            if next_item.get("appear_start") == "yes":
                item["end_index"] = next_item.get("physical_index", end_physical_index) - 1
            else:
                item["end_index"] = next_item.get("physical_index", end_physical_index)
        else:
            item["end_index"] = end_physical_index

    tree = list_to_tree(structure)
    if tree:
        return tree

    # Fallback: return the flat list after cleaning up temp fields
    for node in structure:
        node.pop("appear_start", None)
        node.pop("physical_index", None)
    return structure


def add_node_text(node, pdf_pages):
    """Recursively attach ``text`` content to every node in the tree using
    the node's ``start_index`` / ``end_index`` and the parsed *pdf_pages*.
    """
    if isinstance(node, dict):
        start_page = node.get("start_index")
        end_page = node.get("end_index")
        if start_page is not None and end_page is not None:
            node["text"] = get_text_of_pdf_pages(pdf_pages, start_page, end_page)
        if "nodes" in node:
            add_node_text(node["nodes"], pdf_pages)
    elif isinstance(node, list):
        for item in node:
            add_node_text(item, pdf_pages)


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------

def extract_json(content: str):
    """Best‑effort extraction of a JSON object/array from LLM output that
    may be wrapped in markdown fences.
    """
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
            logger.error("Failed to parse JSON from response")
            return {}
    except Exception:
        logger.error("Unexpected error extracting JSON")
        return {}


def convert_physical_index_to_int(data):
    """Normalise ``physical_index`` values that may be strings like
    ``<physical_index_5>`` into plain integers.
    """
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "physical_index" in item:
                val = item["physical_index"]
                if isinstance(val, str):
                    if val.startswith("<physical_index_"):
                        item["physical_index"] = int(
                            val.split("_")[-1].rstrip(">").strip()
                        )
                    elif val.startswith("physical_index_"):
                        item["physical_index"] = int(val.split("_")[-1].strip())
    elif isinstance(data, str):
        if data.startswith("<physical_index_"):
            return int(data.split("_")[-1].rstrip(">").strip())
        elif data.startswith("physical_index_"):
            return int(data.split("_")[-1].strip())
        try:
            return int(data)
        except (ValueError, TypeError):
            return None
    return data


def add_preface_if_needed(data):
    """Insert a *Preface* node at position 0 when the first section does
    not start on page 1.
    """
    if not isinstance(data, list) or not data:
        return data
    if data[0].get("physical_index") is not None and data[0]["physical_index"] > 1:
        data.insert(0, {"structure": "0", "title": "Preface", "physical_index": 1})
    return data
