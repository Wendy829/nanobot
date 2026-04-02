from types import SimpleNamespace

import pytest

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel


class _DummyChannel(BaseChannel):
    name = "dummy"

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send(self, msg: OutboundMessage) -> None:
        return None


@pytest.mark.asyncio
async def test_handle_message_injects_default_tenant_and_team_ids() -> None:
    bus = MessageBus()
    channel = _DummyChannel(
        SimpleNamespace(allow_from=["u1"], tenant_id="acme", team_ids=["ops"]),
        bus,
    )
    await channel._handle_message(sender_id="u1", chat_id="c1", content="hello")
    msg = await bus.consume_inbound()
    assert msg.metadata["tenant_id"] == "acme"
    assert msg.metadata["team_ids"] == ["ops"]

