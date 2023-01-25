# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

"""File containing function for score."""

import os
import json
import argparse

import numpy as np

from flask import request

from azureml.train.finetune.core.constants.constants import SaveFileConstants
from azureml.train.finetune.core.drivers.deployment import Deployment
from azureml.train.finetune.core.utils.logging_utils import get_logger_app
from azureml.train.finetune.core.utils.decorators import swallow_all_exceptions
from azureml.train.finetune.core.utils.error_handling.exceptions import ResourceException
from azureml.train.finetune.core.utils.error_handling.error_definitions import DeploymentFailed
from azureml._common._error_definition.azureml_error import AzureMLError  # type: ignore

logger = get_logger_app()

DEPLOY_OBJ = None
REQUEST_FILES_PATH = None
REQUEST_FILES_DIR = "request_files"


class _JSONEncoder(json.JSONEncoder):
    """custom `JSONEncoder` to make sure float and int64 ar converted."""

    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return super(_JSONEncoder, self).default(obj)


def encode_json(content):
    """Encode json with custom `JSONEncoder`."""
    return json.dumps(
        content,
        ensure_ascii=False,
        allow_nan=False,
        indent=None,
        cls=_JSONEncoder,
        separators=(",", ":"),
    )


def decode_json(content):
    """Decode the json content."""
    return json.loads(content)


def prepare_request_files_dir():
    """Create directory to store files sent via requests."""
    cwd = os.getcwd()
    global REQUEST_FILES_PATH
    REQUEST_FILES_PATH = os.path.join(cwd, REQUEST_FILES_DIR)
    os.makedirs(REQUEST_FILES_PATH, exist_ok=True)
    logger.info(f"Request files will be saved at {REQUEST_FILES_PATH}")


def post_process_files_dir():
    """Clear files stored by requests."""
    for path, _, files in os.walk(REQUEST_FILES_PATH):
        for name in files:
            file_name = (os.path.join(path, name))
            os.remove(file_name)
            logger.debug(f"removed {file_name}")


def preprocess_request(raw_data):
    """Preprocess request data."""
    inputs = []
    if request.content_type == "application/json":
        logger.debug("Processing json data")
        data = decode_json(raw_data)
        # pop inputs for pipeline
        inputs = data.pop("inputs", data)
    else:
        logger.info("Processing request files")
        for file in request.files:
            file_name = request.files[file].filename
            save_name = os.path.join(REQUEST_FILES_PATH, file_name)
            request.files[file].save(save_name)
            logger.debug(f"created {save_name}")
            inputs.append({"file": save_name})
    return inputs


@swallow_all_exceptions(logger)
def init():
    """
    Call when the container is initialized/started, typically after create/update of the deployment.

    You can write the logic here to perform init operations like caching the model in memory
    """
    global DEPLOY_OBJ

    env_var = json.loads(os.environ[SaveFileConstants.DeploymentSaveKey])
    env_var["model_path"] = os.environ.get("AZUREML_MODEL_DIR", None)

    try:
        model_path = env_var["model_path"]
        parent_dir_name = env_var["parent_dir_name"]
        model_parent_dir_name = os.path.basename(model_path)
        if model_parent_dir_name != parent_dir_name:
            model_path = os.path.join(model_path, parent_dir_name)
        env_var["model_path"] = model_path
        logger.info(f"Model path - {model_path}")
        # model directory contents
        for dirpath, _, filenames in os.walk(model_path):
            for filename in filenames:
                logger.info(os.path.join(dirpath, filename))
        args = argparse.Namespace(**env_var)
        logger.info(args)
        prepare_request_files_dir()
        DEPLOY_OBJ = Deployment(args)
        # initialize tokenizer and model for prediction
        DEPLOY_OBJ.prepare_prediction_service()
    except Exception as e:
        raise ResourceException._with_error(
            AzureMLError.create(DeploymentFailed, error=e)
        )


@swallow_all_exceptions(logger)
def run(raw_data):
    """
    Call for every invocation of the endpoint to perform the actual scoring/prediction.

    `raw_data` is the raw request body data.
    """
    try:
        inputs = preprocess_request(raw_data)
        logger.debug(inputs)
        predictions = DEPLOY_OBJ.predict(inputs)
    except Exception as e:
        # we should never terminate score script by raising exception in run()
        # as it need to continously serve online requests
        # traceback.print_exc()
        predictions = {"msg": "failed", "error": str(e)}
        logger.error("Exception: \n", exc_info=True)
    post_process_files_dir()
    return encode_json(predictions)
