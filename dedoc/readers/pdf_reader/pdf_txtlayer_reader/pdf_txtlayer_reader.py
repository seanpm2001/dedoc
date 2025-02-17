from typing import List, Optional, Tuple

from dedocutils.data_structures import BBox
from numpy import ndarray

from dedoc.readers.pdf_reader.data_classes.line_with_location import LineWithLocation
from dedoc.readers.pdf_reader.data_classes.page_with_bboxes import PageWithBBox
from dedoc.readers.pdf_reader.data_classes.pdf_image_attachment import PdfImageAttachment
from dedoc.readers.pdf_reader.data_classes.tables.scantable import ScanTable
from dedoc.readers.pdf_reader.pdf_base_reader import ParametersForParseDoc, PdfBaseReader


class PdfTxtlayerReader(PdfBaseReader):
    """
    This class allows to extract content (text, tables, attachments) from the .pdf documents with a textual layer (copyable documents).
    It uses a pdfminer library for content extraction.

    For more information, look to `pdf_with_text_layer` option description in :ref:`pdf_handling_parameters`.
    """

    def __init__(self, *, config: Optional[dict] = None) -> None:
        from dedoc.extensions import recognized_extensions, recognized_mimes

        super().__init__(config=config, recognized_extensions=recognized_extensions.pdf_like_format, recognized_mimes=recognized_mimes.pdf_like_format)

        from dedoc.readers.pdf_reader.pdf_txtlayer_reader.pdfminer_reader.pdfminer_extractor import PdfminerExtractor
        self.extractor_layer = PdfminerExtractor(config=self.config)

    def can_read(self, file_path: Optional[str] = None, mime: Optional[str] = None, extension: Optional[str] = None, parameters: Optional[dict] = None) -> bool:
        """
        Check if the document extension is suitable for this reader (PDF format is supported only).
        This method returns `True` only when the key `pdf_with_text_layer` with value `true` is set in the dictionary `parameters`.

        You can look to :ref:`pdf_handling_parameters` to get more information about `parameters` dictionary possible arguments.

        Look to the documentation of :meth:`~dedoc.readers.BaseReader.can_read` to get information about the method's parameters.
        """
        from dedoc.utils.parameter_utils import get_param_pdf_with_txt_layer
        return super().can_read(file_path=file_path, mime=mime, extension=extension) and get_param_pdf_with_txt_layer(parameters) == "true"

    def _process_one_page(self,
                          image: ndarray,
                          parameters: ParametersForParseDoc,
                          page_number: int,
                          path: str) -> Tuple[List[LineWithLocation], List[ScanTable], List[PdfImageAttachment], List[float]]:
        if parameters.need_pdf_table_analysis:
            gray_image = self._convert_to_gray(image)
            cleaned_image, tables = self.table_recognizer.recognize_tables_from_image(
                image=gray_image,
                page_number=page_number,
                language=parameters.language,
                orient_analysis_cells=parameters.orient_analysis_cells,
                orient_cell_angle=parameters.orient_cell_angle,
                table_type=parameters.table_type
            )
        else:
            tables = []

        page = self.extractor_layer.extract_text_layer(path=path, page_number=page_number, parameters=parameters)
        if page is None:
            return [], [], [], []
        if parameters.need_gost_frame_analysis:
            page_shift = self.gost_frame_boxes[page_number]
            self._move_table_cells(tables=tables, page_shift=page_shift, page=page)
            readable_block = page_shift  # bbox representing the content of the gost frame
            page.bboxes = [bbox for bbox in page.bboxes if self._inside_any_unreadable_block(bbox.bbox, [readable_block])]  # exclude boxes outside the frame
        unreadable_blocks = [location.bbox for table in tables for location in table.locations]
        page.bboxes = [bbox for bbox in page.bboxes if not self._inside_any_unreadable_block(bbox.bbox, unreadable_blocks)]
        lines = self.metadata_extractor.extract_metadata_and_set_annotations(page_with_lines=page, call_classifier=False)
        self.__change_table_boxes_page_width_heigth(pdf_width=page.pdf_page_width, pdf_height=page.pdf_page_height, tables=tables)

        return lines, tables, page.attachments, []

    def _move_table_cells(self, tables: List[ScanTable], page_shift: BBox, page: PageWithBBox) -> None:
        """
        Move tables back to original coordinates when parsing a document containing a gost frame
        """
        for table in tables:
            shift_x, shift_y = page_shift.x_top_left, page_shift.y_top_left  # shift tables to original coordinates
            for location in table.locations:
                location.bbox.shift(shift_x=shift_x, shift_y=shift_y)
            for row in table.matrix_cells:
                for cell in row:
                    image_width, image_height = page.pdf_page_width, page.pdf_page_height
                    cell.shift(shift_x=shift_x, shift_y=shift_y, image_width=image_width, image_height=image_height)

    def __change_table_boxes_page_width_heigth(self, pdf_width: int, pdf_height: int, tables: List[ScanTable]) -> None:
        """
        Change table boxes' width height into pdf space like textual lines
        """

        for table in tables:
            for row in table.matrix_cells:

                for cell in row:
                    cell.change_lines_boxes_page_width_height(new_page_width=pdf_width, new_page_height=pdf_height)

    def _inside_any_unreadable_block(self, obj_bbox: BBox, unreadable_blocks: List[BBox]) -> bool:
        """
        Check obj_bbox inside some unreadable blocks or not
        :param obj_bbox: ["x_top_left", "y_top_left", "width", "height"]
        :param unreadable_blocks: List["x_top_left", "y_top_left", "width", "height"]
        :return: Boolean
        """
        for block in unreadable_blocks:
            if block.have_intersection_with_box(obj_bbox):
                return True
        return False
