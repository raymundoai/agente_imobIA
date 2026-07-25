from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChannelCredentials:
    base_url: str
    instance: str
    api_key: str
    webhook_secret: str
