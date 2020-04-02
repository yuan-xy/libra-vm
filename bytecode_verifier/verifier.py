from __future__ import annotations
from bytecode_verifier.check_duplication import DuplicationChecker
from bytecode_verifier.code_unit_verifier import CodeUnitVerifier
from bytecode_verifier.instantiation_loops import InstantiationLoopChecker
from bytecode_verifier.resources import ResourceTransitiveChecker
from bytecode_verifier.signature import SignatureChecker
from bytecode_verifier.struct_defs import RecursiveStructDefChecker

from libra.language_storage import ModuleId
from libra.vm_error import StatusCode, VMStatus
from vm import signature_token_help

from move_vm.types.native_functions.dispatch import NativeFunction
from move_vm.types.native_structs import resolve_native_struct

from vm import ModuleAccess, ScriptAccess, IndexKind, Resolver
from vm.vm_exception import VMException
from vm.errors import append_err_info, verification_error
from vm.file_format import CompiledModule, CompiledProgram, CompiledScript
from vm.views import ModuleView, ViewInternals
from typing import List, Optional, Mapping
from libra.vm_error import StatusCode, VMStatus
from dataclasses import dataclass


# This module contains the public APIs supported by the bytecode verifier.

@dataclass
class VerifyException(VMException):
    data: Union[CompiledModule, CompiledScript]

    def __init__(self, status: Union[VMStatus, List[VMStatus]], data: Union[CompiledModule, CompiledScript]):
        super().__init__(status)
        self.data = data



# A program that has been verified for internal consistency.
#
# This includes cross-module checking for the base dependencies.
@dataclass
class VerifiedProgram:
    script: VerifiedScript
    modules: List[VerifiedModule]
    deps: List[VerifiedModule]


    # Creates a new `VerifiedProgram` after verifying the provided `CompiledProgram` against
    # the provided base dependencies.
    #
    # On error, returns a list of verification statuses.
    @classmethod
    def new(cls,
        program: CompiledProgram,
        deps: Iterable[VerifiedModule],
    ) -> VerifiedProgram:
        modules = []

        for module in program.modules:
            module = VerifiedModule.new(module)
            # {
            #     # Verify against any modules compiled earlier as well.
            #     deps = deps.iter().copied().chain(modules)
            #     errors = verify_module_dependencies(module, deps)
            #     if !errors.is_empty() {
            #         return Err(errors)
            #     }
            # }
            modules.append(module)

        script = VerifiedScript.new(program.script)
        # {
        #     deps = deps.iter().copied().chain(modules)
        #     errors = verify_script_dependencies(&script, deps)
        #     if !errors.is_empty() {
        #         return Err(errors)
        #     }
        # }
        return VerifiedProgram(script, modules, deps)


    # Converts this `VerifiedProgram` into a `CompiledProgram` instance.
    #
    # Converting back would require re-verifying this program.
    def into_inner(self) -> CompiledProgram:
        return CompiledProgram(
            modules= [x.into_inner() for x in self.modules],
            script= self.script.into_inner(),
        )




# A module that has been verified for internal consistency.
#
# This does not include cross-module checking -- that needs to be done separately.
@dataclass
class VerifiedModule(ModuleAccess):
    v0: CompiledModule

    # Verifies this `CompiledModule`, returning a `VerifiedModule` on success.
    #
    # On failure, returns the original `CompiledModule` and a list of verification errors.
    #
    # There is a partial order on the checks. For example, the duplication check must precede the
    # structural recursion check. In general, later checks are more expensive.
    @classmethod
    def new(cls, module: CompiledModule):
        # All CompiledModule instances are statically guaranteed to be bounds checked, so there's
        # no need for more checking.
        errors = DuplicationChecker(module).verify()
        if errors:
            raise VerifyException(errors, module)

        errors = []
        errors.extend(SignatureChecker(module).verify())
        errors.extend(ResourceTransitiveChecker.new(module).verify())
        if errors:
            raise VerifyException(errors, module)

        errors.extend(RecursiveStructDefChecker(module).verify())
        if errors:
            raise VerifyException(errors, module)

        errors.extend(InstantiationLoopChecker.new(module).verify())
        if errors:
            raise VerifyException(errors, module)

        errors.extend(CodeUnitVerifier.verify(module))
        if errors:
            raise VerifyException(errors, module)

        return VerifiedModule(module)


    def bypass_verifier_DANGEROUS_FOR_TESTING_ONLY(module: CompiledModule) -> VerifiedModule:
        return VerifiedModule(module)

    # Serializes this module into the provided buffer.
    #
    # This is merely a convenience wrapper around `module.as_inner().serialize(buf)`.
    #
    # `VerifiedModule` instances cannot be deserialized directly, since the input is potentially
    # untrusted. Instead, one must go through `CompiledModule`.
    def serialize(self) -> bytes:
        return self.as_inner().serialize()


    def as_inner(self) -> CompiledModule:
        return self.v0

    def into_inner(self) -> CompiledModule:
        return self.v0

