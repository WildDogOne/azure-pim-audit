"""Shared CLI plumbing for the four sync/audit entrypoints.

Keeps the argparse setup, client construction and timing identical across the
scripts without changing how each one is invoked - Kestra flows still call the
individual files. Credentials are built on demand (in main()), not at import
time, so `--help` / `-t` never require live secrets to be present.
"""

import argparse
import time
from contextlib import contextmanager

from kestra import Kestra
from atlassian import Confluence
from azure.identity import ClientSecretCredential

from creds import (
    azure_tenant_id,
    azure_client_id,
    azure_client_secret,
    confluence_url,
    confluence_token,
)
from functions.msgraphapi import GraphAPI

logger = Kestra.logger()


def build_parser(prog, description):
    """Common argument parser: just the shared -t/--test dry-run flag."""
    parser = argparse.ArgumentParser(prog=prog, description=description)
    parser.add_argument(
        "-t",
        "--test",
        help="Dry-run the script without writing to Confluence",
        action="store_true",
    )
    return parser


@contextmanager
def timer(name):
    """Record elapsed time for a block as a Kestra timer metric."""
    start = time.perf_counter()
    try:
        yield
    finally:
        Kestra.timer(name, time.perf_counter() - start)


def build_graph_client():
    return GraphAPI(
        azure_tenant_id=azure_tenant_id,
        azure_client_id=azure_client_id,
        azure_client_secret=azure_client_secret,
    )


def build_confluence():
    return Confluence(url=confluence_url, token=confluence_token)


def build_azure_credential():
    return ClientSecretCredential(
        azure_tenant_id, azure_client_id, azure_client_secret
    )
