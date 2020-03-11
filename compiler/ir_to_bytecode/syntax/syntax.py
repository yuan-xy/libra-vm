from __future__ import annotations
from compiler.ir_to_bytecode.syntax.parse_error import ParseError
from compiler.ir_to_bytecode.syntax.lexer import *
from move_ir.types.codespan import ByteIndex, Span
from libra.account_address import Address
from move_core.types.identifier import IdentStr, Identifier
from move_ir.types.ast import *
from move_ir.types.location import *
from typing import List, Optional, Tuple
from dataclasses import dataclass
from libra.rustlib import bail, ensure, usize

def make_loc(file: str, start: usize, end: usize) -> Loc:
    return Loc(
        file,
        Span(start, end),
    )


def current_token_loc(tokens: Lexer) -> Loc:
    start_loc = tokens.start_loc()
    return make_loc(
        tokens.file_name(),
        start_loc,
        start_loc + tokens.content().__len__(),
    )


def spanned(file: str, start: usize, end: usize, value: Any) -> Spanned:
    return Spanned(
        make_loc(file, start, end),
        value,
    )

def consume_token(
    tokens: Lexer,
    tok: Tok,
) -> None:
    if tokens.peek() != tok:
        raise ParseErrorInvalidToken(current_token_loc(tokens))

    tokens.advance()


def adjust_token(
    tokens: Lexer,
    list_end_tokens: List[Tok],
) -> None:
    if tokens.peek() == Tok.GreaterGreater and Tok.Greater in list_end_tokens:
        tokens.replace_token(Tok.Greater, 1)


def parse_comma_list(
    tokens: Lexer,
    list_end_tokens: List[Tok],
    parse_list_item: Callable[[Lexer], Any],
    allow_trailing_comma: bool,
) -> List[Any]:
    v = []
    adjust_token(tokens, list_end_tokens)
    if tokens.peek() not in list_end_tokens:
        while True:
            v.append(parse_list_item(tokens))
            adjust_token(tokens, list_end_tokens)
            if tokens.peek() in list_end_tokens:
                break

            consume_token(tokens, Tok.Comma)
            adjust_token(tokens, list_end_tokens)
            if tokens.peek() in list_end_tokens and allow_trailing_comma:
                break
    return v


def parse_name(
    tokens: Lexer,
) -> str:
    if tokens.peek() != Tok.NameValue:
        raise ParseErrorInvalidToken(current_token_loc(tokens))
    name = tokens.content()
    tokens.advance()
    return name


def parse_name_begin_ty(
    tokens: Lexer,
) -> str:
    if tokens.peek() != Tok.NameBeginTyValue:
        raise ParseErrorInvalidToken(current_token_loc(tokens))
    s = tokens.content()
    # The token includes a "<" at the end, so chop that off to get the name.
    name = s[:(s.__len__() - 1)]
    tokens.advance()
    return name

def parse_dot_name(
    tokens: Lexer,
) -> str:
    if tokens.peek() != Tok.DotNameValue:
        raise ParseErrorInvalidToken(current_token_loc(tokens))
    name = tokens.content()
    tokens.advance()
    return name

# Address: Address = {
#     < s: r"0[xX][0-9a-fA-F]+" > => { ... }
# }

def parse_account_address(
    tokens: Lexer,
) -> Address:
    if tokens.peek() != Tok.AddressValue:
        raise ParseErrorInvalidToken(current_token_loc(tokens))
    addr = Address.from_hex_literal(tokens.content())
    tokens.advance()
    return addr


# Var: Var = {
#     <n:Name> =>? Var.parse(n),
# }

def parse_var_(tokens: Lexer) -> Var_:
    return Var_.new(parse_name(tokens))


def parse_var(tokens: Lexer) -> Var:
    start_loc = tokens.start_loc()
    var = parse_var_(tokens)
    end_loc = tokens.previous_end_loc()
    return spanned(tokens.file_name(), start_loc, end_loc, var)


# Field: Field = {
#     <n:Name> =>? parse_field(n),
# }

def parse_field(
    tokens: Lexer,
) -> Field:
    start_loc = tokens.start_loc()
    f = Field_.new(parse_name(tokens))
    end_loc = tokens.previous_end_loc()
    return spanned(tokens.file_name(), start_loc, end_loc, f)


# CopyableVal: CopyableVal = {
#     Address => CopyableVal.Address(<>),
#     "True" => CopyableVal.Bool(True),
#     "False" => CopyableVal.Bool(False),
#     <i: U64> => CopyableVal.U64(i),
#     <buf: ByteArray> => CopyableVal.ByteArray(buf),
# }

def parse_copyable_val(
    tokens: Lexer,
) -> CopyableVal:
    start_loc = tokens.start_loc()
    tk = tokens.peek()

    if Tok.AddressValue == tk:
        addr = parse_account_address(tokens)
        val = CopyableVal_.Address(addr)
    elif Tok.TRUE == tk:
        tokens.advance()
        val = CopyableVal_.Bool(True)
    elif Tok.FALSE == tk:
        tokens.advance()
        val = CopyableVal_.Bool(False)

    elif Tok.U8Value == tk:
        s = tokens.content()
        if s.ends_with("u8"):
            s = s[:s.__len__() - 2]
        i = Uint8.from_str(s)
        tokens.advance()
        val = CopyableVal_.U8(i)

    elif Tok.U64Value == tk:
        s = tokens.content()
        if s.ends_with("u64"):
            s = s[:s.__len__() - 3]

        i = Uint64.from_str(s)
        tokens.advance()
        val = CopyableVal_.U64(i)

    elif Tok.U128Value == tk:
        s = tokens.content()
        if s.ends_with("u128"):
            s = s[:s.__len__() - 4]

        i = Uint128.from_str(s)
        tokens.advance()
        val = CopyableVal_.U128(i)

    elif Tok.ByteArrayValue == tk:
        s = tokens.content()
        buf = bytes.fromhex(s[2:(s.__len__() - 1)])
        tokens.advance()
        val = CopyableVal_.ByteArray(buf)

    else:
        raise ParseErrorInvalidToken(current_token_loc(tokens))

    end_loc = tokens.previous_end_loc()
    return spanned(tokens.file_name(), start_loc, end_loc, val)


# Get the precedence of a binary operator. The minimum precedence value
# is 1, and larger values have higher precedence. For tokens that are not
# binary operators, this returns a value of zero so that they will be
# below the minimum value and will mark the end of the binary expression
# for the code in parse_rhs_of_binary_exp.
# Precedences are not sequential to make it easier to add new binops without
# renumbering everything.
def get_precedence(token: Tok) -> Uint32:
    token_map = {
        # Reserved minimum precedence value is 1 (specified in parse_exp_)
        # TODO
        # Tok.EqualEqualGreater may not work right,
        # since parse_spec_exp calls parse_rhs_of_spec_exp
        # with min_prec = 1.  So parse_spec_expr will stop parsing instead of reading ==>
        Tok.EqualEqualGreater : 1,
        Tok.ColonEqual : 3,
        Tok.PipePipe : 5,
        Tok.AmpAmp : 10,
        Tok.EqualEqual : 15,
        Tok.ExclaimEqual : 15,
        Tok.Less : 15,
        Tok.Greater : 15,
        Tok.LessEqual : 15,
        Tok.GreaterEqual : 15,
        Tok.PeriodPeriod : 20,
        Tok.Pipe : 25,
        Tok.Caret : 30,
        Tok.Amp : 35,
        Tok.LessLess : 40,
        Tok.GreaterGreater : 40,
        Tok.Plus : 45,
        Tok.Minus : 45,
        Tok.Star : 50,
        Tok.Slash : 50,
        Tok.Percent : 50,
    }
    if token in token_map:
        return token_map[token]
    else:
        return 0 # anything else is not a binary operator


def parse_exp(tokens: Lexer) -> Exp:
    lhs = parse_unary_exp(tokens)
    return parse_rhs_of_binary_exp(tokens, lhs, 1)


