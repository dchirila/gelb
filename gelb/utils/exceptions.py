#!/usr/bin/env python3

import os
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


class GeLBExInvalidGrammarRule(GeLBException):
    """
    GeLB exception, for attempts to use a parser rule which is not part of
    the grammar.
    """
    def __init__(self, rule_name):
        error = f"(internal) can't find rule \"{rule_name}\" @GeLBParser"
        hint = (
            f"If you are a GeLB developer, please check whether rule"
            f" \"{rule_name}\" is part of the grammar (look @\"GeLB.g4\""
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
            f"(internal) can't find method \"{visitation_method_name}\""
            f"@ASTBuilderVisitor"
        )
        hint = (
            f"If you are a GeLB developer, please check whether rule"
            f" \"{rule_name}\" is part of the grammar (look @\"GeLB.g4\""
            f" file). Also, check that the ANTLR4 Java tool actually"
            f" generated a method named \"{visitation_method_name}\" (look"
            f" @\"GeLBVisitor.py\"). " + feedback_on_slack_hint

        )
        super().__init__(error, hint)


class GeLBExMissingASTVisitationMethod(GeLBException):
    """
    GeLB exception, for attempting to invoke an AST visitation method which
    has not been defined.
    """
    def __init__(self, visitor_subclass_name, visitation_method_name):
        error = (
            f"(internal) can't find method \"{visitation_method_name}\""
            f"@{visitor_subclass_name}"
        )
        hint = (
            f"If you are a GeLB developer (maybe implementing a new compiler "
            f"pass) please check whether you actually defined the appropriate "
            f"method in your ASTBaseVisitor subclass"
            f" (i.e. \"{visitor_subclass_name}\"). " + feedback_on_slack_hint

        )
        super().__init__(error, hint)


class GeLBExSyntaxError(GeLBException):
    """
    GeLB exception, for catching syntax errors raised by the generated parser.
    """
    def __init__(self, line, column, error, hint):
        self.line = line
        self.column = column
        super().__init__(error, hint)
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
            if no_occurrences == 0:
                error = (
                    f"We see that you do not specify a \"simulation_name\""
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
                    f"We see that you specify more than one \"simulation_name\""
                    f" statement."
                )
                hint = (
                    f"Every GeLB program needs to have exactly *one* such"
                    f" statement. " + learning_gelb_hint
                )
        elif block_name == "set_simulation_description_stmt":
            if no_occurrences == 0:
                error = (
                    f"We see that you do not specify a"
                    f" \"simulation_description\" statement."
                )
                hint = (
                        f"Every GeLB program needs to have a line like the"
                        f" following:\n\n"
                        f"simulation_description(\"my_simulation_description\");"
                        f"\n\n" +
                        learning_gelb_hint
                )
            elif no_occurrences > 1:
                error = (
                    f"We see that you specify more than one"
                    f" \"simulation_description\" statement."
                )
                hint = (
                        f"Every GeLB program needs to have exactly"
                        f" *one* such statement. " + learning_gelb_hint
                )
        elif block_name == "global_constants_block":
            if no_occurrences > 1:
                error = (
                    f"We see that you specify more than one"
                    f" \"global_constants\" block."
                )
                hint = (
                        f"Every GeLB program may contain at most"
                        f" *one* such block. " +
                        learning_gelb_hint
                )
        elif block_name == "lattices_block":
            if no_occurrences == 0:
                error = (
                    f"We see that you do not specify a"
                    f" \"lattices\" block."
                )
                hint = (
                        f"Every GeLB program needs to have exactly"
                        f" *one* lattices block. " +
                        learning_gelb_hint
                )
            elif no_occurrences > 1:
                error = (
                    f"We see that you specify more than one"
                    f" \"lattices\" block."
                )
                hint = (
                        f"Every GeLB program needs to have exactly"
                        f" *one* such block. " + learning_gelb_hint
                )
        elif block_name == "initializer_block":
            if no_occurrences == 0:
                error = (
                    f"We see that you do not specify any"
                    f" \"initializer\" block."
                )
                hint = (
                        f"Every GeLB program needs to have *at "
                        f"least one* initializer block. " +
                        learning_gelb_hint
                )
        elif block_name == "dynamic_block":
            if no_occurrences == 0:
                error = (
                    f"We see that you do not specify any"
                    f" \"dynamic\" block."
                )
                hint = (
                        f"Every GeLB program needs to have *at "
                        f"least one* dynamic block. " +
                        learning_gelb_hint
                )
        elif block_name == "gauge_block":
            if no_occurrences == 0:
                error = (
                    f"We see that you do not specify any"
                    f" \"gauge\" block."
                )
                hint = (
                        f"Every GeLB program needs to have *at "
                        f"least one* gauge block. " +
                        learning_gelb_hint
                )
        elif block_name == "node_classes_block":
            if no_occurrences == 0:
                error = (
                    f"We see that you do not specify a"
                    f" \"node_classes\" block."
                )
                hint = (
                        f"Every GeLB program needs to have exactly"
                        f" *one* node_classes block. " +
                        learning_gelb_hint
                )
            elif no_occurrences > 1:
                error = (
                    f"We see that you specify more than one"
                    f" \"node_classes\" block."
                )
                hint = (
                        f"Every GeLB program needs to have exactly"
                        f" *one* such block. " + learning_gelb_hint
                )
        elif block_name == "geometry_block":
            if no_occurrences == 0:
                error = (
                    f"We see that you do not specify a"
                    f" \"geometry\" block."
                )
                hint = (
                        f"Every GeLB program needs to have exactly"
                        f" *one* geometry block. " +
                        learning_gelb_hint
                )
            elif no_occurrences > 1:
                error = (
                    f"We see that you specify more than one"
                    f" \"geometry\" block."
                )
                hint = (
                        f"Every GeLB program needs to have exactly"
                        f" *one* such block. " + learning_gelb_hint
                )
        else:
            error = (
                f"(internal) GeLBExInvalidNoOfOccurrences cannot handle"
                f" \"{block_name}\"."
            )
            hint = (
                feedback_on_slack_hint
            )
        super().__init__(error, hint)
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
            f"[Problem] We notice that your input file \"{input_file_name}\""
            f" does not have the \".gelb\" extension."
        )
        hint = (
            f"[Hint] Please speficy a file that ends in \".gelb\""
        )
        super().__init__(error, hint)


