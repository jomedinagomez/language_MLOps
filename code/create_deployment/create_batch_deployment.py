# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import argparse

from azure.ai.ml.entities import BatchEndpoint, BatchDeployment
from azure.ai.ml.constants import BatchDeploymentOutputAction
from azure.identity import ManagedIdentityCredential

from azure.identity import DefaultAzureCredential
from azure.ai.ml.entities import ManagedOnlineEndpoint
from azure.ai.ml import MLClient
from azureml.core import Workspace, Run
import os

import json

def parse_args():
    parser = argparse.ArgumentParser(description="Create batch deployment")
    parser.add_argument("--deployment_name", type=str, help="Name of batch deployment")
    parser.add_argument("--endpoint_name", type=str, help="Name of the online endpoint")
    parser.add_argument("--model_path", type=str, help="Path to model or AML model")
    parser.add_argument("--compute", type=str, help="Name of the compute cluster")
    parser.add_argument("--instance_count", type=int, help="Number of instances to provision for job", default=2)
    parser.add_argument("--max_concurrency_per_instance", type=int, help="Maximum number of cuncurrent jobs per instance", default=4)
    parser.add_argument("--mini_batch_size", type=int, help="The number of examples to score per job", default=32)
    parser.add_argument("--output_file_name", type=str, help="Output file name", default="predictions.csv")

    return parser.parse_args()

def generate_workspace():

    run = Run.get_context(allow_offline=False)
    ws = run.experiment.workspace
    # v1: workspace object
    ws.write_config()
    print("Workspace file generated")

    return ws

def main():
    args = parse_args()
    print(args)

    ws = generate_workspace()
    
    credential = DefaultAzureCredential()
    try:
        client_id = os.environ.get("DEFAULT_IDENTITY_CLIENT_ID")
        ml_client = MLClient.from_config(
            ManagedIdentityCredential(client_id=client_id),
                )

        print("ML client loaded")

    except Exception as ex:
        print("Could not use Managed Identity to log into Azure")
        print(ex)

    #### https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-batch-endpoint?tabs=python

    print("Creating Batch Endpoint")
    try:
        endpoint = ml_client.batch_endpoints.get(args.endpoint_name)
        print("Batch endpoint already exists")
    # create batch endpoint
    except:
        print("Creating Endpoint")
        batch_endpoint = BatchEndpoint(
            name=args.endpoint_name 
        )
        
        endpoint_job = ml_client.batch_endpoints.begin_create_or_update(batch_endpoint)
        endpoint_job.wait()

    print("Finished Batch endpoint creation -")
    print("Creating Batch deployment")
    batch_deployment = BatchDeployment(
        name=args.deployment_name,
        endpoint_name=args.endpoint_name,
        model=args.model_path ,
        compute=args.compute,
        instance_count=args.instance_count,
        max_concurrency_per_instance=args.max_concurrency_per_instance,
        mini_batch_size=args.mini_batch_size,
        output_action=BatchDeploymentOutputAction.APPEND_ROW,
        output_file_name=args.output_file_name
    )

    deployment_job = ml_client.batch_deployments.begin_create_or_update(
        batch_deployment
    )
    deployment_job.wait()

    batch_endpoint = ml_client.batch_endpoints.get(args.endpoint_name)
    batch_endpoint.defaults.deployment_name = batch_deployment.name

    endpoint_update_job = ml_client.batch_endpoints.begin_create_or_update(
        batch_endpoint
    )
    endpoint_update_job.wait()
    print("finished")

if __name__ == "__main__":
    main()