def parse_rhs_of_binary_exp(
    tokens: Lexer,
    lhs: Exp,
    min_prec: Uint32,
) -> Exp:
    result = lhs
    next_tok_prec = get_precedence(tokens.peek())

    # Continue parsing binary expressions as long as they have they
    # specified minimum precedence.
    while next_tok_prec >= min_prec:
        op_token = tokens.peek()
        tokens.advance()

        rhs = parse_unary_exp(tokens)

        # If the next token is another binary operator with a higher
        # precedence, then recursively parse that expression as the RHS.
        this_prec = next_tok_prec
        next_tok_prec = get_precedence(tokens.peek())
        if this_prec < next_tok_prec:
            rhs = parse_rhs_of_binary_exp(tokens, rhs, this_prec + 1)
            next_tok_prec = get_precedence(tokens.peek())

        op_map = {
            Tok.EqualEqual : BinOp.Eq,
            Tok.ExclaimEqual : BinOp.Neq,
            Tok.Less : BinOp.Lt,
            Tok.Greater : BinOp.Gt,
            Tok.LessEqual : BinOp.Le,
            Tok.GreaterEqual : BinOp.Ge,
            Tok.PipePipe : BinOp.Or,
            Tok.AmpAmp : BinOp.And,
            Tok.Caret : BinOp.Xor,
            Tok.LessLess : BinOp.Shl,
            Tok.GreaterGreater : BinOp.Shr,
            Tok.Pipe : BinOp.BitOr,
            Tok.Amp : BinOp.BitAnd,
            Tok.Plus : BinOp.Add,
            Tok.Minus : BinOp.Sub,
            Tok.Star : BinOp.Mul,
            Tok.Slash : BinOp.Div,
            Tok.Percent : BinOp.Mod,
        }
        if op_token in op_map:
            op = op_map[op_token]
        else:
            bail("Unexpected token that is not a binary operator")

        start_loc = result.loc.span().start()
        end_loc = tokens.previous_end_loc()
        e = Exp_.BinopExp(result, op, rhs)
        result = spanned(tokens.file_name(), start_loc, end_loc, e)

    return result


# QualifiedFunctionName : FunctionCall = {
#     <f: Builtin> => FunctionCall.Builtin(f),
#     <module_dot_name: DotName> <type_actuals: TypeActuals> =>? { ... }
# }

def parse_qualified_function_name(
    tokens: Lexer,
) -> FunctionCall:
    start_loc = tokens.start_loc()
    tk = tokens.peek()
    if tk in [
        Tok.Exists,
        Tok.BorrowGlobal,
        Tok.BorrowGlobalMut,
        Tok.GetTxnSender,
        Tok.MoveFrom,
        Tok.MoveToSender,
        Tok.Freeze,
        Tok.ToU8,
        Tok.ToU64,
        Tok.ToU128,
    ]:
        f = parse_builtin(tokens)
        call = FunctionCall_.Builtin(f)

    elif tk == Tok.DotNameValue:
        module_dot_name = parse_dot_name(tokens)
        type_actuals = parse_type_actuals(tokens)
        v: List[str] = module_dot_name.split('.')
        assert (v.__len__() == 2)
        call = FunctionCall_.ModuleFunctionCall(
            ModuleName.new(v[0]),
            FunctionName.new(v[1]),
            type_actuals,
        )

    else:
        raise ParseErrorInvalidToken(current_token_loc(tokens))

    end_loc = tokens.previous_end_loc()
    return spanned(tokens.file_name(), start_loc, end_loc, call)


# UnaryExp : Exp = {
#     "!" <e: Sp<UnaryExp>> => Exp.UnaryExp(UnaryOp.Not, e)),
#     "*" <e: Sp<UnaryExp>> => Exp.Dereference(e)),
#     "&mut " <e: Sp<UnaryExp>> "." <f: Field> => { ... },
#     "&" <e: Sp<UnaryExp>> "." <f: Field> => { ... },
#     CallOrTerm,
# }

def parse_borrow_field_(
    tokens: Lexer,
    mutable: bool,
) -> Exp_:
    # This could be either a field borrow (from UnaryExp) or
    # a borrow of a local variable (from Term). In the latter case,
    # only a simple name token is allowed, and it must not be
    # the start of a pack expression.
    if tokens.peek() == Tok.NameValue:
        if tokens.lookahead() != Tok.LBrace:
            var = parse_var(tokens)
            return Exp_.BorrowLocal(mutable, var)

        start_loc = tokens.start_loc()
        name = parse_name(tokens)
        end_loc = tokens.previous_end_loc()
        type_actuals: List[Type] = []
        e = spanned(
            tokens.file_name(),
            start_loc,
            end_loc,
            parse_pack_(tokens, name, type_actuals),
        )
    else:
        e = parse_unary_exp(tokens)

    consume_token(tokens, Tok.Period)
    f = parse_field(tokens).value
    return Exp_.Borrow(
        is_mutable= mutable,
        exp= e,
        field= f,
    )


def parse_unary_exp_(
    tokens: Lexer,
) -> Exp_:
    tk = tokens.peek()

    if tk == Tok.Exclaim:
        tokens.advance()
        e = parse_unary_exp(tokens)
        return Exp_.UnaryExp(UnaryOp.Not, e)

    elif tk == Tok.Star:
        tokens.advance()
        e = parse_unary_exp(tokens)
        return Exp_.Dereference(e)

    elif tk == Tok.AmpMut:
        tokens.advance()
        return parse_borrow_field_(tokens, True)

    elif tk == Tok.Amp:
        tokens.advance()
        return parse_borrow_field_(tokens, False)
    else:
        return parse_call_or_term_(tokens)



def parse_unary_exp(
    tokens: Lexer,
) -> Exp:
    start_loc = tokens.start_loc()
    e = parse_unary_exp_(tokens)
    end_loc = tokens.previous_end_loc()
    return spanned(tokens.file_name(), start_loc, end_loc, e)


# Call: Exp = {
#     <f: Sp<QualifiedFunctionName>> <exp: Sp<CallOrTerm>> => Exp.FunctionCall(f, exp)),
# }

def parse_call(tokens: Lexer) -> Exp:
    start_loc = tokens.start_loc()
    f = parse_qualified_function_name(tokens)
    exp = parse_call_or_term(tokens)
    end_loc = tokens.previous_end_loc()
    return spanned(
        tokens.file_name(),
        start_loc,
        end_loc,
        Exp_.FunctionCall(f, exp),
    )


# CallOrTerm: Exp = {
#     <f: Sp<QualifiedFunctionName>> <exp: Sp<CallOrTerm>> => Exp.FunctionCall(f, exp)),
#     Term,
# }

def parse_call_or_term_(
    tokens: Lexer,
) -> Exp_:
    if tokens.peek() in [
        Tok.Exists,
        Tok.BorrowGlobal,
        Tok.BorrowGlobalMut,
        Tok.GetTxnSender,
        Tok.MoveFrom,
        Tok.MoveToSender,
        Tok.Freeze,
        Tok.DotNameValue,
        Tok.ToU8,
        Tok.ToU64,
        Tok.ToU128,
    ]:
        f = parse_qualified_function_name(tokens)
        exp = parse_call_or_term(tokens)
        return Exp_.FunctionCall(f, exp)
    else:
        return parse_term_(tokens),


def parse_call_or_term(
    tokens: Lexer,
) -> Exp:
    start_loc = tokens.start_loc()
    v = parse_call_or_term_(tokens)
    end_loc = tokens.previous_end_loc()
    return spanned(tokens.file_name(), start_loc, end_loc, v)


# FieldExp: (Field_, Exp_) = {
#     <f: Sp<Field>> ":" <e: Sp<Exp>> => (f, e)
# }

def parse_field_exp(
    tokens: Lexer,
) -> (Field, Exp):
    f = parse_field(tokens)
    consume_token(tokens, Tok.Colon)
    e = parse_exp(tokens)
    return (f, e)


