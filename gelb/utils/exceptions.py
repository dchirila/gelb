#!/usr/bin/env python3

import os
import click
from colorama import Fore

from gelb.utils import config
from gelb.utils.output_to_terminal import error_with_hint_to_term
from gelb.utils.error_utils import (
    feedback_on_slack_hint,
    learning_gelb_hint,
    show_error_in_src,
    show_double_definition_error
)


def running_within_pytest():
    return "PYTEST_CURRENT_TEST" in os.environ


def _suppress_print_and_exit():
    """Return True if GeLBException subclasses should SKIP their
    `print(self)` + `os._exit(1)` side effects.

    - In pytest, callers assert on the raised exception type, so the
      forced-exit path would abort the test runner.
    - In gelbc's --diagnostics-json mode, the exception is intentionally
      allowed to propagate up to the top-level JSON emitter; any
      stderr output would corrupt the stdout JSON contract.
    """
    return running_within_pytest() or getattr(
        config, 'DIAGNOSTICS_MODE', False)


class GeLBException(Exception):
    """Base-class for all GeLB exceptins."""
    def __init__(self, error, hint):
        # we rely on the custom fields {error,hint} because we want to do our
        # own printing (instead of relying on the Python default)
        self.error = error
        self.hint = hint
        if not _suppress_print_and_exit():
            print(self)

    def _source_location(self):
        """Subclass hook: return ``(line, col)`` to anchor the error
        display at a specific source location, or ``None`` to use the
        default error+hint banner.  When a location is returned,
        :meth:`__str__` displays the offending source line via
        :func:`show_error_in_src`; when ``None``, it falls back to
        :func:`error_with_hint_to_term`.
        """
        return None

    def __str__(self):
        if _suppress_print_and_exit():
            return f"{self.error}: {self.hint}"
        loc = self._source_location()
        if loc is not None:
            show_error_in_src(loc[0], loc[1], self.error, self.hint)
        else:
            error_with_hint_to_term(self.error, self.hint)
        os._exit(1)  # really abort


class GeLBExIncorrectStagesOrdering(GeLBException):
    """
    GeLB exception, for attempts to invoke a compiler stage before its time.
    """
    def __init__(self, error, hint=feedback_on_slack_hint):
        super().__init__(error, hint)


class GeLBExInvalidGrammarRule(GeLBException):
    """
    GeLB exception, for attempts to use a parser rule which is not part of
    the grammar.
    """
    def __init__(self, rule_name):
        error = (
            f"(internal) can't find rule"
            f" {click.style(rule_name, underline=True) + Fore.RED}"
            f" @GeLBParser"
        )
        hint = (
            f"If you are a GeLB developer, please check whether rule"
            f" {click.style(rule_name, underline=True) + Fore.GREEN}"
            f" is part of the grammar (look @"
            f"{click.style('GeLB.g4', underline=True) + Fore.GREEN}"
            f" file). " + feedback_on_slack_hint
        )
        super().__init__(error, hint)


class GeLBExMissingCSTVisitationMethod(GeLBException):
    """
    GeLB exception, for attempting to invoke a CST visitation method which
    has not been defined.
    """
    def __init__(self, rule_name):
        visitation_method_name = f"visit{rule_name.capitalize()}"
        error = (
            f"(internal) can't find method"
            f" {click.style(visitation_method_name, underline=True) + Fore.RED}"
            f" @{click.style('ASTBuilderVisitor', underline=True) + Fore.RED}"
        )
        hint = (
            f"If you are a GeLB developer, please check whether rule"
            f" {click.style(rule_name, underline=True) + Fore.GREEN}"
            f" is part of the grammar (look "
            f"@{click.style('GeLB.g4', underline=True) + Fore.GREEN}"
            f" file). Also, check that the ANTLR4 Java tool actually"
            f" generated a method named "
            f"{click.style(visitation_method_name, underline=True) + Fore.GREEN}"
            f" (look"
            f" @{click.style('GeLBVisitor.py', underline=True) + Fore.GREEN}"
            f"). " + feedback_on_slack_hint
        )
        super().__init__(error, hint)


