"""Génération de rapports PDF avec ReportLab."""
import io
from collections import Counter
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_GREEN = colors.HexColor("#2D5A27")
_LIGHT_GREEN = colors.HexColor("#F0F7EF")
_DARK_GREEN = colors.HexColor("#4A7A44")
_ORANGE = colors.HexColor("#E07B00")
_LIGHT_ORANGE = colors.HexColor("#FFF8F0")
_GREY = colors.HexColor("#CCCCCC")


def _make_table(data: list, col_widths: list, header_color, row_color) -> Table:
    t = Table(data, colWidths=col_widths)
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), header_color),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [row_color, colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, _GREY),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("PADDING", (0, 0), (-1, -1), 5),
        ])
    )
    return t


def generer_rapport(
    nom_client: str,
    titre_projet: str,
    surfaces: dict | None = None,
    exposition: dict | None = None,
    plantation: dict | None = None,
) -> bytes:
    """Génère un rapport PDF et retourne les bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    s_title = ParagraphStyle(
        "t", parent=styles["Title"], fontSize=22, spaceAfter=10,
        textColor=_GREEN, alignment=TA_CENTER,
    )
    s_sub = ParagraphStyle(
        "s", parent=styles["Normal"], fontSize=11, spaceAfter=4,
        textColor=_DARK_GREEN, alignment=TA_CENTER,
    )
    s_h2 = ParagraphStyle(
        "h2", parent=styles["Heading1"], fontSize=13, spaceBefore=14,
        spaceAfter=6, textColor=_GREEN,
    )
    s_body = ParagraphStyle("b", parent=styles["Normal"], fontSize=10, spaceAfter=4, leading=14)
    s_footer = ParagraphStyle(
        "f", parent=styles["Normal"], fontSize=8, textColor=colors.grey, alignment=TA_CENTER,
    )

    story = []

    # En-tête
    story.append(Paragraph("Rapport Paysager", s_title))
    story.append(Paragraph(titre_projet, s_sub))
    story.append(Paragraph(f"Client : {nom_client}", s_sub))
    story.append(Paragraph(f"Date : {datetime.now().strftime('%d/%m/%Y')}", s_sub))
    story.append(HRFlowable(width="100%", thickness=2, color=_GREEN))
    story.append(Spacer(1, 0.4 * cm))

    # Surfaces
    if surfaces:
        story.append(Paragraph("Analyse des Surfaces", s_h2))
        data = [["Zone", "Surface (m2)"]]
        for nom, val in surfaces.get("surfaces_m2", {}).items():
            data.append([nom, f"{val:.1f} m2"])
        story.append(_make_table(data, [12 * cm, 5 * cm], _GREEN, _LIGHT_GREEN))
        story.append(Spacer(1, 0.4 * cm))

    # Exposition
    if exposition:
        story.append(Paragraph("Analyse d'Exposition Solaire", s_h2))
        resume = exposition.get("resume", {})
        data = [
            ["Type d'exposition", "Pourcentage"],
            ["Plein soleil", f"{resume.get('pct_plein_soleil', 0):.1f}%"],
            ["Mi-ombre", f"{resume.get('pct_mi_ombre', 0):.1f}%"],
            ["Ombre", f"{resume.get('pct_ombre', 0):.1f}%"],
        ]
        story.append(_make_table(data, [12 * cm, 5 * cm], _ORANGE, _LIGHT_ORANGE))
        story.append(Spacer(1, 0.4 * cm))

    # Plantation
    if plantation:
        story.append(Paragraph("Plan de Plantation Recommande", s_h2))
        resume_pl = plantation.get("resume", {})
        story.append(Paragraph(
            f"Nombre de plantations recommandees : <b>{resume_pl.get('nb_placements', 0)}</b>",
            s_body,
        ))
        placements = plantation.get("placements", [])
        if placements:
            counts = Counter(p["nom"] for p in placements)
            seen = {p["nom"]: p for p in placements}
            data = [["Plante", "Qte", "Type", "Exposition"]]
            for nom, cnt in sorted(counts.items(), key=lambda x: -x[1]):
                p = seen[nom]
                data.append([nom, str(cnt), p.get("type", "-"), p.get("exposition", "-")])
            story.append(_make_table(
                data,
                [7 * cm, 2 * cm, 4 * cm, 4 * cm],
                _DARK_GREEN,
                _LIGHT_GREEN,
            ))
        story.append(Spacer(1, 0.4 * cm))

    # Pied de page
    story.append(HRFlowable(width="100%", thickness=1, color=_GREY))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        "Rapport genere par IA Paysagiste - Application de conception de jardins assistee par IA",
        s_footer,
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