# Term: Exp = {
#     "move(" <v: Sp<Var>> ")" => Exp.Move(v),
#     "copy(" <v: Sp<Var>> ")" => Exp.Copy(v),
#     "&mut " <v: Sp<Var>> => Exp.BorrowLocal(True, v),
#     "&" <v: Sp<Var>> => Exp.BorrowLocal(False, v),
#     Sp<CopyableVal> => Exp.Value(<>),
#     <name_and_type_actuals: NameAndTypeActuals> "{" <fs:Comma<FieldExp>> "}" =>? { ... },
#     "(" <exps: Comma<Sp<Exp>>> ")" => Exp.ExprList(exps),
# }

def parse_pack_(
    tokens: Lexer,
    name: str,
    type_actuals: List[Type],
) -> Exp_:
    consume_token(tokens, Tok.LBrace)
    fs = parse_comma_list(tokens, [Tok.RBrace], parse_field_exp, True)
    consume_token(tokens, Tok.RBrace)
    return Exp_.Pack(
        StructName.new(name),
        type_actuals,
        fs,
    )


def parse_term_(tokens: Lexer) -> Exp_:
    tk = tokens.peek()

    if tk == Tok.Move:
        tokens.advance()
        v = parse_var(tokens)
        consume_token(tokens, Tok.RParen)
        return Exp_.Move(v)

    elif tk == Tok.Copy:
        tokens.advance()
        v = parse_var(tokens)
        consume_token(tokens, Tok.RParen)
        return Exp_.Copy(v)

    elif tk == Tok.AmpMut:
        tokens.advance()
        v = parse_var(tokens)
        return Exp_.BorrowLocal(True, v)

    elif tk == Tok.Amp:
        tokens.advance()
        v = parse_var(tokens)
        return Exp_.BorrowLocal(False, v)

    elif tk in [
        Tok.AddressValue,
        Tok.TRUE,
        Tok.FALSE,
        Tok.U8Value,
        Tok.U64Value,
        Tok.U128Value,
        Tok.ByteArrayValue,
    ]:
        return Exp_.Value(parse_copyable_val(tokens))

    elif tk == Tok.NameValue or tk == Tok.NameBeginTyValue:
        (name, type_actuals) = parse_name_and_type_actuals(tokens)
        return parse_pack_(tokens, name, type_actuals)

    elif tk == Tok.LParen:
        tokens.advance()
        exps = parse_comma_list(tokens, [Tok.RParen], parse_exp, True)
        consume_token(tokens, Tok.RParen)
        return Exp_.ExprList(exps)
    else:
        raise ParseErrorInvalidToken(current_token_loc(tokens))


# StructName: StructName = {
#     <n: Name> =>? StructName.parse(n),
# }

def parse_struct_name(
    tokens: Lexer,
) -> StructName:
    return StructName.new(parse_name(tokens))


# QualifiedStructIdent : QualifiedStructIdent = {
#     <module_dot_struct: DotName> =>? { ... }
# }

def parse_qualified_struct_ident(
    tokens: Lexer,
) -> QualifiedStructIdent:
    module_dot_struct = parse_dot_name(tokens)
    v: List[str] = module_dot_struct.split('.')
    assert(v.__len__() == 2)
    m: ModuleName = ModuleName.new(v[0])
    n: StructName = StructName.new(v[1])
    return QualifiedStructIdent.new(m, n)


# ModuleName: ModuleName = {
#     <n: Name> =>? ModuleName.parse(n),
# }

def parse_module_name(
    tokens: Lexer,
) -> ModuleName:
    return ModuleName.new(parse_name(token))


def consume_end_of_generics(
    tokens: Lexer,
) -> None:
    tk = tokens.peek()
    if tk == Tok.Greater:
        tokens.advance()
    elif tk == Tok.GreaterGreater:
        tokens.replace_token(Tok.Greater, 1)
        tokens.advance()
    else:
        raise ParseErrorInvalidToken(current_token_loc(tokens))


# Builtin: Builtin = {
#     "exists<" <name_and_type_actuals: NameAndTypeActuals> ">" =>? { ... },
#     "borrow_global<" <name_and_type_actuals: NameAndTypeActuals> ">" =>? { ... },
#     "borrow_global_mut<" <name_and_type_actuals: NameAndTypeActuals> ">" =>? { ... },
#     "get_txn_sender" => Builtin.GetTxnSender,
#     "move_from<" <name_and_type_actuals: NameAndTypeActuals> ">" =>? { ... },
#     "move_to_sender<" <name_and_type_actuals: NameAndTypeActuals> ">" =>? { ...},
#     "freeze" => Builtin.Freeze,
# }

def parse_builtin(
    tokens: Lexer,
) -> Builtin:
    tk = tokens.peek()

    if tk == Tok.Exists:
        tokens.advance()
        (name, type_actuals) = parse_name_and_type_actuals(tokens)
        consume_end_of_generics(tokens)
        return Builtin(BuiltinTag.Exists, exists=(StructName.new(name), type_actuals))

    elif tk == Tok.BorrowGlobal:
        tokens.advance()
        (name, type_actuals) = parse_name_and_type_actuals(tokens)
        consume_end_of_generics(tokens)
        return Builtin(BuiltinTag.BorrowGlobal, borrow=(
            False,
            StructName.new(name),
            type_actuals,
        ))

    elif tk == Tok.BorrowGlobalMut:
        tokens.advance()
        (name, type_actuals) = parse_name_and_type_actuals(tokens)
        consume_end_of_generics(tokens)
        return Builtin(BuiltinTag.BorrowGlobal, borrow=(
            True,
            StructName.new(name),
            type_actuals,
        ))

    elif tk == Tok.GetTxnSender:
        tokens.advance()
        return Builtin(BuiltinTag.GetTxnSender)

    elif tk == Tok.MoveFrom:
        tokens.advance()
        (name, type_actuals) = parse_name_and_type_actuals(tokens)
        consume_end_of_generics(tokens)
        return Builtin(BuiltinTag.MoveFrom, move=(StructName.new(name), type_actuals))

    elif tk == Tok.MoveToSender:
        tokens.advance()
        (name, type_actuals) = parse_name_and_type_actuals(tokens)
        consume_end_of_generics(tokens)
        return Builtin(BuiltinTag.MoveToSender, move=(StructName.new(name), type_actuals))

    elif tk == Tok.Freeze:
        tokens.advance()
        return Builtin(BuiltinTag.Freeze)

    elif tk == Tok.ToU8:
        tokens.advance()
        return Builtin(BuiltinTag.ToU8)

    elif tk == Tok.ToU64:
        tokens.advance()
        return Builtin(BuiltinTag.ToU64)

    elif tk == Tok.ToU128:
        tokens.advance()
        return Builtin(BuiltinTag.ToU128)
    else:
        ParseErrorInvalidToken(current_token_loc(tokens))


# LValue: LValue = {
#     <l:Sp<Var>> => LValue.Var(l),
#     "*" <e: Sp<Exp>> => LValue.Mutate(e),
#     "_" => LValue.Pop,
# }

def parse_lvalue_(
    tokens: Lexer,
) -> LValue_:
    tk = tokens.peek()

    if tk == Tok.NameValue:
        l = parse_var(tokens)
        return LValue_.Var(l)

    elif tk == Tok.Star:
        tokens.advance()
        e = parse_exp(tokens)
        return LValue_.Mutate(e)

    elif tk == Tok.Underscore:
        tokens.advance()
        return LValue_.Pop

    else:
        raise ParseErrorInvalidToken(current_token_loc(tokens))



def parse_lvalue(
    tokens: Lexer,
) -> LValue:
    start_loc = tokens.start_loc()
    lv = parse_lvalue_(tokens)
    end_loc = tokens.previous_end_loc()
    return spanned(tokens.file_name(), start_loc, end_loc, lv)


# FieldBindings: (Field_, Var_) = {
#     <f: Sp<Field>> ":" <v: Sp<Var>> => (f, v),
#     <f: Sp<Field>> => { ... }
# }

