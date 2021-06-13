#!/usr/bin/env python3

from gelb.utils.output_to_terminal import fatal_error_with_hint_to_term

generic_hint = (
    f"visit https://gelb-lang.org to learn how to write your first "
    f"GeLB programs"
)


def complain_about_missing_cst_visitation_method(rule, visitation_method_name):
    fatal_error_with_hint_to_term(
        f"(internal) can't find method \"{visitation_method_name}\""
        f"@ASTBuilderVisitor",
        # hint
        f"If you are a GeLB developer, please check whether rule"
        f" \"{rule}\" is part of the grammar (look @\"GeLB.g4\""
        f" file). Also, check that the ANTLR4 Java tool actually"
        f" generated a method named \"{visitation_method_name}\" (look"
        f" @\"GeLBVisitor.py\").\n\n"
        f"If you are a GeLB user, please report this error on our"
        f" Slack #feedback channel (https://gelb-devs.slack.com)."
    )


def complain_about_missing_ast_visitation_method(class_name,
                                                 visitation_method_name):
    fatal_error_with_hint_to_term(
        f"(internal) can't find method \"{visitation_method_name}\""
        f"@{class_name}",
        # hint
        f"If you are a GeLB developer (maybe implementing a new compiler "
        f"pass) please check whether you actually defined the appropriate "
        f"method in your ASTBaseVisitor subclass (i.e. \"{class_name}\").\n\n"
        f"If you are a GeLB user, please report this error on our"
        f" Slack #feedback channel (https://gelb-devs.slack.com)."
    )


def complain_about_invalid_grammar_rule(rule):
    fatal_error_with_hint_to_term(
        f"(internal) can't find rule \"{rule}\" @GeLBParser",
        # hint
        f"If you are a GeLB developer, please check whether rule"
        f" \"{rule}\" is part of the grammar (look @\"GeLB.g4\""
        f" file).\n\n"
        f"If you are a GeLB user, please report this error on our"
        f" Slack #feedback channel (https://gelb-devs.slack.com)."
    )

def complain_about_invalid_no_of_block_occurrences(name, min, max, line, col):
    if (max == 1):
        error_msg = (
            f"(see line:{line}, column:{col}) "
            f"We see that you declare the \"{name}\" more "
            f"than once. "
        )
        if (min == 1):
            error_msg += (
                f"However, we expect exactly one instance of \"{name}\"."
            )
        elif (min == 0):
            error_msg += (
                f"However, we expect at most one instance of \"{name}\" "
                f"(or none -- it is optional, because not all simulations "
                f"need it)."
            )
        fatal_error_with_hint_to_term(
            error_msg,
            generic_hint
        )
    else:  # max > 1
        raise NotImplementedError()
