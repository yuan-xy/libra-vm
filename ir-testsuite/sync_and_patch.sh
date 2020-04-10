rm -rf ./ir-testsuite/tests/*
cp -rf ../libra/language/ir-testsuite/tests/* ./ir-testsuite/tests/

rpl "check: EventKey" "noCheck: EventKey" ./ir-testsuite/tests/block/block_prologue.mvir
rpl "check: events" "noCheck: events" ./ir-testsuite/tests/discovery/reconfiguration_via_network_address_rotation.mvir
rpl "events: []" "events=[]" ./ir-testsuite/tests/validator_set/reconfiguration_via_key_rotation.mvir
rpl '// check: "key: EventKey' '// noCheck: "key: EventKey' ./ir-testsuite/tests/transaction_fee_distribution/test_txn_fee_distribution_proper_event_address.mvir
rpl 'Some(10)' 'sub_status=10' ./ir-testsuite/tests/natives/vector/vector_remove.mvir
rpl 'Some(1)' 'sub_status=1' ./ir-testsuite/tests/natives/vector/vector_swap_remove.mvir
rpl 'COPYLOC_RESOURCE_ERROR,' 'COPYLOC_RESOURCE_ERROR' ./ir-testsuite/tests/payments/cant_copy_resource.mvir
rpl -e "// check: MISSING_DEPENDENCY\n// check: MISSING_DEPENDENCY" "// check: MISSING_DEPENDENCY" ./ir-testsuite/tests/natives/non_existant_native_struct.mvir


