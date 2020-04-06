from __future__ import annotations
from vm.gas_schedule import AbstractMemorySize, GasAlgebra, GasCarrier, GasPrice, GasUnits
from libra import Address, SignedTransaction
from libra.transaction.authenticator import TransactionAuthenticator, AuthenticationKeyPreimage
from libra.crypto.ed25519 import Ed25519PublicKey, generate_genesis_keypair
from canoser import Struct, Uint64, BytesT
from dataclasses import dataclass

@dataclass
class TransactionMetadata:
    sender: Address
    authentication_key_preimage: bytes
    sequence_number: Uint64
    max_gas_amount: GasUnits
    gas_unit_price: GasPrice
    transaction_size: AbstractMemorySize
    expiration_time: Uint64

    @classmethod
    def new(cls, txn: SignedTransaction) -> TransactionMetadata:
        return TransactionMetadata(
            sender = txn.sender,
            authentication_key_preimage= txn.authenticator.authentication_key_preimage(),
            sequence_number = txn.sequence_number,
            max_gas_amount = GasUnits.new(txn.max_gas_amount),
            gas_unit_price = GasPrice.new(txn.gas_unit_price),
            transaction_size = AbstractMemorySize.new(txn.raw_txn_bytes_len()),
            expiration_time = txn.expiration_time,
        )

    @classmethod
    def default(cls) -> TransactionMetadata:
        (_, public_key) = generate_genesis_keypair()
        return TransactionMetadata(
            sender = Address.default(),
            authentication_key_preimage = AuthenticationKeyPreimage.ed25519(public_key),
            sequence_number = 0,
            max_gas_amount = GasUnits.new(100_000_000),
            gas_unit_price = GasPrice.new(0),
            transaction_size = AbstractMemorySize.new(0),
            expiration_time = 0,
        )


