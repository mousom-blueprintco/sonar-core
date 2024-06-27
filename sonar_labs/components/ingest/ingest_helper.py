import logging
from pathlib import Path
from typing import Optional
import fitz
import uuid
from google.cloud import vision

from llama_index.core.readers import StringIterableReader
from llama_index.core.readers.base import BaseReader
from llama_index.core.readers.json import JSONReader
from llama_index.core.schema import Document
logger = logging.getLogger(__name__)



# Inspired by the `llama_index.core.readers.file.base` module
def _try_loading_included_file_formats() -> dict[str, type[BaseReader]]:
    try:
        from llama_index.readers.file.docs import (  # type: ignore
            DocxReader,
            HWPReader,
            PDFReader,
        )
        from llama_index.readers.file.epub import EpubReader  # type: ignore
        from llama_index.readers.file.image import ImageReader  # type: ignore
        from llama_index.readers.file.ipynb import IPYNBReader  # type: ignore
        from llama_index.readers.file.markdown import MarkdownReader  # type: ignore
        from llama_index.readers.file.mbox import MboxReader  # type: ignore
        from llama_index.readers.file.slides import PptxReader  # type: ignore
        from llama_index.readers.file.tabular import PandasCSVReader  # type: ignore
        from llama_index.readers.file.video_audio import (  # type: ignore
            VideoAudioReader,
        )
    except ImportError as e:
        raise ImportError("`llama-index-readers-file` package not found") from e

    default_file_reader_cls: dict[str, type[BaseReader]] = {
        ".hwp": HWPReader,
        ".pdf": PDFReader,
        ".docx": DocxReader,
        ".pptx": PptxReader,
        ".ppt": PptxReader,
        ".pptm": PptxReader,
        ".jpg": ImageReader,
        ".png": ImageReader,
        ".jpeg": ImageReader,
        ".mp3": VideoAudioReader,
        ".mp4": VideoAudioReader,
        ".csv": PandasCSVReader,
        ".epub": EpubReader,
        ".md": MarkdownReader,
        ".mbox": MboxReader,
        ".ipynb": IPYNBReader,
    }
    return default_file_reader_cls


# Patching the default file reader to support other file types
FILE_READER_CLS = _try_loading_included_file_formats()
FILE_READER_CLS.update(
    {
        ".json": JSONReader,
    }
)


