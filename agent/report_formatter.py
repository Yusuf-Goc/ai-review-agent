def format_review_report(review_result):
    findings = review_result.get("findings", [])
    lines = [f"Ozet: {review_result.get('summary', 'Inceleme tamamlandi.')}"]

    if not findings:
        lines.append("Bulgu: Kritik hata bulunamadi.")
        return "\n".join(lines)

    lines.append("Bulgular:")
    for finding in findings:
        file_name = finding.get("file", "bilinmeyen dosya")
        line = finding.get("line", "bilinmeyen satir")
        severity = finding.get("severity", "unknown")
        category = finding.get("category", "unknown")
        message = finding.get("message", "")
        suggestion = finding.get("suggestion", "")
        lines.append(f"- {file_name}:{line} [{severity}/{category}] {message}")
        if suggestion:
            lines.append(f"  Oneri: {suggestion}")

    return "\n".join(lines)

