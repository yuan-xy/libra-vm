from libra.account_config import AccountConfig
from libra.identifier import Identifier
from libra.language_storage import ModuleId

# Names of modules and functions used by Libra System.


# Data to resolve basic account and transaction flow functions and structs
# The ModuleId for the Account module
ACCOUNT_MODULE =  ModuleId(
        AccountConfig.core_code_address_bytes(),
        "LibraAccount",
    )

# The ModuleId for the LibraTransactionTimeout module
LIBRA_TRANSACTION_TIMEOUT = ModuleId(
        AccountConfig.core_code_address_bytes(),
        "LibraTransactionTimeout",
    )

# The ModuleId for the LibraCoin module
COIN_MODULE = ModuleId(
        AccountConfig.core_code_address_bytes(),
        "LibraCoin",
    )

# The ModuleId for the Event
EVENT_MODULE = ModuleId(
        AccountConfig.core_code_address_bytes(),
        "Event",
    )

# The ModuleId for the validator config
VALIDATOR_CONFIG_MODULE = ModuleId(
        AccountConfig.core_code_address_bytes(),
        "ValidatorConfig",
    )

# The ModuleId for the libra system module
LIBRA_SYSTEM_MODULE = ModuleId(
        AccountConfig.core_code_address_bytes(),
        "LibraSystem",
    )

# The ModuleId for the gas schedule module
GAS_SCHEDULE_MODULE = ModuleId(
        AccountConfig.core_code_address_bytes(),
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