def parse_field_bindings(
    tokens: Lexer,
) -> Tuple[Field, Var]:
    f = parse_field(tokens)
    if tokens.peek() == Tok.Colon:
        tokens.advance() # consume the colon
        v = parse_var(tokens)
        return (f, v)
    else:
        return (
            deepcopy(f),
            Spanned(
                loc= f.loc,
                value= Var_.new(f.value.into_inner()),
            ),
        )

# pub Cmd : Cmd = {
#     <lvalues: Comma<Sp<LValue>>> "=" <e: Sp<Exp>> => Cmd.Assign(lvalues, e),
#     <name_and_type_actuals: NameAndTypeActuals> "{" <bindings: Comma<FieldBindings>> "}" "=" <e: Sp<Exp>> =>? { ... },
#     "abort" <err: Sp<Exp>?> => { ... },
#     "return" <v: Comma<Sp<Exp>>> => Cmd.Return(Spanned.unsafe_no_loc(Exp.ExprList(v)))),
#     "continue" => Cmd.Continue,
#     "break" => Cmd.Break,
#     <Sp<Call>> => Cmd.Exp(<>)),
#     "(" <Comma<Sp<Exp>>> ")" => Cmd.Exp(Spanned.unsafe_no_loc(Exp.ExprList(<>)))),
# }

def parse_assign_(
    tokens: Lexer,
) -> Cmd_:
    lvalues = parse_comma_list(tokens, [Tok.Equal], parse_lvalue, False)
    if not lvalues:
        raise ParseErrorInvalidToken(current_token_loc(tokens))
    consume_token(tokens, Tok.Equal)
    e = parse_exp(tokens)
    return Cmd_.Assign(lvalues, e)


def parse_unpack_(
    tokens: Lexer,
    name: str,
    type_actuals: List[Type],
) -> Cmd_:
    consume_token(tokens, Tok.LBrace)
    bindings = parse_comma_list(tokens, [Tok.RBrace], parse_field_bindings, True)
    consume_token(tokens, Tok.RBrace)
    consume_token(tokens, Tok.Equal)
    e = parse_exp(tokens)
    return Cmd_.Unpack(
        StructName.new(name),
        type_actuals,
        bindings,
        e,
    )


def parse_cmd_(tokens: Lexer) -> Cmd_:
    tk = tokens.peek()

    if tk == Tok.NameValue:
        # This could be either an LValue for an assignment or
        # NameAndTypeActuals (with no type_actuals) for an unpack.
        if tokens.lookahead() == Tok.LBrace:
            name = parse_name(tokens)
            return parse_unpack_(tokens, name, [])
        else:
            return parse_assign_(tokens)

    elif tk == Tok.Star or tk == Tok.Underscore:
        return parse_assign_(tokens)

    elif tk == Tok.NameBeginTyValue:
        (name, tys) = parse_name_and_type_actuals(tokens)
        return parse_unpack_(tokens, name, tys)

    elif tk == Tok.Abort:
        tokens.advance()
        if tokens.peek() == Tok.Semicolon:
            val = None
        else:
            val = parse_exp(tokens)

        return Cmd_.Abort(val)

    elif tk == Tok.Return:
        tokens.advance()
        start = tokens.start_loc()
        v = parse_comma_list(tokens, [Tok.Semicolon], parse_exp, True)
        end = tokens.start_loc()
        return Cmd_.Return(spanned(
            tokens.file_name(),
            start,
            end,
            Exp_.ExprList(v),
        ))

    elif tk == Tok.Continue:
        tokens.advance()
        return Cmd_.Continue

    elif tk == Tok.Break:
        tokens.advance()
        return Cmd_.Break

    elif tk in [
        Tok.Exists,
        Tok.BorrowGlobal,
        Tok.BorrowGlobalMut,
        Tok.GetTxnSender,
        Tok.MoveFrom,
        Tok.MoveToSender,
        Tok.Freeze,
        Tok.DotNameValue,
        Tok.ToU8,
        Tok.ToU64,
        Tok.ToU128,
    ]:
        return Cmd_.Exp(parse_call(token))

    elif tk == Tok.LParen:
        tokens.advance()
        start = tokens.start_loc()
        v = parse_comma_list(tokens, [Tok.RParen], parse_exp, True)
        consume_token(tokens, Tok.RParen)
        end = tokens.start_loc()
        return Cmd_.Exp(spanned(
            tokens.file_name(),
            start,
            end,
            Exp_.ExprList(v),
        ))
    else:
        raise ParseErrorInvalidToken(current_token_loc(tokens))


# Statement : Statement = {
#     <cmd: Cmd_> ";" => Statement.CommandStatement(cmd),
#     "assert(" <e: Sp<Exp>> "," <err: Sp<Exp>> ")" => { ... },
#     <IfStatement>,
#     <WhileStatement>,
#     <LoopStatement>,
#     ";" => Statement.EmptyStatement,
# }

def parse_statement(
    tokens: Lexer,
) -> Statement:
    tk = tokens.peek()

    if tk == Tok.Assert:
        tokens.advance()
        e = parse_exp(tokens)
        consume_token(tokens, Tok.Comma)
        err = parse_exp(tokens)
        consume_token(tokens, Tok.RParen)
        cond = sp(e.loc, Exp_.UnaryExp(UnaryOp.Not, e))
        loc = err.loc
        stmt = Statement.CommandStatement(sp(loc, Cmd_.Abort(err)))
        return Statement.IfElseStatement(IfElse.if_block(
            cond,
            sp(loc, Block_.new([stmt])),
        ))

    elif tk == Tok.If:
        return parse_if_statement(tokens),
    elif tk == Tok.While:
        return parse_while_statement(tokens),
    elif tk == Tok.Loop:
        return parse_loop_statement(tokens),
    elif tk == Tok.Semicolon:
        tokens.advance()
        return Statement.EmptyStatement
    else:
        # Anything else should be parsed as a Cmd...
        start_loc = tokens.start_loc()
        c = parse_cmd_(tokens)
        end_loc = tokens.previous_end_loc()
        cmd = spanned(tokens.file_name(), start_loc, end_loc, c)
        consume_token(tokens, Tok.Semicolon)
        return Statement.CommandStatement(cmd)


# IfStatement : Statement = {
#     "if" "(" <cond: Sp<Exp>> ")" <block: Sp<Block>> => { ... }
#     "if" "(" <cond: Sp<Exp>> ")" <if_block: Sp<Block>> "else" <else_block: Sp<Block>> => { ... }
# }

def parse_if_statement(
    tokens: Lexer,
) -> Statement:
    consume_token(tokens, Tok.If)
    consume_token(tokens, Tok.LParen)
    cond = parse_exp(tokens)
    consume_token(tokens, Tok.RParen)
    if_block = parse_block(tokens)
    if tokens.peek() == Tok.Else:
        tokens.advance()
        else_block = parse_block(tokens)
        return Statement.IfElseStatement(IfElse.if_else(
            cond, if_block, else_block,
        ))
    else:
        return Statement.IfElseStatement(IfElse.if_block(cond, if_block))



# WhileStatement : Statement = {
#     "while" "(" <cond: Sp<Exp>> ")" <block: Sp<Block>> => { ... }
# }

def parse_while_statement(
    tokens: Lexer,
) -> Statement:
    consume_token(tokens, Tok.While)
    consume_token(tokens, Tok.LParen)
    cond = parse_exp(tokens)
    consume_token(tokens, Tok.RParen)
    block = parse_block(tokens)
    return Statement.WhileStatement(While(cond, block ))


# LoopStatement : Statement = {
#     "loop" <block: Sp<Block>> => { ... }
# }

def parse_loop_statement(
    tokens: Lexer,
) -> Statement:
    consume_token(tokens, Tok.Loop)
    block = parse_block(tokens)
    return Statement.LoopStatement(Loop(block ))


# Statements : List[Statement] = {
#     <Statement*>
# }

def parse_statements(
    tokens: Lexer,
) -> List[Statement]:
    stmts: List[Statement] = []
    # The Statements non-terminal in the grammar is always followed by a
    # closing brace, so continue parsing until we find one of those.
    while tokens.peek() != Tok.RBrace:
        stmts.append(parse_statement(tokens))

    return stmts


