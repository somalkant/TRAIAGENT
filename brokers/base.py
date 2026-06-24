"""
Abstract base class for all broker integrations.

To add a new broker:
  1. Create brokers/<broker_name>.py with a class inheriting BaseBroker
  2. Register it in brokers/__init__.py BROKER_REGISTRY
  3. Add credentials to .env (e.g. GROWW_API_KEY, GROWW_API_SECRET)

The agent and run_live.py are broker-agnostic — they only call the methods below.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseBroker(ABC):
    """
    Abstract broker interface. Each concrete broker must implement all methods.

    Design contract:
    - authenticate()     called by run_live.py — interactive terminal auth flow
    - get_credentials()  called by live/agent.py — returns (api_key, access_token)
    - get_api_classes()  called by live/agent.py — returns (ClientClass, TickerClass)

    The ClientClass must support the same interface as kiteconnect.KiteConnect:
      client.instruments(exchange)     → list of instrument dicts
      client.historical_data(...)      → list of candle dicts
    The TickerClass must support the same interface as kiteconnect.KiteTicker:
      ticker.subscribe(tokens)
      ticker.set_mode(mode, tokens)
      ticker.connect(threaded=True)
      ticker.close()
      ticker.on_connect / on_ticks / on_close / on_error callbacks
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Machine-readable broker identifier, e.g. 'zerodha', 'groww'."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable broker name, e.g. 'Zerodha (Kite Connect)'."""

    @abstractmethod
    def authenticate(self, log) -> str:
        """
        Interactive authentication flow — runs in run_live.py before the agent starts.

        Responsibilities:
          - Check checkpoint cache (checkpoints/access_token.json) for today's token
          - If fresh login needed: print instructions, prompt user, exchange token
          - Cache the token for the day
          - Return access_token string

        Args:
            log: Python logger instance (for info/error messages)

        Returns:
            str: Today's access_token
        """

    @abstractmethod
    def get_credentials(self, args) -> tuple[str, str]:
        """
        Returns (api_key, access_token) for the live agent.
        Called inside live/agent.py — reads from env + args + checkpoint.

        Args:
            args: argparse.Namespace with at least args.token (may be None)

        Returns:
            (api_key, access_token)

        Raises:
            RuntimeError: If credentials cannot be found
        """

    @abstractmethod
    def get_api_classes(self) -> tuple[type, type]:
        """
        Returns (ClientClass, TickerClass) for this broker.

        For Zerodha:  (kiteconnect.KiteConnect, kiteconnect.KiteTicker)
        For a new broker: adapter classes that implement the same interface

        Raises:
            NotImplementedError: If the broker library is not yet installed/configured
        """
