import json
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import ActivityLog, Cabinet, CabinetCheck, InspectionState


STATUS_LABELS = {
    CabinetCheck.Status.UNCHECKED: CabinetCheck.Status.UNCHECKED.label,
    CabinetCheck.Status.DONE: CabinetCheck.Status.DONE.label,
    CabinetCheck.Status.PROBLEM: CabinetCheck.Status.PROBLEM.label,
}


def user_display_name(user) -> str:
    if not user:
        return "Система"
    return user.get_full_name() or user.username


def format_datetime(value) -> str:
    if not value:
        return ""
    local_value = timezone.localtime(value)
    return local_value.strftime("%d.%m %H:%M")


def load_json_body(request: HttpRequest) -> dict:
    if not request.body:
        return {}

    try:
        return json.loads(request.body)
    except json.JSONDecodeError:
        return {}


def get_inspection_state() -> InspectionState:
    state, _ = InspectionState.objects.get_or_create(
        pk=1,
        defaults={
            "round_number": 1,
        },
    )
    return state


def ensure_checks_exist() -> None:
    cabinet_ids = list(Cabinet.objects.values_list("id", flat=True))
    if not cabinet_ids:
        return

    existing = set(CabinetCheck.objects.values_list("cabinet_id", flat=True))
    missing_checks = [
        CabinetCheck(cabinet_id=cabinet_id)
        for cabinet_id in cabinet_ids
        if cabinet_id not in existing
    ]
    if missing_checks:
        CabinetCheck.objects.bulk_create(missing_checks, ignore_conflicts=True)


def create_activity_log(
    *,
    user,
    action: str,
    cabinet_name: str = "",
    status: str = "",
    comment: str = "",
    details: str = "",
) -> None:
    ActivityLog.objects.create(
        user=user,
        action=action,
        cabinet_name=cabinet_name,
        status=status,
        comment=comment,
        details=details,
    )


def activity_text(log: ActivityLog) -> str:
    actor = user_display_name(log.user)

    if log.action == ActivityLog.Action.RESULT_UPDATED:
        text = f"{actor}: {log.cabinet_name} -> {STATUS_LABELS.get(log.status, log.status)}"
        if log.comment:
            short_comment = log.comment.strip()
            if len(short_comment) > 90:
                short_comment = f"{short_comment[:87]}..."
            text = f'{text} | "{short_comment}"'
        return text

    if log.action == ActivityLog.Action.CABINET_TOGGLED:
        return f"{actor}: {log.details}"

    if log.action == ActivityLog.Action.ALL_RESET:
        return f"{actor}: {log.details or 'начал новый обход'}"

    return f"{actor}: {log.details}"


def build_problem_report(round_number: int, cabinets: list[dict]) -> str:
    problem_lines = []
    for cabinet in cabinets:
        if not cabinet["included"] or cabinet["status"] != CabinetCheck.Status.PROBLEM:
            continue

        comment = cabinet["comment"].strip() or "Комментарий не указан"
        problem_lines.append(f"- {cabinet['name']}: {comment}")

    if not problem_lines:
        return (
            f"Автоотчет по обходу №{round_number}\n"
            "Проблемы по кабинетам не зафиксированы."
        )

    return (
        f"Автоотчет по обходу №{round_number}\n"
        f"Проблемных кабинетов: {len(problem_lines)}\n\n"
        + "\n".join(problem_lines)
    )


def excel_column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def excel_cell(
    *,
    row_index: int,
    column_index: int,
    value,
    style_id: int = 0,
) -> str:
    cell_ref = f"{excel_column_name(column_index)}{row_index}"
    text = escape(str(value), {'"': "&quot;"})
    style = f' s="{style_id}"' if style_id else ""
    return f'<c r="{cell_ref}" t="inlineStr"{style}><is><t>{text}</t></is></c>'


def build_xlsx(rows: list[list], bold_rows: set[int] | None = None) -> bytes:
    bold_rows = bold_rows or set()
    sheet_rows = []

    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            if value in (None, ""):
                continue
            style_id = 1 if row_index in bold_rows else 0
            cells.append(
                excel_cell(
                    row_index=row_index,
                    column_index=column_index,
                    value=value,
                    style_id=style_id,
                )
            )
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    sheet_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
    <cols>
        <col min="1" max="1" width="18" customWidth="1"/>
        <col min="2" max="2" width="46" customWidth="1"/>
        <col min="3" max="3" width="18" customWidth="1"/>
        <col min="4" max="4" width="22" customWidth="1"/>
        <col min="5" max="5" width="18" customWidth="1"/>
    </cols>
    <sheetData>{"".join(sheet_rows)}</sheetData>
