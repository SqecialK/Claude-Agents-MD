import asyncio
import json

import websockets

from btcmm.adapters.transport import reconnecting_ws


async def test_reconnects_and_resubscribes():
    """Server drops the connection after one message; client must reconnect,
    re-run on_open (resubscribe) and report connected/disconnected."""
    async def handler(ws):
        sub = json.loads(await ws.recv())
        await ws.send(json.dumps({"n": sub["n"]}))
        await ws.close()

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        opens, statuses, got = [], [], []

        async def on_open(ws):
            opens.append(1)
            await ws.send(json.dumps({"n": len(opens)}))

        stop = asyncio.Event()
        async def run():
            async for m in reconnecting_ws(f"ws://127.0.0.1:{port}", name="t", on_open=on_open, stop=stop,
                                           on_status=lambda e, d: statuses.append(e)):
                got.append(m["n"])
                if len(got) == 2:
                    stop.set()
                    return
        await asyncio.wait_for(run(), timeout=10)
    assert got == [1, 2] and len(opens) == 2
    assert statuses.count("connected") == 2 and "disconnected" in statuses
