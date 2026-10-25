import math
from functools import partial
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus.doctemplate import LayoutError

from app.finance.schemas import MetricName
from app.reporting.schemas import ReportSnapshot

NAVY = colors.HexColor("#142538")
TEAL = colors.HexColor("#087F79")
PALE = colors.HexColor("#EAF5F3")
AMBER = colors.HexColor("#82510B")
GREY = colors.HexColor("#536374")
FONT = "BusinessAI-DejaVu"
WIDTH = A4[0] - 88
SCENARIOS = {"conservative": "Консервативный", "base": "Базовый", "optimistic": "Оптимистичный"}
CRITERIA = {
    "transit": "Транспорт",
    "infrastructure": "Инфраструктура",
    "complementary": "Окружение",
    "competitors": "Конкуренты",
}
ORIGINS = {
    "synthetic": "СИНТЕТИКА / допущение",
    "modelled": "Модельный расчёт",
    "open_data": "Открытые данные",
    "user_input": "Ввод пользователя",
    "licensed": "Лицензированные",
    "bank_internal": "Данные банка",
}
ITEMS = {
    "equipment": "Оборудование",
    "renovation": "Ремонт",
    "rent_deposit": "Депозит аренды",
    "initial_inventory": "Первоначальный запас",
    "registration": "Регистрация",
    "other": "Прочие",
    "working_capital_reserve": "Оборотный резерв",
    "rent": "Аренда",
    "payroll": "Зарплаты",
    "utilities": "Коммунальные",
    "average_check": "Средний чек",
    "sales_per_day": "Продажи в день",
    "variable_cost_ratio": "Переменные затраты, доля",
}


def text(value: object) -> str:
    return str(value).replace("—", "-").replace("–", "-").replace("\u2011", "-")


def number(value: object) -> str:
    if value is None:
        return "Нет данных"
    return f"{value:,.2f}".replace(",", " ") if isinstance(value, (float, int)) else str(value)


