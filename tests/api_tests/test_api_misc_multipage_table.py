import os
from typing import List

from tests.api_tests.abstract_api_test import AbstractTestApiDocReader


class TestMultipageTable(AbstractTestApiDocReader):

    def _get_abs_path(self, file_name: str) -> str:
        return os.path.join(self.data_directory_path, "tables", file_name)

    def _get_tables(self, file_name: str) -> List[dict]:
        result = self._send_request(file_name, {"pdf_with_text_layer": "false"})
        content = result["content"]
        self._test_table_refs(content=content)
        tables = content["tables"]
        tree = content["structure"]
        self._check_tree_sanity(tree=tree)
        return tables

    def test_api_ml_table_recognition_0(self) -> None:
        file_name = "example_with_table0.pdf"
        tables = self._get_tables(file_name)
        self.assertEqual(len(tables), 1)

    def test_api_ml_table_recognition_3(self) -> None:
        file_name = "example_with_table9.pdf"
        tables = self._get_tables(file_name)
        self.assertEqual(len(tables), 1)

    def test_api_ml_table_recognition_7(self) -> None:
        file_name = "example_table_with_90_orient_cells.pdf"
        tables = self._get_tables(file_name)
        self.assertEqual(len(tables), 1)

    def test_api_ml_table_recognition_8(self) -> None:
        file_name = "example_with_table8.pdf"
        tables = self._get_tables(file_name)
        self.assertEqual(len(tables), 1)

    def test_api_ml_table_recognition_synthetic_data_1(self) -> None:
        file_name = "example_mp_table_wo_repeate_header.pdf"
        tables = self._get_tables(file_name)
        self.assertEqual(len(tables), 1)

    def test_api_ml_table_recognition_synthetic_data_3(self) -> None:
        file_name = "example_mp_table_with_repeate_header_2.pdf"
        tables = self._get_tables(file_name)
        self.assertEqual(len(tables), 1)
        table = tables[0]["cells"]

        self.assertListEqual(
            ["Заголовок\nБольшой", "Еще один большой заголовок", "Еще один большой заголовок", "Еще один большой заголовок", "Еще один большой заголовок"],
            self._get_text_of_row(table[0])
        )
        self.assertListEqual(["Заголовок\nБольшой", "Заголовок поменьше 1", "Заголовок поменьше 1", "Заголовок поменьше 2", "Заголовок поменьше 2"],
                             self._get_text_of_row(table[1]))
        self.assertListEqual(["Заголовок\nБольшой", "Заголовочек 1", "Заголовочек 2", "Заголовочек 3", "Заголовочек 4"], self._get_text_of_row(table[2]))
        self.assertListEqual(["Данные 1", "Данные 1", "Данные 1", "Данные 1", "Данные 1"], self._get_text_of_row(table[3]))
        self.assertListEqual(["Данные 2", "Данные 2", "Данные 2", "Данные 2", "Данные 2"], self._get_text_of_row(table[4]))
        self.assertListEqual(["Данные 3", "Данные 3", "Данные 3", "Данные 3", "Данные 3"], self._get_text_of_row(table[5]))
        self.assertListEqual(["Данные 4", "Данные 4", "Данные 4", "Данные 4", "Данные 4"], self._get_text_of_row(table[6]))
        self.assertListEqual(["Данные 5", "Данные 5", "Данные 5", "Данные 5", "Данные 5"], self._get_text_of_row(table[7]))
        self.assertListEqual(["Заголовок\nБольшой", "Заголовок поменьше 1", "Заголовок поменьше 1", "Заголовок поменьше 2", "Заголовок поменьше 2"],
                             self._get_text_of_row(table[8]))
        self.assertListEqual(["Заголовок\nБольшой", "Заголовочек 1", "Заголовочек 2", "Заголовочек 3", "Заголовочек 4"], self._get_text_of_row(table[9]))
        self.assertListEqual(["Данные 6", "Данные 6", "Данные 6", "Данные 6", "Данные 6"], self._get_text_of_row(table[10]))
        self.assertListEqual(["Данные 7", "Данные 7", "Данные 7", "Данные 7", "Данные 7"], self._get_text_of_row(table[11]))