# Block : Block = {
#     "{" <stmts: Statements> "}" => Block.new(stmts)
# }

def parse_block(
    tokens: Lexer,
) -> Block:
    start_loc = tokens.start_loc()
    consume_token(tokens, Tok.LBrace)
    stmts = parse_statements(tokens)
    consume_token(tokens, Tok.RBrace)
    end_loc = tokens.previous_end_loc()
    return spanned(
        tokens.file_name(),
        start_loc,
        end_loc,
        Block_.new(stmts),
    )


# Declaration: (Var_, Type) = {
#   "let" <v: Sp<Var>> ":" <t: Type> ";" => (v, t),
# }

def parse_declaration(
    tokens: Lexer,
) -> Tuple[Var, Type]:
    consume_token(tokens, Tok.Let)
    v = parse_var(tokens)
    consume_token(tokens, Tok.Colon)
    t = parse_type(tokens)
    consume_token(tokens, Tok.Semicolon)
    return (v, t)


# Declarations: List[(Var_, Type)] = {
#     <Declaration*>
# }

def parse_declarations(
    tokens: Lexer,
) -> List[Tuple[Var, Type]]:
    decls= []
    # Declarations always begin with the "let" token so continue parsing
    # them until we hit something else.
    while tokens.peek() == Tok.Let:
        decls.append(parse_declaration(tokens))

    return decls


# FunctionBlock: (List[(Var_, Type)], Block) = {
#     "{" <locals: Declarations> <stmts: Statements> "}" => (locals, Block.new(stmts))
# }

def parse_function_block_(
    tokens: Lexer,
) -> Tuple[List[Tuple[Var, Type]], Block_]:
    consume_token(tokens, Tok.LBrace)
    localss = parse_declarations(tokens)
    stmts = parse_statements(tokens)
    consume_token(tokens, Tok.RBrace)
    (localss, Block_.new(stmts))


# Kind: Kind = {
#     "resource" => Kind.Resource,
#     "unrestricted" => Kind.Unrestricted,
# }

def parse_kind(tokens: Lexer) -> Kind:
    tk = tokens.peek()
    if tk == Tok.Resource:
        k = Kind.Resource
    elif tk == Tok.Unrestricted:
        k = Kind.Unrestricted
    else:
        raise ParseErrorInvalidToken(current_token_loc(tokens))

    tokens.advance()
    return k


# Type: Type = {
#     "address" => Type.Address,
#     "Uint64" => Type.U64,
#     "bool" => Type.Bool,
#     "bytearray" => Type.ByteArray,
#     <s: QualifiedStructIdent> <tys: TypeActuals> => Type.Struct(s, tys),
#     "&" <t: Type> => Type.Reference(False, t)),
#     "&mut " <t: Type> => Type.Reference(True, t)),
#     <n: Name> =>? Type.TypeParameter(TypeVar.parse(n?)),
# }

def parse_type(tokens: Lexer) -> Type:
    tk = tokens.peek()

    if tk == Tok.Address:
        tokens.advance()
        return Type.Address

    elif tk == Tok.U8:
        tokens.advance()
        return Type.U8

    elif tk == Tok.U64:
        tokens.advance()
        return Type.U64

    elif tk == Tok.U128:
        tokens.advance()
        return Type.U128

    elif tk == Tok.Bool:
        tokens.advance()
        return Type.Bool

    elif tk == Tok.Bytearray:
        tokens.advance()
        return Type.ByteArray

    elif tk == Tok.Vector:
        tokens.advance()
        consume_token(tokens, Tok.Less)
        ty = parse_type(tokens)
        adjust_token(tokens, [Tok.Greater])
        consume_token(tokens, Tok.Greater)
        return Type.Vector(ty)

    elif tk == Tok.DotNameValue:
        s = parse_qualified_struct_ident(tokens)
        tys = parse_type_actuals(tokens)
        return Type.Struct(s, tys)

    elif tk == Tok.Amp:
        tokens.advance()
        return Type.Reference(False, parse_type(tokens))

    elif tk == Tok.AmpMut:
        tokens.advance()
        return Type.Reference(True, parse_type(tokens))

    elif tk == Tok.NameValue:
        return Type.TypeParameter(TypeVar_.new(parse_name(tokens)))
    else:
        raise ParseErrorInvalidToken(current_token_loc(tokens))




# TypeVar: TypeVar = {
#     <n: Name> =>? TypeVar.parse(n),
# }
# TypeVar_ = Sp<TypeVar>

def parse_type_var(
    tokens: Lexer,
) -> TypeVar:
    start_loc = tokens.start_loc()
    type_var = TypeVar_.new(parse_name(tokens))
    end_loc = tokens.previous_end_loc()
    return spanned(tokens.file_name(), start_loc, end_loc, type_var)


# TypeFormal: (TypeVar_, Kind) = {
#     <type_var: Sp<TypeVar>> <k: (":" <Kind>)?> =>? {
# }

def parse_type_formal(
    tokens: Lexer,
) -> Tuple[TypeVar, Kind]:
    type_var = parse_type_var(tokens)
    if tokens.peek() == Tok.Colon:
        tokens.advance() # consume the ":"
        k = parse_kind(tokens)
        return (type_var, k)
    else:
        return (type_var, Kind.All)


# TypeActuals: List[Type] = {
#     <tys: ("<" <Comma<Type>> ">")?> => { ... }
# }

def parse_type_actuals(
    tokens: Lexer,
) -> List[Type]:
    if tokens.peek() == Tok.Less:
        tokens.advance() # consume the "<"
        list = parse_comma_list(tokens, [Tok.Greater], parse_type, True)
        consume_token(tokens, Tok.Greater)
        return list
    else:
        return []

# NameAndTypeFormals: (String, List[(TypeVar_, Kind)]) = {
#     <n: NameBeginTy> <k: Comma<TypeFormal>> ">" => (n, k),
#     <n: Name> => (n, []),
# }

def parse_name_and_type_formals(
    tokens: Lexer,
) -> Tuple[str, List[Tuple[TypeVar, Kind]]]:
    has_types = False

    if tokens.peek() == Tok.NameBeginTyValue:
        has_types = True
        n = parse_name_begin_ty(tokens)
    else:
        n = parse_name(tokens)

    if has_types:
        list = parse_comma_list(tokens, [Tok.Greater], parse_type_formal, True)
        consume_token(tokens, Tok.Greater)
        k = list
    else:
        k = []

    return (n, k)


# NameAndTypeActuals: (String, List[Type]) = {
#     <n: NameBeginTy> <tys: Comma<Type>> ">" => (n, tys),
#     <n: Name> => (n, []),
# }

def parse_name_and_type_actuals(
    tokens: Lexer,
) -> Tuple[str, List[Type]]:
    has_types = False

    if tokens.peek() == Tok.NameBeginTyValue:
        has_types = True
        n = parse_name_begin_ty(tokens)
    else:
        n = parse_name(tokens)

    if has_types:
        list = parse_comma_list(tokens, [Tok.Greater], parse_type, True)
        consume_token(tokens, Tok.Greater)
        tys = list
    else:
        tys = []

    return (n, tys)


# ArgDecl : (Var_, Type) = {
#     <v: Sp<Var>> ":" <t: Type> => (v, t)
# }

def parse_arg_decl(
    tokens: Lexer,
) -> Tuple[Var, Type]:
    v = parse_var(tokens)
    consume_token(tokens, Tok.Colon)
    t = parse_type(tokens)
    return (v, t)


# ReturnType: List[Type] = {
#     ":" <t: Type> <v: ("*" <Type>)*> => { ... }
# }

def parse_return_type(
    tokens: Lexer,
) -> List[Type]:
    consume_token(tokens, Tok.Colon)
    t = parse_type(tokens)
    v = [t]
    while tokens.peek() == Tok.Star: #TTODO: maybe Security vulnerabilities?
        tokens.advance()
        v.append(parse_type(tokens))

    return v


