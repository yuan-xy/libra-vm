from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import List, Mapping, Optional, Tuple

from canoser import Uint32, Uint64
from libra.crypto.ed25519 import (ED25519_SIGNATURE_LENGTH, Ed25519PublicKey,
                                  Ed25519Signature)
from libra.hasher import HashValue, new_sha3_256
from libra.language_storage import TypeTag
from libra.rustlib import flatten, usize
from libra.vm_error import StatusCode, VMStatus
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from mol.move_vm.types.native_functions import NativeResult, native_gas, pop_arg
from mol.move_vm.types.native_functions.primitive_helpers import check_arg_number
from mol.move_vm.types.values import Value
from mol.vm.gas_schedule import CostTable, GasUnits, NativeCostIndex
from mol.vm.vm_exception import VMException, VMExceptionBase

BITMAP_SIZE: usize = 32

# Starting error code number
DEFAULT_ERROR_CODE: Uint64 = 0x0ED2_5519
# Batch signature verification failed
SIGNATURE_VERIFICATION_FAILURE: Uint64 = DEFAULT_ERROR_CODE + 1
# Public keys deserialization error
PUBLIC_KEY_DESERIALIZATION_FAILURE: Uint64 = DEFAULT_ERROR_CODE + 2
# Signatures deserialization error
SIGNATURE_DESERIALIZATION_FAILURE: Uint64 = DEFAULT_ERROR_CODE + 3
# Bitmap is all zeros
ZERO_BITMAP_FAILURE: Uint64 = DEFAULT_ERROR_CODE + 4
# Invalid bitmap length
INVALID_BITMAP_LENGTH_FAILURE: Uint64 = DEFAULT_ERROR_CODE + 5
# Mismatch between bitmap's Hamming weight and number or size of signatures
SIGNATURE_SIZE_FAILURE: Uint64 = DEFAULT_ERROR_CODE + 6
# Bitmap points to a non-existent key
BITMAP_PUBLIC_KEY_SIZE_FAILURE: Uint64 = DEFAULT_ERROR_CODE + 7
# Length of bytes of concatenated keys exceeds the maximum allowed
OVERSIZED_PUBLIC_KEY_SIZE_FAILURE: Uint64 = DEFAULT_ERROR_CODE + 8
# Concatenated Ed25519 public keys should be a multiple of 32 bytes
INVALID_PUBLIC_KEY_SIZE_FAILURE: Uint64 = DEFAULT_ERROR_CODE + 9

def native_ed25519_signature_verification(
    _ty_args: List[TypeTag],
    arguments: List[Value],
    cost_table: CostTable,
) -> NativeResult:
    check_arg_number(arguments, 3, 'ed25519_signature_verification')
    msg = pop_arg(arguments, bytes)
    pubkey = pop_arg(arguments, bytes)
    signature = pop_arg(arguments, bytes)

    cost = native_gas(cost_table, NativeCostIndex.ED25519_VERIFY, msg.__len__())

    sig = bytes(signature)
    if len(sig) != ED25519_SIGNATURE_LENGTH:
        status = VMStatus(StatusCode.NATIVE_FUNCTION_ERROR).with_sub_status(DEFAULT_ERROR_CODE)
        return NativeResult.err(cost, status)

    try:
        pk = VerifyKey(bytes(pubkey))
    except Exception as err:
        traceback.print_exc()
        status = VMStatus(StatusCode.NATIVE_FUNCTION_ERROR)\
            .with_sub_status(DEFAULT_ERROR_CODE).with_message(err.__str__())
        return NativeResult.err(cost, status)

    try:
        pk.verify(bytes(msg), sig)
        bool_value = True
    except BadSignatureError:
        bool_value = False

    return_values = [Value.bool(bool_value)]
    return NativeResult.ok(cost, return_values)


# Batch verify a collection of signatures using a bitmap for matching signatures to keys.
def native_ed25519_threshold_signature_verification(
    _ty_args: List[TypeTag],
    arguments: List[Value],
    cost_table: CostTable,
) -> NativeResult:
    check_arg_number(arguments, 4, 'ed25519_threshold_signature_verification')
    message = pop_arg(arguments, bytes)
    public_keys = pop_arg(arguments, bytes)
    signatures = pop_arg(arguments, bytes)
    bitmap = pop_arg(arguments, bytes)

    return ed25519_threshold_signature_verification(
        bitmap,
        signatures,
        public_keys,
        message,
        cost_table,
    )