class GeLBExMissingASTVisitationMethod(GeLBException):
    """
    GeLB exception, for attempting to invoke an AST visitation method which
    has not been defined.
    """
    def __init__(self, visitor_subclass_name, visitation_method_name):
        error = (
            f"(internal) can't find method "
            f"{click.style(visitation_method_name, underline=True) + Fore.RED}"
            f" @"
            f"{click.style(visitor_subclass_name, underline=True) + Fore.RED}"
        )
        hint = (
            f"If you are a GeLB developer (maybe implementing a new compiler "
            f"pass) please check whether you actually defined the appropriate "
            f"method in your ASTBaseVisitor subclass"
            f" (i.e. "
            f"{click.style(visitor_subclass_name, underline=True) + Fore.GREEN}"
            f"). " + feedback_on_slack_hint

        )
        super().__init__(error, hint)


class GeLBExSyntaxError(GeLBException):
    """
    GeLB exception, for catching syntax errors raised by the generated parser.

    NOTE: Attempts to use a reserved keyword as an identifier are also
    reported by ANTLR4 as plain syntax errors -- it is better to check for
    that particular case, s.t. we give a better error-message.
    """
    def __init__(self, line, column, error, hint):
        self.line = line
        self.column = column

        # check the special case of trying to use a reserved keyword as an
        # identifier
        import re
        if re.search("^mismatched input \'.*\' expecting ID$", hint):
            # extract keyword
            keyword = re.sub(
                "^mismatched input \'", "",
                re.sub("\' expecting ID$", "", hint)
            )
            if keyword in config.GELB_RESERVED_KEYWORDS:
                # construct a better hint
                hint = (
                    f"You cannot use"
                    f" {click.style(keyword, underline=True) + Fore.GREEN}"
                    f" as an identifier, because it is a reserved keyword."
                    f" Please choose another identifier."
                )

        super().__init__(error, hint)

    def _source_location(self):
        return (self.line, self.column)


