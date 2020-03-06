from __future__ import annotations
from vm_genesis.lib import encode_genesis_transaction_with_validator_and_modules, make_placeholder_discovery_set, GENESIS_KEYPAIR
from bytecode_verifier import VerifiedModule
from libra.transaction import Transaction
from libra.validator_public_keys import ValidatorPublicKeys
# use move_lang_stdlib.move_lang_stdlib_modules
from stdlib import stdlib_modules


CONFIG_LOCATION = "genesis/vm_config.toml"
GENESIS_LOCATION = "genesis/genesis.blob"
MOVELANG_GENESIS_LOCATION = "genesis/movelang_genesis.blob"


def generate_genesis_tx(stdlib_modules: List[VerifiedModule]) -> Transaction:
    # swarm = generator.validator_swarm_for_testing(10)
    # discovery_set = make_placeholder_discovery_set(swarm.validator_set)

    validator_set = [
            ValidatorPublicKeys(
                account_address = bytes.fromhex("5181c01f6005d3236cb950f21a83c22489b9f9d1fadc027cf9532d6f99041522"),
                consensus_public_key = bytes.fromhex("edf3fca3dd1cb6531a172ac978cc8b272dc00df88fa89e63e69fddd34f82777b"),
                consensus_voting_power = 1,
                network_signing_public_key = bytes.fromhex("b9c92427fb556e509a2afe7cf6d102d4556a4c9748ed0c8d75338fa8b5b38fd1"),
                network_identity_public_key = bytes.fromhex("362310b9ce4dc15258ddf5ebe2ddeaad3ab2ca34cb2b3582b94ef61b990d2c61"),
            ),
            ValidatorPublicKeys(
                account_address = bytes.fromhex("5c7bdc35ea7d5e5650f74e06812e3470963d39c834aa39d02bcf85103bd49e1d"),
                consensus_public_key = bytes.fromhex("ee69eb78f516ec586b1b6f50d342baf284bfdebc287a7068d70f9df266e1f8fd"),
                consensus_voting_power = 1,
                network_signing_public_key = bytes.fromhex("f61b321778e78481caa18d27f52af269cd5be7376535aee007dea802a7f33ae5"),
                network_identity_public_key = bytes.fromhex("6d168c904a92d03090c331e27431ceae1e5adbd8ea0699139b498757427c1355"),
            ),
            ValidatorPublicKeys(
                account_address = bytes.fromhex("6689850ab011894daf9ff189e372edce2f5c0957a2c951cd055772e5d8d0b202"),
                consensus_public_key = bytes.fromhex("6333041071db31a16a154df5aa14b4102d1585074dcc8f45fecbb05fbb4a7354"),
                consensus_voting_power = 1,
                network_signing_public_key = bytes.fromhex("ec0dd6852264cf6a3d69552ef73c9ba6af96a0539381823d9997cb9da5fc7b31"),
                network_identity_public_key = bytes.fromhex("3555049e0153079e64a9fdf87d132bab5d85ab3153b80e6010facef8816db51d"),
            ),
            ValidatorPublicKeys(
                account_address = bytes.fromhex("693124105a409f104267a364427f45929b6d2924fb332700c2bc1372f71d1657"),
                consensus_public_key = bytes.fromhex("e4296c6510dd48f3b6767b0e7a6112796ddd12b6d1b6eb166cb3a3d829c27c6b"),
                consensus_voting_power = 1,
                network_signing_public_key = bytes.fromhex("416acb96912aae2ea193943a0ddb929b7f8bd8be3270447913cbd91ae195ac74"),
                network_identity_public_key = bytes.fromhex("24322690e4396d9349c8ee5d81726a8e976b9955619e57526b7eb808f47a827f"),
            ),
            ValidatorPublicKeys(
                account_address = bytes.fromhex("6a76d034e3c89733834cbbe2be9b7e4c3a97274bc887b1d1786450ac8469ea44"),
                consensus_public_key = bytes.fromhex("496ad739e15e727f152d3729cb2c37aa6196be4821321d53b0371d17dcacd50a"),
                consensus_voting_power = 1,
                network_signing_public_key = bytes.fromhex("674423a354b25699ab6700e7b4a6d8f2a5eaf50b87131308e9ed621cc7932fb1"),
                network_identity_public_key = bytes.fromhex("2040e06de241e6f65db31e5c787a58c907cc7776c8db5dda8c5c739c6f0a7c38"),
            ),
            ValidatorPublicKeys(
                account_address = bytes.fromhex("78b108fa9667712c761d70c1e526be8901cad453fcc40c359ce850fd9efb1b50"),
                consensus_public_key = bytes.fromhex("edce4e4f32a6f0a2bd0a0eb9a57d9c0b169ee80011524e4eab6ad26a265530a6"),
                consensus_voting_power = 1,
                network_signing_public_key = bytes.fromhex("b1fec5ac87778a8c8f399a609bcbb129898f43cab16a97f94420e6ef45860d7f"),
                network_identity_public_key = bytes.fromhex("a15d83780bf63ef55208ce0fd9eace023b9918b6b652485b722df90e4a37e57e"),
            ),
            ValidatorPublicKeys(
                account_address = bytes.fromhex("826b443135b47a8bfdf090f0088a427aeae1de70c6cf833823715c07539bcc3a"),
                consensus_public_key = bytes.fromhex("951fcbd7bfe3f8de24fa8f8f4cac7305248e9e643d3d065c1770379b919a32fb"),
                consensus_voting_power = 1,
                network_signing_public_key = bytes.fromhex("70d328bde1450126f985f7d01c8af639eaae657fba357f3ed84ac865beb4bfdb"),
                network_identity_public_key = bytes.fromhex("fb3d12f9bbf3be4b9e2774dec38d7c36832c770e32583e1d46cdfa2849149a18"),
            ),
            ValidatorPublicKeys(
                account_address = bytes.fromhex("95efd320a03cfab116191ccf04c8a8f6f54120cebf0047fc06923a39673ebbb8"),
                consensus_public_key = bytes.fromhex("38f9ff5f7a2ad3b8d39317520a548e3f2010e782402f31b82120e26497ac4dd6"),
                consensus_voting_power = 1,
                network_signing_public_key = bytes.fromhex("bef883bba1c63947fa6143b6c8c9b103a7dc905090e56ed6632b876772716cec"),
                network_identity_public_key = bytes.fromhex("a4ace5ee7da7e56e08194bfa93310d789fba224137175c910eece333b2545a17"),
            ),
            ValidatorPublicKeys(
                account_address = bytes.fromhex("a02afc51b04befbf77c3a33d5bcba016401bad8eef79939fde82f6a29adf3e27"),
                consensus_public_key = bytes.fromhex("9475396426f07702ff58dca2b2ea32202052c9c00178c8de8bad83fd2ca3a40e"),
                consensus_voting_power = 1,
                network_signing_public_key = bytes.fromhex("88c067eb8b779ebdfb5af506aa3b0965402ddcba51b3a93737c84d3cbabd9df1"),
                network_identity_public_key = bytes.fromhex("0f8fd6be0174c5a70ef22c2a65ac59a3e33361c8555b003f84341546b8c3343f"),
            ),
            ValidatorPublicKeys(
                account_address = bytes.fromhex("ac9571d0894723b7e0664a338707972b03978f662c92b6ec005a4d758cbfdd1d"),
                consensus_public_key = bytes.fromhex("d21e08e0eeedf42f6084b5130261275102e23a456d72733eebf1ab329aadc9e1"),
                consensus_voting_power = 1,
                network_signing_public_key = bytes.fromhex("938592e5531ea2374b4ab87dd57ca2013cfc645a05722fc64f0fbedae0554c72"),
                network_identity_public_key = bytes.fromhex("8ac3120524009751497025009a45f577212ad3e9e1e0536053de624319ecd869"),
            ),
        ]
    discovery_set = make_placeholder_discovery_set(validator_set)

    return Transaction('UserTransaction',
        encode_genesis_transaction_with_validator_and_modules(
            GENESIS_KEYPAIR[0],
            GENESIS_KEYPAIR[1],
            validator_set,
            discovery_set,
            stdlib_modules,
        ).into_inner(),
    )