class GeLBExCouldNotFindInputFile(GeLBException):
    """
    GeLB exception, for signaling that the input file could not be found.
    """
    def __init__(self, input_file_name, suggest_files):
        error = (
            f"[Problem] We could not find the input file \"{input_file_name}\"."
        )
        hint = (
            f"[Hint] Please specify a file that exists."
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
            f"[Problem] We could not read the input file \"{input_file_name}\"."
        )
        hint = (
            f"[Hint] Change permissions for file \"{input_file_name}\","
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
            f"[Problem] The input file \"{input_file_name}\" does not"
            f" contain any GeLB code."
        )
        hint = (
            f"[Hint] {learning_gelb_hint}"
        )
        super().__init__(error, hint)


class GeLBExAntlr4JavaLibNotFound(GeLBException):
    """
    GeLB exception, for signaling that the ANTLR4 Java library (jar) file
    isn't where we expect it to be.
    """
    def __init__(self, antlr4_lib_path):
        error = (
            f"[Problem] We could not find the Antlr4 java library file"
            f" (expecting location was \"{antlr4_lib_path}\")."
        )
        hint = (
            f"[Hint] Download the file from"
            f" https://antlr.org and copy it to the expected location."
        )
        super().__init__(error, hint)


class GeLBExPython3PackageMissing(GeLBException):
    """
    GeLB exception, for signaling that a Python3 package is missing.
    """
    def __init__(self, package_name):
        error = (
            f"[Problem] We could not find the \"{package_name}\" Python3 "
            f"package."
        )
        hint = (
            f"[Hint] If you are a GeLB developer, please install "
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
            f"[Problem] We could not find the \"{grammar_path}\" file."
        )
        hint = (
                f"[Hint] If you are a GeLB developer, you can try"
                f" restoring it with \"git checkout\". " +
                feedback_on_slack_hint
        )
        super().__init__(error, hint)


class GeLBExAntlr4JavaToolFailed(GeLBException):
    """
    GeLB exception, for signaling that the ANTLR4 Java tool failed to compile
    the grammar.
    """
    def __init__(self, antlr4_tool_stat):
        error = (
            f"[Problem] The ANTLR4 Java tool failed to compile the "
            f"\"GeLB.g4\" grammar."
        )
        hint = (
                f"[Hint] If you are a GeLB developer (perhaps working on the "
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
        error = (
            f"We see that you define a {curr_instance['type']}"
            f" named \"{curr_instance['name']}\"."
            f" However, you are using that name (for a "
            f"{prev_instance['type']}) already."
        )
        hint = (
            f"Rename (or remove) one of the instances of"
            f" \"{curr_instance['name']}\"."
        )
        super().__init__(error, hint)
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            print(self)

    def __str__(self):
        """Override base-class's __str__, because we want to print the code"""
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            show_double_definition_error(
                self.curr_instance['value'].code_range.start_line,
                self.curr_instance['value'].code_range.start_col,
                self.prev_instance['value'].code_range.start_line,
                self.prev_instance['value'].code_range.start_col,
                self.prev_instance['name'],
                self.prev_instance['type']
            )
            super().__str__()
            os._exit(1)  # really abort