class GeLBExInvalidNoOfOccurrences(GeLBException):
    """
    GeLB exception, for signaling an invalid number of high-level block
    occurrences.
    """
    def __init__(self, block_name, no_occurrences,
                 line, column):
        self.line = line
        self.column = column
        # Initialize error & hint, for the case when an invalid number of
        # occurrences is not (yet) properly handled by the code below.
        error = (
            f"(internal) GeLBExInvalidNoOfOccurrences cannot handle "
            f"{click.style(block_name, underline=True) + Fore.RED}."
        )
        hint = (
            feedback_on_slack_hint
        )

        if block_name == "set_simulation_description_stmt":
            informal_name = "simulation_description"
            if no_occurrences == 0:
                error = (
                    f"You do not specify a"
                    f" {click.style(informal_name, underline=True) + Fore.RED}"
                    f" statement."
                )
                hint = (
                    f"Every GeLB program needs to have a line like the"
                    f" following:\n\n"
                    f"simulation_description(\"my_simulation_description\");"
                    f"\n\n" + learning_gelb_hint
                )
            elif no_occurrences > 1:
                error = (
                    f"You specify more than one"
                    f" {click.style(informal_name, underline=True) + Fore.RED}"
                    f" statement."
                )
                hint = (
                    f"Every GeLB program needs to have exactly"
                    f" *one* such statement. " + learning_gelb_hint
                )
        elif block_name == "global_constants_block":
            informal_name = "global_constants"
            if no_occurrences > 1:
                error = (
                    f"You specify more than one"
                    f" {click.style(informal_name, underline=True) + Fore.RED}"
                    f" block."
                )
                hint = (
                    f"Every GeLB program may contain at most"
                    f" *one* such block. " + learning_gelb_hint
                )
        elif block_name == "lattices_block":
            if no_occurrences == 0:
                error = (
                    f"You do not specify a"
                    f" {click.style('lattices', underline=True) + Fore.RED}"
                    f" block."
                )
                hint = (
                    f"Every GeLB program needs to have exactly"
                    f" *one* "
                    f" {click.style('lattices', underline=True) + Fore.GREEN}"
                    f" block. " + learning_gelb_hint
                )
            elif no_occurrences > 1:
                error = (
                    f"You specify more than one "
                    f" {click.style('lattices', underline=True) + Fore.RED}"
                    f" block."
                )
                hint = (
                    f"Every GeLB program needs to have exactly *one* "
                    f" {click.style('lattices', underline=True) + Fore.GREEN}"
                    f" block. " + learning_gelb_hint
                )
        elif block_name == "initializer_block":
            if no_occurrences == 0:
                error = (
                    f"You do not specify any "
                    f"{click.style('initializer', underline=True) + Fore.RED}"
                    f" block."
                )
                hint = (
                    f"Every GeLB program needs to have *at "
                    f"least one* "
                    f"{click.style('initializer', underline=True) + Fore.GREEN}"
                    f" block. " + learning_gelb_hint
                )
        elif block_name == "dynamic_block":
            if no_occurrences == 0:
                error = (
                    f"You do not specify any "
                    f"{click.style('dynamic', underline=True) + Fore.RED}"
                    f" block."
                )
                hint = (
                    f"Every GeLB program needs to have *at "
                    f"least one* "
                    f"{click.style('dynamic', underline=True) + Fore.GREEN}"
                    f" block. " + learning_gelb_hint
                )
        elif block_name == "gauge_block":
            if no_occurrences == 0:
                error = (
                    f"You do not specify any "
                    f"{click.style('gauge', underline=True) + Fore.RED}"
                    f" block."
                )
                hint = (
                        f"Every GeLB program needs to have *at "
                        f"least one* "
                        f"{click.style('gauge', underline=True) + Fore.GREEN}"
                        f" block. " + learning_gelb_hint
                )
        elif block_name == "node_classes_block":
            informal_name = "node_classes"
            if no_occurrences == 0:
                error = (
                    f"You do not specify a "
                    f"{click.style(informal_name, underline=True) + Fore.RED}"
                    f" block."
                )
                hint = (
                    f"Every GeLB program needs to have exactly *one* "
                    f"{click.style(informal_name, underline=True) + Fore.GREEN}"
                    f" block. " + learning_gelb_hint
                )
            elif no_occurrences > 1:
                error = (
                    f"You specify more than one "
                    f"{click.style(informal_name, underline=True) + Fore.RED}"
                    f" block."
                )
                hint = (
                        f"Every GeLB program needs to have exactly *one* "
                        f"{click.style(informal_name, underline=True) + Fore.GREEN}"
                        f" block. " + learning_gelb_hint
                )
        elif block_name == "geometry_block":
            if no_occurrences == 0:
                error = (
                    f"You do not specify a "
                    f"{click.style('geometry', underline=True) + Fore.RED}"
                    f" block."
                )
                hint = (
                    f"Every GeLB program needs to have exactly *one* "
                    f"{click.style('geometry', underline=True) + Fore.GREEN}"
                    f" block. " + learning_gelb_hint
                )
            elif no_occurrences > 1:
                error = (
                    f"You specify more than one "
                    f"{click.style('geometry', underline=True) + Fore.RED}"
                    f" block."
                )
                hint = (
                        f"Every GeLB program needs to have exactly *one* "
                        f"{click.style('geometry', underline=True) + Fore.GREEN}"
                        f" block. " + learning_gelb_hint
                )
        super().__init__(error, hint)

    def _source_location(self):
        if self.line is not None and self.column is not None:
            return (self.line, self.column)
        return None


class GeLBExIncorrectInputFileExtension(GeLBException):
    """
    GeLB exception, for signaling an incorrect input-file extension.
    """
    def __init__(self, input_file_name):
        error = (
            f"Your input file "
            f"{click.style(input_file_name, underline=True) + Fore.RED}"
            f" does not have the "
            f"{click.style('.gelb', underline=True) + Fore.RED}"
            f" extension."
        )
        hint = (
            f"Please speficy a file that ends in "
            f"{click.style('.gelb', underline=True) + Fore.RED}"
        )
        super().__init__(error, hint)


class GeLBExCouldNotFindInputFile(GeLBException):
    """
    GeLB exception, for signaling that the input file could not be found.
    """
    def __init__(self, input_file_name, suggest_files):
        error = (
            f"Could not find the input file "
            f"{click.style(input_file_name, underline=True) + Fore.RED}."
        )
        hint = (
            f"Please specify a file that exists."
        )
        if suggest_files:
            hint += (
                f" Maybe you meant one of the following files?"
                f" {suggest_files}"
            )
        super().__init__(error, hint)


