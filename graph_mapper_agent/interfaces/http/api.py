from flask import Blueprint, request, jsonify, send_file
from graph_mapper_agent.interfaces.http.services import (
    load_profiles, load_profile_payload, empty_profile, optional_str,
    record_plan_state, record_plan_turn_messages, build_chat_request,
    create_chat_job, job_snapshot, resolve_local_artifact_path,
    is_allowed_artifact_path, DEFAULT_LEDGER_URL, runtime_from_profile
)
from graph_mapper_agent.interfaces.http.planning_service import (
    create_plan_state, get_plan_state, hydrate_plan_state_from_session, process_plan_turn
)
from graph_mapper_agent.ledger.application.query_service import (
    build_ledger_query_service,
)

api_bp = Blueprint("api", __name__)

@api_bp.get("/config-profiles")
def get_config_profiles():
    return jsonify({"items": load_profiles()})

@api_bp.post("/plan/turn")
def create_plan_turn():
    raw_payload = request.get_json(silent=True)
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    profile_name = str(payload.get("profile_name") or "").strip()
    profiles = load_profiles()
    selected_profile = next(
        (item for item in profiles if item["name"] == profile_name),
        profiles[0] if profiles else empty_profile(),
    )
    profile_payload = load_profile_payload(selected_profile["name"])
    state = process_plan_turn(
        session_id=optional_str(payload.get("session_id")),
        profile=selected_profile,
        user_message=str(payload.get("user_message") or "").strip(),
        entry_url=optional_str(payload.get("entry_url")),
        source_namespace=optional_str(payload.get("source_namespace")),
        follow_up_context=payload.get("follow_up_context")
        if isinstance(payload.get("follow_up_context"), dict)
        else None,
        llm_runtime_config=runtime_from_profile(profile_payload, "llm_runtime"),
    )
    ledger_url = optional_str(payload.get("ledger_database_url")) or DEFAULT_LEDGER_URL
    record_plan_state(
        session_id=state.session_id,
        state_payload=state.to_dict(),
        ledger_database_url=ledger_url,
    )
    record_plan_turn_messages(
        session_id=state.session_id,
        state_payload=state.to_dict(),
        ledger_database_url=ledger_url,
    )
    return jsonify(state.to_dict())

@api_bp.get("/plan/<session_id>")
def get_plan(session_id: str):
    state = get_plan_state(session_id)
    if state is None:
        profile_name = optional_str(request.args.get("profile_name"))
        profiles = load_profiles()
        selected_profile = next(
            (item for item in profiles if item["name"] == profile_name),
            profiles[0] if profiles else empty_profile(),
        )
        state = create_plan_state(selected_profile, session_id=session_id)
    return jsonify(state.to_dict())

@api_bp.post("/jobs")
def create_job():
    raw_payload = request.get_json(silent=True)
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    chat_request, profile = build_chat_request(payload)
    job_id = create_chat_job(chat_request, profile)
    
    return (
        jsonify(
            {
                "job_id": job_id,
                "status": "queued",
                "session_id": chat_request.resolved_session_id(),
                "run_id": chat_request.run_id,
                "research_mode": chat_request.research_mode,
                "profile_name": profile["name"],
            }
        ),
        202,
    )

@api_bp.get("/jobs/<job_id>")
def get_job(job_id: str):
    job = job_snapshot(job_id)
    if job is None:
        return jsonify({"error": "job_not_found", "job_id": job_id}), 404
    return jsonify(job)

@api_bp.get("/sessions/<session_id>")
def get_session(session_id: str):
    ledger_database_url = request.args.get("ledger_database_url") or DEFAULT_LEDGER_URL
    query = build_ledger_query_service(ledger_database_url)
    data = query.get_session(session_id)
    if data is None:
        return jsonify({"error": "session_not_found", "session_id": session_id}), 404
    return jsonify(data)

@api_bp.get("/sessions")
def list_sessions():
    ledger_database_url = request.args.get("ledger_database_url") or DEFAULT_LEDGER_URL
    query = build_ledger_query_service(ledger_database_url)
    items = query.list_sessions(
        limit=int(request.args.get("limit") or 20),
        session_kind=optional_str(request.args.get("session_kind")),
    )
    return jsonify({"items": items, "count": len(items)})

@api_bp.post("/plan/load-session")
def load_plan_session():
    raw_payload = request.get_json(silent=True)
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    session_id = optional_str(payload.get("session_id"))
    if not session_id:
        return jsonify({"error": "session_id_required"}), 400
    profile_name = str(payload.get("profile_name") or "").strip()
    profiles = load_profiles()
    selected_profile = next(
        (item for item in profiles if item["name"] == profile_name),
        profiles[0] if profiles else empty_profile(),
    )
    query = build_ledger_query_service(
        optional_str(payload.get("ledger_database_url")) or DEFAULT_LEDGER_URL
    )
    session_data = query.get_session(session_id)
    if session_data is None:
        return jsonify({"error": "session_not_found", "session_id": session_id}), 404
    state = hydrate_plan_state_from_session(
        session_id=session_id,
        profile=selected_profile,
        session_payload=session_data,
    )
    last_run_id = None
    runs = session_data.get("runs")
    if isinstance(runs, list) and runs:
        last_run = runs[-1]
        if isinstance(last_run, dict):
            last_run_id = optional_str(last_run.get("run_id"))
    return jsonify(
        {
            "state": state.to_dict(),
            "session": session_data,
            "last_run_id": last_run_id,
        }
    )

@api_bp.get("/runs/<run_id>")
def get_run(run_id: str):
    ledger_database_url = request.args.get("ledger_database_url") or DEFAULT_LEDGER_URL
    query = build_ledger_query_service(ledger_database_url)
    data = query.get_run(run_id)
    if data is None:
        return jsonify({"error": "run_not_found", "run_id": run_id}), 404
    return jsonify(data)

@api_bp.get("/evidence")
def get_evidence():
    ledger_database_url = request.args.get("ledger_database_url") or DEFAULT_LEDGER_URL
    query = build_ledger_query_service(ledger_database_url)
    data = query.get_evidence(
        run_id=optional_str(request.args.get("run_id")),
        session_id=optional_str(request.args.get("session_id")),
        evidence_kind=optional_str(request.args.get("evidence_kind")),
        limit=int(request.args.get("limit") or 100),
    )
    return jsonify({"items": data, "count": len(data)})

@api_bp.get("/artifacts/open")
def open_artifact_file():
    raw_path = optional_str(request.args.get("path"))
    if not raw_path:
        return jsonify({"error": "path_required"}), 400
    resolved_path = resolve_local_artifact_path(raw_path)
    if resolved_path is None:
        return jsonify({"error": "artifact_not_found"}), 404
    if not is_allowed_artifact_path(resolved_path):
        return jsonify({"error": "artifact_path_not_allowed"}), 403
    return send_file(resolved_path, as_attachment=False)
