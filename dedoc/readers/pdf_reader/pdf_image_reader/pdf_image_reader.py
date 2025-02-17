import os
from typing import List, Optional, Tuple

from numpy import ndarray

from dedoc.readers.pdf_reader.data_classes.line_with_location import LineWithLocation
from dedoc.readers.pdf_reader.data_classes.pdf_image_attachment import PdfImageAttachment
from dedoc.readers.pdf_reader.data_classes.tables.scantable import ScanTable
from dedoc.readers.pdf_reader.pdf_base_reader import ParametersForParseDoc, PdfBaseReader


class PdfImageReader(PdfBaseReader):
    """
    This class allows to extract content from the .pdf documents without a textual layer (not copyable documents),
    as well as from images (scanned documents).

    The following features are implemented to enhance the recognition results:

    * optical character recognition using Tesseract OCR;

    * table detection and recognition;

    * document binarization (configure via `need_binarization` parameter);

    * document orientation correction (automatically rotate on 90, 180, 270 degrees if it's needed);

    * one and two column documents classification;

    * detection of bold text.

    It isn't recommended to use this reader for extracting content from PDF documents with a correct textual layer, use other PDF readers instead.
    """

    def __init__(self, *, config: Optional[dict] = None) -> None:
        from dedocutils.preprocessing import AdaptiveBinarizer, SkewCorrector
        from dedoc.readers.pdf_reader.pdf_image_reader.columns_orientation_classifier.columns_orientation_classifier import ColumnsOrientationClassifier
        from dedoc.readers.pdf_reader.pdf_image_reader.ocr.ocr_line_extractor import OCRLineExtractor
        from dedoc.config import get_config
        from dedoc.extensions import recognized_extensions, recognized_mimes
        from dedoc.utils import supported_image_types

        supported_image_extensions = {ext for ext in supported_image_types if ext.startswith(".")}
        super().__init__(
            config=config,
            recognized_extensions=recognized_extensions.pdf_like_format.union(recognized_extensions.image_like_format).union(supported_image_extensions),
            recognized_mimes=recognized_mimes.pdf_like_format.union(recognized_mimes.image_like_format)
        )
        self.skew_corrector = SkewCorrector()
        self.column_orientation_classifier = ColumnsOrientationClassifier(on_gpu=self.config.get("on_gpu", False),
                                                                          checkpoint_path=os.path.join(get_config()["resources_path"],
                                                                                                       "scan_orientation_efficient_net_b0.pth"),
                                                                          config=self.config)
        self.binarizer = AdaptiveBinarizer()
        self.ocr = OCRLineExtractor(config=self.config)

    def _process_one_page(self,
                          image: ndarray,
                          parameters: ParametersForParseDoc,
                          page_number: int,
                          path: str) -> Tuple[List[LineWithLocation], List[ScanTable], List[PdfImageAttachment], List[float]]:
        import os
        from datetime import datetime
        import cv2
        from dedoc.utils.parameter_utils import get_path_param

        #  --- Step 1: correct orientation and detect column count ---
        rotated_image, is_one_column_document, angle = self._detect_column_count_and_orientation(image, parameters)
        if self.config.get("debug_mode", False):
            self.logger.info(f"Angle page rotation = {angle}")

        #  --- Step 2: do binarization ---
        if parameters.need_binarization:
            rotated_image, _ = self.binarizer.preprocess(rotated_image)
            if self.config.get("debug_mode", False):
                debug_dir = get_path_param(self.config, "path_debug")
                cv2.imwrite(os.path.join(debug_dir, f"{datetime.now().strftime('%H-%M-%S')}_result_binarization.jpg"), rotated_image)

        #  --- Step 3: table detection and recognition ---
        if parameters.need_pdf_table_analysis:
            clean_image, tables = self.table_recognizer.recognize_tables_from_image(
                image=rotated_image,
                page_number=page_number,
                language=parameters.language,
                orient_analysis_cells=parameters.orient_analysis_cells,
                orient_cell_angle=parameters.orient_cell_angle,
                table_type=parameters.table_type
            )
        else:
            clean_image, tables = rotated_image, []

        # --- Step 4: plain text recognition and text style detection ---
        page = self.ocr.split_image2lines(image=clean_image, language=parameters.language, is_one_column_document=is_one_column_document, page_num=page_number)

        lines = self.metadata_extractor.extract_metadata_and_set_annotations(page_with_lines=page)
        return lines, tables, page.attachments, [angle]

    def _detect_column_count_and_orientation(self, image: ndarray, parameters: ParametersForParseDoc) -> Tuple[ndarray, bool, float]:
        """
        Function :
            - detects the number of page columns
            - detects page orientation angle
            - rotates the page on detected angle
        Return: rotated_image and indicator if the page is one-column
        """
        import os
        from datetime import datetime
        import cv2
        from dedoc.utils.parameter_utils import get_path_param

        columns, angle = None, None

        if parameters.is_one_column_document is None or parameters.document_orientation is None:
            columns, angle = self.column_orientation_classifier.predict(image)
            self.logger.info(f"Predicted orientation angle = {angle}, columns = {columns}")

        is_one_column_document = columns == 1 if parameters.is_one_column_document is None else parameters.is_one_column_document
        angle = angle if parameters.document_orientation is None else 0
        self.logger.info(f"Final orientation angle = {angle}, is_one_column_document = {is_one_column_document}")

        rotated_image, result_angle = self.skew_corrector.preprocess(image, {"orientation_angle": angle})
        result_angle = result_angle["rotated_angle"]

        if self.config.get("debug_mode", False):
            debug_dir = get_path_param(self.config, "path_debug")
            img_path = os.path.join(debug_dir, f"{datetime.now().strftime('%H-%M-%S')}_result_orientation.jpg")
            self.logger.info(f"Save image to {img_path}")
            cv2.imwrite(img_path, rotated_image)

        return rotated_image, is_one_column_document, result_angle
