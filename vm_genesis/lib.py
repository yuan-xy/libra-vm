from __future__ import annotations
from vm_genesis.genesis_gas_schedule import initial_gas_schedule
from bytecode_verifier import VerifiedModule
from libra_storage.state_view import StateView, EmptyStateView

from libra.access_path import AccessPath
from libra.account_address import Address
from libra.account_config import AccountConfig, CORE_CODE_ADDRESS
from libra.contract_event import ContractEvent
from libra.event import EventKey
from move_core.types.identifier import Identifier
from libra.transaction import ChangeSet, RawTransaction, SignatureCheckedTransaction
from libra.discovery_info import DiscoveryInfo
from libra.discovery_set import DiscoverySet
from libra.validator_set import ValidatorSet
from libra.crypto.ed25519 import generate_keypair, Ed25519PrivateKey, Ed25519PublicKey, ED25519_PUBLIC_KEY_LENGTH
from libra.rustlib import assert_equal, bail
from stdlib import stdlib_modules
from vm.vm_exception import VMException
from vm.file_format import ModuleAccess
from vm.gas_schedule import CostTable, GasAlgebra, GasUnits
from vm.file_format_common import Opcodes
from vm.transaction_metadata import TransactionMetadata
from move_vm.types.chain_state import ChainState
from move_vm.state.execution_context import TransactionExecutionContext
from move_vm.state.data_cache import BlockDataCache
from move_vm.runtime.move_vm import MoveVM
from libra_vm.system_module_names import *
from move_vm.types.values import Value
from multiaddr import Multiaddr

def assert_equal_bail(a, b, hint, *args):
    if not a==b:
        bail(hint, *args)


# The seed is arbitrarily picked to produce a consistent key. XXX make this more formal
GENESIS_SEED = bytes([42]*ED25519_PUBLIC_KEY_LENGTH)

# The initial balance of the association account.
ASSOCIATION_INIT_BALANCE: Uint64 = 1_000_000_000_000_000

# GENESIS_KEYPAIR: Tuple[Ed25519PrivateKey, Ed25519PublicKey] = generate_keypair(GENESIS_SEED)
GENESIS_KEYPAIR = (
        bytes.fromhex("4db4ef1992889d4428e400be3428843db6e89bb2e8aaf4ce8efe00df64012544"),
        bytes.fromhex("01add5624932fc6e5e82ea4b8b4217c2ea4372a1e4fbc9d910a38b2514931166"),
    )

# Identifiers for well-known functions.
ADD_VALIDATOR = "add_validator"
INITIALIZE = "initialize"
INITIALIZE_BLOCK = "initialize_block_metadata"
INITIALIZE_TXN_FEES = "initialize_transaction_fees"
INITIALIZE_VALIDATOR_SET = "initialize_validator_set"
INITIALIZE_DISCOVERY_SET = "initialize_discovery_set"
MINT_TO_ADDRESS = "mint_to_address"
RECONFIGURE = "reconfigure"
REGISTER_CANDIDATE_VALIDATOR = "register_candidate_validator"
ROTATE_AUTHENTICATION_KEY = "rotate_authentication_key"
EPILOGUE = "epilogue"

# TODO(philiphayes): remove this after integrating on-chain discovery with config.
# Make a placeholder `DiscoverySet` from the `ValidatorSet`.
def make_placeholder_discovery_set(validator_set: ValidatorSet) -> DiscoverySet:
    fullnodes_network_identity_pubkeys = [
        '362310b9ce4dc15258ddf5ebe2ddeaad3ab2ca34cb2b3582b94ef61b990d2c61',
        '6d168c904a92d03090c331e27431ceae1e5adbd8ea0699139b498757427c1355',
        '3555049e0153079e64a9fdf87d132bab5d85ab3153b80e6010facef8816db51d',
        '24322690e4396d9349c8ee5d81726a8e976b9955619e57526b7eb808f47a827f',
        '2040e06de241e6f65db31e5c787a58c907cc7776c8db5dda8c5c739c6f0a7c38',
        'a15d83780bf63ef55208ce0fd9eace023b9918b6b652485b722df90e4a37e57e',
        'fb3d12f9bbf3be4b9e2774dec38d7c36832c770e32583e1d46cdfa2849149a18',
        'a4ace5ee7da7e56e08194bfa93310d789fba224137175c910eece333b2545a17',
        '0f8fd6be0174c5a70ef22c2a65ac59a3e33361c8555b003f84341546b8c3343f',
        '8ac3120524009751497025009a45f577212ad3e9e1e0536053de624319ecd869',
    ]
    def validator_pubkeys_to_discovery_info(idx, validator_pubkeys):
        return DiscoveryInfo(
            validator_pubkeys.account_address,
            # validator_network_identity_pubkey
            validator_pubkeys.network_identity_public_key,
            # validator_network_address PLACEHOLDER
            Multiaddr("/ip4/127.0.0.1/tcp/6180").to_bytes(),
            # fullnodes_network_identity_pubkey PLACEHOLDER
            bytes.fromhex(fullnodes_network_identity_pubkeys[idx]),
            # fullnodes_network_address PLACEHOLDER
            Multiaddr("/ip4/127.0.0.1/tcp/6180").to_bytes(),
        )
    discovery_set = [validator_pubkeys_to_discovery_info(i,x) for i,x in enumerate(validator_set)]
    return discovery_set


