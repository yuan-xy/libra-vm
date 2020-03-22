from __future__ import annotations
from functional_tests.checker import *
from functional_tests.compiler import Compiler
from functional_tests.config.globl import Config as GlobalConfig
from functional_tests.evaluator import eeval
from functional_tests.preprocessor import build_transactions, split_input
from pathlib import Path


char = str

def at_most_n_chars(s: List[char], n: usize) -> str:
    if len(s) > n:
        return s[0:n] + "..."
    else:
        return s


def at_most_n_before_and_m_after(
    s: str,
    n: usize,
    start: usize,
    end: usize,
    m: usize,
) -> Tuple[str, str, str]:
    before = s[0:start]
    if len(before) > n:
        before = before[start-n: start]

    matched = s[start:end]
    after = at_most_n_chars(s[end:], m)

    return (before, matched, after)


def pretty_mode() -> bool:
    return False
    # pretty = env_var("PRETTY")
    # pretty == "1" || pretty == "True"


# Runs all tests under the test/testsuite directory.
def functional_tests(
    compiler: Compiler,
    path: str,
) -> None:
    ins =Path(path).read_text()

    lines: List[str] = ins.splitlines()

    (config, directives, transactions) = split_input(lines)

    config = GlobalConfig.build(config)
    commands = build_transactions(config, transactions)

    log = eeval(config, compiler, commands)
    res = match_output(log, directives)

    if res.status.tag == MatchStatus.vSuccess:
        return
    else:
        errs: List[MatchError] = res.status.value
        bail(errs.__str__())

"""
    # Set up colored output stream for error rendering.
    bufwtr = BufferWriter.stdout(ColorChoice.Auto)
    output = bufwtr.buffer()

    # Helpers for directives and matches.
    macro_rules! print_directive {
        ($idx: expr) => {{
            d = &directives[$idx]
            write!(output, "{} | {}", d.line + 1, &lines[d.line][..d.start])
            output.set_color(ColorSpec.new().set_underline(True))
            write!(output, "{}", &lines[d.line][d.start..d.end])
            output.reset()
            write!(output, "{}", &lines[d.line][d.end..])
        }}
    }

    macro_rules! print_match {
        ($indent: expr, $is_positive: expr, $m: expr) => {{
            m: &Match = $m
            indent: &str = $indent
            prefix = format_str("[{}] ", m.entry_id)
            (before, matched, after) =
                at_most_n_before_and_m_after(&res.text[m.entry_id], 30, m.start, m.end, 50)
            write!(output, "{}", indent)
            write!(output, "{}{}", prefix, before)
            output.set_color(ColorSpec.new().set_underline(True).set_fg(Some(
                if $is_positive {
                    Color.Green
                else:
                    Color.Red
                },
            )))
            write!(output, "{}", matched)
            output.reset()
            writeln!(output, "{}", after)

            offset = prefix.chars().count() + before.chars().count()
            write!(output, "{}", indent)
            write!(
                output,
                "{}",
                iter.repeat(' ').take(offset).collect.<String>()
            )
            print_directive!(m.pat_id)
            writeln!(output)
        }}
    }

    writeln!(output)
    writeln!(
        output,
        "{}",
        iter.repeat('=').take(100).collect.<String>()
    )
    writeln!(output, "{}", path.display())
    writeln!(output)

    # Render the evaluation log.
    output.set_color(ColorSpec.new().set_bold(True).set_fg(Some(Color.Yellow)))
    write!(output, "info: ")
    output.set_color(ColorSpec.new().set_bold(True))
    writeln!(output, "Evaluation Outputs")
    output.reset()
    if pretty_mode() {
        writeln!(
            output,
            "{}",
            format_str("{}", log)
                .lines()
                .map(|line| format_str("    {}\n", line))
                .collect.<String>()
        )
    else:
        for (id, entry) in res.text.iter().enumerate() {
            writeln!(output, "    [{}] {}", id, entry)
        }
        writeln!(output)
        writeln!(
            output,
            "    Note: enable pretty printing by setting 'env PRETTY=1'."
        )
        writeln!(output)
    }
    writeln!(output)

    # Render previously successful matches if any.
    if !res.matches.is_empty() {
        output.set_color(ColorSpec.new().set_bold(True).set_fg(Some(Color.Yellow)))
        write!(output, "info: ")
        output.set_color(ColorSpec.new().set_bold(True))
        writeln!(output, "Successful Matches")
        output.reset()
        for m in &res.matches {
            print_match!("    ", True, m)
            writeln!(output)
        }
        writeln!(output)
    }

    # Render errors.
    for err in errs {
        output.set_color(ColorSpec.new().set_bold(True).set_fg(Some(Color.Red)))
        write!(output, "error: ")
        output.reset()
        match err {
            MatchError.UnmatchedErrors(errs) => {
                output.set_color(ColorSpec.new().set_bold(True))
                writeln!(output, "Unmatched Errors")
                output.reset()
                for id in errs.iter() {
                    write!(output, "    [{}] ", id)
                    writeln!(output, "{}", at_most_n_chars(res.text[*id].chars(), 80))
                }
            }
            MatchError.NegativeMatch(m) => {
                output.set_color(ColorSpec.new().set_bold(True))
                writeln!(output, "Negative Match")
                output.reset()
                print_match!("    ", False, &m)
            }
            MatchError.UnmatchedDirectives(dirs) => {
                output.set_color(ColorSpec.new().set_bold(True))
                writeln!(output, "Unmatched Directives")
                output.reset()
                for idx in &dirs {
                    write!(output, "    ")
                    print_directive!(*idx)
                    writeln!(output)
                }
                writeln!(output)
                writeln!(output)
            }
        }
    }
    writeln!(output)
    bufwtr.print(&output)

    bail("test failed")

"""