# Generate the genesis blob used by the Libra blockchain
def generate_genesis_blob(stdlib_modules: List[VerifiedModule]) -> bytes:
    return generate_genesis_tx(stdlib_modules).serialize()

def main():
    print(
        "Creating genesis binary blob at {} from configuration file {}",
        GENESIS_LOCATION, CONFIG_LOCATION
    )
    # config = default_config()
    # config.save_config(CONFIG_LOCATION)

    with open(GENESIS_LOCATION, 'wb') as file:
        file.write(generate_genesis_blob(stdlib_modules()))

    # movelang_file = File.create(MOVELANG_GENESIS_LOCATION)
    # movelang_file
    #     .write_all(generate_genesis_blob(move_lang_stdlib_modules()))



# A test that fails if the generated genesis blob is different from the one on disk. Intended
# to catch commits that
# - accidentally change the genesis block
# - change it without remembering to update the on-disk copy
# - cause generation of the genesis block to fail

def diff_tx(old_tx, tx):
    cs = tx.value.payload.value
    old_cs = old_tx.value.payload.value
    for (oe, ee) in zip(old_cs.events, cs.events):
        if oe.event_data != ee.event_data and oe.type_tag.value.name == 'DiscoverySetChangeEvent':
            from libra.discovery_set import DiscoverySet
            oset = DiscoverySet.deserialize(oe.event_data)
            eset = DiscoverySet.deserialize(ee.event_data)
            for idx, (oinfo, einfo) in enumerate(zip(oset, eset)):
                assert oinfo == einfo
            assert oset == eset
        assert oe == ee
    assert len(old_cs.write_set.write_set) == len(cs.write_set.write_set)
    for idx, (ow, ew) in enumerate(zip(old_cs.write_set.write_set, cs.write_set.write_set)):
        if idx == 20:
            from libra import AccountResource
            oar = AccountResource.deserialize(ow[1].value)
            ear = AccountResource.deserialize(ew[1].value)
            assert oar == ear
        if idx == 21:
            from libra_vm.gas_schedule import CostTable
            from vm_genesis.genesis_gas_schedule import init_cost_table
            cost_table = init_cost_table()
            orig_table = CostTable.deserialize(ow[1].value)
            for (g0, g1) in zip(orig_table.instruction_table, cost_table.instruction_table):
                assert g0 == g1
            assert cost_table.instruction_table == orig_table.instruction_table
            assert cost_table.native_table == orig_table.native_table
            assert cost_table.serialize() == ew[1].value
        assert ow[0] == ew[0]
        if ow != ew:
            print(idx)
            print(ow[0])
            breakpoint()
    assert cs.events == old_cs.events
    assert cs == old_cs
    assert old_tx == tx

def test_genesis_blob_unchanged():
    from os.path import join, abspath, dirname
    curdir = dirname(__file__)
    file = join(curdir, GENESIS_LOCATION)
    with open(file, 'rb') as genesis_file:
        old_genesis_bytes = genesis_file.read()
        old_tx = Transaction.deserialize(old_genesis_bytes)
        tx = generate_genesis_tx(stdlib_modules())
        diff_tx(old_tx, tx)
        genesis_bytes = generate_genesis_blob(stdlib_modules())
        assert old_genesis_bytes == genesis_bytes

