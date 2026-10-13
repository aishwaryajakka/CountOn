"""Credential-only AWS preflight. Never invokes Bedrock or prints identities/secrets."""

import argparse
import logging
import re
import sys
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.core.config import Settings, get_settings
from db.scripts.bedrock_smoke import AWS_ERROR_CODES

PROVIDERS = {"env", "shared-credentials-file", "config-file", "assume-role", "assume-role-with-web-identity", "sso", "login", "custom-process", "container-role", "iam-role", "boto-config"}
ERRORS = {"LoginRefreshRequired", "LoginTokenLoadError", "SSOTokenLoadError", "UnauthorizedSSOTokenError", "CredentialRetrievalError", "NoCredentialsError", "PartialCredentialsError", "ProfileNotFound", "RefreshWithMFAUnsupportedError", "EndpointConnectionError", "ConnectTimeoutError", "ReadTimeoutError"}


def run(settings: Settings, *, verify_identity: bool = False, session=None) -> int:
    client = None
    profile = "default"
    provider = "unresolved"
    try:
        session = session or boto3.Session(region_name=settings.aws_region)
        selected = session.profile_name
        profile = selected if isinstance(selected, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", selected) else "<configured-profile>"
        credentials = session.get_credentials()
        if credentials is None:
            print("FAIL AWS credentials unavailable; configure a supported runtime provider")
            return 1
        provider = credentials.method if credentials.method in PROVIDERS else "other"
        credentials.get_frozen_credentials()  # triggers expiry/refresh validation, never printed
        print(f"PASS AWS credentials resolved; provider={provider}")
        if verify_identity:
            client = session.client("sts", region_name=settings.aws_region, config=Config(connect_timeout=5, read_timeout=5, retries={"total_max_attempts": 1}))
            client.get_caller_identity()  # discard account/user/ARN; only report success
            print("PASS AWS identity accepted by STS; identity values suppressed")
        else:
            print("AWS remote identity/IAM/model access: NOT VERIFIED (use --verify-identity, then Bedrock smoke)")
        return 0
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code")
        print(f"FAIL AWS identity; AWS error code: {code if isinstance(code, str) and code in AWS_ERROR_CODES else 'UNKNOWN_AWS_ERROR'}")
        return 1
    except Exception as error:  # noqa: BLE001 -- process/SDK messages may include credentials
        name = type(error).__name__
        print(f"FAIL AWS credentials; SDK error: {name if name in ERRORS else 'AWS_PROVIDER_FAILURE'}")
        if name.startswith("Login") or provider == "login":
            print(f"Local interactive refresh: aws login --profile {profile}")
        elif provider == "sso" or name in {"SSOTokenLoadError", "UnauthorizedSSOTokenError"}:
            print(f"Local interactive refresh: aws sso login --profile {profile}")
        elif name == "CredentialRetrievalError":
            print("Check the configured credential_process and refresh its source login; do not print process output")
        print("Bedrock invocation: NOT RUN; no model permission conclusion")
        return 1
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001, S110 -- cleanup must not leak provider errors
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-identity", action="store_true", help="Also make a read-only STS GetCallerIdentity request")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        settings = get_settings()
    except Exception:  # noqa: BLE001 -- Settings errors include rejected values
        print("FAIL backend configuration; private details suppressed")
        return 1
    return run(settings, verify_identity=args.verify_identity)


if __name__ == "__main__":
    raise SystemExit(main())
