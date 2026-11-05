import argparse
from .service import PlatformService


def main():
    parser = argparse.ArgumentParser(description="Mock Studio — API và worker độc lập")
    parser.add_argument(
        "command", choices=["serve", "worker", "crawl-worker", "status"]
    )
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn
        from .api import create_app

        uvicorn.run(create_app(), host="127.0.0.1", port=args.port)
    elif args.command == "crawl-worker":
        from .crawler import CrawlerWorker
        import signal

        def stop_crawler(signum, frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, stop_crawler)
        CrawlerWorker().loop()
    elif args.command == "worker":
        from .worker import Worker

        Worker().loop()
    else:
        import json

        print(json.dumps(PlatformService().summary(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
