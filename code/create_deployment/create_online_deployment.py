# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import argparse

from azure.ai.ml.entities import ManagedOnlineEndpoint
from azure.ai.ml.entities import ManagedOnlineDeployment
from azure.identity import ManagedIdentityCredential

from azure.identity import DefaultAzureCredential
from azure.ai.ml import MLClient
from azureml.core import Workspace, Run
import os

import json

def parse_args():
    parser = argparse.ArgumentParser(description="Create online deployment")
    parser.add_argument("--deployment_name", type=str, help="Name of online deployment")
    parser.add_argument("--endpoint_name", type=str, help="Name of the online endpoint")
    parser.add_argument("--model_path", type=str, help="Path to model or AML model")
    parser.add_argument("--instance_type", type=str, help="Instance type", default="Standard_DS2_v2")
    parser.add_argument("--instance_count", type=int, help="Instance count", default=1)
    parser.add_argument("--traffic_allocation", type=str, help="Deployment traffic allocation percentage")

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

    print("Creating batch endpoint")
    try:
        endpoint = ml_client.online_endpoints.get(args.endpoint_name)
        print("Batch endpoint already exists")
    # create batch endpoint

    except:
        print("Creating Endpoint")
        online_endpoint = ManagedOnlineEndpoint(
            name=args.endpoint_name, 
            auth_mode=args.auth_mode,
        )
        
        endpoint_job = ml_client.online_endpoints.begin_create_or_update(online_endpoint)
        endpoint_job.wait()
    
    print("Finished Online endpoint creation -")
    print("Creating online deployment")
    # Create online deployment
    online_deployment = ManagedOnlineDeployment(
        name=args.deployment_name,
        endpoint_name=args.endpoint_name,
        model=args.model_path,
        instance_type=args.instance_type,
        instance_count=args.instance_count,
    )

    deployment_job = ml_client.online_deployments.begin_create_or_update(
        deployment=online_deployment
    )
    deployment_job.wait()

    # allocate traffic
    online_endpoint = ManagedOnlineEndpoint(
        name=args.endpoint_name
    )
    online_endpoint.traffic = {args.deployment_name: args.traffic_allocation}
    endpoint_update_job = ml_client.begin_create_or_update(online_endpoint)
    endpoint_update_job.wait()

if __name__ == "__main__":
    main()
