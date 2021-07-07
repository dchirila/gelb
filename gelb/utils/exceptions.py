#!/usr/bin/env python3

import os
import click
from colorama import Fore, Style

import gelb.utils.config
from gelb.utils.output_to_terminal import error_with_hint_to_term
from gelb.utils.error_utils import (
    feedback_on_slack_hint,
    learning_gelb_hint,
    show_error_in_src,
    show_double_definition_error
)


class GeLBException(Exception):
    """Base-class for all GeLB exceptins."""
    def __init__(self, error, hint):
        # we rely on the custom fields {error,hint} because we want to do our
        # own printing (instead of relying on the Python default)
        self.error = error
        self.hint = hint

    def __str__(self):
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            error_with_hint_to_term(self.error, self.hint)
            os._exit(1)  # really abort


class GeLBExIncorrectStagesOrdering(GeLBException):
    """
    GeLB exception, for attempts to invoke a compiler stage before its time.
    """
    def __init__(self, error, hint=feedback_on_slack_hint):
        super().__init__(error, hint)
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)


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
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)


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
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)


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
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)


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
            if keyword in gelb.utils.config.GELB_RESERVED_KEYWORDS:
                # construct a better hint
                hint = (
                    f"You cannot use"
                    f" {click.style(keyword, underline=True) + Fore.GREEN}"
                    f" as an identifier, because it is a reserved keyword."
                    f" Please choose another identifier."
                )

        super().__init__(error, hint)
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)

    def __str__(self):
        """Override base-class's __str__, because we want to print the code"""
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            show_error_in_src(self.line, self.column, self.error, self.hint)
            os._exit(1)  # really abort


class GeLBExInvalidNoOfOccurrences(GeLBException):
    """
    GeLB exception, for signaling an invalid number of high-level block
    occurrences.
    """
    def __init__(self, block_name, no_occurrences,
                 line, column):
        self.line = line
        self.column = column

        if block_name == "set_simulation_name_stmt":
            informal_name = "simulation_name"
            if no_occurrences == 0:
                error = (
                    f"You do not specify a "
                    f"{click.style(informal_name, underline=True) + Fore.RED}"
                    f" statement."
                )
                hint = (
                    f"Every GeLB program needs to have a line like the"
                    f" following:\n\n"
                    f"simulation_name(\"my_simulation_name\");\n\n" +
                    learning_gelb_hint
                )
            elif no_occurrences > 1:
                error = (
                    f"You specify more than one "
                    f"{click.style(informal_name, underline=True) + Fore.RED}"
                    f" statement."
                )
                hint = (
                    f"Every GeLB program needs to have exactly *one* such"
                    f" statement. " + learning_gelb_hint
                )
        elif block_name == "set_simulation_description_stmt":
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
        else:
            error = (
                f"(internal) GeLBExInvalidNoOfOccurrences cannot handle "
                f"{click.style(block_name, underline=True) + Fore.RED}."
            )
            hint = (
                feedback_on_slack_hint
            )
        super().__init__(error, hint)
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)

    def __str__(self):
        """
        Override base-class's __str__, because we want to print the code (but
        only sometimes).
        """
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            if (self.line is not None) and (self.column is not None):
                show_error_in_src(self.line, self.column, self.error, self.hint)
            else:
                super().__str__()
            os._exit(1)  # really abort


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
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)


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
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)


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
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)


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
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)


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
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)


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
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)


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
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)


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
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)


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
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)

    def __str__(self):
        """Override base-class's __str__, because we want to print the code"""
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            show_double_definition_error(
                self.curr_instance.value.code_range.start_line,
                self.curr_instance.value.code_range.start_col,
                self.prev_instance.value.code_range.start_line,
                self.prev_instance.value.code_range.start_col,
                self.prev_instance.name,
                self.prev_instance.tag
            )
            super().__str__()
            os._exit(1)  # really abort


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
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)

    def __str__(self):
        """Override base-class's __str__, because we want to print the code"""
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            show_error_in_src(
                self.symbol_ref.code_range.start_line,
                self.symbol_ref.code_range.start_col,
                self.error, self.hint
            )
            # super().__str__()
            os._exit(1)  # really abort


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
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)

    def __str__(self):
        """Override base-class's __str__, because we want to print the code"""
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            show_error_in_src(
                self.symbol_ref.code_range.start_line,
                self.symbol_ref.code_range.start_col,
                self.error, self.hint
            )
            # super().__str__()
            os._exit(1)  # really abort

