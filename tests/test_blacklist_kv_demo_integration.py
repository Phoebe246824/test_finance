import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from scripts.blacklist_demo_assertions import assert_case_state, collect_case_state_snapshot
from scripts.blacklist_demo_cases import TEST_CASES
from scripts.reset_and_seed_blacklist import main as reset_blacklist_main

ROOT = Path(__file__).resolve().parents[1]

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_blacklist_kv_demo_database_states():
    if os.getenv("RUN_BLACKLIST_DEMO_INTEGRATION") != "1":
        pytest.skip("set RUN_BLACKLIST_DEMO_INTEGRATION=1 to run live blacklist demo integration test")

    load_dotenv(ROOT / ".env")
    await reset_blacklist_main()

    import main as sentinel_main

    config = sentinel_main.load_config()
    processed_cases = []
    try:
        for case in TEST_CASES:
            await sentinel_main.process_message(case["text"], config=config)
            processed_cases.append(case)
            snapshot = await collect_case_state_snapshot(processed_cases)
            failures = assert_case_state(case, snapshot)
            assert failures == []
    finally:
        close_all_llms = getattr(sentinel_main, "close_all_llms", None)
        if close_all_llms is not None:
            await close_all_llms()
