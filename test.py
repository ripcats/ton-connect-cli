import asyncio
import json
from TonConnect import TonConnectClient, TonConnectException


async def main():
    client = TonConnectClient()
    try:
        await client.init()
    except TonConnectException as e:
        output = {"error_code": e.code.value, "error_message": str(e)}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    try:
        while True:
            tc_url = input("Ton-connect link: ").strip()
            if not tc_url:
                continue
            if tc_url.lower() in {"exit", "quit"}:
                break
            try:
                result = await client.connect(tc_url)
                output = {
                    "code": result.code.value,
                    "data": result.data,
                    "error_code": (
                        result.error_code.value if result.error_code else None
                    ),
                    "error_message": result.error_message,
                }
                print(json.dumps(output, ensure_ascii=False, indent=2))
            except TonConnectException as e:
                output = {"error_code": e.code.value, "error_message": str(e)}
                print(json.dumps(output, ensure_ascii=False, indent=2))
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
