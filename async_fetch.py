import asyncio
import aiohttp
import idna

CONCURRENT_LIMIT = 100
REQUEST_TIMEOUT = 5
DOMAIN_FILE = "domains.txt"


async def fetch(session: aiohttp.ClientSession, url: str):
    try:
        # asyncio.timeout is the correct context manager for Python 3.11+
        async with asyncio.timeout(REQUEST_TIMEOUT):
            async with session.get(url, allow_redirects=True) as resp:
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

        try:
            punycode_domain = idna.encode(domain).decode()
            url = f"http://{punycode_domain}"
        except idna.IDNAError:
            print(f"[SKIP] {domain} -> invalid_idn")
            domain_queue.task_done()
            continue

        result = await fetch(session, url)

        if "error" in result:
            print(f"[SKIP] {domain} -> {result['error']}")
        else:
            print(f"[OK] {domain} -> {result['status']} ({result['final_url']})")

        domain_queue.task_done()


async def main():
    with open(DOMAIN_FILE, "r") as f:
        domains = [line.strip() for line in f if line.strip()]

    domain_queue = asyncio.Queue()

    for d in domains:
        domain_queue.put_nowait(d)

    connector = aiohttp.TCPConnector(
        limit=CONCURRENT_LIMIT,
        ttl_dns_cache=300,
        ssl=False
    )

    async with aiohttp.ClientSession(connector=connector) as session:
        workers = []
        for _ in range(CONCURRENT_LIMIT):
            w = asyncio.create_task(worker(domain_queue, session))
            workers.append(w)

        await domain_queue.join()

        for _ in workers:
            domain_queue.put_nowait(None)

        await asyncio.gather(*workers)


if __name__ == "__main__":
    asyncio.run(main())