def encode_genesis_transaction_with_validator(
    private_key: Ed25519PrivateKey,
    public_key: Ed25519PublicKey,
    validator_set: ValidatorSet,
    discovery_set: DiscoverySet,
) -> SignatureCheckedTransaction:
    return encode_genesis_transaction_with_validator_and_modules(
        private_key,
        public_key,
        validator_set,
        discovery_set,
        stdlib_modules(),
    )


def encode_genesis_transaction_with_validator_and_modules(
    private_key: Ed25519PrivateKey,
    public_key: Ed25519PublicKey,
    validator_set: ValidatorSet,
    discovery_set: DiscoverySet,
    stdlib_modules: List[VerifiedModule],
) -> SignatureCheckedTransaction:
    # create a MoveVM
    move_vm = MoveVM.new()

    # create a data view for move_vm
    state_view = GenesisStateView()
    gas_schedule = CostTable.zero()
    data_cache = BlockDataCache.new(state_view)

    # create an execution context for the move_vm.
    # It will contain the genesis WriteSet after execution
    interpreter_context =\
        TransactionExecutionContext.new(GasUnits.new(100_000_000), data_cache)

    # initialize the VM with stdlib modules.
    # This step is needed because we are creating the main accounts and we are calling
    # code to create those. However, code lives under an account but we have none.
    # So we are pushing code into the VM blindly in order to create the main accounts.
    for module in stdlib_modules:
        move_vm.cache_module(module)


    # generate the genesis WriteSet
    create_and_initialize_main_accounts(
        move_vm,
        gas_schedule,
        interpreter_context,
        public_key,
        initial_gas_schedule(move_vm, data_cache),
    )

    create_and_initialize_validator_and_discovery_set(
        move_vm,
        gas_schedule,
        interpreter_context,
        validator_set,
        discovery_set,
    )
    reconfigure(move_vm, gas_schedule, interpreter_context)
    publish_stdlib(interpreter_context, stdlib_modules)
    verify_genesis_write_set(interpreter_context.events(), validator_set, discovery_set)

    genesis_write_set = ChangeSet(
        interpreter_context.make_write_set(),
        interpreter_context.events(),
    )

    transaction = RawTransaction.new_change_set(
        AccountConfig.association_address_bytes(), 0, genesis_write_set
    )
    return transaction.sign(private_key, public_key)


