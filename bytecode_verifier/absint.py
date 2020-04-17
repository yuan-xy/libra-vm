from __future__ import annotations
from bytecode_verifier.control_flow_graph import BlockId, ControlFlowGraph
from vm.views import FunctionDefinitionView
from vm.file_format import Bytecode, CompiledModule
from vm import Opcodes
from libra.rustlib import bail, usize
from typing import List, Any, Optional, Mapping
from dataclasses import dataclass
from enum import IntEnum
from copy import deepcopy
import abc


# Trait for finite-height abstract domains. Infinite height domains would require a more complex
# trait with widening and a partial order.
class AbstractDomain(abc.ABC):
    @abc.abstractmethod
    def join(self, other: AbstractDomain) -> JoinResult:
        bail("unimplemented!")



class JoinResult(IntEnum):
    Unchanged = 1
    Changed = 2
    Error = 3

@dataclass
class BlockPrecondition:
    tag: int
    state: Any#State

    STATE = 1
    # joining postconditions of previous blocks ended in failure
    JOIN_FAILURE = 2

    @classmethod
    def State(cls, value):
        return cls(BlockPrecondition.STATE, value)

    # joining postconditions of previous blocks ended in failure
    @classmethod
    def JoinFailure(cls):
        return cls(BlockPrecondition.JOIN_FAILURE, None)


@dataclass
class BlockPostcondition:
    tag: int
    error: Any#AnalysisError

    # Analyzing block was successful
    SUCCESS = 1
    # Analyzing block ended in an error
    ERROR = 2

    @classmethod
    def Success(cls):
        return cls(BlockPostcondition.SUCCESS, None)

    @classmethod
    def Error(cls, err):
        return cls(BlockPostcondition.ERROR, err)

@dataclass
class BlockInvariant:
    # Precondition of the block
    pre: BlockPrecondition
    # Postcondition of the block---just success/error for now
    post: BlockPostcondition


# A map from block id's to the pre/post of each block after a fixed point is reached.
#[allow(dead_code)]
InvariantMap = Mapping[BlockId, BlockInvariant]

# Take a pre-state + instruction and mutate it to produce a post-state
# Auxiliary data can be stored in self.
class TransferFunctions(abc.ABC):
    # State: AbstractDomain
    # AnalysisError: Clone

    # Execute local@instr found at index local@index in the current basic block from pre-state
    # local@pre.
    # Should return an AnalysisError if executing the instruction is unsuccessful, and () if
    # the effects of successfully executing local@instr have been reflected by mutatating
    # local@pre.
    # Auxilary data from the analysis that is not part of the abstract state can be collected by
    # mutating local@self.
    # The last instruction index in the current block is local@last_index. Knowing this
    # information allows clients to detect the end of a basic block and special-case appropriately
    # (e.g., normalizing the abstract state before a join).
    @abc.abstractmethod
    def execute(
        self,
        pre: Any,
        instr: Bytecode,
        index: usize,
        last_index: usize,
    ) -> Optional[Any]:
        bail("unimplemented!")


class AbstractInterpreter(TransferFunctions):
    # Analyze procedure local@function_view starting from pre-state local@initial_state.
    def analyze_function(
        self,
        initial_state: Any,
        function_view: FunctionDefinitionView,
        cfg: ControlFlowGraph,
    ) -> InvariantMap:
        inv_map: InvariantMap = {}
        entry_block_id = cfg.entry_block_id()
        work_list = [entry_block_id]
        inv_map[entry_block_id] = \
            BlockInvariant(
                BlockPrecondition.State(initial_state),
                BlockPostcondition.Success(),
            )

        while work_list:
            block_id = work_list.pop()
            if block_id not in inv_map:
                bail("Missing invariant for block {}", block_id)

            block_invariant = inv_map[block_id]

            if block_invariant.pre.tag == BlockPrecondition.STATE:
                state = deepcopy(block_invariant.pre.state)
            else:
                # Can't analyze the block from a failing precondition
                continue

            errors = self.execute_block(block_id, state, function_view, cfg)
            if errors is not None:
                block_invariant.post = BlockPostcondition.Error(errors)
                continue
            else:
                block_invariant.post = BlockPostcondition.Success()

            # propagate postcondition of this block to successor blocks
            for next_block_id in cfg.successors(block_id):
                if next_block_id in inv_map:
                    next_block_invariant = inv_map[next_block_id]

                    if next_block_invariant.pre.tag == BlockPrecondition.STATE:
                        join_result = next_block_invariant.pre.state.join(state)
                    else:
                        join_result = JoinResult.Error

                    if join_result == JoinResult.Unchanged:
                        # Pre is the same after join. Reanalyzing this block would produce
                        # the same post. Don't schedule it.
                        continue
                    elif join_result == JoinResult.Changed:
                        # The pre changed. Schedule the next block.
                        work_list.append(next_block_id)
                    elif join_result == JoinResult.Error:
                        # This join produced an error. Don't schedule the block.
                        next_block_invariant.pre = BlockPrecondition.JoinFailure()
                        continue
                    else:
                        bail("unreachable!")

                else:
                    # Haven't visited the next block yet. Use the post of the current block as
                    # its pre and schedule it.
                    inv_map[next_block_id] = BlockInvariant(
                            BlockPrecondition.State(deepcopy(state)),
                            BlockPostcondition.Success(),
                        )

                    work_list.append(next_block_id)

        return inv_map


    def execute_block(
        self,
        block_id: BlockId,
        state: Any,
        function_view: FunctionDefinitionView,
        cfg: ControlFlowGraph,
    ) -> Optional[Any]:
        block_end = cfg.block_end(block_id)
        for offset in cfg.instr_indexes(block_id):
            instr = function_view.code().code[offset]
            err = self.execute(state, instr, offset, block_end)
            if err:
                return err

        return None