"""
Amazon Order Inferred Connector.

IMPORTANT ARCHITECTURAL DESIGN:
AWS itself does not provide a general personal Amazon consumer shopping-orders API,
and Amazon.com consumer shopping accounts do not have an open OAuth API like Google or Microsoft Graph.
Therefore, CountOn does NOT assume direct personal shopping API access.

Instead, Amazon Orders and delivery commitments are inferred through:
1. Amazon Shipment & Confirmation Emails (received via Gmail API or Microsoft Graph Outlook Mail).
2. Carrier Delivery Tracking Webhooks (Amazon Logistics TBA, UPS, FedEx).
3. User-Provided Tracking Statements or Order Numbers via Alexa / CountOn UI.
"""

import re
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from app.ai.amazon_intelligence import (
    AmazonOrderContext,
    AmazonDeliveryPayload,
    AmazonExtractionResult,
    extract_from_amazon_context,
    convert_amazon_to_evidence,
)


class AmazonOrderInferredConnector:
    """
    Infers and tracks Amazon Orders without assuming direct personal shopping API access.
    """

    AMAZON_ORDER_REGEX = re.compile(r"\b(\d{3}-\d{7}-\d{7})\b")
    TRACKING_REGEX = re.compile(r"\b(TBA\d{10,14}|1Z[0-9A-Z]{16})\b", re.IGNORECASE)

    @classmethod
    def parse_from_email_receipt(
        cls,
        sender: str,
        subject: str,
        body: str,
        user_statement: Optional[str] = None,
        mock_mode: Optional[bool] = None,
    ) -> AmazonExtractionResult:
        """
        Parses an Amazon confirmation or shipment notice email (from Gmail or Outlook)
        into an AmazonOrderContext.
        """
        body_clean = body or ""
        subject_clean = subject or ""
        combined = f"{subject_clean}\n{body_clean}"

        # 1. Extract Order ID
        order_match = cls.AMAZON_ORDER_REGEX.search(combined)
        order_id = order_match.group(1) if order_match else "114-0000000-0000000"

        # 2. Extract Carrier / Tracking
        tracking_match = cls.TRACKING_REGEX.search(combined)
        tracking_num = tracking_match.group(1) if tracking_match else None
        carrier = "Amazon Logistics" if (tracking_num and tracking_num.upper().startswith("TBA")) else "UPS"

        # 3. Extract Item Title (from subject or body)
        item_title = "Amazon Purchased Item"
        if "shipped:" in subject_clean.lower():
            item_title = subject_clean.split(":")[-1].strip()
        elif "ordered:" in subject_clean.lower():
            item_title = subject_clean.split(":")[-1].strip()
        elif "your order of" in combined.lower():
            m = re.search(r"your order of\s+([^\n\.,]+)", combined, re.IGNORECASE)
            if m:
                item_title = m.group(1).strip()

        # 4. Status & Anomaly Detection (delayed, cancelled, delivered, shipped)
        status: str = "shipped"
        delay_reason: Optional[str] = None
        lowered = combined.lower()

        if "delay" in lowered or "delayed" in lowered:
            status = "delayed"
            delay_reason = "Carrier reported transit delay"
        elif "cancelled" in lowered or "canceled" in lowered:
            status = "cancelled"
            delay_reason = "Order was cancelled"
        elif "delivered" in lowered:
            status = "delivered"
        elif "out for delivery" in lowered:
            status = "out_for_delivery"

        # 5. Extract expected date
        expected_date = "today"
        if "tomorrow" in lowered:
            expected_date = "tomorrow"
        elif "friday" in lowered:
            expected_date = "friday"
        elif "monday" in lowered:
            expected_date = "monday"

        order_ctx = AmazonOrderContext(
            order_id=order_id,
            item_title=item_title,
            status=status,
            expected_delivery_date=expected_date,
            carrier=carrier,
            tracking_number=tracking_num,
            delay_reason=delay_reason,
        )

        payload = AmazonDeliveryPayload(
            order=order_ctx,
            user_statement=user_statement or f"My Amazon order for {item_title} should arrive as promised",
            mock_mode=mock_mode,
        )
        return extract_from_amazon_context(payload)

    @classmethod
    def parse_from_carrier_update(
        cls,
        tracking_update: Dict[str, Any],
        user_statement: Optional[str] = None,
        mock_mode: Optional[bool] = None,
    ) -> AmazonExtractionResult:
        """
        Parses a carrier tracking webhook or update dictionary.
        """
        order_ctx = AmazonOrderContext(
            order_id=tracking_update.get("order_id", "114-1234567-8901234"),
            item_title=tracking_update.get("item_title", "Amazon Package"),
            status=tracking_update.get("status", "shipped"),
            expected_delivery_date=tracking_update.get("expected_delivery_date", "today"),
            actual_delivery_date=tracking_update.get("actual_delivery_date"),
            carrier=tracking_update.get("carrier", "Amazon Logistics"),
            tracking_number=tracking_update.get("tracking_number"),
            delay_reason=tracking_update.get("delay_reason"),
        )
        payload = AmazonDeliveryPayload(
            order=order_ctx,
            user_statement=user_statement,
            mock_mode=mock_mode,
        )
        return extract_from_amazon_context(payload)
