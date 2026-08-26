from backend.app.gateways.base import PaymentGateway
from backend.app.gateways.razorpay_adapter import RazorpayTestAdapter
from backend.app.gateways.mock_adapter import MockPaymentGateway

# Default system adapter
default_gateway: PaymentGateway = RazorpayTestAdapter()