# impl ModuleAccess for VerifiedModule {
    def as_module(self) -> CompiledModule:
        return self.v0


# A script that has been verified for internal consistency.
#
# This does not include cross-module checking -- that needs to be done separately.
@dataclass
class VerifiedScript:
    v0: CompiledScript

    # Verifies this `CompiledScript`, returning a `VerifiedScript` on success.
    #
    # On failure, returns the original `CompiledScript` and a list of verification errors.
    #
    # Verification of a script is done in two steps:
    # - Convert the script into a module and run all the usual verification performed on a module
    # - Check the signature of the main function of the script
    #
    # This approach works because critical operations such as MoveFrom, MoveToSender, and
    # BorrowGlobal that are not allowed in the script function take a StructDefinitionIndex as an
    # argument. Since the module constructed from a script is guaranteed to have an empty vector
    # of class definitions, the bounds checker will catch any occurrences of these illegal
    # operations.
    @classmethod
    def new(cls, script: CompiledScript) -> VerifiedScript:
        fake_module = script.into_module()
        module = VerifiedModule.new(fake_module).into_inner()

        script = fake_module.into_script()
        errors = verify_main_signature(script)
        for err in errors:
            append_err_info(err, IndexKind.FunctionDefinition, 0)

        if errors:
            raise VerifyException(errors, script)
        else:
            return VerifiedScript(script)


    # Returns the corresponding `VerifiedModule` for this script.
    #
    # Every `VerifiedScript` is a `VerifiedModule`, but the inverse is not True, so there's no
    # corresponding `VerifiedModule.into_script` function.
    def into_module(self) -> VerifiedModule:
        return VerifiedModule(self.into_inner().into_module())


    # Serializes this script into the provided buffer.
    #
    # This is merely a convenience wrapper around `script.as_inner().serialize(buf)`.
    #
    # `VerifiedScript` instances cannot be deserialized directly, since the input is potentially
    # untrusted. Instead, one must go through `CompiledScript`.
    def serialize(self) -> bytes:
        return self.as_inner().serialize()

    def as_inner(self) -> CompiledScript:
        return self.v0

    def into_inner(self) -> CompiledScript:
        return self.v0

# impl ScriptAccess for VerifiedScript {
    def as_script(self) -> CompiledScript:
        return self.as_inner()



# This function checks the extra requirements on the signature of the main function of a script.
def verify_main_signature(script: CompiledScript) -> List[VMStatus]:
    function_handle = script.function_handle_at(script.main().function)
    function_signature = script.function_signature_at(function_handle.signature)
    if function_signature.return_types:
        return [VMStatus(StatusCode.INVALID_MAIN_FUNCTION_SIGNATURE)]

    for arg_type in function_signature.arg_types:
        if not (arg_type.is_primitive() or arg_type == signature_token_help.VectorU8):
            return [VMStatus(StatusCode.INVALID_MAIN_FUNCTION_SIGNATURE)]

    return []


# Verification of a module in isolation (using `VerifiedModule.new`) trusts that struct and
# function handles not implemented in the module are declared correctly. The following procedure
# justifies this trust by checking that these declarations match the definitions in the module
# dependencies. Each dependency of 'module' is looked up in 'dependencies'.  If not found, an
# error is included in the returned list of errors.  If found, usage of types and functions of the
# dependency in 'module' is checked against the declarations in the found module and mismatch
# errors are returned.
def verify_module_dependencies(
    module: VerifiedModule,
    dependencies: Iterable[VerifiedModule],
) -> List[VMStatus]:
    module_id = module.self_id()
    dependency_map = {} #BTreeMap.new()
    for dependency in dependencies:
        dependency_id = dependency.self_id()
        if module_id != dependency_id:
            dependency_map[dependency_id] = dependency

    errors = []
    module_view = ModuleView.new(module)
    errors.extend(verify_struct_kind(module_view, dependency_map))
    errors.extend(verify_function_visibility_and_type(
        module_view,
        dependency_map,
    ))
    errors.extend(verify_all_dependencies_provided(
        module_view,
        dependency_map,
    ))
    errors.extend(verify_native_functions(module_view))
    errors.extend(verify_native_structs(module_view))
    return errors


# Verifying the dependencies of a script follows the same recipe as `VerifiedScript.new`
# ---convert to a module and invoke verify_module_dependencies. Each dependency of 'script' is
# looked up in 'dependencies'.  If not found, an error is included in the returned list of errors.
# If found, usage of types and functions of the dependency in 'script' is checked against the
# declarations in the found module and mismatch errors are returned.
def verify_script_dependencies(
    script: VerifiedScript,
    dependencies: Iterable[VerifiedModule],
) -> List[VMStatus]:
    fake_module = script.into_module()
    return verify_module_dependencies(fake_module, dependencies)


