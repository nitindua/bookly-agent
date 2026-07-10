import json
from data import ORDERS, REFUNDS

# Tool definitions for Claude API
TOOLS = [
    {
        "name": "lookup_order",
        "description": "Look up order status by order ID. Use this before answering any questions about order status, delivery, or shipping.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order ID, e.g. ORD-123"
                }
            },
            "required": ["order_id"]
        }
    },
    {
        "name": "request_refund",
        "description": "Submit a refund request for an order. Requires order ID and reason for refund.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order ID to refund"
                },
                "reason": {
                    "type": "string",
                    "description": "Customer's reason for requesting refund"
                }
            },
            "required": ["order_id", "reason"]
        }
    }
]


def handle_lookup_order(order_id: str) -> dict:
    """Look up an order in the mock database."""
    order_id = order_id.upper().strip()

    if order_id in ORDERS:
        order = ORDERS[order_id]
        # PII (customer_name, customer_email) is intentionally not returned.
        # In production, PII should only be surfaced after identity verification.
        return {
            "success": True,
            "order_id": order_id,
            "status": order["status"],
            "item": order["item"],
            "delivery_date": order["delivery_date"],
            "order_value": order["order_value"]
        }
    else:
        return {
            "success": False,
            "error": f"Order {order_id} not found"
        }


def handle_request_refund(order_id: str, reason: str) -> dict:
    """Process a refund request."""
    order_id = order_id.upper().strip()

    if order_id not in ORDERS:
        return {
            "success": False,
            "error": f"Order {order_id} not found"
        }

    order = ORDERS[order_id]

    # Check escalation condition: order value > 100
    if order["order_value"] > 100:
        return {
            "success": False,
            "escalate": True,
            "reason": "Order value exceeds $100. Requires human approval.",
            "order_value": order["order_value"]
        }

    # Process refund
    refund_id = f"REF-{len(REFUNDS) + 1001}"
    REFUNDS[refund_id] = {
        "order_id": order_id,
        "reason": reason,
        "amount": order["order_value"],
        "status": "submitted"
    }

    return {
        "success": True,
        "refund_id": refund_id,
        "amount": order["order_value"],
        "message": "Refund submitted. Expect processing in 5-7 business days."
    }


def run_tool(tool_name: str, tool_input: dict) -> str:
    """Route tool calls to the appropriate handler."""
    if tool_name == "lookup_order":
        result = handle_lookup_order(tool_input["order_id"])
    elif tool_name == "request_refund":
        result = handle_request_refund(tool_input["order_id"], tool_input["reason"])
    else:
        result = {"error": f"Unknown tool: {tool_name}"}

    return json.dumps(result)
