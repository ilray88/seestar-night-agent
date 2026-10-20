import asyncio, sys
from seestar_mcp.config import Settings
from seestar_mcp.alpaca_client import AlpacaClient

async def main():
    s = Settings()
    print("base:", s.alpaca_base_url, "dev:", s.alpaca_device_num)
    c = AlpacaClient(s.alpaca_base_url, device_num=s.alpaca_device_num)
    print("connected:", await c.get_connected())
    print("tracking :", await c.get_tracking())
    print("ra/dec   :", await c.get_ra(), await c.get_dec())
    await c.aclose()
asyncio.run(main())