def verify_native_functions(module_view: ModuleView) -> List[VMStatus]:
    errors = []

    module_id = module_view.id()
    for (idx, native_function_definition_view) in enumerate(module_view.functions()):
        if not native_function_definition_view.is_native():
            continue

        function_name = native_function_definition_view.name()

        import move_vm
        vm_native_function = move_vm.types.native_functions.dispatch.resolve_native_function(module_id, function_name)
        # vm_native_function = NativeFunction.resolve(module_id, function_name)
        if vm_native_function is None:
            errors.append(verification_error(
                IndexKind.FunctionHandle,
                idx,
                StatusCode.MISSING_DEPENDENCY,
            ))
        else:
            declared_function_signature =\
                native_function_definition_view.signature().as_inner()
            expected_function_signature_res =\
                vm_native_function.signature()
            #   vm_native_function.signature(module_view)
            # expected_function_signature_opt = match expected_function_signature_res {
            #     opt => opt,
            #     Err(e) => {
            #         errors.append(e)
            #         continue
            #     }
            # }
            # matching_signatures = expected_function_signature_opt
            #     .map(|e| &e == declared_function_signature)
            #     .unwrap_or(False)
            if declared_function_signature != expected_function_signature_res:
                errors.append(verification_error(
                    IndexKind.FunctionHandle,
                    idx,
                    StatusCode.TYPE_MISMATCH,
                ))

    return errors


def verify_native_structs(module_view: ModuleView) -> List[VMStatus]:
    return []

def verify_all_dependencies_provided(
    module_view: ModuleView,
    dependency_map: Mapping[ModuleId, VerifiedModule],
) -> List[VMStatus]:
    errors = []
    for (idx, module_handle_view) in enumerate(module_view.module_handles()):
        module_id = module_handle_view.module_id()
        if idx != CompiledModule.IMPLEMENTED_MODULE_INDEX and\
            module_id not in dependency_map:
            errors.append(verification_error(
                IndexKind.ModuleHandle,
                idx,
                StatusCode.MISSING_DEPENDENCY,
            ))
    return errors


def verify_struct_kind(
    module_view: ModuleView,
    dependency_map: Mapping[ModuleId, VerifiedModule],
) -> List[VMStatus]:
    errors = []
    for (idx, struct_handle_view) in enumerate(module_view.struct_handles()):
        owner_module_id = struct_handle_view.module_id()
        if owner_module_id not in dependency_map:
            continue

        struct_name = struct_handle_view.name()
        owner_module = dependency_map[owner_module_id]
        owner_module_view = ModuleView.new(owner_module)
        struct_definition_view = owner_module_view.struct_definition(struct_name)
        if struct_definition_view is not None:
            if struct_handle_view.is_nominal_resource()\
                != struct_definition_view.is_nominal_resource()\
                or struct_handle_view.type_formals() != struct_definition_view.type_formals():
                errors.append(verification_error(
                    IndexKind.StructHandle,
                    idx,
                    StatusCode.TYPE_MISMATCH,
                ))
        else:
            errors.append(verification_error(
                IndexKind.StructHandle,
                idx,
                StatusCode.LOOKUP_FAILED,
            ))

    return errors


def verify_function_visibility_and_type(
    module_view: ModuleView,
    dependency_map: Mapping[ModuleId, VerifiedModule],
) -> List[VMStatus]:
    resolver = Resolver.new(module_view.as_inner())
    errors = []
    for (idx, function_handle_view) in enumerate(module_view.function_handles()):
        owner_module_id = function_handle_view.module_id()
        if owner_module_id not in dependency_map:
            continue

        function_name = function_handle_view.name()
        owner_module = dependency_map[owner_module_id]
        owner_module_view = ModuleView.new(owner_module)
        function_definition_view = owner_module_view.function_definition(function_name)
        if function_definition_view is not None:
            if function_definition_view.is_public():
                function_definition_signature = function_definition_view.signature().as_inner()
                imported_function_signature = resolver\
                    .import_function_signature(owner_module, function_definition_signature)
                # Err(err) => {
                #     errors.append(append_err_info(err, IndexKind.FunctionHandle, idx))
                # }
                function_handle_signature = function_handle_view.signature().as_inner()
                if imported_function_signature != function_handle_signature:
                    errors.append(verification_error(
                        IndexKind.FunctionHandle,
                        idx,
                        StatusCode.TYPE_MISMATCH,
                    ))
            else:
                errors.append(verification_error(
                    IndexKind.FunctionHandle,
                    idx,
                    StatusCode.VISIBILITY_MISMATCH,
                ))
        else:
            errors.append(verification_error(
                IndexKind.FunctionHandle,
                idx,
                StatusCode.LOOKUP_FAILED,
            ))
    return errors


# Batch verify a list of modules and panic on any error. The modules should be topologically
# sorted in their dependency order.
def batch_verify_modules(modules: List[CompiledModule]) -> List[VerifiedModule]:
    verified_modules = []
    for module in modules.into_iter():
        verified_module = VerifiedModule.new(module)
        verification_errors = verify_module_dependencies(verified_module, verified_modules)
        for e in verification_errors:
            print(f"{e} at {verified_module.self_id()}")

        assert not verification_errors
        verified_modules.push(verified_module)
    return verified_modules

