# Mock database for Bookly bookstore

ORDERS = {
    "ORD-123": {
        "customer_email": "freddie@example.com",
        "customer_name": "Freddie Mercury",
        "status": "shipped",
        "item": "The Great Gatsby",
        "delivery_date": "July 10, 2026",
        "order_value": 24.99,
    },
    "ORD-456": {
        "customer_email": "david@example.com",
        "customer_name": "David Bowie",
        "status": "processing",
        "item": "1984",
        "delivery_date": "July 15, 2026",
        "order_value": 18.99,
    },
    "ORD-789": {
        "customer_email": "frida@example.com",
        "customer_name": "Frida Kahlo",
        "status": "delivered",
        "item": "To Kill a Mockingbird",
        "delivery_date": "July 3, 2026",
        "order_value": 149.99,
    },
}

REFUNDS = {}  # Will store refund requests

POLICIES = {
    "return_window": "30 days from delivery",
    "refund_processing": "5-7 business days",
    "shipping_time": "3-5 business days standard, 1-2 days express",
    "free_shipping_threshold": 35.00,
}
