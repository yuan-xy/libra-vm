from libra.account_config import AccountConfig, CORE_CODE_ADDRESS
from libra.identifier import Identifier
from libra.language_storage import ModuleId

# Names of modules and functions used by Libra System.


# Data to resolve basic account and transaction flow functions and structs
# The ModuleId for the Account module
ACCOUNT_MODULE =  ModuleId(
        CORE_CODE_ADDRESS,
        "LibraAccount",
    )

# The ModuleId for the LibraTransactionTimeout module
LIBRA_TRANSACTION_TIMEOUT = ModuleId(
        CORE_CODE_ADDRESS,
        "LibraTransactionTimeout",
    )

# The ModuleId for the LibraCoin module
COIN_MODULE = ModuleId(
        CORE_CODE_ADDRESS,
        "LibraCoin",
    )

# The ModuleId for the Event
EVENT_MODULE = ModuleId(
        CORE_CODE_ADDRESS,
        "Event",
    )

# The ModuleId for the validator config
VALIDATOR_CONFIG_MODULE = ModuleId(
        CORE_CODE_ADDRESS,
        "ValidatorConfig",
    )

# The ModuleId for the libra system module
LIBRA_SYSTEM_MODULE = ModuleId(
        CORE_CODE_ADDRESS,
        "LibraSystem",
    )

# The ModuleId for the gas schedule module
GAS_SCHEDULE_MODULE = ModuleId(
        CORE_CODE_ADDRESS,
        "GasSchedule",
    )

# Names for special functions and structs
CREATE_ACCOUNT_NAME: Identifier = "create_account"
ACCOUNT_STRUCT_NAME: Identifier = "T"
EMIT_EVENT_NAME: Identifier = "write_to_event_store"
SAVE_ACCOUNT_NAME: Identifier = "save_account"
PROLOGUE_NAME: Identifier = "prologue"
EPILOGUE_NAME: Identifier = "epilogue"
BLOCK_PROLOGUE: Identifier = "block_prologue"
