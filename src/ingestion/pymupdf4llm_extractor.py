import pymupdf
import pymupdf4llm

from domain.models import Page


class Pymupdf4llmExtractor:
    def extract(self, data: bytes, filename: str) -> list[Page]:
        doc = pymupdf.open(stream=data, filetype="pdf")
        page_dicts = pymupdf4llm.to_markdown(doc, page_chunks=True, show_progress=False)
        if not isinstance(page_dicts, list):
            raise TypeError(
                f"{filename}: expected a list of page dicts from pymupdf4llm, "
                f"got {type(page_dicts).__name__}"
            )

        pages: list[Page] = []
        breadcrumb: dict[int, str] = {}
        for number, page_dict in enumerate(page_dicts, start=1):
            if not isinstance(page_dict, dict):
                raise TypeError(
                    f"{filename} page {number}: expected a page dict, "
                    f"got {type(page_dict).__name__}"
                )
            text = page_dict.get("text")
            if not isinstance(text, str):
                raise TypeError(
                    f"{filename} page {number}: expected str text, "
                    f"got {type(text).__name__}"
                )
            for item in page_dict.get("toc_items", []):
                level, title = item[0], item[1]
                breadcrumb = {lvl: t for lvl, t in breadcrumb.items() if lvl < level}
                breadcrumb[level] = title
            section = " > ".join(title for _, title in sorted(breadcrumb.items())) or None
            pages.append(Page(number=number, text=text, section=section))
        return pages
