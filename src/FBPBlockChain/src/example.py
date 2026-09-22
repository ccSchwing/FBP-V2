from blockchain import Blockchain

bc = Blockchain()

bc.add_block({"user": "alice", "pick": "Chiefs", "week": 1})
bc.add_block({"user": "bob",   "pick": "Eagles", "week": 1})

for block in bc.chain:
    print(f"[{block.index}] {block.hash[:16]}... | data: {block.data}")

print(f"\nChain valid: {bc.is_valid()}")
