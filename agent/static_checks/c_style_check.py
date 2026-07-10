import os
import re


def _looks_like_c_style_statement(stripped):
    if not stripped or stripped.startswith(("//", "/*", "*", "@")):
        return False
    if stripped.endswith((";", "{", "}", ":", ",")):
        return False
    if stripped in {"else", "try", "finally"}:
        return False
    if re.match(r"^(if|for|while|switch|catch|else|try|finally|class|interface|enum|struct)\b", stripped):
        return False
    if re.match(r"^(public|private|protected|static|final|abstract|synchronized)\b.*\)\s*$", stripped):
        return False
    if re.match(r"^[A-Za-z_][\w<>\[\], ?]*\s+[A-Za-z_]\w*\s*\([^;{}]*\)\s*$", stripped):
        return False

    declaration_pattern = (
        r"^(int|long|double|float|boolean|bool|char|String|string|var|"
        r"Scanner|ArrayList|List|Map|Set|HashMap|HashSet)\b"
    )
    return (
        stripped.startswith(("return ", "throw ", "break", "continue", "import ", "package ", "using ", "System.", "Console.", "fmt."))
        or re.match(declaration_pattern, stripped) is not None
        or "=" in stripped
        or re.match(r"^[A-Za-z_]\w*\.[A-Za-z_]\w*\(.*\)$", stripped) is not None
    )


def check_c_style(file_name, language, source_text, make_finding):
    findings = []
    lines = source_text.splitlines()
    base_name = os.path.splitext(os.path.basename(file_name))[0]

    if language == "java":
        for line_number, line in enumerate(lines, start=1):
            match = re.search(r"\bpublic\s+class\s+([A-Za-z_]\w*)", line)
            if match and match.group(1) != base_name:
                findings.append(
                    make_finding(
                        file_name,
                        line_number,
                        "critical",
                        "syntax_error",
                        f"Java'da public class adi `{match.group(1)}` ile dosya adi `{os.path.basename(file_name)}` eslesmiyor.",
                        f"Dosya adini `{match.group(1)}.java` yapin veya public class adini `{base_name}` olarak degistirin.",
                    )
                )

    brace_balance = 0
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        brace_balance += stripped.count("{") - stripped.count("}")

        if re.match(r"^if\s*\(.*\)\s*;\s*$", stripped):
            findings.append(
                make_finding(
                    file_name,
                    line_number,
                    "high",
                    "logic_error",
                    "`if` kosulundan hemen sonra gelen `;` if blogunu bosaltir; sonraki blok kosuldan bagimsiz calisir.",
                    "`if (...) ;` sonundaki noktali virgulu kaldirin.",
                )
            )

        if language in {"java", "csharp"} and re.search(r"\bif\s*\([^)]*[^=!<>]=[^=][^)]*\)", stripped):
            findings.append(
                make_finding(
                    file_name,
                    line_number,
                    "critical",
                    "syntax_error",
                    "`if` kosulunda atama operatoru `=` kullanilmis gorunuyor; karsilastirma icin `==` gerekir.",
                    "`=` yerine `==` kullanin veya bilincli atama ise kosulu acik bir boolean ifadeye cevirin.",
                )
            )

        if language in {"java", "c", "cpp", "csharp"} and _looks_like_c_style_statement(stripped):
            findings.append(
                make_finding(
                    file_name,
                    line_number,
                    "critical",
                    "syntax_error",
                    "Bu satir ifade/deklarasyon gibi gorunuyor ancak sonunda `;` yok.",
                    "Satirin sonuna `;` ekleyin ya da satir bir blok/metot bildirimi ise yapisini duzeltin.",
                )
            )

    if brace_balance != 0:
        findings.append(
            make_finding(
                file_name,
                len(lines) or 1,
                "critical",
                "syntax_error",
                "Dosyadaki suslu parantez sayisi dengeli gorunmuyor.",
                "Acili ve kapanis `{` / `}` parantezlerini kontrol edin.",
            )
        )

    return findings