# AcquireList: List[StructName] = {
#     "acquires" <s: StructName> <al: ("," <StructName>)*> => { ... }
# }

def parse_acquire_list(
    tokens: Lexer,
) -> List[StructName]:
    consume_token(tokens, Tok.Acquires)
    s = parse_struct_name(tokens)
    al = [s]
    while tokens.peek() == Tok.Comma:
        tokens.advance()
        al.append(parse_struct_name(tokens))

    return al


#/ Spec language parsing #/

# parses Name '.' Name and returns pair of strings.
def spec_parse_dot_name(
    tokens: Lexer,
) -> Tuple[str, str]:
    name1 = parse_name(tokens)
    consume_token(tokens, Tok.Period)
    name2 = parse_name(tokens)
    return (name1, name2)


def spec_parse_qualified_struct_ident(
    tokens: Lexer,
) -> QualifiedStructIdent:
    (m_string, n_string) = spec_parse_dot_name(tokens)
    m: ModuleName = ModuleName.new(m_string)
    n: StructName = StructName.new(n_string)
    return QualifiedStructIdent.new(m, n)


def parse_storage_location(
    tokens: Lexer,
) -> StorageLocation:
    tk = tokens.peek()

    if tk == Tok.SpecReturn:
        # RET(i)
        tokens.advance()
        if tokens.peek() == Tok.LParen:
            consume_token(tokens, Tok.LParen)
            i = Uint8.from_str(tokens.content())
            consume_token(tokens, Tok.U64Value)
            consume_token(tokens, Tok.RParen)
        else:
            # RET without brackets; use RET(0)
            i = 0

        base = StorageLocation.Ret(i)

    elif tk == Tok.TxnSender:
        tokens.advance()
        base = StorageLocation.TxnSenderAddress

    elif tk == Tok.AddressValue:
        base = StorageLocation.Address(parse_account_address(tokens))

    elif tk == Tok.Global:
        consume_token(tokens, Tok.Global)
        consume_token(tokens, Tok.Less)
        type_ = spec_parse_qualified_struct_ident(tokens)
        type_actuals = parse_type_actuals(tokens)
        consume_token(tokens, Tok.Greater)
        consume_token(tokens, Tok.LParen)
        address = parse_storage_location(tokens)
        consume_token(tokens, Tok.RParen)
        base = StorageLocation.GlobalResource(
            type_,
            type_actuals,
            address,
        )
    else:
        base = StorageLocation.Formal(parse_name(tokens)),


    # parsed the storage location base. now parse its fields and indices (if any)
    fields_and_indices = []
    while True:
        tok = tokens.peek()
        if tok == Tok.Period:
            tokens.advance()
            fields_and_indices.append(FieldOrIndex.Field(parse_field(tokens).value))
        elif tok == Tok.LSquare:
            tokens.advance()
            # Index expr can be ordinary expr, subrange, or update.
            index_exp = parse_spec_exp(tokens)
            fields_and_indices.append(FieldOrIndex.Index(index_exp))
            consume_token(tokens, Tok.RSquare)
        else:
            break

    if not fields_and_indices:
        return base
    else:
        return StorageLocation.AccessPath(
            base,
            fields_and_indices,
        )


def parse_unary_spec_exp(
    tokens: Lexer,
) -> SpecExp:
    tk = tokens.peek()
    if tk in [
        Tok.AddressValue,
        Tok.TRUE,
        Tok.FALSE,
        Tok.U8Value,
        Tok.U64Value,
        Tok.U128Value,
        Tok.ByteArrayValue,
    ]:
        return SpecExp.Constant(parse_copyable_val(tokens).value)

    elif tk == Tok.GlobalExists:
        consume_token(tokens, Tok.GlobalExists)
        consume_token(tokens, Tok.Less)
        type_ = spec_parse_qualified_struct_ident(tokens)
        type_actuals = parse_type_actuals(tokens)
        consume_token(tokens, Tok.Greater)
        consume_token(tokens, Tok.LParen)
        address = parse_storage_location(tokens)
        consume_token(tokens, Tok.RParen)
        return SpecExp.GlobalExists(
            type_,
            type_actuals,
            address,
        )

    elif tk == Tok.Star:
        tokens.advance()
        stloc = parse_storage_location(tokens)
        return SpecExp.Dereference(stloc)

    elif tk == Tok.Amp:
        tokens.advance()
        stloc = parse_storage_location(tokens)
        return SpecExp.Reference(stloc)

    elif tk == Tok.Exclaim:
        tokens.advance()
        exp = parse_unary_spec_exp(tokens)
        return SpecExp.Not(exp)

    elif tk == Tok.Old:
        tokens.advance()
        consume_token(tokens, Tok.LParen)
        exp = parse_spec_exp(tokens)
        consume_token(tokens, Tok.RParen)
        return SpecExp.Old(exp)

    elif tk == Tok.NameValue:
        try:
            nextt = tokens.lookahead()
        except Exception as err:
            nextt = None
        if nextt is None or nextt != Tok.LParen:
            return SpecExp.StorageLocation(parse_storage_location(tokens))
        else:
            name = parse_name(tokens)
            args = []
            consume_token(tokens, Tok.LParen)
            while tokens.peek() != Tok.RParen:
                exp = parse_spec_exp(tokens)
                args.append(exp)
                if tokens.peek() != Tok.Comma:
                    break

                consume_token(tokens, Tok.Comma)

            consume_token(tokens, Tok.RParen)
            return SpecExp.Call(name, args)
    else:
        return SpecExp.StorageLocation(parse_storage_location(tokens))


def parse_rhs_of_spec_exp(
    tokens: Lexer,
    lhs: SpecExp,
    min_prec: Uint32,
) -> SpecExp:
    result = lhs
    next_tok_prec = get_precedence(tokens.peek())

    # Continue parsing binary expressions as long as they have they
    # specified minimum precedence.
    while next_tok_prec >= min_prec:
        op_token = tokens.peek()
        tokens.advance()

        rhs = parse_unary_spec_exp(tokens)

        # If the next token is another binary operator with a higher
        # precedence, then recursively parse that expression as the RHS.
        this_prec = next_tok_prec
        next_tok_prec = get_precedence(tokens.peek())
        if this_prec < next_tok_prec:
            rhs = parse_rhs_of_spec_exp(tokens, rhs, this_prec + 1)
            next_tok_prec = get_precedence(tokens.peek())

        # TODO: Should we treat ==> like a normal BinOp
        # TODO: Implement IFF
        if op_token == Tok.EqualEqualGreater:
            # Syntactic sugar: p ==> c ~~~> !p || c
            result = SpecExp.Binop(
                SpecExp.Not(result),
                BinOp.Or,
                rhs,
            )
        elif op_token == Tok.ColonEqual:
            # it's an update expr
            result = SpecExp.Update(result, rhs)
        else:
            op_map = {
                Tok.EqualEqual: BinOp.Eq,
                Tok.ExclaimEqual: BinOp.Neq,
                Tok.Less: BinOp.Lt,
                Tok.Greater: BinOp.Gt,
                Tok.LessEqual: BinOp.Le,
                Tok.GreaterEqual: BinOp.Ge,
                Tok.PipePipe: BinOp.Or,
                Tok.AmpAmp: BinOp.And,
                Tok.Caret: BinOp.Xor,
                Tok.Pipe: BinOp.BitOr,
                Tok.Amp: BinOp.BitAnd,
                Tok.Plus: BinOp.Add,
                Tok.Minus: BinOp.Sub,
                Tok.Star: BinOp.Mul,
                Tok.Slash: BinOp.Div,
                Tok.Percent: BinOp.Mod,
                Tok.PeriodPeriod: BinOp.Subrange,
            }
            if op_token in op_map:
                op = op_map[op_token]
            else:
                bail("Unexpected token that is not a binary operator")
            result = SpecExp.Binop(result, op, rhs)

    return result


def parse_spec_exp(
    tokens: Lexer,
) -> SpecExp:
    lhs = parse_unary_spec_exp(tokens)
    return parse_rhs_of_spec_exp(tokens, lhs, 1)


