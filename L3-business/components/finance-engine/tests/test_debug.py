import sys

def test_path():
    print("\nSYS.PATH:")
    for i, p in enumerate(sys.path):
        print(f"  [{i}] {p}")
    print()
    from finance_engine.services.account_svc import AccountService
    print("Import OK:", AccountService)