class IngestionHelper:
    """Helper class to transform a file into a list of documents.

    This class should be used to transform a file into a list of documents.
    These methods are thread-safe (and multiprocessing-safe).
    """

    @staticmethod
    def transform_file_into_documents(
        file_name: str, file_path: Path, file_id: str, 
        project_id: Optional[str], user_id: Optional[str], org_id: Optional[str]
    ) -> list[Document]:
        documents = IngestionHelper._load_file_to_documents(file_name, file_path)
        for document in documents:
            document.metadata["file_name"] = file_name
            document.metadata["file_id"] = file_id
            document.metadata["project_id"] = project_id
            document.metadata["user_id"] = user_id
            document.metadata["org_id"] = org_id
        IngestionHelper._exclude_metadata(documents)
        return documents

    @staticmethod
    def _load_file_to_documents(file_name: str, file_path: Path) -> list[Document]:
        logger.debug("Transforming file_name=%s into documents", file_name)
        extension = Path(file_name).suffix
        reader_cls = FILE_READER_CLS.get(extension)
        if reader_cls is None:
            logger.debug(
                "No reader found for extension=%s, using default string reader",
                extension,
            )
            # Read as a plain text
            string_reader = StringIterableReader()
            
            return string_reader.load_data([file_path.read_text()])

        logger.debug("Specific reader found for extension=%s", extension)
        # return reader_cls().load_data(file_path)
        return IngestionHelper._sonar_parser(file_path)

    @staticmethod
    def _exclude_metadata(documents: list[Document]) -> None:
        logger.debug("Excluding metadata from count=%s documents", len(documents))
        for document in documents:
            document.metadata["doc_id"] = document.doc_id
            # We don't want the Embeddings search to receive this metadata
            document.excluded_embed_metadata_keys = ["doc_id"]
            # We don't want the LLM to receive these metadata in the context
            document.excluded_llm_metadata_keys = ["doc_id", "file_id", "org_id"]
            
    @staticmethod
    def _get_text_percentage(page) -> float:
        """
        Calculate the percentage of the page that is covered by (searchable) text.
        """
        total_page_area = abs(page.rect)
        total_text_area = 0.0
        
        for b in page.get_text_blocks():
            r = fitz.Rect(b[:4])  # rectangle where block text appears
            total_text_area += abs(r)
            
        return total_text_area / total_page_area
    
    
    
    @staticmethod
    def _perform_ocr_with_google(page) -> str:
        """
        Perform OCR on the given PDF page using Google Cloud Vision API.
        """
        client = vision.ImageAnnotatorClient()
        
        pix = page.get_pixmap()
        # logger.info(f'Image size: width={pix.width}, height={pix.height}')
        img_bytes = pix.tobytes(output="png")
        # file_size_kb = len(img_bytes) / 1024
        # logger.info(f'File size: {file_size_kb:.2f} KB')
        image = vision.Image(content=img_bytes)

        response = client.text_detection(image=image)
        texts = response.text_annotations

        text = ""
        if texts:
            text = texts[0].description  # Full text
        if response.error.message:
            raise Exception(f'{response.error.message}')
        
        return text

    @staticmethod
    def _get_page_title(page) -> str:
        """
        Extract the title from the given PDF page using heuristics.
        """
        text_blocks = page.get_text("dict")["blocks"]
        if not text_blocks:
            return None

        # Simple heuristic: assume the first text block is the title
        first_block = text_blocks[0]
        if first_block["type"] == 0:  # text block
            title = first_block["lines"][0]["spans"][0]["text"]
            return title.strip()
        
        return None
    
    @staticmethod
    def _sonar_parser(file_path: Path) -> list[Document]:
        doc = fitz.open(file_path)
        parsed_documents = []
        
        for page_num, page in enumerate(doc):
            title = IngestionHelper._get_page_title(page)
            if title is None:
                title = f"Document {page_num + 1}"
            
            text_perc = IngestionHelper._get_text_percentage(page)
            print(f"Page {page_num + 1} Text percentage: {text_perc:.2%}")
            if text_perc < 30.00:
                print(f"Page {page_num + 1} is a fully scanned page - performing OCR using Google Vision")
                ocr_text = IngestionHelper._perform_ocr_with_google(page)
                parsed_documents.append(Document(
                id_=str(uuid.uuid4()),
                embedding=None,
                metadata={"page_label": page_num + 1},
                excluded_embed_metadata_keys=[],
                excluded_llm_metadata_keys=[],
                relationships={},
                text=ocr_text,
                start_char_idx=None,
                end_char_idx=None,
                text_template='{metadata_str}\n\n{content}',
                metadata_template='{key}: {value}',
                metadata_seperator='\n',
                class_name="Document"
            ))
                print(f"OCR Text for Page {page_num + 1}:\n{ocr_text}")
            else:
                page_text = page.get_text()
                parsed_documents.append(Document(
                id_=str(uuid.uuid4()),
                embedding=None,
                metadata={"page_label": page_num + 1},
                excluded_embed_metadata_keys=[],
                excluded_llm_metadata_keys=[],
                relationships={},
                text=page_text,
                start_char_idx=None,
                end_char_idx=None,
                text_template='{metadata_str}\n\n{content}',
                metadata_template='{key}: {value}',
                metadata_seperator='\n',
                class_name="Document"
            ))
                print(f"Text for Page {page_num + 1}:\n{page_text}")
        doc.close()             
        return parsed_documents
