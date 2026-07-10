import re


def check_sql(file_name, source_text, make_finding):
    findings = []
    single_quote_count = 0
    parenthesis_balance = 0
    previous_significant_line = None

    for line_number, line in enumerate(source_text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("--"):
            continue

        single_quote_count += stripped.count("'") - stripped.count("''") * 2
        parenthesis_balance += stripped.count("(") - stripped.count(")")

        if parenthesis_balance < 0:
            findings.append(
                make_finding(
                    file_name,
                    line_number,
                    "critical",
                    "syntax_error",
                    "SQL sorgusunda kapanis parantezi acilis parantezinden fazla gorunuyor.",
                    "Parantezleri dengeleyin.",
                )
            )
            parenthesis_balance = 0

        if (
            previous_significant_line
            and previous_significant_line["content"].rstrip().endswith(",")
            and re.match(r"^(from|where|group\s+by|order\s+by|having|limit|union)\b", stripped, re.IGNORECASE)
        ):
            findings.append(
                make_finding(
                    file_name,
                    previous_significant_line["line"],
                    "critical",
                    "syntax_error",
                    "SQL SELECT/ifade listesi clause baslamadan hemen once virgulle bitiyor.",
                    "Clause oncesindeki fazladan virgulu kaldirin.",
                )
            )

        if stripped:
            previous_significant_line = {"line": line_number, "content": stripped}

    if single_quote_count % 2 != 0:
        findings.append(
            make_finding(
                file_name,
                len(source_text.splitlines()) or 1,
                "critical",
                "syntax_error",
                "SQL sorgusunda tek tirnaklar dengeli gorunmuyor.",
                "String literal icin acilan tek tirnagi kapatin veya kacis karakterlerini kontrol edin.",
            )
        )

    if parenthesis_balance > 0:
        findings.append(
            make_finding(
                file_name,
                len(source_text.splitlines()) or 1,
                "critical",
                "syntax_error",
                "SQL sorgusunda acilis parantezi kapanis parantezinden fazla gorunuyor.",
                "Parantezleri dengeleyin.",
            )
        )

    return findings