def render(snapshot: ReportSnapshot) -> bytes:
    from app.reporting.service import serialize, sha

    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT, str(Path(__file__).parent / "fonts/DejaVuSans.ttf")))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT, italic=FONT, boldItalic=FONT)
    body = ParagraphStyle(
        "body",
        fontName=FONT,
        fontSize=9,
        leading=13,
        textColor=NAVY,
        spaceAfter=7,
        splitLongWords=True,
    )
    small = ParagraphStyle(
        "small", parent=body, fontSize=7.5, leading=10, textColor=GREY, spaceAfter=3
    )
    heading = ParagraphStyle(
        "heading",
        parent=body,
        fontSize=18,
        leading=23,
        textColor=TEAL,
        spaceBefore=10,
        spaceAfter=14,
        keepWithNext=True,
    )
    subheading = ParagraphStyle(
        "subheading",
        parent=body,
        fontSize=12,
        leading=16,
        spaceBefore=12,
        spaceAfter=8,
        keepWithNext=True,
    )
    story: list[Any] = []

    def p(value: object, style: Any = body) -> Any:
        return Paragraph(escape(text(value)).replace("\n", "<br/>"), style)

    def note(value: object) -> None:
        story.append(p(value, small))

    def h(value: str) -> None:
        story.append(p(value, subheading))

    def table(
        headers: list[str], rows: list[list[object]], widths: list[float] | None = None
    ) -> None:
        if not rows:
            note("Нет рассчитанных значений.")
            return
        content = [[p(v, small) for v in headers]] + [[p(v, small) for v in row] for row in rows]
        item = Table(
            content,
            colWidths=widths or [WIDTH / len(headers)] * len(headers),
            repeatRows=1,
            hAlign="LEFT",
        )
        item.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), PALE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.8, TEAL),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#D9E1E7")),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.extend([item, Spacer(1, 10)])

    story.append(p("BUSINESS AI  /  SAB0TAGE", heading))
    title = ParagraphStyle("title", parent=body, fontSize=28, leading=35, spaceAfter=18)
    story.append(p("План открытия бизнеса", title))
    story.append(p(f"{snapshot.profile.category} · {snapshot.profile.city}", heading))
    note(
        "Сформирован "
        f"{snapshot.created_at.isoformat()}"
        " · версия документа "
        f"{snapshot.schema_version}"
    )
    note(f"Снимок {snapshot.id} · профиль v{snapshot.profile_version}")
    table(
        ["Подтверждённый параметр", "Значение"],
        [
            ["Бюджет, ₽", snapshot.profile.budget],
            ["Формат", snapshot.profile.preferences.format or "Не указан"],
            ["Источник финансирования", snapshot.profile.funding or "Не указан"],
            [
                "Предпочитаемые районы",
                ", ".join(snapshot.profile.preferences.preferred_districts) or "Не указаны",
            ],
            ["Ограничения", "; ".join(snapshot.profile.preferences.constraints) or "Не указаны"],
        ],
        [170, WIDTH - 170],
    )
    note(
        "Источник P: подтверждённый BusinessProfile, origin"
        "=user_input, версия "
        f"{snapshot.profile_version}"
        "; дата "
        f"{snapshot.profile_updated_at.isoformat()}"
        ". Подтверждение пользователем не является независи"
        "мой проверкой."
    )
    h("Что показывает этот отчёт")
    for line in snapshot.summary:
        story.append(p(line))
    if snapshot.missing_sections:
        note("Не включены / не рассчитаны разделы: " + ", ".join(snapshot.missing_sections))
    for line in snapshot.limitations:
        story.append(p(line, small))

    if snapshot.geo:
        story.extend([PageBreak(), p("01  Локации и окружение", heading)])
        geo = snapshot.geo
        features = {f.id: f for f in geo.candidates.features}
        names = {f.id: f"Зона {i + 1}" for i, f in enumerate(geo.candidates.features)}
        story.append(zone_map(snapshot, names))
        note(
            "Векторная схема EPSG:4326 без картографической под"
            "ложки. Зоны не являются помещениями. Масштаб прибл"
            "изительный; не использовать для навигации. © OpenS"
            "treetMap contributors, ODbL-1.0."
        )
        table(
            [
                "Зона / координаты",
                "Место / баллы",
                "Конкуренты / инфраструктура",
                "Остановка по прямой",
            ],
            [
                [
                    names[e.candidate_id]
                    + (" · ВЫБРАНА" if e.candidate_id == snapshot.selected_zone else "")
                    + "\n"
                    + str(features[e.candidate_id].properties.representative_point.coordinates),
                    f"{e.rank or '-'} / {number(e.score)}",
                    f"{e.raw.competitor_count} / {e.raw.infrastructure_count} объектов",
                    f"{number(e.raw.nearest_transit_m)} м",
                ]
                for e in geo.evaluations
            ],
        )
        note(
            "Баллы 0-100 - модельная сравнительная оценка в это"
            "й группе, не доходность. Counts - картированные OS"
            "M features; расстояния по прямой, не пешеходные. Н"
            "еполное покрытие / нехватка данных не превращаются"
            " в балл."
        )
        for evaluation in geo.evaluations:
            h(names[evaluation.candidate_id] + " · составляющие оценки")
            table(
                ["Критерий", "Исходный показатель / единица", "Нормализация / вес", "Вклад, баллы"],
                [
                    [
                        CRITERIA[c.criterion],
                        f"{number(c.raw_value)} {c.unit}",
                        f"{number(c.normalized)} / {number(c.weight)}",
                        number(c.contribution),
                    ]
                    for c in evaluation.components
                ],
            )
            for explanation in evaluation.explanations:
                note(explanation.text)
            if evaluation.missing_data:
                note("Недостающие данные: " + "; ".join(evaluation.missing_data))
        h("Источники G и метод расчёта")
        source = geo.candidates.dataset
        note(
            f"{source.source_name}"
            " · origin=open_data · "
            f"{source.attribution}"
            " · "
            f"{source.license}"
            "\n"
            f"{source.source_url}"
            "\nВерсия "
            f"{source.data_version}"
            "\nСрез "
            f"{source.osm_base.isoformat()}"
            " · импорт "
            f"{source.imported_at.isoformat()}"
            " · stale="
            f"{source.stale}"
        )
        note(
            "Алгоритм "
            f"{geo.algorithm_version}"
            "; генерация зон "
            f"{geo.candidates.algorithm_version}"
            "; политика "
            f"{geo.policy.version}"
            ", fingerprint "
            f"{geo.policy.fingerprint}"
            ". Веса: "
            f"{geo.policy.weight_rationale}"
        )
        for line in (*source.limitations, *geo.limitations):
            note(line)

    if snapshot.walking:
        story.extend([PageBreak(), p("02  Пешеходная доступность", heading)])
        walk = snapshot.walking
        table(
            ["Параметр", "Результат"],
            [
                [
                    "Статус / бюджет расстояния",
                    f"{walk.status} / {walk.request_snapshot.distance_m} м",
                ],
                [
                    "Точка longitude, latitude",
                    f"{walk.request_snapshot.longitude}, {walk.request_snapshot.latitude}",
                ],
                [
                    "Доступные POI по сети / в круге по прямой",
                    f"{walk.reachable_poi_count} / {walk.straight_line_poi_count} объектов",
                ],
                [
                    "Не привязаны к сети / нет пути в загруженном графе",
                    f"{walk.unsnapped_poi_count} / {walk.no_route_in_loaded_graph_count} объектов",
                ],
                ["Привязка начала к сети", f"{number(walk.source_snap_m)} м"],
            ],
            [WIDTH * 0.60, WIDTH * 0.40],
        )
        note("Ниже восемь крупнейших категорий; полный перечень доступен в JSON-снимке.")
        table(
            ["Категория", "Достижимые OSM features"],
            [
                [k, v]
                for k, v in sorted(
                    walk.category_counts.items(), key=lambda item: (-item[1], item[0])
                )[:8]
            ],
        )
        note(
            "Сетевые расстояния включают модельные прямолинейны"
            "е соединители. Нет пути в неполном графе не означа"
            "ет физическую недоступность. Origin=modelled; исто"
            "чник W - пешеходный OSM-граф."
        )
        if walk.graph:
            note(
                "Граф "
                f"{walk.graph.graph_version}"
                "; build "
                f"{walk.graph.build_version}"
                "; данные "
                f"{walk.graph.manifest.sha256}"
                "; срез "
                f"{walk.graph.manifest.osm_base.isoformat()}"
                "; "
                f"{walk.graph.manifest.license}"
                "; "
                f"{walk.graph.manifest.attribution}"
            )
        note(f"Алгоритм {walk.algorithm_version}; запрос {walk.request_fingerprint}")
        for line in (*walk.reasons, *walk.limitations):
            note(line)

    if snapshot.finance:
        story.extend([PageBreak(), p("03  Финансовая модель", heading)])
        finance = snapshot.finance
        story.append(
            p(
                "СЦЕНАРНАЯ МОДЕЛЬ. Синтетические допущения не являются рыночными данными.",
                ParagraphStyle("warning", parent=body, textColor=AMBER),
            )
        )
        table(
            ["Капитал и бюджет", "Сумма, ₽"],
            [
                ["Бюджет пользователя [P]", finance.budget.budget],
                [
                    "Запуск без оборотного резерва [F, modelled]",
                    finance.startup.launch_uses_excluding_reserve,
                ],
                ["Оборотный резерв [вводное допущение]", finance.startup.working_capital_reserve],
                [
                    "Всего начального финансирования [F, modelled]",
                    finance.startup.total_initial_funding,
                ],
                ["Остаток бюджета по модели [F]", finance.budget.remaining],
                ["Дефицит бюджета по модели [F]", finance.budget.funding_gap],
            ],
        )
        story.append(finance_chart(snapshot))
        note(
            "График: бирюзовый - выручка, тёмный - операционный"
            " результат; значения в ₽/месяц. Ни спрос, ни прода"
            "жи не измерены: это расчёт по вводным ниже."
        )
        keys: list[tuple[MetricName, str]] = [
            ("monthly_revenue", "Выручка, ₽/месяц"),
            ("monthly_fixed_cost", "Постоянные расходы, ₽/месяц"),
            ("monthly_variable_cost", "Переменные расходы, ₽/месяц"),
            ("monthly_contribution", "Маржинальный доход, ₽/месяц"),
            ("operating_result", "Операционный результат, ₽/месяц"),
            ("break_even_sales_per_day", "Безубыточность, продаж/день"),
        ]
        table(
            ["Показатель [F, modelled]", *[SCENARIOS[s.name] for s in finance.scenarios]],
            [[label, *[s.metrics[key].value for s in finance.scenarios]] for key, label in keys],
        )
        note(
            "Не чистая прибыль и не денежный поток. Налоги, кре"
            "дитные платежи и окупаемость не рассчитаны. Депози"
            "т/резерв не приравниваются к операционным расходам"
            "."
        )
        h("Сравнение с базовым сценарием [F, modelled]")
        table(
            ["Сценарий", "Разница выручки, ₽/месяц", "Разница результата, ₽/месяц"],
            [
                [
                    SCENARIOS[s.scenario],
                    s.revenue_difference_from_base,
                    s.operating_result_difference_from_base,
                ]
                for s in finance.comparison
            ],
        )
        h("Финансовые вводные и источники")
        assumptions = finance.request_snapshot
        sources: dict[str, Any] = {}

        def input_rows(
            group: str, values: dict[str, Any], units: dict[str, str]
        ) -> list[list[object]]:
            rows: list[list[object]] = []
            for key, value in values.items():
                source = value["source"]
                ref = next((k for k, v in sources.items() if v == source), None)
                if ref is None:
                    ref = f"F{len(sources) + 1}"
                    sources[ref] = source
                rows.append(
                    [
                        group + ": " + ITEMS.get(key, key),
                        str(value["value"]) + " " + units.get(key, "₽"),
                        ORIGINS[source["origin"]],
                        ref,
                    ]
                )
            return rows

        rows = input_rows("Старт", assumptions.startup.model_dump(mode="json"), {})
        rows += input_rows(
            "Ежемесячные", assumptions.monthly_fixed_costs.model_dump(mode="json"), {}
        )
        rows += input_rows(
            "Режим работы",
            {"Дней в месяц": assumptions.working_days_per_month.model_dump(mode="json")},
            {"Дней в месяц": "дней/месяц"},
        )
        for name in SCENARIOS:
            values = getattr(assumptions.scenarios, name).model_dump(mode="json")
            fixed = values.pop("fixed_costs")
            rows += input_rows(
                SCENARIOS[name],
                values,
                {
                    "average_check": "₽/продажа",
                    "sales_per_day": "продаж/день",
                    "variable_cost_ratio": "доля",
                },
            )
            if fixed:
                rows += input_rows(SCENARIOS[name] + " постоянные", fixed, {})
        table(
            ["Вводное", "Значение / единица", "Происхождение", "Источник"],
            rows,
            [170, 100, 170, WIDTH - 440],
        )
        for ref, source in sources.items():
            note(
                "["
                f"{ref}"
                "] "
                f"{source['source_name']}"
                " · origin="
                f"{source['origin']}"
                " · версия "
                f"{source['data_version']}"
                " · observation="
                f"{source['observed_at'] or 'нет'}"
                " · зафиксировано "
                f"{snapshot.created_at.isoformat()}"
                "; ограничения: "
                f"{'; '.join(source['limitations'])}"
            )
        h("Чувствительность базового сценария [F, modelled]")
        note(
            "Единицы нового значения: средний чек - ₽/продажа; продажи - продаж/день; "
            "аренда - ₽/месяц; переменная доля - доля от 0 до 1."
        )
        table(
            [
                "Изменяемый фактор",
                "Изменение / новое значение",
                "Операционный результат, ₽/месяц",
                "Разница с базой, ₽/месяц",
            ],
            [
                [
                    ITEMS.get(s.driver, s.driver),
                    f"{s.relative_change * 100}% / {s.actual_value}",
                    s.operating_result if s.status == "calculated" else "Вне области модели",
                    s.difference_from_base,
                ]
                for s in finance.sensitivity
            ],
        )
        h("Формулы и ограничения F")
        note(
            "Версия "
            f"{finance.algorithm_version}"
            "; fingerprint "
            f"{finance.request_fingerprint}"
            "; "
            f"{finance.rounding}"
        )
        for name, formula in finance.formulas.items():
            note(f"{name}: {formula}")
        for line in (*finance.limitations, *finance.missing_data, *finance.warnings):
            note(line)

    if snapshot.bank:
        story.extend([PageBreak(), p("04  Банковские продукты", heading)])
        bank = snapshot.bank
        story.append(
            p(
                "Демонстрационный / информационный каталог. "
                "Не оферта, не кредитное одобрение, не заявка."
            )
        )
        relevant = [d for d in bank.decisions if d.status not in {"not_matched", "unavailable"}]
        table(
            ["Продукт / категория", "Основание подбора", "Условия к проверке"],
            [
                [
                    d.entry.product.name + " / " + d.entry.product.category + " / " + d.status,
                    "; ".join(d.reasons),
                    "; ".join(d.entry.product.unknown_conditions)
                    + (" Уточнить: " + ", ".join(d.missing_fields) if d.missing_fields else ""),
                ]
                for d in relevant
            ],
            [130, 190, WIDTH - 320],
        )
        evidence = {e.id: e for d in relevant for e in d.entry.sources}
        for key, entry_source in sorted(evidence.items()):
            note(
                f"[B:{key}] {entry_source.title}; {entry_source.url}; "
                f"проверено {entry_source.reviewed_at}; {entry_source.verification}."
            )
            note("; ".join(entry_source.limitations))
        note(
            f"Каталог {bank.catalogue.version}; fingerprint {bank.catalogue.fingerprint}; "
            f"as_of {bank.catalogue.as_of}; алгоритм {bank.algorithm_version}; "
            f"credit_decision={bank.credit_decision}"
        )
        for line in dict.fromkeys(
            [*bank.limitations, *(v for d in relevant for v in d.entry.product.limitations)]
        ):
            note(line)

    if snapshot.providers:
        story.extend([PageBreak(), p("05  Дополнительные источники", heading)])
        for index, result in enumerate(snapshot.providers):
            dataset = result.dataset
            h(dataset.source_name)
            if dataset.origin == "synthetic":
                story.append(
                    p(
                        (
                            "СИНТЕТИЧЕСКИЕ ДАННЫЕ. НЕ РЫНОК КАЗАНИ. Не использо"
                            "ваны автоматически в рейтинге или финансах."
                        ),
                        ParagraphStyle("synthetic", parent=body, textColor=AMBER),
                    )
                )
            table(
                ["Показатель", "Значение / единица", "Происхождение / статус"],
                [
                    [
                        i.name,
                        f"{number(i.measurement.value)} {i.unit}"
                        if i.measurement
                        else "Нет данных",
                        (ORIGINS[i.measurement.origin] if i.measurement else "Отсутствует")
                        + " / "
                        + i.status,
                    ]
                    for i in result.indicators
                ],
            )
            note(
                "[D"
                f"{index + 1}"
                "] "
                f"{dataset.provider}"
                "/"
                f"{dataset.slug}"
                "; origin="
                f"{dataset.origin}"
                "; "
                f"{dataset.license}"
                "; "
                f"{dataset.attribution}"
                "; "
                f"{dataset.source_url or 'локальный авторский набор'}"
                "\nВерсия "
                f"{dataset.data_version}"
                "; revision "
                f"{dataset.revision}"
                "; observation="
                f"{dataset.observed_at}"
                "; generated="
                f"{dataset.generated_at}"
                "; stale="
                f"{dataset.stale}"
                "; bbox="
                f"{dataset.bbox.model_dump()}"
            )
            for line in dataset.limitations:
                note(line)

    story.extend([PageBreak(), p("Источники, воспроизводимость и следующие шаги", heading)])
    for rule in snapshot.provenance_rules:
        note(rule)
    h("Для принятия решения")
    story.append(p("Данные в ВТБ не отправляются. Кредитное решение не принимается."))
    for line in snapshot.summary:
        story.append(p(line))
    note(
        "Полный машиночитаемый снимок в JSON содержит все и"
        "сходные вводные, геометрии, правила, версии, даты "
        "и ограничения. PDF является представлением того же"
        " снимка; данные не дополняются LLM."
    )
    digest = sha(serialize(snapshot))
    note("SHA256 JSON-снимка: " + digest)

    def footer(canvas: Any, doc: Any) -> None:
        if doc.page > 40:
            raise ValueError("Report exceeds 40 pages")
        canvas.saveState()
        canvas.setStrokeColor(TEAL)
        canvas.line(44, A4[1] - 31, A4[0] - 44, A4[1] - 31)
        canvas.setFont(FONT, 7)
        canvas.setFillColor(GREY)
        canvas.drawString(
            44, 25, f"Business AI · {snapshot.created_at.date()} · v1 · {str(snapshot.id)[:8]}"
        )
        canvas.drawRightString(A4[0] - 44, 25, f"Страница {doc.page}")
        canvas.restoreState()

    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=44,
        leftMargin=44,
        topMargin=48,
        bottomMargin=46,
        title="Business AI - аналитический отчёт",
        author="Sab0tage",
        invariant=1,
        pageCompression=1,
    )
    try:
        doc.build(
            story, onFirstPage=footer, onLaterPages=footer, canvasmaker=partial(Canvas, invariant=1)
        )
    except LayoutError:
        raise ValueError("Content cannot fit report layout") from None
    return output.getvalue()


