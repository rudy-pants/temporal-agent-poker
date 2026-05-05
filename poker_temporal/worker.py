import asyncio
import os

from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.worker import Worker

from workflow.poker_workflow import PokerGameWorkflow
from workflow.activities import gpt_decide, gpt_reflect_hand, gpt_compress_learnings

load_dotenv()


async def main():
    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue="poker",
        workflows=[PokerGameWorkflow],
        activities=[gpt_decide, gpt_reflect_hand, gpt_compress_learnings],
    )

    print(f"Poker worker started. OPENAI_API_KEY={'set' if os.environ.get('OPENAI_API_KEY') else 'MISSING'}")
    print("Listening on task queue 'poker'...")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
