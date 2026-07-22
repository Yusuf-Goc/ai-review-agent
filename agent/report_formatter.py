def format_review_report(review_result):
    changes = [
        item
        for item in review_result.get("changes", [])
        if isinstance(item, dict)
    ]
    findings = [
        item
        for item in review_result.get("findings", [])
        if isinstance(item, dict)
    ]
    impact_analysis = [
        item
        for item in review_result.get("impact_analysis", [])
        if isinstance(item, dict)
    ]
    review_status = review_result.get("review_status", "completed")
    context_source_type = review_result.get("context_source_type", "none")
    context_sources = review_result.get("context_sources", [])

    lines = [f"Ozet: {review_result.get('summary', 'Inceleme tamamlandi.')}"]

    if changes:
        lines.append("Degisiklikler:")
        for change in changes:
            file_name = change.get("file", "bilinmeyen dosya")
            symbol = change.get("symbol") or "dosya geneli"
            change_type = change.get("change_type", "modified")
            after = change.get("after", "")
            behavior_change = change.get("behavior_change", "")
            detail = behavior_change or after or "Degisiklik aciklamasi yok."
            lines.append(
                f"- {file_name} [{change_type}] {symbol}: {detail}"
            )

    if impact_analysis:
        lines.append("Capraz dosya etkileri:")
        for item in impact_analysis:
            symbol = item.get("symbol", "bilinmeyen sembol")
            changed_file = item.get("changed_file", "bilinmeyen dosya")
            impact_text = item.get("impact", "Etki aciklamasi yok.")
            lines.append(f"- {changed_file} {symbol}: {impact_text}")

    lines.append(f"Baglam: {context_source_type}")
    if context_sources:
        lines.append("Baglam kaynaklari: " + ", ".join(context_sources))
    analysis_sources = review_result.get("analysis_sources", [])
    if analysis_sources:
        lines.append("Repository analiz kaynaklari: " + ", ".join(analysis_sources))

    if not findings:
        if review_status == "completed":
            lines.append("Bulgu: Kritik hata bulunamadi.")
        else:
            lines.append(
                "Bulgu: Inceleme tamamlanamadigi icin guvenilir bir "
                "hata bulunamadi sonucu uretilemedi."
            )
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
