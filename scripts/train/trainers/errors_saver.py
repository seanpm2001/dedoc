import json
import logging
import os
import tempfile
import zipfile
from collections import Counter, defaultdict
from typing import List, Tuple

import pandas as pd
from tqdm import tqdm

from train_dataset.data_structures.images_archive import ImagesArchive
from train_dataset.taskers.images_creators.concrete_creators.abstract_images_creator import AbstractImagesCreator
from train_dataset.taskers.images_creators.concrete_creators.docx_images_creator import DocxImagesCreator
from train_dataset.taskers.images_creators.concrete_creators.scanned_images_creator import ScannedImagesCreator
from train_dataset.taskers.images_creators.concrete_creators.txt_images_creator import TxtImagesCreator


class ErrorsSaver:
    """
    Class for saving line classifier's errors during training.
    Errors are saved in the directory with a path `errors_path` as a list of TXT files.
    Each TXT file contains information about lines with similar errors (same substitution true_type -> predicted_type).

    In addition, images can be saved for misclassified lines visualization (misclassified lines are highlighted by a bounding box).
    """

    def __init__(self, errors_path: str, dataset_path: str, logger: logging.Logger, *, config: dict) -> None:
        """
        :param errors_path: path to the directory where txt files with errors will be saved (and archive with images if needed)
        :param dataset_path: path to the ZIP file with a training dataset downloaded by :class:`~scripts.train.trainers.data_loader.DataLoader`
        :param logger: logger for logging details of errors saving
        :param config: any custom configuration
        """
        self.logger = logger
        self.config = config
        self.errors_path = errors_path
        self.dataset_path = dataset_path
        dataset_dir = os.path.dirname(dataset_path)

        # archive with images of all lines
        self.images_archive = os.path.join(dataset_dir, "images.zip")

        # file with the list of processed document names
        self.errors_documents_file = os.path.join(dataset_dir, "errors_documents.json")

        # archive with images of misclassified lines
        self.errors_images_archive = os.path.join(self.errors_path, "errors_images.zip")

    def save_errors(self, error_cnt: Counter, errors_uids: List[str], csv_path: str, save_errors_images: bool = False) -> None:
        """
        :param error_cnt:  counter of label pairs (y_true, y_pred) where y_true != y_pred
        :param errors_uids: list of lines' uids corresponding misclassified lines
        :param csv_path: path to the csv-file with dataset in form of a feature matrix (:class:`~scripts.train.trainers.dataset.LineClassifierDataset`)
        :param save_errors_images: whether to save images with highlighted misclassified lines, if True images will be saved in "errors_images.zip"
        """
        assert len(set(errors_uids)) == len(errors_uids)
        self.logger.info(f"Save errors in {self.errors_path}")
        errors_total_num = sum(error_cnt.values())
        self.logger.info(f"{'true':16s} -> {'predicted':16s} {'cnt':6s} {'(percent)':16s}")
        for error, cnt in error_cnt.most_common():
            y_true, y_pred = error
            self.logger.info(f"{y_true:16s} -> {y_pred:16s} {cnt:06,} ({100 * cnt / errors_total_num:02.2f}%)")

        if save_errors_images:
            self.__save_images(errors_uids, csv_path)
        for file_name in os.listdir(self.errors_path):
            if not file_name.endswith("txt"):
                continue
            path_file = os.path.join(self.errors_path, file_name)
            with open(path_file) as file:
                lines = file.readlines()
            lines_cnt = Counter(lines)
            lines.sort(key=lambda value: (-lines_cnt[value], value))
            path_out = os.path.join(self.errors_path, f"{int(1000 * len(lines) / errors_total_num):04d}_{file_name}")

            with open(path_out, "w") as file_out:
                for line in lines:
                    file_out.write(line)
                    if save_errors_images:
                        path_out_dir = path_out.rsplit(".", maxsplit=1)[0]
                        os.makedirs(path_out_dir, exist_ok=True)
                        d = json.loads(line)
                        images_dataset = ImagesArchive(self.images_archive)
                        image_name = d["uid"] + ".jpg"
                        image = images_dataset.get_page_by_uid(image_name)
                        if image is not None:
                            image.save(os.path.join(path_out_dir, image_name))
            os.remove(path_file)

    def __save_images(self, errors_uids: List[str], csv_path: str) -> None:
        """
        1 - find image in the images archive, save to errors_images_archive if was found, else do the following:
        2 - find line uid and document name in the dataframe
        3 - find document in the dataset archive
        4 - add images with bboxes to images_archive
        5 - add images with bboxes from errors_uids to errors_images_archive
        """
        csv_dataset_path = os.path.join(csv_path, "dataset.csv")
        if not os.path.isfile(self.dataset_path) or not os.path.isfile(csv_dataset_path):
            return

        with tempfile.TemporaryDirectory() as documents_tmp_dir:
            with zipfile.ZipFile(self.dataset_path, "r") as dataset_archive:
                dataset_archive.extractall(documents_tmp_dir)
            path2docs = os.path.join(documents_tmp_dir, "original_documents")
            images_creators = [
                ScannedImagesCreator(path2docs=path2docs),
                DocxImagesCreator(path2docs=path2docs, config=self.config),
                TxtImagesCreator(path2docs=path2docs, config=self.config)
            ]
            self.__group_data(os.path.join(documents_tmp_dir, "labeled.json"))

            dataset = pd.read_csv(csv_dataset_path)
            filtered_dataset = dataset[dataset.uid.isin(errors_uids)][["group", "uid"]]

            ready_documents, ready_images = self.__prepare_files()

            with zipfile.ZipFile(self.images_archive, "a") as images_archive, zipfile.ZipFile(self.errors_images_archive, "w") as errors_images_archive:
                for uid in tqdm(errors_uids):
                    self.__process_uid(errors_images_archive, filtered_dataset, images_archive, images_creators, ready_documents, ready_images, uid)

    def __process_uid(self,
                      errors_images_archive: zipfile.ZipFile,
                      filtered_dataset: pd.DataFrame,
                      images_archive: zipfile.ZipFile,
                      images_creators: List[AbstractImagesCreator],
                      ready_documents: List[str],
                      ready_images: List[str],
                      uid: str) -> None:
        """
        Add the image to the `errors_images_archive` with the given `uid`
        """
        done_set = set()
        document_name = filtered_dataset[filtered_dataset.uid == uid].head(1).group.item()
        img_name = f"{uid}.jpg"
        if img_name in done_set:
            return  # skip done image
        done_set.add(img_name)
        if document_name not in ready_documents and img_name not in ready_images:
            document_lines = self.data[document_name]
            # process document
            # add do ready_documents and ready_images
            for creator in images_creators:
                if creator.can_read(document_lines):
                    creator.add_images(page=document_lines, archive=images_archive)
                    ready_images = images_archive.namelist()
                    ready_documents.append(document_name)

        # find image and write to errors_images_archive
        if img_name in ready_images:
            with images_archive.open(img_name, "r") as read_image:
                error_image = read_image.read()
            with errors_images_archive.open(img_name, "w") as write_image:
                write_image.write(error_image)
        # save new list of ready documents
        with open(self.errors_documents_file, "w") as json_file:
            json.dump(ready_documents, json_file)

    def __prepare_files(self) -> Tuple[List[str], List[str]]:
        """
        Initialize the list of documents whose pages was processed, and the list of page images with line bboxes
        """
        if not os.path.isfile(self.errors_documents_file):
            with open(self.errors_documents_file, "w") as json_file:
                json.dump([], json_file)

        if not os.path.isfile(self.images_archive):
            with zipfile.ZipFile(self.images_archive, "w"):
                ready_images = []
                ready_documents = []
        else:
            with zipfile.ZipFile(self.images_archive, "r") as images_archive:
                ready_images = images_archive.namelist()
            with open(self.errors_documents_file, "r") as json_file:
                ready_documents = json.load(json_file)

        return ready_documents, ready_images

    def __group_data(self, data_path: str) -> None:
        """
        Group lines dicts into document groups
        """
        with open(data_path, "r") as f:
            data = json.load(f)
        result_dict = defaultdict(list)
        for line_dict in data.values():
            line_data = line_dict["data"]
            group = line_data["original_document"]
            result_dict[group].append(line_data)
        self.data = result_dict
