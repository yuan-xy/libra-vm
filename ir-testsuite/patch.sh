rpl "check: events" "nocheck: events" ../../libra/language/ir-testsuite/tests/discovery/reconfiguration_via_network_address_rotation.mvir
rpl "events: []" "events=[]" ../../libra/language/ir-testsuite/tests/validator_set/reconfiguration_via_key_rotation.mvir
rpl '// check: "key: EventKey' '// nocheck: "key: EventKey' ../../libra/language/ir-testsuite/tests/transaction_fee_distribution/test_txn_fee_distribution_proper_event_address.mvir
rpl 'Some(10)' 'sub_status=10' ../../libra/language/ir-testsuite/tests/natives/vector/vector_remove.mvir
rpl 'Some(1)' 'sub_status=1' ../../libra/language/ir-testsuite/tests/natives/vector/vector_swap_remove.mvir
rpl 'COPYLOC_RESOURCE_ERROR,' 'COPYLOC_RESOURCE_ERROR' ../../libra/language/ir-testsuite/tests/payments/cant_copy_resource.mvir
rpl -e "// check: MISSING_DEPENDENCY\n// check: MISSING_DEPENDENCY" "// check: MISSING_DEPENDENCY" ../../libra/language/ir-testsuite/tests/natives/non_existant_native_struct.mvir
#rpl -e "// check: MOVELOC_UNAVAILABLE_ERROR\n// check: MOVELOC_UNAVAILABLE_ERROR" "// check: MOVELOC_UNAVAILABLE_ERROR" ../../libra/language/ir-testsuite/tests/commands/while_move_local.mvir