class GeLBExCouldNotReadInputFile(GeLBException):
    """
    GeLB exception, for signaling that the input file could not be read (
    presumably due to file-permission errors).
    """
    def __init__(self, input_file_name):
        error = (
            f"Could not read the input file "
            f"{click.style(input_file_name, underline=True) + Fore.RED}."
        )
        hint = (
            f"Change permissions for file "
            f"{click.style(input_file_name, underline=True) + Fore.GREEN},"
            f" to allow gelbc to read it."
        )
        super().__init__(error, hint)


class GeLBExEmptyInputFile(GeLBException):
    """
    GeLB exception, for signaling that the input file does not contain any
    code (could be empty, or just whitespace).
    """
    def __init__(self, input_file_name=None):
        error = (
            f"The input file "
            f"{click.style(input_file_name, underline=True) + Fore.RED}"
            f" does not contain any GeLB code."
        )
        hint = (
            f"{learning_gelb_hint}"
        )
        super().__init__(error, hint)


class GeLBExAntlr4JavaLibNotFound(GeLBException):
    """
    GeLB exception, for signaling that the ANTLR4 Java library (jar) file
    isn't where we expect it to be.
    """
    def __init__(self, antlr4_lib_path):
        error = (
            f"Could not find the Antlr4 java library file"
            f" (expected location was "
            f"{click.style(antlr4_lib_path, underline=True) + Fore.RED})."
        )
        hint = (
            f"Download the file from https://antlr.org and"
            f" copy it to the expected location."
        )
        super().__init__(error, hint)


class GeLBExPython3PackageMissing(GeLBException):
    """
    GeLB exception, for signaling that a Python3 package is missing.
    """
    def __init__(self, package_name):
        error = (
            f"Could not find the "
            f"{click.style(package_name, underline=True) + Fore.RED}"
            f" Python3 package."
        )
        hint = (
            f"If you are a GeLB developer, please install "
            f"Anaconda and run the command"
            f" \"conda env create -f gelb.yml\" from the root-dir of your"
            f" GeLB repository clone. " + feedback_on_slack_hint
        )
        super().__init__(error, hint)


class GeLBExGrammarFileNotFound(GeLBException):
    """
    GeLB exception, for signaling that the GeLB.g4 grammar file is missing.
    """
    def __init__(self, grammar_path):
        error = (
            f"Could not find the "
            f"{click.style(grammar_path, underline=True) + Fore.RED}"
            f" file."
        )
        hint = (
            f"If you are a GeLB developer, you can try"
            f" restoring it with \"git checkout\". " + feedback_on_slack_hint
        )
        super().__init__(error, hint)


class GeLBExAntlr4JavaToolFailed(GeLBException):
    """
    GeLB exception, for signaling that the ANTLR4 Java tool failed to compile
    the grammar.
    """
    def __init__(self, antlr4_tool_stat):
        error = (
            f"The ANTLR4 Java tool failed to compile the "
            f"{click.style('GeLB.g4', underline=True) + Fore.RED}"
            f" grammar."
        )
        hint = (
            f"If you are a GeLB developer (perhaps working on the "
            f"grammar), try to compile it manually.\n\n" +
            feedback_on_slack_hint
        )
        super().__init__(error, hint)


class GeLBExSymbolExists(GeLBException):
    """
    GeLB exception, for signaling that another symbol with the same name
    exists within the same scope.
    """
    def __init__(self, curr_instance, prev_instance):
        self.prev_instance = prev_instance
        self.curr_instance = curr_instance
        name = curr_instance.name
        error = (
            f"You define a {curr_instance.tag}"
            f" named"
            f" {click.style(name, underline=True) + Fore.RED}."
            f" However, you are using that name (as "
            f"{prev_instance.tag}) already."
        )
        hint = (
            f"Rename (or remove) one of the instances of "
            f"{click.style(name, underline=True) + Fore.GREEN}"
            f"."
        )
        super().__init__(error, hint)

    def __str__(self):
        """Show both definitions, with the error and hint at the new one."""
        if _suppress_print_and_exit():
            return f"{self.error}: {self.hint}"
        show_double_definition_error(
            self.curr_instance.value.code_range.start_line,
            self.curr_instance.value.code_range.start_col,
            self.prev_instance.value.code_range.start_line,
            self.prev_instance.value.code_range.start_col,
            self.prev_instance.name,
            self.prev_instance.tag,
            self.error,
            self.hint,
        )
        os._exit(1)


