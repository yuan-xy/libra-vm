from __future__ import annotations
# This module defines the control-flow graph uses for bytecode verification.
from vm.file_format import Bytecode, CodeOffset
from typing import List, Set, Mapping, Iterable, Optional
from libra.rustlib import assert_equal, bail
from dataclasses import dataclass
from canoser import Uint16
import abc

BlockId = CodeOffset

# A trait that specifies the basic requirements for a CFG
class ControlFlowGraph(abc.ABC):
    # Start index of the block ID in the bytecode vector
    @abc.abstractmethod
    def block_start(self, block_id: BlockId) -> CodeOffset:
        bail("unimplemented!")

    # End index of the block ID in the bytecode vector
    @abc.abstractmethod
    def block_end(self, block_id: BlockId) -> CodeOffset:
        bail("unimplemented!")

    # Successors of the block ID in the bytecode vector
    @abc.abstractmethod
    def successors(self, block_id: BlockId) -> List[BlockId]:
        bail("unimplemented!")

    # Iterator over the indexes of instructions in this block
    @abc.abstractmethod
    def instr_indexes(self, block_id: BlockId) -> Iterable[CodeOffset]:
        bail("unimplemented!")

    # Return an iterator over the blocks of the CFG
    @abc.abstractmethod
    def blocks(self) -> List[BlockId]:
        bail("unimplemented!")

    # Return the number of blocks (vertices) in the control flow graph
    @abc.abstractmethod
    def num_blocks(self) -> Uint16:
        bail("unimplemented!")

    # Return the id of the entry block for this control-flow graph
    # Note: even a CFG with no instructions has an (empty) entry block.
    @abc.abstractmethod
    def entry_block_id(self) -> BlockId:
        bail("unimplemented!")


@dataclass
class BasicBlock:
    entry: CodeOffset
    exit: CodeOffset
    successors: List[BlockId]

    def display(self):
        print("+=======================+")
        print("| Enter:  {}            |", self.entry)
        print("+-----------------------+")
        print("==> Children: {}", self.successors)
        print("+-----------------------+")
        print("| Exit:   {}            |", self.exit)
        print("+=======================+")


ENTRY_BLOCK_ID: BlockId = 0

# The control flow graph that we build from the bytecode.
@dataclass
class VMControlFlowGraph(ControlFlowGraph):
    # The basic blocks
    blocks: Mapping[BlockId, BasicBlock]

    @classmethod
    def new(cls, code: List[Bytecode]) -> VMControlFlowGraph:
        # First go through and collect block ids, i.e., offsets that begin basic blocks.
        # Need to do this first in order to handle backwards edges.
        block_ids = set()
        block_ids.add(ENTRY_BLOCK_ID)
        for pc in range(code.__len__()):
            VMControlFlowGraph.record_block_ids(pc, code, block_ids)


        # Create basic blocks
        cfg = VMControlFlowGraph({})
        entry = 0
        for pc in range(code.__len__()):
            co_pc: CodeOffset = pc

            # Create a basic block
            if VMControlFlowGraph.is_end_of_block(co_pc, code, block_ids):
                successors = Bytecode.get_successors(co_pc, code)
                bb = BasicBlock(
                    entry,
                    co_pc,
                    successors,
                )
                cfg.blocks[entry] = bb
                entry = co_pc + 1

        assert_equal(entry, code.__len__())
        return cfg


    def display(self):
        for block in self.blocks.values():
            block.display()


    def is_end_of_block(pc: CodeOffset, code: List[Bytecode], block_ids: Set[BlockId]) -> bool:
        return pc + 1 == code.__len__()  or (pc + 1) in block_ids


    def record_block_ids(pc: CodeOffset, code: List[Bytecode], block_ids: Set[BlockId]):
        bytecode = code[pc]

        offset = bytecode.offset()
        if offset is not None:
            block_ids.add(offset)

        if bytecode.is_branch() and pc + 1 < (code.__len__()):
            block_ids.add(pc + 1)


    # A utility function that implements BFS-reachability from block_id with
    # respect to get_targets function
    def traverse_by(self, block_id: BlockId) -> List[BlockId]:
        ret = []
        # We use this index to keep track of our frontier.
        index = 0
        # Guard against cycles
        seen = set()

        ret.append(block_id)
        seen.add(block_id)

        while index < ret.__len__():
            block_id = ret[index]
            index += 1
            successors = self.successors(block_id)
            for block_id in successors:
                if block_id not in seen:
                    ret.append(block_id)
                    seen.add(block_id)

        return ret


    def reachable_from(self, block_id: BlockId) -> List[BlockId]:
        return self.traverse_by(block_id)

    # Note: in the following procedures, it's safe not to check bounds because:
    # - Every CFG (even one with no instructions) has a block at ENTRY_BLOCK_ID
    # - The only way to acquire new BlockId's is via block_successors()
    # - block_successors only() returns valid BlockId's
    # Note: it is still possible to get a BlockId from one CFG and use it in another CFG where it
    # is not valid. The design does not attempt to prevent this abuse of the API.

    def block_start(self, block_id: BlockId) -> CodeOffset:
        return self.blocks[block_id].entry


    def block_end(self, block_id: BlockId) -> CodeOffset:
        return self.blocks[block_id].exit


    def successors(self, block_id: BlockId) -> List[BlockId]:
        return self.blocks[block_id].successors


    def blocks(self) -> List[BlockId]:
        self.blocks.keys()


    def instr_indexes(self, block_id: BlockId) -> Iterable[CodeOffset]:
        start = self.block_start(block_id)
        end = self.block_end(block_id)
        return range(start, end+1)


    def num_blocks(self) -> Uint16:
        return self.blocks.__len__()


    def entry_block_id(self) -> BlockId:
        return ENTRY_BLOCK_ID

