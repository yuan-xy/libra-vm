from .command import *


class TransferCommand(Command):
    def get_aliases(self):
        return ["transfer", "transferb", "t", "tb"]

    def get_params_help(self):
        return ("\n\t<sender_account_address>|<sender_account_ref_id>"
                " [gas_unit_price_in_micro_libras (default=0)] [max_gas_amount_in_micro_libras (default 140000)]"
                " Suffix 'b' is for blocking. ")

    def get_description(self):
        return "Transfer coins (in libra) from account to another."

    def execute(self, client, params, **kwargs):
        print("Transaction submitted to validator")
