import os
import shutil
from tempfile import TemporaryDirectory
from unittest import TestCase

from dedoc.converters.concrete_converters.abstract_converter import AbstractConverter


class AbstractConverterTest(TestCase):
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))

    def setUp(self) -> None:
        super().setUp()
        self.tmp_dir = TemporaryDirectory()

    def tearDown(self) -> None:
        super().tearDown()
        self.tmp_dir.cleanup()

    def _convert(self, filename: str, extension: str, converter: AbstractConverter):
        filename_with_extension = filename + extension
        file = os.path.join(self.path, filename_with_extension)
        tmp_file = os.path.join(self.tmp_dir.name, filename_with_extension)
        shutil.copy(file, tmp_file)
        result = converter.do_convert(tmp_dir=self.tmp_dir.name, filename=filename, extension=extension)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp_dir.name, result)))