# Parse a top-level requires, ensures, aborts_if, or succeeds_if spec
# in a function decl.  This has to set the lexer into "spec_mode" to
# return names without eating trailing punctuation such as '<' or '.'.
# That is needed to parse paths with dots separating field names.
def parse_spec_condition(
    tokens: Lexer,
) -> Condition_:
    # Set lexer to read names without trailing punctuation
    tokens.spec_mode = True
    tk = tokens.peek()

    if tk == Tok.AbortsIf:
        tokens.advance()
        retval = Condition_.AbortsIf(parse_spec_exp(tokens))

    elif tk == Tok.Ensures:
        tokens.advance()
        retval = Condition_.Ensures(parse_spec_exp(tokens))

    elif tk == Tok.Requires:
        tokens.advance()
        retval = Condition_.Requires(parse_spec_exp(tokens))

    elif tk == Tok.SucceedsIf:
        tokens.advance()
        retval = Condition_.SucceedsIf(parse_spec_exp(tokens))

    else:
        tokens.spec_mode = False
        raise ParseErrorInvalidToken(current_token_loc(tokens))

    tokens.spec_mode = False
    return retval


def parse_invariant(
    tokens: Lexer,
) -> Invariant:
    # Set lexer to read names without trailing punctuation
    tokens.spec_mode = True
    start = tokens.start_loc()
    result = parse_invariant_(tokens)
    tokens.spec_mode = False
    return spanned(
        tokens.file_name(),
        start,
        tokens.previous_end_loc(),
        result,
    )


def parse_invariant_(
    tokens: Lexer,
) -> Invariant_:
    consume_token(tokens, Tok.Invariant)
    if tokens.peek() == Tok.LBrace:
        tokens.advance()
        s = parse_name(tokens)
        consume_token(tokens, Tok.RBrace)
        modifier = s
    else:
        modifier = ""

    # Check whether this invariant has the assignment form `invariant target = <expr>;`
    if tokens.peek() == Tok.NameValue:
        # There must always be some token following (e.g. ;), so we can force lookahead.
        if tokens.lookahead() == Tok.Equal:
            name = parse_name(tokens)
            consume_token(tokens, Tok.Equal)
            target = name
        else:
            target = None
    else:
        target = None

    condition = parse_spec_exp(tokens)
    return Invariant_(
        modifier,
        target,
        condition,
    )


def parse_synthetic(
    tokens: Lexer,
) -> SyntheticDefinition:
    # Set lexer to read names without trailing punctuation
    tokens.spec_mode = True
    start = tokens.start_loc()
    result = parse_synthetic_(tokens)
    tokens.spec_mode = False
    return spanned(
        tokens.file_name(),
        start,
        tokens.previous_end_loc(),
        result,
    )


def parse_synthetic_(
    tokens: Lexer,
) -> SyntheticDefinition_:
    consume_token(tokens, Tok.Synthetic)
    field = parse_field(tokens)
    istr = field.value.as_inner()
    name = istr
    consume_token(tokens, Tok.Colon)
    type_ = parse_type(tokens)
    consume_token(tokens, Tok.Semicolon)
    return SyntheticDefinition_(name, type_)


# FunctionDecl : (FunctionName, Function_) = {
#   <f: Sp<MoveFunctionDecl>> => (f.value.0, Spanned { span: f.loc, value: f.value.1 }),
#   <f: Sp<NativeFunctionDecl>> => (f.value.0, Spanned { span: f.loc, value: f.value.1 }),
# }

# MoveFunctionDecl : (FunctionName, Function) = {
#     <p: Public?> <name_and_type_formals: NameAndTypeFormals> "(" <args:
#     (ArgDecl)*> ")" <ret: ReturnType?>
#     <acquires: AcquireList?>
#     <locals_body: FunctionBlock> =>? { ... }
# }

# NativeFunctionDecl: (FunctionName, Function) = {
#     <nat: NativeTag> <p: Public?> <name_and_type_formals: NameAndTypeFormals>
#     "(" <args: Comma<ArgDecl>> ")" <ret: ReturnType?>
#         <acquires: AcquireList?>
#         ";" =>? { ... }
# }

def parse_function_decl(
    tokens: Lexer,
) -> Tuple[FunctionName, Function]:
    start_loc = tokens.start_loc()

    if tokens.peek() == Tok.Native:
        tokens.advance()
        is_native = True
    else:
        is_native = False


    if tokens.peek() == Tok.Public:
        tokens.advance()
        is_public = True
    else:
        is_public = False


    (name, type_formals) = parse_name_and_type_formals(tokens)
    consume_token(tokens, Tok.LParen)
    args = parse_comma_list(tokens, [Tok.RParen], parse_arg_decl, True)
    consume_token(tokens, Tok.RParen)

    if tokens.peek() == Tok.Colon:
        ret = parse_return_type(tokens)
    else:
        ret = []

    if tokens.peek() == Tok.Acquires:
        acquires = parse_acquire_list(tokens)
    else:
        acquires = []

    # parse each specification directive--there may be zero or more
    specifications = []
    while tokens.peek().is_spec_directive():
        start_loc = tokens.start_loc()
        cond = parse_spec_condition(tokens)
        end_loc = tokens.previous_end_loc()
        specifications.append(spanned(tokens.file_name(), start_loc, end_loc, cond))

    func_name = FunctionName.new(name)
    if is_public:
        visibility = FunctionVisibility.Public
    else:
        visibility = FunctionVisibility.Internal

    if is_native:
        consume_token(tokens, Tok.Semicolon)
        body = FunctionBodyNative()
    else:
        (localss, body) = parse_function_block_(tokens)
        body = FunctionBodyMove(localss, body)

    func = Function_.new(
        visibility,
        args,
        ret,
        type_formals,
        acquires,
        specifications,
        body,
    )

    end_loc = tokens.previous_end_loc()
    return (
        func_name,
        spanned(tokens.file_name(), start_loc, end_loc, func),
    )


# FieldDecl : (Field_, Type) = {
#     <f: Sp<Field>> ":" <t: Type> => (f, t)
# }

def parse_field_decl(
    tokens: Lexer,
) -> Tuple[Field, Type]:
    f = parse_field(tokens)
    consume_token(tokens, Tok.Colon)
    t = parse_type(tokens)
    return (f, t)


# Modules: List[ModuleDefinition] = {
#     "modules:" <c: Module*> "script:" => c,
# }

def parse_modules(
    tokens: Lexer,
) -> List[ModuleDefinition]:
    consume_token(tokens, Tok.Modules)
    c: List[ModuleDefinition] = []
    while tokens.peek() == Tok.Module:
        c.append(parse_module(tokens))

    consume_token(tokens, Tok.Script)
    return c


# pub Program : Program = {
#     <m: Modules?> <s: Script> => { ... },
#     <m: Module> => { ... }
# }

def parse_program(
    tokens: Lexer,
) -> Program:
    if tokens.peek() == Tok.Module:
        m = parse_module(tokens)
        loc = tokens.start_loc()
        ret_args = spanned(tokens.file_name(), loc, loc, Exp_.ExprList([]))
        ret = spanned(
            tokens.file_name(),
            loc,
            loc,
            Cmd_.Return(ret_args),
        )
        return_stmt = Statement.CommandStatement(ret)
        body = FunctionBodyMove(
            locls= [],
            code= Block_.new([return_stmt]),
        )
        main = Function_.new(
            FunctionVisibility.Public,
            [],
            [],
            [],
            [],
            [],
            body,
        )
        return Program.new(
            [m],
            Script.new([], [], spanned(tokens.file_name(), loc, loc, main)),
        )
    else:
        if tokens.peek() == Tok.Modules:
            modules = parse_modules(tokens)
        else:
            modules = []

        s = parse_script(tokens)
        return Program.new(modules, s)


# pub Script : Script = {
#     <imports: (ImportDecl)*>
#     "main" "(" <args: Comma<ArgDecl>> ")" <locals_body: FunctionBlock> => { ... }
# }