</worksheet>"""

    workbook_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
    <sheets>
        <sheet name="Автоотчет" sheetId="1" r:id="rId1"/>
    </sheets>
</workbook>"""

    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
    <fonts count="2">
        <font><sz val="11"/><name val="Calibri"/></font>
        <font><b/><sz val="11"/><name val="Calibri"/></font>
    </fonts>
    <fills count="2">
        <fill><patternFill patternType="none"/></fill>
        <fill><patternFill patternType="gray125"/></fill>
    </fills>
    <borders count="1"><border/></borders>
    <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
    <cellXfs count="2">
        <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
        <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/>
    </cellXfs>
</styleSheet>"""

    content_types_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
    <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
    <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

    root_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

    workbook_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", content_types_xml)
        workbook.writestr("_rels/.rels", root_rels_xml)
        workbook.writestr("xl/workbook.xml", workbook_xml)
        workbook.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        workbook.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        workbook.writestr("xl/styles.xml", styles_xml)

    return output.getvalue()


def build_problem_report_xlsx(payload: dict) -> bytes:
    problem_cabinets = [
        cabinet
        for cabinet in payload["cabinets"]
        if cabinet["included"] and cabinet["status"] == CabinetCheck.Status.PROBLEM
    ]

    rows = [
        ["Автоотчет по обходу", f"№{payload['round']['number']}"],
        ["Сформировано", payload["generated_at"]],
        ["Проблемных кабинетов", payload["summary"]["problem"]],
        [],
        ["Кабинет", "Комментарий", "Статус", "Обновил", "Обновлено"],
    ]

    if problem_cabinets:
        rows.extend(
            [
                [
                    cabinet["name"],
                    cabinet["comment"].strip() or "Комментарий не указан",
                    cabinet["status_label"],
                    cabinet["updated_by"],
                    cabinet["updated_at"],
                ]
                for cabinet in problem_cabinets
            ]
        )
    else:
        rows.append(["Проблемы по кабинетам не зафиксированы."])

    return build_xlsx(rows, bold_rows={1, 5})


def build_dashboard_payload(request: HttpRequest) -> dict:
    ensure_checks_exist()
    state = get_inspection_state()

    checks = list(
        CabinetCheck.objects.select_related(
            "cabinet",
            "updated_by",
            "cabinet__availability_updated_by",
        ).order_by("cabinet__sort_order", "cabinet__name")
    )
    activity_logs = list(ActivityLog.objects.select_related("user")[:20])

    cabinet_payload = []
    done_count = 0
    problem_count = 0
    unchecked_count = 0
    active_cabinet_count = 0

    for check in checks:
        cabinet = check.cabinet
        if cabinet.included:
            active_cabinet_count += 1
            if check.status == CabinetCheck.Status.DONE:
                done_count += 1
            elif check.status == CabinetCheck.Status.PROBLEM:
                problem_count += 1
            else:
                unchecked_count += 1

        cabinet_payload.append(
            {
                "id": cabinet.id,
                "name": cabinet.name,
                "included": cabinet.included,
                "can_skip": cabinet.can_be_skipped,
                "availability_updated_by": user_display_name(
                    cabinet.availability_updated_by
                )
                if cabinet.availability_updated_by
                else "",
                "availability_updated_at": format_datetime(
                    cabinet.availability_updated_at
                ),
                "check_id": check.id,
                "status": check.status,
                "status_label": STATUS_LABELS[check.status],
                "comment": check.comment,
                "updated_by": user_display_name(check.updated_by)
                if check.updated_by
                else "",
                "updated_at": format_datetime(check.updated_at),
            }
        )

    percent = round((done_count / active_cabinet_count) * 100) if active_cabinet_count else 0

    return {
        "current_user": user_display_name(request.user),
        "generated_at": format_datetime(timezone.now()),
        "poll_interval_ms": 3000,
        "structure_signature": {
            "cabinets": ",".join(str(cabinet["id"]) for cabinet in cabinet_payload),
        },
        "round": {
            "number": state.round_number,
            "started_by": user_display_name(state.last_reset_by)
            if state.last_reset_by
            else "",
            "started_at": format_datetime(state.last_reset_at),
        },
        "summary": {
            "done": done_count,
            "problem": problem_count,
            "unchecked": unchecked_count,
            "active_cabinets": active_cabinet_count,
            "all_cabinets": len(cabinet_payload),
            "percent": percent,
        },
        "report_text": build_problem_report(state.round_number, cabinet_payload),
        "cabinets": cabinet_payload,
        "activities": [
            {
                "id": log.id,
                "created_at": format_datetime(log.created_at),
                "text": activity_text(log),
            }
            for log in activity_logs
        ],
    }


@login_required
@require_GET
def checklist_dashboard(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "main/checklist.html",
        {
            "dashboard_payload": build_dashboard_payload(request),
        },
    )


@login_required
@require_GET
def dashboard_state(request: HttpRequest) -> JsonResponse:
    return JsonResponse(build_dashboard_payload(request))


@login_required
@require_GET
def problem_report_excel(request: HttpRequest) -> HttpResponse:
    payload = build_dashboard_payload(request)
    filename = f"routtraker-report-round-{payload['round']['number']}.xlsx"
    response = HttpResponse(
        build_problem_report_xlsx(payload),
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_POST
def update_check(request: HttpRequest, check_id: int) -> JsonResponse:
    check = get_object_or_404(
        CabinetCheck.objects.select_related("cabinet"),
        pk=check_id,
    )
    payload = load_json_body(request)

    new_status = payload.get("status", check.status)
    new_comment = payload.get("comment", check.comment)
    if isinstance(new_comment, str):
        new_comment = new_comment.strip()
    else:
        new_comment = ""

    if new_status not in STATUS_LABELS:
        return JsonResponse({"error": "Неизвестный статус."}, status=400)

    if new_status == check.status and new_comment == check.comment:
        return JsonResponse(build_dashboard_payload(request))

    check.status = new_status
    check.comment = new_comment
    check.updated_by = request.user
    check.updated_at = timezone.now()
    check.save(update_fields=("status", "comment", "updated_by", "updated_at"))

    create_activity_log(
        user=request.user,
        action=ActivityLog.Action.RESULT_UPDATED,
        cabinet_name=check.cabinet.name,
        status=check.status,
        comment=check.comment,
    )
    return JsonResponse(build_dashboard_payload(request))


@login_required
@require_POST
def toggle_cabinet(request: HttpRequest, cabinet_id: int) -> JsonResponse:
    cabinet = get_object_or_404(Cabinet, pk=cabinet_id)
    if not cabinet.can_be_skipped:
        return JsonResponse(
            {"error": "Этот кабинет нельзя исключать из обхода."},
            status=400,
        )

    payload = load_json_body(request)
    requested_value = payload.get("included")
    new_value = requested_value if isinstance(requested_value, bool) else not cabinet.included

    if new_value != cabinet.included:
        cabinet.included = new_value
        cabinet.availability_updated_by = request.user
        cabinet.availability_updated_at = timezone.now()
        cabinet.save(
            update_fields=(
                "included",
                "availability_updated_by",
                "availability_updated_at",
            )
        )
        details = (
            f"вернул {cabinet.name} в текущий обход"
            if new_value
            else f"исключил {cabinet.name} из текущего обхода"
        )
        create_activity_log(
            user=request.user,
            action=ActivityLog.Action.CABINET_TOGGLED,
            cabinet_name=cabinet.name,
            details=details,
        )

    return JsonResponse(build_dashboard_payload(request))


@login_required
@require_POST
def reset_checklist(request: HttpRequest) -> JsonResponse:
    state = get_inspection_state()
    state.round_number += 1
    state.last_reset_by = request.user
    state.last_reset_at = timezone.now()
    state.save(update_fields=("round_number", "last_reset_by", "last_reset_at"))

    CabinetCheck.objects.all().update(
        status=CabinetCheck.Status.UNCHECKED,
        comment="",
        updated_by=None,
        updated_at=None,
    )
    Cabinet.objects.filter(can_be_skipped=True).update(
        included=True,
        availability_updated_by=request.user,
        availability_updated_at=timezone.now(),
    )
    create_activity_log(
        user=request.user,
        action=ActivityLog.Action.ALL_RESET,
        details=f"открыл обход №{state.round_number}",
    )
    return JsonResponse(build_dashboard_payload(request))