def zone_map(snapshot: ReportSnapshot, names: dict[str, str]) -> Any:
    drawing = Drawing(WIDTH, 230)
    drawing.add(Rect(0, 0, WIDTH, 230, fillColor=PALE, strokeColor=None))
    assert snapshot.geo is not None
    points = [
        f.properties.representative_point.coordinates for f in snapshot.geo.candidates.features
    ]
    if not points:
        drawing.add(String(15, 110, "Нет зон для схемы", fontName=FONT, fontSize=10))
        return drawing
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    west, east, south, north = min(xs) - 0.007, max(xs) + 0.007, min(ys) - 0.005, max(ys) + 0.005
    cos = math.cos(math.radians((north + south) / 2))
    scale = min((WIDTH - 70) / ((east - west) * cos), 175 / (north - south))

    def project(lon: float, lat: float) -> tuple[float, float]:
        return (35 + (lon - west) * cos * scale, 25 + (lat - south) * scale)

    for f in snapshot.geo.candidates.features:
        for polygon in f.geometry.coordinates:
            ring = polygon[0]
            coords = [v for lon, lat in ring for v in project(lon, lat)]
            drawing.add(
                Polygon(
                    coords, strokeColor=TEAL, fillColor=colors.HexColor("#BBDDD6"), strokeWidth=0.5
                )
            )
        x, y = project(*f.properties.representative_point.coordinates)
        drawing.add(
            Circle(
                x,
                y,
                4,
                fillColor=NAVY if f.id == snapshot.selected_zone else TEAL,
                strokeColor=None,
            )
        )
        drawing.add(String(x + 6, y + 6, names[f.id], fontName=FONT, fontSize=8, fillColor=NAVY))
    drawing.add(String(WIDTH - 35, 205, "N ↑", fontName=FONT, fontSize=9, fillColor=NAVY))
    return drawing


