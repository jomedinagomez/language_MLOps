# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

"""File defining function for deploy component."""

import os
import json
import argparse
import datetime
from azure.ai.ml import MLClient
from azure.core.exceptions import HttpResponseError
from azureml.core import Workspace, Run
from azureml.core.model import Model as Model_v1
from azure.ai.ml.entities import (
    Model as Model_v2,
    Environment as Environment_v2,
    CodeConfiguration,
    ManagedOnlineEndpoint,
    ManagedOnlineDeployment,
    OnlineRequestSettings,
    BuildContext,
)
from azure.identity import ManagedIdentityCredential
from azureml.train.finetune.core.constants import task_definitions
from azureml.train.finetune.core.constants.constants import SaveFileConstants
from azureml.train.finetune.core.utils.logging_utils import get_logger_app
from azureml.train.finetune.core.utils.decorators import swallow_all_exceptions
from azureml.train.finetune.core.utils.error_handling.exceptions import (
    ValidationException,
    ArgumentException,
    ResourceException,
)
from azureml.train.finetune.core.utils.error_handling.error_definitions import (
    TaskNotSupported,
    EmptyLabelSeparator,
    InvalidCheckpointDirectory,
    MLClientNotCreated,
    DeploymentFailed,
    LLMInternalError,
)
from azureml._common._error_definition.azureml_error import AzureMLError  # type: ignore

logger = get_logger_app()


def get_task_parser(task_metadata):
    """Parse all arguments."""
    parser = argparse.ArgumentParser(task_metadata.hf_task_name, allow_abbrev=False)
    for item in task_metadata.arg_parse_data:
        arg_name = item["dest"]
        # NOTE force converting the target_key required status to False
        # This is done only for inference as for inference the target_key might
        # might not exist
        if arg_name == task_metadata.dataset_target_key:
            item["required"] = False
        key = f"--{arg_name}"
        parser.add_argument(key, **item)

    return parser


@swallow_all_exceptions(logger)
def get_environment_variables():
    """Get the environment variables."""
    common_parser = argparse.ArgumentParser(description="Inference sub component", allow_abbrev=False)
    # inputs to Deployment script
    # NOTE The input arguments slightly varies compared to inference as the `test_file_name`
    # does not exist in deployment
    # Batch inference is supported
    common_parser.add_argument(
        "--apply_ort",
        type=str,
        default="false",
        help="If set to true, will use the ONNXRunTime training",
    )
    common_parser.add_argument(
        "--apply_deepspeed",
        type=str,
        default="false",
        help="If set to true, will enable deepspeed for training",
    )
    common_parser.add_argument(
        "--deepspeed_config",
        type=str,
        default="./ds_config_zero3.json",
        help="Deepspeed config to use if apply_deepspeed is set to true",
    )
    common_parser.add_argument(
        "--precision",
        type=int,
        default=32,
        help=(
            "Apply mixed precision training. "
            "This can reduce memory footprint by performing operations in half-precision."
        ),
    )
    common_parser.add_argument(
        "--local_rank",
        type=int,
        default=0,
        help="Local rank passed by torch distributed launch",
    )
    common_parser.add_argument("--batch_size", default=4, type=int, help="Test batch size")
    common_parser.add_argument(
        "--output_dir",
        default="output",
        type=str,
        help="Output dir to save the finetune model and other metadata",
    )
    common_args, _ = common_parser.parse_known_args()

    # combine common args and task related args
    args = argparse.Namespace(**vars(common_args))

    # Check if the label_separator is not empty
    # This is applicable only for MultiLabelClassification
    # Convert the boolean variables from string to bool
    if isinstance(args.apply_ort, str):
        args.apply_ort = args.apply_ort.lower() == "true"

    # convert str to bool
    if isinstance(args.apply_deepspeed, str):
        args.apply_deepspeed = args.apply_deepspeed.lower() == "true"

    if args.apply_deepspeed and args.deepspeed_config is None:
        args.deepspeed_config = "./ds_config_zero3.json"

    args.use_fp16 = (args.precision == 16)

    # update the task info
    decode_dataset_columns = []
    decode_datast_columns_dtypes = []
    # if_target_key_exist flag decides whether or not to do the label key formatting
    # if True ==> data format happens => metrics will be computed on model predictions
    # if False ==> ONLY model prediction happens

    return {SaveFileConstants.DeploymentSaveKey: json.dumps(vars(args))}


