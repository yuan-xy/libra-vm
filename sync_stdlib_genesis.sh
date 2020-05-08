rm -rf stdlib/staged/*
cp -rf ../libra/language/stdlib/staged/*  ./mol/stdlib/staged/

rm -rf ./mol/stdlib/modules/*
cp -rf ../libra/language/stdlib/modules/*.move  ./mol/stdlib/modules/

# rm -rf ./mol/stdlib/transaction_scripts/*
# cp -rf ../libra/language/stdlib/transaction_scripts/*.move  ./mol/stdlib/transaction_scripts/


cp ../libra/language/tools/vm-genesis/genesis/genesis.blob ./mol/vm_genesis/genesis/genesis.blob
