from typing import Mapping, Optional
from mol.compiler.bytecode_source_map.mapping import SourceMapping


class GlobalSourceMapping:
    mapping: Mapping[str, SourceMapping] = {}

    @classmethod
    def add(cls, address: str, module: str, function: str, mapping: SourceMapping) -> None:
        qual_name = "::".join([address, module, function])
        cls.add_mapping(qual_name, mapping)

    @classmethod
    def add_mapping(cls, qual_name: str, mapping: SourceMapping) -> None:
        cls.mapping[qual_name] = mapping

    @classmethod
    def find_mapping(cls, qual_name: str) -> Optional[SourceMapping]:
        if qual_name in cls.mapping:
            return cls.mapping[qual_name]
        else:
            return None

    @classmethod
    def find(cls, address: str, module: str, function: str) -> Optional[SourceMapping]:
        """

        :rtype: object
        """
        qual_name = "::".join([address, module, function])
        return cls.find_mapping(qual_name)


