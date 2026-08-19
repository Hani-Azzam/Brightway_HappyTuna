"""
Journalist Agent — Event-driven entrypoint.
Subscribes to 'press' events from the event generator
and automatically investigates each one.
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
from agents.journalist.event_client import subscribe
from agents.journalist.journalist_agent import JournalistAgent, JournalistConfig

load_dotenv()


async def main():
    print("=" * 60)
    print("  Journalist Agent — Event Listener")
    print("  Subscribing to: press events")
    print("=" * 60)

    config = JournalistConfig.from_env()

    if not config.gemini_api_key:
        print("\n ERROR: GEMINI_API_KEY not set in .env file")
        return

    with JournalistAgent(config) as agent:
        # Load knowledge base once on startup
        print("\n Loading knowledge base...")
        agent.index_knowledge("agents/journalist/knowledge")
        print(" Agent ready — waiting for press events...\n")

        async for event in subscribe("press"):
            print(f"\n{'=' * 60}")
            print(f"  NEW EVENT [seq={event.seq}] tag={event.tag}")
            print(f"  {event.text[:120]}...")
            print(f"{'=' * 60}\n")

            print(" Journalist is investigating...\n")
            response = agent.chat(event.text)
            print(f"\n Agent: {response}\n")
            print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())