"""Script de inicialização — roda uvicorn dentro de ProactorEventLoop no Windows."""
import sys
import asyncio

if sys.platform == "win32":
    # Forçar ProactorEventLoop antes de qualquer import do uvicorn
    loop = asyncio.ProactorEventLoop()
    asyncio.set_event_loop(loop)
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

async def _main():
    config = uvicorn.Config("app.main:app", host="0.0.0.0", port=8000, loop="none")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.get_event_loop().run_until_complete(_main())
    else:
        asyncio.run(_main())

