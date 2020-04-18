rm -rf compiler/ir_stdlib/*
cp -rf ../libra/language/compiler/src/ir_stdlib/* compiler/ir_stdlib/


# cd ../libra/language/compiler/src/ir_stdlib

#  cargo run -p compiler -- -m address_util.mvir
#  cargo run -p compiler -- -m bytearray_util.mvir
#  cargo run -p compiler -- -m gas_schedule.mvir
#  cargo run -p compiler -- -m hash.mvir
#  cargo run -p compiler -- -m libra_account.mvir
#  cargo run -p compiler -- -m libra_coin.mvir
#  cargo run -p compiler -- -m libra_system.mvir
#  cargo run -p compiler -- -m libra_time.mvir
#  cargo run -p compiler -- -m libra_transaction_timeout.mvir
#  cargo run -p compiler -- -m offer.mvir
#  cargo run -p compiler -- -m signature.mvir
#  cargo run -p compiler -- -m u64_util.mvir
#  cargo run -p compiler -- -m validator_config.mvir
#  cargo run -p compiler -- -m vector.mvir


# cargo run -p compiler -- add_validator.mvir
# cargo run -p compiler -- block_prologue.mvir
# cargo run -p compiler -- create_account.mvir
# cargo run -p compiler -- mint.mvir
# cargo run -p compiler -- peer_to_peer_transfer.mvir
# cargo run -p compiler -- peer_to_peer_transfer_with_metadata.mvir
# cargo run -p compiler -- placeholder_script.mvir
# cargo run -p compiler -- register_validator.mvir
# cargo run -p compiler -- remove_validator.mvir
# cargo run -p compiler -- rotate_authentication_key.mvir
# cargo run -p compiler -- rotate_consensus_pubkey.mvir