class GeLBExSymbolUnknown(GeLBException):
    """
    GeLB exception, for signaling that a symbol is unknown.
    """
    def __init__(self, symbol_ref):
        self.symbol_ref = symbol_ref
        name = symbol_ref.name
        error = (
            f"You mention"
            f" {click.style(name, underline=True) + Fore.RED}."
            f" However, you did not define it."
        )
        hint = (
            f"Define"
            f" {click.style(name, underline=True) + Fore.GREEN}."
        )
        super().__init__(error, hint)

    def _source_location(self):
        return (self.symbol_ref.code_range.start_line,
                self.symbol_ref.code_range.start_col)


class GeLBExSymbolConstantRecursion(GeLBException):
    """
    GeLB exception, for signaling that a symbol is defined in terms of itself.
    """
    def __init__(self, symbol_ref):
        self.symbol_ref = symbol_ref
        name = symbol_ref.name
        error = (
            f"You define the constant"
            f" {click.style(name, underline=True) + Fore.RED}"
            f" with an expression which depends on"
            f" {click.style(name, underline=True) + Fore.RED}"
            f" itself."
        )
        hint = (
            f"The expression assigned to a constant may depend only on"
            f" literal values or on other (already-defined) constants."
        )
        super().__init__(error, hint)

    def _source_location(self):
        return (self.symbol_ref.code_range.start_line,
                self.symbol_ref.code_range.start_col)


class GeLBExFunctionRecursion(GeLBException):
    """
    GeLB exception, for signaling that user-defined functions form a
    recursive call cycle (e.g. A -> B -> A).
    """
    def __init__(self, call_node, cycle_path):
        self.call_node = call_node
        self.cycle_path = cycle_path
        cycle_str = ' → '.join(cycle_path)
        error = (
            f"Function"
            f" {click.style(cycle_path[0], underline=True) + Fore.RED}"
            f" is part of a recursive call cycle:"
            f" {click.style(cycle_str, underline=True) + Fore.RED}."
        )
        hint = (
            f"GeLB functions must be non-recursive"
            f" (they are inlined at compile time)."
        )
        super().__init__(error, hint)

    def _source_location(self):
        return (self.call_node.code_range.start_line,
                self.call_node.code_range.start_col)


class GeLBExSymbolWrongType(GeLBException):
    """
    GeLB exception, for signaling that a symbol of the wrong type is used.
    """
    def __init__(self, symbol_ref, expected_type):
        self.symbol_ref = symbol_ref
        name = symbol_ref.name
        error = (
            f"You specify"
            f" {click.style(name, underline=True) + Fore.RED}."
            f" However, I expected the name of a"
            f" {click.style(expected_type) + Fore.RED} here."
        )
        hint = f"Specify the name of a {expected_type}."
        super().__init__(error, hint)

    def _source_location(self):
        return (self.symbol_ref.code_range.start_line,
                self.symbol_ref.code_range.start_col)


class GeLBExSymbolRefBeforeDef(GeLBException):
    """
    GeLB exception, for signaling that a symbol is referenced before it is
    defined.
    """
    def __init__(self, symbol_ref, symbol_def):
        self.symbol_ref = symbol_ref
        self.symbol_def = symbol_def
        name = symbol_ref.name
        def_line = symbol_def.value.code_range.start_line
        self.error = (
            f"You reference"
            f" {click.style(name, underline=True) + Fore.RED}."
            f" However, you only define it later (on line"
            f" {click.style(def_line, underline=True) + Fore.RED}"
            f")."
        )
        self.hint = (
            f"Please move the definition (from line"
            f" {click.style(def_line, underline=True) + Fore.GREEN})"
            f" above the first reference."
        )
        super().__init__(self.error, self.hint)

    def _source_location(self):
        return (self.symbol_ref.code_range.start_line,
                self.symbol_ref.code_range.start_col)


