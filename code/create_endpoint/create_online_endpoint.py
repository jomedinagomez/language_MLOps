# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import argparse

from azure.ai.ml.entities import ManagedOnlineEndpoint
import os

from azure.identity import ManagedIdentityCredential
from azureml.core import Workspace, Run

from azure.identity import DefaultAzureCredential
from azure.ai.ml import MLClient

import json

def parse_args():
    parser = argparse.ArgumentParser(description="Create online endpoint")
    parser.add_argument("--endpoint_name", type=str, help="Name of online endpoint")
    parser.add_argument("--auth_mode", type=str, help="endpoint authentication mode", default="aml_token")
    return parser.parse_args()

def generate_workspace():

    run = Run.get_context(allow_offline=False)
    ws = run.experiment.workspace
    # v1: workspace object
    ws.write_config()
    print("Workspace file generated")

    return ws

def main():
    print("Initializing Batch endpoint creation")
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
    
    try:
        endpoint = ml_client.online_endpoints.get(args.endpoint_name)
        print("Batch endpoint already exists")
    # create batch endpoint

    except:
        online_endpoint = ManagedOnlineEndpoint(
            name=args.endpoint_name, 
            auth_mode=args.auth_mode,
        )
        
        endpoint_job = ml_client.online_endpoints.begin_create_or_update(online_endpoint)
        endpoint_job.wait()

if __name__ == "__main__":
    main()