def finance_chart(snapshot: ReportSnapshot) -> Any:
    assert snapshot.finance is not None
    drawing = Drawing(WIDTH, 175)
    chart_keys: tuple[MetricName, ...] = ("monthly_revenue", "operating_result")
    values = [float(s.metrics[k].value) for s in snapshot.finance.scenarios for k in chart_keys]
    minimum = min(0, min(values))
    maximum = max(1, max(values))
    scale = 120 / (maximum - minimum)
    zero = 30 - minimum * scale
    drawing.add(Line(12, zero, WIDTH - 12, zero, strokeColor=GREY, strokeWidth=0.4))
    for index, scenario in enumerate(snapshot.finance.scenarios):
        x = 35 + index * (WIDTH / 3)
        for offset, key in enumerate(("monthly_revenue", "operating_result")):
            metric_key: MetricName = "monthly_revenue" if offset == 0 else "operating_result"
            value = float(scenario.metrics[metric_key].value)
            height = value * scale
            drawing.add(
                Rect(
                    x + offset * 40,
                    min(zero, zero + height),
                    28,
                    abs(height),
                    fillColor=TEAL if offset == 0 else NAVY,
                    strokeColor=None,
                )
            )
        drawing.add(
            String(x - 10, 12, SCENARIOS[scenario.name], fontName=FONT, fontSize=8, fillColor=NAVY)
        )
    return drawing