class GeLBExSymbolNotAllowedHere(GeLBException):
    """
    GeLB exception, for signaling when a certain symbol is not allowed in a
    particular block.
    """
    def __init__(self, symbol_ref, error, hint):
        self.symbol_ref = symbol_ref
        self.error = error
        self.hint = hint

        super().__init__(self.error, self.hint)

    def _source_location(self):
        return (self.symbol_ref.code_range.start_line,
                self.symbol_ref.code_range.start_col)


class GeLBExConstantAssignment(GeLBException):
    """
    GeLB exception, for signaling that a constant is being assigned to (which is not allowed).
    """
    def __init__(self, identifier_node, symbol_def):
        self.identifier_node = identifier_node
        self.symbol_def = symbol_def
        name = identifier_node.name
        error = (
            f"You are trying to assign a value to"
            f" {click.style(name, underline=True) + Fore.RED}."
            f" However, {click.style(name, underline=True) + Fore.RED}"
            f" is a constant and cannot be modified."
        )
        hint = (
            f"Constants are immutable once defined. If you need to modify"
            f" {click.style(name, underline=True) + Fore.GREEN},"
            f" declare it as a variable instead, or use a different name."
        )
        super().__init__(error, hint)

    def _source_location(self):
        return (self.identifier_node.code_range.start_line,
                self.identifier_node.code_range.start_col)


class GeLBExTypeError(GeLBException):
    """
    GeLB exception, for signaling type validation errors.
    
    This exception is raised when type validation fails after type promotion,
    indicating incompatible types in operations or assignments.
    """
    def __init__(self, node, error, hint):
        self.node = node
        super().__init__(error, hint)
    
    def _source_location(self):
        return (self.node.code_range.start_line,
                self.node.code_range.start_col)


class GeLBExStencilError(GeLBException):
    """
    GeLB exception for stencil-level validation errors.

    Raised when compile-time stencil analysis detects issues such as
    uninitialized lattice DFs or out-of-bounds lattice access.
    When source_line is provided, anchors the diagnostic at the block
    name; source_end_line is retained for machine-readable ranges.
    """
    def __init__(self, error, hint, source_line=None, source_end_line=None):
        self.source_line = source_line
        self.source_end_line = source_end_line
        super().__init__(error, hint)

    def _source_location(self):
        if self.source_line is not None:
            from gelb.utils.error_utils import source_anchor_column
            return self.source_line, source_anchor_column(self.source_line, self.error)
        return None


class GeLBExGeometryDiscontinuity(GeLBException):
    """GeLB exception, for signaling that the painted geometry has a
    node-class discontinuity at the wrap edge of an axis declared
    periodic.

    Periodic wrapping would silently stream distribution functions
    across the discontinuity, producing wrong results.  The user must
    either make the geometry continuous at that wrap edge or declare
    the axis non-periodic in the lattice declaration.
    """
    def __init__(self, axis_name, coord_first, coord_last,
                 nc_first, nc_last, periodicity_stmt=None):
        self.axis_name = axis_name
        self.coord_first = coord_first
        self.coord_last = coord_last
        self.nc_first = nc_first
        self.nc_last = nc_last
        self.periodicity_stmt = periodicity_stmt
        error = (
            f"Axis {click.style(axis_name, underline=True) + Fore.RED}"
            f" is declared periodic, but cell"
            f" {click.style(str(coord_first), underline=True) + Fore.RED}"
            f" is {click.style(nc_first, underline=True) + Fore.RED}"
            f" while its wrap-partner"
            f" {click.style(str(coord_last), underline=True) + Fore.RED}"
            f" is {click.style(nc_last, underline=True) + Fore.RED}."
            f" Periodic wrapping would stream across an NC boundary."
        )
        hint = (
            f"Either make the geometry continuous at the wrap edge of"
            f" axis {click.style(axis_name, underline=True) + Fore.GREEN},"
            f" or declare that axis as non-periodic in the"
            f" lattice declaration."
        )
        super().__init__(error, hint)

    def _source_location(self):
        if self.periodicity_stmt is None:
            return None
        cr = self.periodicity_stmt.code_range
        return (cr.start_line, cr.start_col)
