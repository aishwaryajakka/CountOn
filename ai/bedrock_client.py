"""
Amazon Bedrock Client Integration (Person 2 - Day 3)
"""

import os
import json
import re
from typing import Optional, Dict, Any
from mycounton.ai.exceptions import BedrockClientError, InvalidModelResponse


def strip_markdown_code_fences(text: str) -> str:
    """
    Utility function to remove ```json ... ``` code fences or leading/trailing whitespace.
    Handles responses wrapped in markdown code blocks.
    """
    text = text.strip()
    # Match ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


class BedrockClient:
    """
    Isolated Amazon Bedrock client using boto3 Converse API.
    Uses standard AWS credential provider chain.
    """

    def __init__(
        self,
        model_id: Optional[str] = None,
        region_name: Optional[str] = None,
    ):
        self.model_id = (
            model_id
            or os.environ.get("BEDROCK_MODEL_ID")
            or "amazon.nova-2-lite-v1:0"
        )
        self.region_name = (
            region_name
            or os.environ.get("AWS_REGION")
            or "ap-northeast-1"
        )
        self._client = None

    def _get_client(self):
        """Lazy instantiation of boto3 bedrock-runtime client."""
        if self._client is None:
            try:
                import boto3
                self._client = boto3.client(
                    "bedrock-runtime",
                    region_name=self.region_name,
                )
            except Exception as e:
                raise BedrockClientError(
                    f"Failed to initialize AWS Bedrock client in region '{self.region_name}': {str(e)}"
                ) from e
        return self._client

    def invoke(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Sends a request to Amazon Bedrock Converse API and returns parsed JSON.
        Catches boto3 / botocore errors and wraps them in clean domain exceptions.
        """
        client = self._get_client()

        try:
            response = client.converse(
                modelId=self.model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": user_message}],
                    }
                ],
                system=[
                    {"text": system_prompt}
                ],
                inferenceConfig={
                    "temperature": temperature,
                    "maxTokens": 1000,
                },
            )

            # Extract generated response text
            output_content = response.get("output", {}).get("message", {}).get("content", [])
            if not output_content or "text" not in output_content[0]:
                raise InvalidModelResponse("Bedrock response returned empty or missing text content.")

            raw_text = output_content[0]["text"]
            clean_text = strip_markdown_code_fences(raw_text)

            try:
                parsed_json = json.loads(clean_text)
                return parsed_json
            except json.JSONDecodeError as json_err:
                raise InvalidModelResponse(
                    f"Bedrock response is not valid JSON: {str(json_err)}. Response was: '{raw_text[:200]}...'"
                ) from json_err

        except (InvalidModelResponse, BedrockClientError):
            raise
        except Exception as e:
            raise BedrockClientError(f"Bedrock Converse API call failed: {str(e)}") from e
