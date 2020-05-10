from .command import *


class QueryCommand(Command):
    def get_aliases(self):
        return ["query", "q"]

    def get_description(self):
        return "Query operations"

    def execute(self, client, params, **kwargs):
        commands = [
            QueryCommandGetBalance(),
        ]
        self.subcommand_execute(
            params[0], commands, client, params[1:], **kwargs)


class QueryCommandGetBalance(Command):
    def get_aliases(self):
        return ["balance", "b"]

    def get_params_help(self):
        return "<account_ref_id>|<account_address>"

    def get_description(self):
        return "Get the current balance of an account"

    def execute(self, client, params, **kwargs):
        try:
            balance = 12345
            print(f"Balance is: {balance}")
        except AccountError:
            print(f"Failed to get balance: No account exists at {params[1]}")
