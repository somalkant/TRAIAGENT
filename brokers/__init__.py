"""
Broker abstraction layer.

Adding a new broker (e.g. AngelOne):
  1. Create brokers/angelone.py with a class inheriting BaseBroker
  2. Implement: name, display_name, authenticate(), get_credentials(), get_api_classes()
  3. Add one line to BROKER_REGISTRY below: "angelone": AngelOneBroker
  4. Add credentials to .env
  That's it — run_live.py and live/agent.py pick it up automatically.
"""

from brokers.base import BaseBroker
from brokers.zerodha import ZerodhaBroker
from brokers.groww import GrowwBroker

# Registry: broker name → class. Order controls display order in the broker selection menu.
BROKER_REGISTRY: dict[str, type[BaseBroker]] = {
    "zerodha": ZerodhaBroker,
    "groww":   GrowwBroker,
    # "angelone": AngelOneBroker,   ← example: import and add here
}

__all__ = ["BaseBroker", "BROKER_REGISTRY", "get_broker"]


def get_broker(name: str) -> BaseBroker:
    """
    Instantiate a broker by name.

    Args:
        name: Case-insensitive broker identifier (e.g. 'zerodha', 'groww')

    Returns:
        BaseBroker instance

    Raises:
        ValueError: If the broker name is not in BROKER_REGISTRY
    """
    cls = BROKER_REGISTRY.get(name.lower())
    if cls is None:
        available = ", ".join(BROKER_REGISTRY.keys())
        raise ValueError(f"Unknown broker '{name}'. Available: {available}")
    return cls()
