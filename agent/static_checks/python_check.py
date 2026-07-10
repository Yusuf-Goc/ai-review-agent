import ast


def check_python(file_name, source_text, make_finding):
    try:
        ast.parse(source_text, filename=file_name)
    except SyntaxError as exc:
        return [
            make_finding(
                file_name,
                exc.lineno or 1,
                "critical",
                "syntax_error",
                f"Python syntax hatasi: {exc.msg}.",
                "Ilgili satirdaki Python sozdizimini duzeltin ve dosyayi tekrar calistirin.",
            )
        ]
    return []