def parse_script(
    tokens: Lexer,
) -> Script:
    start_loc = tokens.start_loc()
    imports: List[ImportDefinition] = []
    while tokens.peek() == Tok.Import:
        imports.append(parse_import_decl(tokens))

    consume_token(tokens, Tok.Main)
    consume_token(tokens, Tok.LParen)
    args = parse_comma_list(tokens, [Tok.RParen], parse_arg_decl, True)
    consume_token(tokens, Tok.RParen)
    (localss, body) = parse_function_block_(tokens)
    end_loc = tokens.previous_end_loc()
    main = Function_.new(
        FunctionVisibility.Public,
        args,
        [],
        [],
        [],
        [],
        FunctionBodyMove(localss, body),
    )
    main = spanned(tokens.file_name(), start_loc, end_loc, main)
    Script.new(imports, [], main)


# StructKind: bool = {
#     "struct" => False,
#     "resource" => True
# }
# StructDecl: StructDefinition_ = {
#     <is_nominal_resource: StructKind> <name_and_type_formals:
#     NameAndTypeFormals> "{" <data: Comma<FieldDecl>> "}" =>? { ... }
#     <native: NativeTag> <is_nominal_resource: StructKind>
#     <name_and_type_formals: NameAndTypeFormals> ";" =>? { ... }
# }

def parse_struct_decl(
    tokens: Lexer,
) -> StructDefinition:
    start_loc = tokens.start_loc()

    if tokens.peek() == Tok.Native:
        tokens.advance()
        is_native = True
    else:
        is_native = False

    tk = tokens.peek()
    if tk == Tok.Struct:
        is_nominal_resource = False
    elif tk == Tok.Resource:
        is_nominal_resource = True
    else:
        raise ParseErrorInvalidToken(current_token_loc(tokens))

    tokens.advance()

    (name, type_formals) = parse_name_and_type_formals(tokens)

    if is_native:
        consume_token(tokens, Tok.Semicolon)
        end_loc = tokens.previous_end_loc()
        return spanned(
            tokens.file_name(),
            start_loc,
            end_loc,
            StructDefinition_.native(is_nominal_resource, name, type_formals),
        )

    consume_token(tokens, Tok.LBrace)
    fields = parse_comma_list(
        tokens,
        [Tok.RBrace, Tok.Invariant],
        parse_field_decl,
        True,
    )
    if tokens.peek() == Tok.Invariant:
        invariants = parse_comma_list(tokens, [Tok.RBrace], parse_invariant, True)
    else:
        invariants = []

    consume_token(tokens, Tok.RBrace)
    end_loc = tokens.previous_end_loc()
    return spanned(
        tokens.file_name(),
        start_loc,
        end_loc,
        StructDefinition_.move_declared(
            is_nominal_resource,
            name,
            type_formals,
            fields,
            invariants,
        ),
    )


# QualifiedModuleIdent: QualifiedModuleIdent = {
#     <a: Address> "." <m: ModuleName> => QualifiedModuleIdent.new(m, a),
# }

def parse_qualified_module_ident(
    tokens: Lexer,
) -> QualifiedModuleIdent:
    a = parse_account_address(tokens)
    consume_token(tokens, Tok.Period)
    m = parse_module_name(tokens)
    return QualifiedModuleIdent.new(m, a)


# ModuleIdent: ModuleIdent = {
#     <q: QualifiedModuleIdent> => ModuleIdent.Qualified(q),
#     <transaction_dot_module: DotName> =>? { ... }
# }

def parse_module_ident(
    tokens: Lexer,
) -> ModuleIdent:
    if tokens.peek() == Tok.AddressValue:
        return ModuleIdent.Qualified(parse_qualified_module_ident(tokens))

    transaction_dot_module = parse_dot_name(tokens)
    v = transaction_dot_module.split('.')
    assert(v.__len__() == 2)
    ident: str = v[0]
    if ident != "Transaction":
        bail("Ident = {} which is not Transaction", ident)

    m: ModuleName = ModuleName.new(v[1])
    return ModuleIdent.Transaction(m)


# ImportAlias: ModuleName = {
#     "as" <alias: ModuleName> => { ... }
# }

def parse_import_alias(
    tokens: Lexer,
) -> ModuleName:
    consume_token(tokens, Tok.As)
    alias = parse_module_name(tokens)
    if alias.as_inner() == ModuleName.self_name():
        bail(
            "Invalid use of reserved module alias '{}'",
            ModuleName.self_name()
        )
    return alias


# ImportDecl: ImportDefinition = {
#     "import" <ident: ModuleIdent> <alias: ImportAlias?> ";" => { ... }
# }

def parse_import_decl(
    tokens: Lexer,
) -> ImportDefinition:
    consume_token(tokens, Tok.Import)
    ident = parse_module_ident(tokens)
    if tokens.peek() == Tok.As:
        alias = parse_import_alias(tokens)
    else:
        alias = None

    consume_token(tokens, Tok.Semicolon)
    return ImportDefinition.new(ident, alias)


# pub Module : ModuleDefinition = {
#     "module" <n: Name> "{"
#         <imports: (ImportDecl)*>
#         <structs: (StructDecl)*>
#         <functions: (FunctionDecl)*>
#     "}" =>? ModuleDefinition.new(n, imports, structs, functions),
# }

def is_struct_decl(
    tokens: Lexer,
) -> bool:
    t = tokens.peek()
    if t == Tok.Native:
        t = tokens.lookahead()

    return t == Tok.Struct or t == Tok.Resource


def parse_module(
    tokens: Lexer,
) -> ModuleDefinition:
    consume_token(tokens, Tok.Module)
    name = parse_name(tokens)
    consume_token(tokens, Tok.LBrace)

    imports: List[ImportDefinition] = []
    while tokens.peek() == Tok.Import:
        imports.append(parse_import_decl(tokens))

    synthetics = []
    while tokens.peek() == Tok.Synthetic:
        synthetics.append(parse_synthetic(tokens))

    structs: List[StructDefinition] = []
    while is_struct_decl(tokens):
        structs.append(parse_struct_decl(tokens))

    functions: List[Tuple[FunctionName, Function]] = []
    while tokens.peek() != Tok.RBrace:
        functions.append(parse_function_decl(tokens))

    tokens.advance()  # consume the RBrace

    return ModuleDefinition.new(
        name,
        imports,
        [],
        structs,
        functions,
        synthetics,
    )


# pub ScriptOrModule: ScriptOrModule = {
#     <s: Script> => ScriptOrModule.Script(s),
#     <m: Module> => ScriptOrModule.Module(m),
# }

def parse_script_or_module(
    tokens: Lexer,
) -> ScriptOrModule:
    if tokens.peek() == Tok.Module:
        return ScriptOrModule(ScriptOrModule.MODULE, parse_module(token))
    else:
        return ScriptOrModule(ScriptOrModule.SCRIPT, parse_script(token))


def parse_cmd_string(file: str, inputs: str) -> Cmd_:
    tokens = Lexer.new(leak_str(file), inputs)
    tokens.advance()
    return parse_cmd_(tokens)


def parse_module_string(
    file: str,
    inputs: str,
) -> ModuleDefinition:
    tokens = Lexer.new(leak_str(file), inputs)
    tokens.advance()
    return parse_module(tokens)


def parse_program_string(
    file: str,
    inputs: str,
) -> Program:
    tokens = Lexer.new(leak_str(file), inputs)
    tokens.advance()
    return parse_program(tokens)


def parse_script_string(
    file: str,
    inputs: str,
) -> Script:
    tokens = Lexer.new(leak_str(file), inputs)
    tokens.advance()
    return parse_script(tokens)


def parse_script_or_module_string(
    file: str,
    inputs: str,
) -> ScriptOrModule:
    tokens = Lexer.new(leak_str(file), inputs)
    tokens.advance()
    return parse_script_or_module(tokens)


# TODO replace with some sort of intern table
def leak_str(s: str) -> str:
    return s #leak in rust consumes and leaks the Box, returning a mutable reference, &'a mut T.