def ed25519_threshold_signature_verification(
    bitmap: bytes,
    signatures: bytes,
    public_keys: bytes,
    message: bytes,
    cost_table: CostTable,
) -> NativeResult:
    bitvec = flatten([bin(x)[2:].rjust(8, '0') for x in bitmap])
    try:
        num_of_sigs = sanity_check(bitvec, signatures, public_keys, cost_table)
    except NativeException as err:
        return err.result

    cost = native_gas(
        cost_table,
        NativeCostIndex.ED25519_THRESHOLD_VERIFY,
        num_of_sigs * message.__len__(),
    )

    chunks, chunk_size = len(signatures), 64
    sig_chunks = [signatures[i:i+chunk_size] for i in range(0, chunks, chunk_size)]

    chunks, chunk_size = len(public_keys), 32
    key_chunks = [public_keys[i:i+chunk_size] for i in range(0, chunks, chunk_size)]

    keys_and_signatures = matching_keys_and_signatures(num_of_sigs, bitvec, sig_chunks, key_chunks)

    if len(message) != HashValue.LENGTH:
        status = VMStatus(StatusCode.NATIVE_FUNCTION_ERROR).with_sub_status(DEFAULT_ERROR_CODE)
        return NativeResult.err(cost, status)

    try:
        for (pubkey, sig) in keys_and_signatures:
            pk = VerifyKey(bytes(pubkey))
            pk.verify(message, sig)

        return NativeResult.ok(cost, [Value.Uint64(num_of_sigs)])
    except BadSignatureError:
        return NativeResult.err(
            cost,
            VMStatus(StatusCode.NATIVE_FUNCTION_ERROR)\
                .with_sub_status(SIGNATURE_VERIFICATION_FAILURE),
        )


def matching_keys_and_signatures(
    num_of_sigs: Uint64,
    bitmap: List,
    signatures: List[Ed25519Signature],
    public_keys: List[Ed25519PublicKey],
) -> List[Tuple[Ed25519PublicKey, Ed25519Signature]]:
    sig_index = 0
    keys_and_signatures = []

    for (key_index, bit) in enumerate(bitmap):
        if bit == '1':
            keys_and_signatures.append((
                # unwrap() will always succeed because we already did the sanity check.
                public_keys[key_index],
                signatures[sig_index],
            ))
            sig_index += 1
            if sig_index == num_of_sigs:
                break

    return keys_and_signatures


# Check for correct input sizes and return the number of submitted signatures iff everything is
# valid.
def sanity_check(
    bitmap: List,
    signatures: bytes,
    pubkeys: bytes,
    cost_table: CostTable,
) -> Uint64:
    bitmap_len = bitmap.__len__()
    signatures_len = signatures.__len__()
    public_keys_len = pubkeys.__len__()

    cost = native_gas(
        cost_table,
        NativeCostIndex.ED25519_THRESHOLD_VERIFY,
        bitmap_len + signatures_len + public_keys_len,
    )

    # Ensure a BITMAP_SIZE bitmap.
    if bitmap_len != BITMAP_SIZE:
        # Invalid bitmap length
        raise NativeException(NativeResult.err(
            cost,
            VMStatus(StatusCode.NATIVE_FUNCTION_ERROR)\
                .with_sub_status(INVALID_BITMAP_LENGTH_FAILURE),
        ))

    bitmap_last_bit_set: usize = 0; # This is fine as we expect at least one set bit.
    bitmap_count_ones: usize = 0
    for (i, bit) in enumerate(bitmap):
        if bit == '1':
            bitmap_count_ones += 1
            bitmap_last_bit_set = i

    if bitmap_count_ones == 0:
        # Bitmap is all zeros
        raise NativeException(NativeResult.err(
            cost,
            VMStatus(StatusCode.NATIVE_FUNCTION_ERROR).with_sub_status(ZERO_BITMAP_FAILURE),
        ))

    # Ensure we have as many signatures as the number of set bits in bitmap.
    if bitmap_count_ones * 64 != signatures_len:
        # Mismatch between Bitmap Hamming weight and number of signatures
        raise NativeException(NativeResult.err(
            cost,
            VMStatus(StatusCode.NATIVE_FUNCTION_ERROR)\
                .with_sub_status(SIGNATURE_SIZE_FAILURE),
        ))

    # Ensure that we have at least as many keys as the index of the last set bit in bitmap.
    if public_keys_len < 32 * (bitmap_last_bit_set + 1):
        # Bitmap points to a non-existent key
        raise NativeException(NativeResult.err(
            cost,
            VMStatus(StatusCode.NATIVE_FUNCTION_ERROR)\
                .with_sub_status(BITMAP_PUBLIC_KEY_SIZE_FAILURE),
        ))

    # Ensure no more than BITMAP_SIZE keys.
    if public_keys_len > 32 * BITMAP_SIZE:
        # Length of bytes of concatenated keys exceeds the maximum allowed
        raise NativeException(NativeResult.err(
            cost,
            VMStatus(StatusCode.NATIVE_FUNCTION_ERROR)
                .with_sub_status(OVERSIZED_PUBLIC_KEY_SIZE_FAILURE),
        ))

    # Ensure bytearray for keys is a multiple of 32 bytes.
    if public_keys_len % 32 != 0:
        # Concatenated Ed25519 public keys should be a multiple of 32 bytes
        raise NativeException(NativeResult.err(
            cost,
            VMStatus(StatusCode.NATIVE_FUNCTION_ERROR)
                .with_sub_status(INVALID_PUBLIC_KEY_SIZE_FAILURE),
        ))

    return bitmap_count_ones



@dataclass
class NativeException(VMExceptionBase):
    result: NativeResult
