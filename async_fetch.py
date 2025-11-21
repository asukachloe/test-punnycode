import asyncio
import aiohttp
import async_timeout

CONCURRENT_LIMIT = 100          # Max concurrent requests
REQUEST_TIMEOUT = 5             # Seconds per request
DOMAIN_FILE = "domains.txt"     # Input file


async def fetch(session: aiohttp.ClientSession, url: str):
    try:
        with async_timeout.timeout(REQUEST_TIMEOUT):
            async with session.get(url, allow_redirects=True) as resp:
                # We only fetch status and final URL, not body, for speed
                return {
                    "url": url,
                    "status": resp.status,
                    "final_url": str(resp.url)
                }
    except asyncio.TimeoutError:
        return {"url": url, "error": "timeout"}
    except aiohttp.ClientError as e:
        return {"url": url, "error": f"client_error: {e}"}
    except Exception as e:
        return {"url": url, "error": f"unexpected_error: {e}"}


async def worker(domain_queue: asyncio.Queue, session: aiohttp.ClientSession):
    while True:
        domain = await domain_queue.get()
        if domain is None:
            domain_queue.task_done()
            break

        url = f"http://{domain.strip()}"
        result = await fetch(session, url)

        if "error" in result:
            print(f"[SKIP] {domain} -> {result['error']}")
        else:
            print(f"[OK] {domain} -> {result['status']} ({result['final_url']})")

        domain_queue.task_done()


async def main():
    # Load domains
    with open(DOMAIN_FILE, "r") as f:
        domains = [line.strip() for line in f if line.strip()]

    domain_queue = asyncio.Queue()

    for d in domains:
        domain_queue.put_nowait(d)

    # Prepare HTTP client with tuned connector
    connector = aiohttp.TCPConnector(
        limit=CONCURRENT_LIMIT,
        ttl_dns_cache=300,
        ssl=False  # disable SSL verify to avoid slow handshake failures
    )

    async with aiohttp.ClientSession(connector=connector) as session:
        workers = []
        for _ in range(CONCURRENT_LIMIT):
            w = asyncio.create_task(worker(domain_queue, session))
            workers.append(w)

        # Wait until all work items are processed
        await domain_queue.join()

        # Stop workers
        for _ in workers:
            domain_queue.put_nowait(None)

        await asyncio.gather(*workers)


if __name__ == "__main__":
    asyncio.run(main())
