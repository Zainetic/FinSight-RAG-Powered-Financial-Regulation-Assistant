"""
Concurrency & Anti-Forking Tests
Verifies that parallel concurrent inserts for the same organization
serialize correctly under database locking and do NOT fork the hash chain.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from src.core.ledger import (
    append_compliance_record,
    create_genesis_block,
    verify_ledger_chain,
)


def test_concurrent_inserts_do_not_fork_chain(test_organization):
    org_id = test_organization["id"]
    org_name = test_organization["name"]

    # 1. Initialize Genesis Block #0
    genesis = create_genesis_block(org_id, org_name, "admin@concurrency.org")
    assert genesis is not None

    num_concurrent_inserts = 10

    def insert_record(idx: int):
        return append_compliance_record(
            user_query=f"Concurrent audit turn {idx}", payload={"turn": idx, "is_compliant": True}, org_id=org_id
        )

    # 2. Dispatch parallel inserts across thread pool
    receipts = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(insert_record, i) for i in range(1, num_concurrent_inserts + 1)]
        for fut in as_completed(futures):
            res = fut.result()
            assert res is not None, "Concurrent insert failed or returned None"
            receipts.append(res)

    assert len(receipts) == num_concurrent_inserts

    # 3. Verify that the entire chain is valid and unforked
    is_valid, count, error_msg = verify_ledger_chain(org_id)
    assert is_valid is True, f"Concurrent inserts caused a chain fork or corruption: {error_msg}"
    assert count == num_concurrent_inserts + 1  # 1 genesis + 10 inserts
    assert error_msg is None
