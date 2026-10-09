import os
import hashlib
import json
from datetime import datetime
import pytz
import boto3
import logging
from boto3.dynamodb.conditions import Key


logging.basicConfig(format="%(levelname)s %(message)s")
logger = logging.getLogger()
logger.info("Initializing FBPBlockChain Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)
logger.info("FBPBlockChain Lambda function initialized successfully")


FBP_BLOCKCHAIN_TABLE_NAME = os.getenv("FBPBlockChainTableName", "2026-FBPBlockChain")
print(f"FBP_BLOCKCHAIN_TABLE_NAME: {FBP_BLOCKCHAIN_TABLE_NAME}")


class Block:
    ##
    # add email as optional field
    ##
    
    def __init__(self, index, data, previous_hash, timestamp=None, email=None, event=None, week=None):
        self.index = index
        self.email = email or (data.get("email") if isinstance(data, dict) else None)
        mytimestamp = datetime.now(pytz.utc).astimezone(pytz.timezone("America/New_York")).strftime("%Y-%m-%d %H:%M:%S")
        # self.timestamp = timestamp or mytimestamp 
        self.timestamp = mytimestamp
        # logger.info(f"Block timestamp set to: {self.timestamp}")
        self.data = data
        self.previous_hash = previous_hash
        self.event = event
        self.week = week
        self.hash = self._compute_hash()

    def _compute_hash(self):
        block_string = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "email": self.email,
            "previous_hash": self.previous_hash,
        }, sort_keys=True)
        return hashlib.sha256(block_string.encode()).hexdigest()


class Blockchain:
    def __init__(self):
        print(f"Initializing Blockchain with table: {FBP_BLOCKCHAIN_TABLE_NAME}")
        self.table = boto3.resource("dynamodb").Table(FBP_BLOCKCHAIN_TABLE_NAME)
        # print(f"Blockchain initialized with table: {self.table}")
        self.chain = self._load_chain()

    def _load_chain(self):
        print(f"Loading blockchain from DynamoDB table: {FBP_BLOCKCHAIN_TABLE_NAME}")
        response = self.table.scan()
        items = sorted(response.get("Items", []), key=lambda x: int(x["index"]))
        if not items:
            genesis = self._create_genesis_block()
            self._save_block(genesis)
            return [genesis]
        return [
            Block(int(item["index"]), item["data"], item["previous_hash"],
                  item["timestamp"], email=item.get("email"), event=item.get("event"), week=item.get("week"))
            for item in items
        ]

    def _create_genesis_block(self):
        return Block(0, "Genesis Block", "0", email="genesis@blockchain.com")

    def _save_block(self, block):
        item = {
            "index": block.index,
            "timestamp": block.timestamp,
            "data": block.data,
            "previous_hash": block.previous_hash,
            "hash": block.hash,
        }
        if block.email:
            item["email"] = block.email
        if block.event:
            item["event"] = block.event
        if block.week:
            item["week"] = block.week
        self.table.put_item(Item=item)

    @property
    def latest_block(self):
        return self.chain[-1]

    def add_block(self, data, event=None, email=None, week=None):
        block = Block(len(self.chain), data, self.latest_block.hash, event=event, email=email, week=week)
        self._save_block(block)
        self.chain.append(block)
        return block

    def is_valid(self):
        for i in range(1, len(self.chain)):
            current, previous = self.chain[i], self.chain[i - 1]
            if current.hash != current._compute_hash():
                return False
            if current.previous_hash != previous.hash:
                return False
        return True
