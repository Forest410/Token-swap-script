

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import random
from web3 import Web3
from time import sleep
import json
from eth_abi import abi
from utils.wallet_tools_scroll import WalletTool
from utils.utilities import Receipt, determine_decimals, get_amount, check_and_compare_balance, get_swap_deadline
import time
from loguru import logger as LOGGER

with open('coinData.json', 'r') as f:
    coin_data = json.load(f)

# pip freeze, pip install eth_abi


from config import (
    ZEBRASWAP_CLASSIC_POOL_DATA_ABI,
    ZERO_ADDRESS,
    ZEBRASWAP_CONTRACTS,
    ZEBRASWAP_ROUTER_ABI,
    ZEBRASWAP_CLASSIC_POOL_ABI,
    SCROLL_TOKENS

)

class ZebraSwap(WalletTool):
    def __init__(self, acc: WalletTool) -> None:
        super().__init__(acc)
        self.id = 'id placeholder' #ignore this
        wallet = WalletTool(acc)
        self.swap_contract = self.get_contract(ZEBRASWAP_CONTRACTS["router"], ZEBRASWAP_ROUTER_ABI)
        self.nonce = self.get_nonce('scroll')
        self.tx = {
            "from": wallet.checksum_address,
            "gasPrice": self.w3.eth.gas_price,
            "nonce": self.nonce,
        }

    def get_pool(self, sell_token: str, buy_token: str):
        contract = self.get_contract(ZEBRASWAP_CONTRACTS["classic_pool"], ZEBRASWAP_CLASSIC_POOL_ABI)
        print(contract.address)
        pool_address = contract.functions.getPair(
            Web3.to_checksum_address(SCROLL_TOKENS[sell_token]),
            Web3.to_checksum_address(SCROLL_TOKENS[buy_token])
        ).call()

        return pool_address

    #TODO randomize slippage
    #TODO move some of these functions to a swap utility class
    def get_min_amount_out(self, pool_address: str, token_address: str, buytoken: str, amount: int, slippage: float, sellToken_decimal: int):
        pool_contract = self.get_contract(pool_address, ZEBRASWAP_CLASSIC_POOL_DATA_ABI)
        factory_contract = self.get_contract(ZEBRASWAP_CONTRACTS["classic_pool"], ZEBRASWAP_CLASSIC_POOL_ABI)
        getAmountsOut = factory_contract.functions.getAmountsOut(amount, [token_address, SCROLL_TOKENS[buytoken]]).call()
        return getAmountsOut[1]

    def swap(
            self,
            sell_token: str,
            buy_token: str,
            slippage: float,
            amount
    ):
        token_address = Web3.to_checksum_address(SCROLL_TOKENS[sell_token])

        buy_token_decimals, sell_token_decimals = determine_decimals(buy_token, sell_token, coin_data)

        amount_parsed = get_amount(
            sell_token,
            amount,
            sell_token_decimals,
        )

        LOGGER.info(
            f"[{self.id}][{self.pubkey}] Swap on ZebraSwap – {sell_token} -> {buy_token} |Sell {amount} {sell_token}"
        )

        pool_address = self.get_pool(sell_token, buy_token)
        print(pool_address)
        if pool_address != ZERO_ADDRESS:
            if sell_token == "ETH":
                self.tx.update({"value": amount_parsed})
            else:
                if self.approve(amount_parsed, token_address, Web3.to_checksum_address(ZEBRASWAP_CONTRACTS["router"])):
                    self.tx.update({"nonce": self.get_nonce('scroll')})
            min_amount_out = self.get_min_amount_out(pool_address, token_address, buy_token, amount_parsed, slippage, sell_token_decimals)
            print(min_amount_out)
            steps = [{
                "pool": pool_address,
                "data": abi.encode(["address", "address", "uint8"], [token_address, self.pubkey, 1]),
                "callback": ZERO_ADDRESS,
                "callbackData": "0x"
            }]

            paths = [{
                "steps": steps,
                "tokenIn": ZERO_ADDRESS if sell_token == "ETH" else token_address,
                "amountIn": amount_parsed
            }]

            deadline_options = [300, 600, 900, 1200]
            deadline = get_swap_deadline()

            tx = self.tx

            # try:
            LOGGER.info(f'[PK: {self.id}] Sending Syncswap transaction...')
            contract_txn = ''
            if sell_token == 'ETH':
                contract_txn = self.swap_contract.functions.swapExactETHForTokens(
                    min_amount_out,
                    [SCROLL_TOKENS[sell_token], SCROLL_TOKENS[buy_token]],
                    self.pubkey,
                    deadline
                ).build_transaction(self.tx)
            elif buy_token == 'ETH':
                contract_txn = self.swap_contract.functions.swapExactTokensForETH(
                    amount_parsed,
                    min_amount_out,
                    [SCROLL_TOKENS[sell_token], SCROLL_TOKENS[buy_token]],
                    self.pubkey,
                    deadline
                ).build_transaction(self.tx)
            else :
                contract_txn = self.swap_contract.functions.swapExactTokensForTokens(
                    amount_parsed,
                    min_amount_out,
                    [SCROLL_TOKENS[sell_token], SCROLL_TOKENS[buy_token]],
                    self.pubkey,
                    deadline
                ).build_transaction(self.tx)

            signed_txn = self.sign(contract_txn)

            txn_hash = self.send_raw_transaction(signed_txn)

            receipt = self.wait_until_tx_finished(txn_hash.hex())

            return txn_hash.hex(), receipt
            # except Exception as e:
                # LOGGER.error(f"[PK: {self.id}][{self.pubkey}] ZebraSwap failed: {e}")
                # return False

        else:
            LOGGER.error(f"[PK: {self.id}][{self.pubkey}] Swap path {sell_token} to {buy_token} not found!")

if __name__ == '__main__':
    with open('privkey.txt','r') as f:
        privkey = f.read()
    zebraswap_instance = ZebraSwap(privkey)
    # zebraswap_instance.swap('ETH','USDC',.02,0.01)
    # zebraswap_instance.swap('ETH','USDC',.01,0.001)
    # zebraswap_instance.swap('USDC','WBTC',.01,1)
    zebraswap_instance.swap('WBTC', 'ETH',.01,0.00001)

    # pool = zebraswap_instance.get_pool('ETH', 'USDC')

    # zebraswap_instance.get_min_amount_out(pool, 0.01, 0.001)
