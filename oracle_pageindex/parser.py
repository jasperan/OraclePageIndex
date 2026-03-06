"""
Document parser for OraclePageIndex.

Adapted from PageIndex's page_index.py — uses OllamaClient instead of
OpenAI for all LLM interactions.  Pure parsing logic (token counting,
PDF reading, tree manipulation) lives in utils.py.
"""

import asyncio
import copy
import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed

from .llm import OllamaClient
from .utils import (
    add_node_text,
    add_preface_if_needed,
    convert_physical_index_to_int,
    count_tokens,
    extract_json,
    get_number_of_pages,
    get_page_tokens,
    get_pdf_name,
    get_text_of_pdf_pages_with_labels,
    list_to_tree,
    post_processing,
    structure_to_list,
    write_node_id,
)

logger = logging.getLogger(__name__)


class DocumentParser:
    """High-level document parser that turns a PDF into a structured tree.

    Parameters
    ----------
    llm : OllamaClient
        Pre-configured Ollama client used for all LLM interactions.
    toc_check_page_num : int
        How many initial pages to send for ToC / structure extraction.
    max_token_num_each_node : int
        Upper token budget when grouping pages for the LLM.
    pdf_parser : str
        Backend for PDF text extraction (``"PyMuPDF"`` or ``"PyPDF2"``).
    add_node_id : bool
        Whether to assign sequential node IDs to every tree node.
    add_summaries : bool
        Whether to generate per-node summaries via the LLM.
    """

    def __init__(
        self,
        llm: OllamaClient,
        toc_check_page_num: int = 20,
        max_token_num_each_node: int = 20_000,
        pdf_parser: str = "PyMuPDF",
        add_node_id: bool = True,
        add_summaries: bool = True,
    ):
        self.llm = llm
        self.toc_check_page_num = toc_check_page_num
        self.max_token_num_each_node = max_token_num_each_node
        self.pdf_parser = pdf_parser
        self.add_node_id = add_node_id
        self.add_summaries = add_summaries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_pdf(self, pdf_path: str):
        """Extract per-page text and token counts from a PDF.

        Returns
        -------
        page_list : list[tuple[str, int]]
            Each element is ``(page_text, token_count)``.
        doc_name : str
            Human-friendly document name derived from the file path.

        Raises
        ------
        FileNotFoundError
            If the PDF file does not exist.
        ValueError
            If the path does not point to a PDF file.
        """
        import os
        if isinstance(pdf_path, str):
            if not os.path.isfile(pdf_path):
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")
            if not pdf_path.lower().endswith(".pdf"):
                raise ValueError(f"Expected a .pdf file, got: {pdf_path}")

        page_list = get_page_tokens(
            pdf_path, model=self.llm.model, pdf_parser=self.pdf_parser
        )
        doc_name = get_pdf_name(pdf_path)
        logger.info(f"Parsed {len(page_list)} pages from '{doc_name}'")
        return page_list, doc_name

    def build_tree(self, pdf_path) -> dict:
        """Full pipeline: parse PDF -> extract structure via Ollama ->
        assign node IDs -> attach page text -> optionally summarise.

        Returns
        -------
        dict
            ``{"doc_name": str, "structure": list, "page_list": list}``
        """
        page_list, doc_name = self.parse_pdf(pdf_path)
        total_pages = len(page_list)

        # --- Generate flat ToC via LLM ------------------------------------
        flat_toc = self.generate_tree_from_pages(page_list, doc_name)

        if flat_toc is None or len(flat_toc) == 0:
            logger.warning("ToC extraction failed — using fallback structure")
            flat_toc = self._create_fallback_structure(page_list)

        # --- Normalise physical_index to int ------------------------------
        flat_toc = convert_physical_index_to_int(flat_toc)

        # --- Optionally prepend a Preface node ----------------------------
        flat_toc = add_preface_if_needed(flat_toc)

        # --- Build the nested tree ----------------------------------------
        structure = post_processing(flat_toc, end_physical_index=total_pages)

        # --- Node IDs -----------------------------------------------------
        if self.add_node_id:
            write_node_id(structure)

        # --- Attach page text to every node --------------------------------
        add_node_text(structure, page_list)

        # --- Per-node summaries -------------------------------------------
        if self.add_summaries:
            try:
                self._generate_summaries(structure)
            except Exception:
                logger.exception("Summary generation failed — continuing without")

        return {
            "doc_name": doc_name,
            "structure": structure,
            "page_list": page_list,
        }

    # ------------------------------------------------------------------
    # Tree generation from pages
    # ------------------------------------------------------------------

    def generate_tree_from_pages(self, page_list, doc_name: str):
        """Send the first N pages to Ollama and ask for a hierarchical
        table-of-contents / section structure as a JSON array.

        Each item has ``structure``, ``title``, and ``physical_index``.
        """
        total_pages = len(page_list)
        check_pages = min(self.toc_check_page_num, total_pages)

        # Build labelled text for the first N pages
        labelled_text = get_text_of_pdf_pages_with_labels(
            page_list, start_page=1, end_page=check_pages
        )

        prompt = (
            f"You are analyzing a document called '{doc_name}' with "
            f"{total_pages} pages. Below are the first {check_pages} pages.\n\n"
            f"Extract the table of contents / section structure. Return a JSON "
            f"array where each item has:\n"
            f'  - "structure": hierarchical numbering like "1", "1.1", "2", etc.\n'
            f'  - "title": the section title\n'
            f'  - "physical_index": the 1-based page number where this section starts\n\n'
            f"Rules:\n"
            f"- Use the <physical_index_N> tags in the text to determine page numbers.\n"
            f"- Only include sections you can actually identify in the text.\n"
            f"- Return ONLY the JSON array, no other text.\n\n"
            f"Document text:\n{labelled_text}"
        )

        from .llm import OllamaError
        try:
            response = self.llm.chat(prompt)
        except OllamaError:
            logger.error("LLM failed for tree generation")
            return None

        parsed = self.llm.extract_json(response)
        if not parsed:
            # Try the utils-level extractor as a fallback
            parsed = extract_json(response)

        if isinstance(parsed, dict) and "table_of_contents" in parsed:
            parsed = parsed["table_of_contents"]

        if isinstance(parsed, list):
            logger.info(f"Extracted {len(parsed)} sections from first {check_pages} pages")

            # If there are remaining pages beyond what we checked, continue
            if total_pages > check_pages:
                additional = self._generate_tree_continuation(
                    page_list, parsed, start_page=check_pages + 1
                )
                if additional:
                    parsed.extend(additional)
                    logger.info(
                        f"Extended structure with {len(additional)} additional sections"
                    )
            return parsed

        logger.warning("Could not parse ToC from LLM response")
        return None

    # ------------------------------------------------------------------
    # Internal: continuation for long documents
    # ------------------------------------------------------------------

    def _generate_tree_continuation(self, page_list, existing_toc, start_page: int):
        """For documents longer than *toc_check_page_num*, continue
        extracting the structure from the remaining pages in chunks.
        """
        total_pages = len(page_list)
        all_additional = []
        current_start = start_page
        chunk_size = self.toc_check_page_num

        while current_start <= total_pages:
            end_page = min(current_start + chunk_size - 1, total_pages)
            labelled_text = get_text_of_pdf_pages_with_labels(
                page_list, start_page=current_start, end_page=end_page
            )

            # Only send the last 10 sections for context to keep prompt
            # within num_ctx limits (full ToC grows too large for long docs)
            recent_toc = existing_toc[-10:] if len(existing_toc) > 10 else existing_toc
            prompt = (
                "You are an expert in extracting hierarchical tree structures.\n"
                "You are given the most recent sections extracted so far and the text of "
                "additional pages. Continue the tree structure to include these pages.\n\n"
                "Return ONLY a JSON array of new items (do NOT repeat previous items). "
                "Each item has:\n"
                '  - "structure": hierarchical numbering\n'
                '  - "title": the section title\n'
                '  - "physical_index": the 1-based page number\n\n'
                f"Recent sections:\n{json.dumps(recent_toc)}\n\n"
                f"Additional pages:\n{labelled_text}"
            )

            try:
                response = self.llm.chat(prompt)
            except OllamaError:
                break

            parsed = self.llm.extract_json(response)
            if not parsed:
                parsed = extract_json(response)

            if isinstance(parsed, list) and parsed:
                parsed = convert_physical_index_to_int(parsed)
                all_additional.extend(parsed)
                existing_toc = existing_toc + parsed

            current_start = end_page + 1

        return all_additional

    # ------------------------------------------------------------------
    # Fallback structure
    # ------------------------------------------------------------------

    def _create_fallback_structure(self, page_list):
        """Create a simple one-section-per-page structure when ToC
        detection fails entirely.
        """
        fallback = []
        for i in range(len(page_list)):
            fallback.append(
                {
                    "structure": str(i + 1),
                    "title": f"Page {i + 1}",
                    "physical_index": i + 1,
                }
            )
        logger.info(f"Created fallback structure with {len(fallback)} page-level sections")
        return fallback

    # ------------------------------------------------------------------
    # Summary generation
    # ------------------------------------------------------------------

    def _generate_summaries(self, structure):
        """Generate summaries for all nodes concurrently using threads.

        Each node gets a ``summary`` field added in-place.
        """
        nodes = structure_to_list(structure)
        nodes_with_text = [n for n in nodes if n.get("text")]

        if not nodes_with_text:
            return

        logger.info(f"Generating summaries for {len(nodes_with_text)} nodes")

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(self._summarize_node, node): node
                for node in nodes_with_text
            }
            for future in as_completed(futures):
                node = futures[future]
                try:
                    summary = future.result()
                    node["summary"] = summary
                except Exception:
                    logger.exception(
                        f"Failed to summarize node '{node.get('title', '?')}'"
                    )
                    node["summary"] = ""

    def _summarize_node(self, node) -> str:
        """Generate a concise summary for a single tree node via the LLM."""
        text = node.get("text", "")
        title = node.get("title", "Untitled")

        # Truncate very long text to stay within context limits (token-aware)
        max_tokens = 10_000
        token_count = count_tokens(text)
        if token_count > max_tokens:
            # Rough truncation: 1 token ~ 4 chars, then verify
            text = text[:max_tokens * 4]
            while count_tokens(text) > max_tokens:
                text = text[:int(len(text) * 0.9)]
            text = text + "\n[...truncated...]"

        prompt = (
            "You are given a section of a document. Generate a concise description "
            "of what the main points covered in this section are.\n\n"
            f"Section title: {title}\n\n"
            f"Section text:\n{text}\n\n"
            "Directly return the description, do not include any other text."
        )

        from .llm import OllamaError
        try:
            return self.llm.chat(prompt)
        except OllamaError:
            return ""