# Create an initialize Association, Transaction Fee and Core Code accounts.
def create_and_initialize_main_accounts(
    move_vm: MoveVM,
    gas_schedule: CostTable,
    interpreter_context: TransactionExecutionContext,
    public_key: Ed25519PublicKey,
    initial_gas_schedule: Value,
) -> None:
    association_addr = AccountConfig.association_address_bytes()
    txn_data = TransactionMetadata.default()
    txn_data.sender = association_addr

    # create the association account
    move_vm.execute_function(
            ACCOUNT_MODULE,
            CREATE_ACCOUNT_NAME,
            gas_schedule,
            interpreter_context,
            txn_data,
            [Value.address(association_addr)],
        )

    # create the transaction fee account
    transaction_fee_address = AccountConfig.transaction_fee_address_bytes()
    move_vm.execute_function(
            ACCOUNT_MODULE,
            CREATE_ACCOUNT_NAME,
            gas_schedule,
            interpreter_context,
            txn_data,
            [Value.address(transaction_fee_address)],
        )

    move_vm.execute_function(
            COIN_MODULE,
            INITIALIZE,
            gas_schedule,
            interpreter_context,
            txn_data,
            [],
        )

    move_vm.execute_function(
            LIBRA_TRANSACTION_TIMEOUT,
            INITIALIZE,
            gas_schedule,
            interpreter_context,
            txn_data,
            [],
        )

    move_vm.execute_function(
            LIBRA_BLOCK_MODULE,
            INITIALIZE_BLOCK,
            gas_schedule,
            interpreter_context,
            txn_data,
            [],
        )

    move_vm.execute_function(
            GAS_SCHEDULE_MODULE,
            INITIALIZE,
            gas_schedule,
            interpreter_context,
            txn_data,
            [initial_gas_schedule],
        )

    move_vm.execute_function(
            ACCOUNT_MODULE,
            MINT_TO_ADDRESS,
            gas_schedule,
            interpreter_context,
            txn_data,
            [
                Value.address(association_addr),
                Value.Uint64(ASSOCIATION_INIT_BALANCE),
            ],
        )

    genesis_auth_key = Address.from_public_key(public_key)
    move_vm.execute_function(
            ACCOUNT_MODULE,
            ROTATE_AUTHENTICATION_KEY,
            gas_schedule,
            interpreter_context,
            txn_data,
            [Value.vector_u8(genesis_auth_key)],
        )

    # Bump the sequence number for the Association account. If we don't do this and a
    # subsequent transaction (e.g., minting) is sent from the Assocation account, a problem
    # arises: both the genesis transaction and the subsequent transaction have sequence
    # number 0
    move_vm.execute_function(
            ACCOUNT_MODULE,
            EPILOGUE,
            gas_schedule,
            interpreter_context,
            txn_data,
            [
                Value.Uint64(0),#/* txn_sequence_number */
                Value.Uint64(0),#/* txn_gas_price */
                Value.Uint64(0),#/* txn_max_gas_units */
                Value.Uint64(0),#/* gas_units_remaining */
            ],
        )


    txn_data.sender = AccountConfig.transaction_fee_address_bytes()
    move_vm.execute_function(
            TRANSACTION_FEE_MODULE,
            INITIALIZE_TXN_FEES,
            gas_schedule,
            interpreter_context,
            txn_data,
            [],
        )


# Create and initialize validator and discovery set.
def create_and_initialize_validator_and_discovery_set(
    move_vm: MoveVM,
    gas_schedule: CostTable,
    interpreter_context: TransactionExecutionContext,
    validator_set: ValidatorSet,
    discovery_set: DiscoverySet,
) -> None:
    create_and_initialize_validator_set(move_vm, gas_schedule, interpreter_context)
    create_and_initialize_discovery_set(move_vm, gas_schedule, interpreter_context)
    initialize_validators(
        move_vm,
        gas_schedule,
        interpreter_context,
        validator_set,
        discovery_set,
    )


# Create and initialize the validator set.
def create_and_initialize_validator_set(
    move_vm: MoveVM,
    gas_schedule: CostTable,
    interpreter_context: TransactionExecutionContext,
) -> None:
    txn_data = TransactionMetadata.default()
    validator_set_address = AccountConfig.validator_set_address_bytes()
    txn_data.sender = validator_set_address

    move_vm.execute_function(
            ACCOUNT_MODULE,
            CREATE_ACCOUNT_NAME,
            gas_schedule,
            interpreter_context,
            txn_data,
            [Value.address(validator_set_address)],
        )


    move_vm.execute_function(
            LIBRA_SYSTEM_MODULE,
            INITIALIZE_VALIDATOR_SET,
            gas_schedule,
            interpreter_context,
            txn_data,
            [],
        )


# Create and initialize the discovery set.
def create_and_initialize_discovery_set(
    move_vm: MoveVM,
    gas_schedule: CostTable,
    interpreter_context: TransactionExecutionContext,
) -> None:
    txn_data = TransactionMetadata.default()
    discovery_set_address = AccountConfig.discovery_set_address_bytes()
    txn_data.sender = discovery_set_address

    move_vm.execute_function(
            ACCOUNT_MODULE,
            CREATE_ACCOUNT_NAME,
            gas_schedule,
            interpreter_context,
            txn_data,
            [Value.address(discovery_set_address)],
        )

    move_vm.execute_function(
            LIBRA_SYSTEM_MODULE,
            INITIALIZE_DISCOVERY_SET,
            gas_schedule,
            interpreter_context,
            txn_data,
            [],
        )