# TODO Need to upgrade v1 to v2 when available
@swallow_all_exceptions(logger)
def main():
    """Run main function."""
    # parse arguments
    parser = argparse.ArgumentParser(description="Deploy component", allow_abbrev=False)
    parser.add_argument(
        "--local_mode",
        type=str,
        default="false",
        help="script run mode",
    )
    parser.add_argument(
        "--local_deployment",
        type=str,
        default="false",
        help="script run mode",
    )
    # inputs to Register model
    parser.add_argument(
        "--name_for_registered_model",
        type=str,
        default="inferencemodel",
        help="The name you want to give to the registered model",
    )

    # inputs for registry
    parser.add_argument("--registry_name", type=str, default=None, help="The name of the registry")

    # environment name which is to be used for endpoint deployment
    parser.add_argument(
        "--deployment_env_name",
        type=str,
        default=None,
        help="The name of the environment to be deployed at online endpoint",
    )

    # inputs to Deploy model
    parser.add_argument(
        "--endpoint_name",
        type=str,
        default="inference-end-point",
        help="The name of the endpoint to deploy the model to",
    )
    parser.add_argument(
        "--deployment_name",
        type=str,
        default="blue",
        help="The name of the endpoint to deploy the model to",
    )
    parser.add_argument(
        "--instance_type",
        type=str,
        default="Standard_F8s_v2",
        help="The instance type to use for the deployment",
    )
    parser.add_argument(
        "--instance_count",
        type=int,
        default=1,
        help="Number of vms for the deployment",
    )

    # Online Request Settings
    parser.add_argument(
        "--max_concurrent_requests_per_instance",
        type=int,
        default=1,
        help="Maximum concurrent requests to be handled per instance",
    )
    parser.add_argument(
        "--request_timeout_ms",
        type=int,
        default=5000,
        help="Request timeout in ms. Max limit is 90000.",
    )
    parser.add_argument(
        "--max_queue_wait_ms",
        type=int,
        default=500,
        help="Maximum queue wait time of a request in ms"
    )

    args, _ = parser.parse_known_args()

    # parse inference arguments to set as environment variables
    env_var = get_environment_variables()

    # fetch workspace
    if isinstance(args.local_mode, str):
        args.local_mode = args.local_mode.lower() == "true"
    logger.info(f"local run - {args.local_mode}")
    run = None
    if args.local_mode:
        ws = Workspace.from_config()
    else:
        run = Run.get_context(allow_offline=False)
        ws = run.experiment.workspace
    # v1: workspace object
    ws.write_config()
    logger.info("Workspace loaded")

    if isinstance(args.local_deployment, str):
        args.local_deployment = args.local_mode and args.local_deployment.lower() == "true"
    logger.info(f"local deployment - {args.local_deployment}")

    # fields
    DATETIME_SUFFIX = datetime.datetime.now().strftime("%m%d%H%M%f")
    # AZUREML_ENVIRONMENT_NAME = "azure-ml-environment"
    DEPLOYMENT_NAME = args.deployment_name
    # DEPLOYMENT_ENV_NAME = "gllm-openmpi410-cuda111-cudnn8-ubuntu1804"
    # DOCKERFILE_FILEPATH = "Dockerfile"
    if args.registry_name is None:
        args.registry_name = os.environ.get("GLLM_REGISTRY_NAME", None)
    if args.deployment_env_name is None:
        args.deployment_env_name = os.environ.get("GLLM_DEPLOYMENT_ENV_NAME", None)

    logger.info(f"Deployment args - {args}")

    # v2: ml client: resource manager
    try:
        if args.local_mode:
            # TODO: add registry for ml client
            logger.info("Using default credential")
            from azure.identity import DefaultAzureCredential

            ml_client = MLClient(
                DefaultAzureCredential(),
                ws._subscription_id,
                ws._resource_group,
                ws._workspace_name,
                registry_name=args.registry_name,
            )
        else:
            client_id = os.environ.get("DEFAULT_IDENTITY_CLIENT_ID")
            logger.info(f"Using client id: {client_id}")
            ml_client = MLClient.from_config(
                ManagedIdentityCredential(client_id=client_id),
                registry_name=args.registry_name,
            )
    except HttpResponseError as e:
        # registry access exception
        raise ResourceException._with_error(
            AzureMLError.create(LLMInternalError, error=e)
        )
    except Exception:
        raise ResourceException._with_error(
            AzureMLError.create(MLClientNotCreated)
        )
    logger.info("Created ML Client")

    if args.local_mode:
        if not args.local_deployment:
            # maintaining v1 as v2 is not working in local
            # v1: register model to workspace
            model = Model_v1.register(
                model_path=args.model_checkpoint_dir,
                model_name=args.name_for_registered_model,
                description=run.description if run else None,
                workspace=ws,
            )
            model_name, model_version = model.name, model.version
            logger.info(f"Registered model info v1: {model_name}:{model_version}")

            # load model using MLClient
            model_v2 = ml_client.models.get(name=model_name, version=model_version)
            logger.info("Loaded ML client model")
        else:
            model_v2 = Model_v2(
                name=args.name_for_registered_model,
                path=args.model_checkpoint_dir,
            )
            model_name, model_version = args.name_for_registered_model, "1"
            logger.info("Local ML client model")
    else:
        # v2: register model to workspace
        models_list = ml_client.models.list(name=args.name_for_registered_model)
        try:
            models_list = [m for m in models_list]
        except Exception:
            models_list = []
        model_versions_list = [0]
        for model in models_list:
            try:
                model_versions_list.append(int(model.version))
            except Exception:
                pass
        model_version = str(max(model_versions_list))
        #model_version = 1
        #model = Model_v2(
        #    name=args.name_for_registered_model,
        #    version=model_version,
        #    path=args.model_checkpoint_dir,
        #    description=run.description if run else None,
        #    type="custom_model",
        #)
        #ml_client.models.create_or_update(model)
        model = ml_client.models.get(name=args.name_for_registered_model)
        model_name, model_version = model.name, model.version
        logger.info(f"Registered model info v2: {model_name}:{model_version}")

        # load model using MLClient
        model_v2 = ml_client.models.get(name=model_name, version=model_version)
        logger.info(f"Loaded ML client model : {model_v2.name}:{model_v2.version}")

    # get/create the endpoint
    endpoint_name = args.endpoint_name
    try:
        endpoint = ml_client.online_endpoints.get(endpoint_name, local=args.local_deployment)
    except Exception:
        logger.info(f"Creating endpoint {endpoint_name}")
        endpoint = ManagedOnlineEndpoint(
            name=endpoint_name,
            description=f"endpoint created on {DATETIME_SUFFIX}",
            auth_mode="key",
            tags={"model": model_name, "version": model_version},
        )
        ml_client.begin_create_or_update(endpoint, local=args.local_deployment)
    logger.info(f"Using endpoint {endpoint_name}")

    # deployment to the endpoint
    deployment = ManagedOnlineDeployment(
        name=DEPLOYMENT_NAME,
        endpoint_name=endpoint_name,
        model=model_v2,
        #environment=env_name,
        code_configuration=CodeConfiguration(code=".", scoring_script="score.py"),
        environment_variables=env_var,
        instance_type=args.instance_type,
        instance_count=args.instance_count,
        # TODO add Scale settings to args
        request_settings=OnlineRequestSettings(
            max_concurrent_requests_per_instance=args.max_concurrent_requests_per_instance,
            request_timeout_ms=args.request_timeout_ms,
            max_queue_wait_ms=args.max_queue_wait_ms,
        ),
    )

    try:
        ml_client.online_deployments.begin_create_or_update(deployment, local=args.local_deployment)
    except Exception as e:
        try:
            # logger.info(e)
            logger.info("fetching logs")
            logger.info(
                ml_client.online_deployments.get_logs(name=DEPLOYMENT_NAME, endpoint_name=endpoint_name, lines=100000)
            )
        except Exception as e2:
            logger.info(f"No logs found for current deployment. Error - {e2}")
        raise ResourceException._with_error(
            AzureMLError.create(DeploymentFailed, error=e)
        )
    logger.info("Deployment object created")

    # set this deployment as the default for the endpoint (100% traffic)
    endpoint.traffic = {DEPLOYMENT_NAME: 100}
    ml_client.begin_create_or_update(endpoint)
    logger.info("Deployment done")
    logger.info(f"{datetime.datetime.now().isoformat()} Scoring URI is : {endpoint.scoring_uri}")

if __name__ == "__main__":
    main()