# Initialize each validator.
def initialize_validators(
    move_vm: MoveVM,
    gas_schedule: CostTable,
    interpreter_context: TransactionExecutionContext,
    validator_set: ValidatorSet,
    discovery_set: DiscoverySet,
) -> None:
    txn_data = TransactionMetadata.default()
    txn_data.sender = AccountConfig.association_address_bytes()

    zipped = zip(reversed(validator_set), reversed(discovery_set))
    for (validator_keys, discovery_info) in zipped:
        # First, add a ValidatorConfig resource under each account
        validator_address = validator_keys.account_address
        move_vm.execute_function(
                ACCOUNT_MODULE,
                CREATE_ACCOUNT_NAME,
                gas_schedule,
                interpreter_context,
                txn_data,
                [Value.address(validator_address)],
            )

        validator_txn_data = TransactionMetadata.default()
        validator_txn_data.sender = validator_address
        move_vm.execute_function(
                VALIDATOR_CONFIG_MODULE,
                REGISTER_CANDIDATE_VALIDATOR,
                gas_schedule,
                interpreter_context,
                validator_txn_data,
                [
                    # consensus_pubkey
                    Value.vector_u8(validator_keys.consensus_public_key),

                    # network_signing_pubkey
                    Value.vector_u8(validator_keys.network_signing_public_key),

                    # validator_network_identity_pubkey
                    Value.vector_u8(discovery_info.validator_network_identity_pubkey),

                    # validator_network_address placeholder
                    Value.vector_u8(discovery_info.validator_network_address),

                    # fullnodes_network_identity_pubkey placeholder
                    Value.vector_u8(discovery_info.fullnodes_network_identity_pubkey),

                    # fullnodes_network_address placeholder
                    Value.vector_u8(discovery_info.fullnodes_network_address),
                ],
            )

        # Then, add the account to the validator set
        move_vm.execute_function(
                LIBRA_SYSTEM_MODULE,
                ADD_VALIDATOR,
                gas_schedule,
                interpreter_context,
                txn_data,
                [Value.address(validator_address)],
            )


# Publish the standard library.
def publish_stdlib(interpreter_context: ChainState, stdlib: List[VerifiedModule]) -> None:
    for module in stdlib:
        module_vec = module.as_inner().serialize()
        interpreter_context\
            .publish_module(module.self_id(), module_vec)
            # .unwrap_or_else(|_| panic!("Failure publishing module {}", module.self_id()))



# Trigger a reconfiguration. This emits an event that will be passed along to the storage layer.
def reconfigure(
    move_vm: MoveVM,
    gas_schedule: CostTable,
    interpreter_context: TransactionExecutionContext,
) -> None:
    txn_data = TransactionMetadata.default()

    # TODO: Direct write set transactions cannot specify emitted events, so this currently
    # will not work.
    move_vm.execute_function(
            LIBRA_SYSTEM_MODULE,
            RECONFIGURE,
            gas_schedule,
            interpreter_context,
            txn_data,
            [],
        )


# Verify the consistency of the genesis `WriteSet`
def verify_genesis_write_set(
    events: List[ContractEvent],
    validator_set: ValidatorSet,
    discovery_set: DiscoverySet,
) -> None:
    # Sanity checks on emitted events:
    # (1) The genesis tx should emit 4 events: a pair of payment sent/received events for
    # minting to the genesis address, a ValidatorSetChangeEvent, and a
    # DiscoverySetChangeEvent.
    assert_equal_bail(
        events.__len__(),
        4,
        "Genesis transaction should emit four events, but found {} events: {}",
        events.__len__(),
        events,
    )

    # (2) The third event should be the validator set change event
    validator_set_change_event = events[2]
    assert_equal_bail(
        validator_set_change_event.key,
        ValidatorSet.change_event_key(),
        "Key of emitted event {} does not match change event key {}",
        validator_set_change_event.key,
        ValidatorSet.change_event_key()
    )
    # (3) This should be the first validator set change event
    assert_equal_bail(
        validator_set_change_event.sequence_number,
        0,
        "Expected sequence number 0 for validator set change event but got {}",
        validator_set_change_event.sequence_number
    )
    # (4) It should emit the validator set we fed into the genesis tx
    assert_equal_bail(
        ValidatorSet.deserialize(validator_set_change_event.event_data),
        validator_set,
        "Validator set in emitted event does not match validator set fed into genesis transaction"
    )

    # (5) The fourth event should be the discovery set change event
    discovery_set_change_event = events[3]
    assert_equal_bail(
        discovery_set_change_event.key,
        DiscoverySet.change_event_key(),
        "Key of emitted event {} does not match change event key {}",
        discovery_set_change_event.key,
        DiscoverySet.change_event_key()
    )
    # (6) This should be the first discovery set change event
    assert_equal_bail(
        discovery_set_change_event.sequence_number,
        0,
        "Expected sequence number 0 for discovery set change event but got {}",
        discovery_set_change_event.sequence_number
    )
    # (7) It should emit the discovery set we fed into the genesis tx
    assert_equal_bail(
        DiscoverySet.deserialize(discovery_set_change_event.event_data),
        discovery_set,
        "Discovery set in emitted event does not match discovery set fed into genesis transaction",
    )


# `StateView` has no data given we are creating the genesis
class GenesisStateView(EmptyStateView):
    pass
