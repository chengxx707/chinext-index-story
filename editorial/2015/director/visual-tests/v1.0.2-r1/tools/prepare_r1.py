"""Bind R1 to the delivered 48-cue Git snapshot and validate its revised timeline."""
import argparse
from hashlib import file_digest, sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys

from jsonschema import Draft202012Validator
from r1_candidate import BASE_CANDIDATE_SHA256, BASE_COMMIT, apply_r1_candidate
from runtime_audit_r1 import audit_runtime

RUNTIME_COMMIT = "67a8cc6740c521675f71c6c733997e429681c3a2"
COMPILED_COMMIT = "5e211d52afe376ff393a050493c4a1e780e780d9"
DIRECTOR = Path("editorial/2015/director")
COMPILED = DIRECTOR/"compiled/v1.0.2"
PRIOR = DIRECTOR/"visual-tests/v1.0.2"
RELEASE = Path("editorial/2015/releases/v1.0.1")
SCHEMA = RELEASE/"director_timeline.schema.json"
FROZEN = [Path(item) for item in ("data/cyb_daily.csv","config/production/film_master_v1.json",
    "config/event_registry.json","assets/earth_cinematic.png","assets/earth_body.png",
    "assets/reference/approved_visual_reference.png")]
BLOCKS = {"B01-B02":[0,540],"B08-B10":[2280,3600],"B16-B18":[5520,7320]}
B08 = ("target.mp4","phone-390.mp4","keyframe-contact.jpg","manifest.json","review.md",
       "contact_sources.json","diagnostics.json","media_validation.json")


def blob(root, commit, path):
    return subprocess.check_output(["git","show",f"{commit}:{path}"],cwd=root)


def paths_at(root, commit, *paths):
    return [Path(name) for name in subprocess.check_output(
        ["git","ls-tree","-r","--name-only",commit,*map(str,paths)],cwd=root,text=True).splitlines()]


def write(path, body):
    path.write_text(json.dumps(body,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def checksum(path):
    with path.open("rb") as stream:
        return file_digest(stream,"sha256").hexdigest()


def bind(root, runtime, inputs):
    records = {}
    release_paths = paths_at(root,BASE_COMMIT,RELEASE)
    actual_release = {p.relative_to(root) for p in (root/RELEASE).rglob("*") if p.is_file()}
    if len(release_paths) != 29 or set(release_paths) != actual_release:
        raise ValueError("Frozen V1.0.1 release file set changed")
    for path in FROZEN+release_paths:
        body=blob(root,BASE_COMMIT,path)
        if (root/path).read_bytes() != body:
            raise ValueError(f"Frozen working-directory bytes changed: {path}")
        records[str(root/path)] = sha256(body).hexdigest()
    for path in paths_at(root,RUNTIME_COMMIT,"src/chinext_v6","tools/render_editorial_preview.py",SCHEMA):
        body=blob(root,RUNTIME_COMMIT,path)
        if (runtime/path).read_bytes() != body:
            raise ValueError(f"Legacy renderer differs from the published commit: {path}")
        records[str(runtime/path)] = sha256(body).hexdigest()
    for path in (
        Path("editorial/2015/HANDOFF_TO_CODEX.md"),DIRECTOR/"GPT_VISUAL_DECISIONS_V1.0.2.md",
        DIRECTOR/"EVENT_CLOCK_REGISTER_V1.0.2.json",COMPILED/"candidate.schema.json",
        Path("docs/production/PROJECT-DASHBOARD.md")
    ):
        body=blob(root,BASE_COMMIT,path)
        if (inputs/path).read_bytes() != body:
            raise ValueError(f"Unpinned editorial input: {path}")
        records[str(inputs/path)] = sha256(body).hexdigest()
    for name in ("compile_candidate.py","event_audit.py","market_audit.py","runtime_audit.py","scene_plan.py"):
        path = COMPILED/"tools"/name
        body=blob(root,COMPILED_COMMIT,path)
        if (inputs/path).read_bytes() != body:
            raise ValueError(f"Unpinned compiler helper: {path}")
        records[str(inputs/path)] = sha256(body).hexdigest()
    return records


def reuse_b08(old_result, out, manifest, root):
    dest = out/"B08-B10"
    dest.mkdir(exist_ok=True)
    records = {}
    published = set(paths_at(root,BASE_COMMIT,PRIOR/"B08-B10"))
    for name in (*B08,"solo-review/playback_observation.json"):
        rel = Path("B08-B10")/name
        old = old_result/rel
        wanted = manifest["artifacts"][str(rel)]
        if old.stat().st_size != wanted["bytes"] or checksum(old) != wanted["sha256"]:
            raise ValueError(f"Reuse SHA does not match baseline manifest: {rel}")
        if PRIOR/rel in published and sha256(blob(root,BASE_COMMIT,PRIOR/rel)).hexdigest() != wanted["sha256"]:
            raise ValueError(f"Reuse artifact differs from the GitHub file: {rel}")
        location = dest/name
        location.parent.mkdir(exist_ok=True)
        shutil.copyfile(old,location)
        assert checksum(location) == wanted["sha256"]
        records[str(rel)] = wanted
    return {"status":"REUSED_AND_HASH_VERIFIED","source_commit":BASE_COMMIT,"frame_span":BLOCKS["B08-B10"],
            "seconds":44,"files":records,"prior_media_report":"B08-B10/media_validation.json",
            "prior_single_playback":"B08-B10/solo-review/playback_observation.json"}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--repo-root", type=Path, default=Path.cwd())
    cli.add_argument("--runtime-root", type=Path, required=True)
    cli.add_argument("--inputs", type=Path, required=True)
    cli.add_argument("--old-result", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    args=cli.parse_args()
    root,runtime,inputs,old_result,out = (getattr(args,name).resolve() for name in
                                         ("repo_root","runtime_root","inputs","old_result","output"))
    if not out.is_relative_to(root/"output"):
        cli.error("Use an ignored output/ subdirectory")
    out.mkdir(parents=True,exist_ok=True)
    records=bind(root,runtime,inputs)
    for filename,short in (("candidate.json","baseline_candidate.json"),("manifest.json","baseline_manifest.json"),
                           ("execution_receipt.json","baseline_receipt.json")):
        path=inputs/short
        if path.read_bytes()!=blob(root,BASE_COMMIT,PRIOR/filename):
            raise ValueError(f"Input does not match delivered visual baseline: {filename}")
        records[str(path)]=checksum(path)
    base_path=inputs/"baseline_candidate.json"
    if checksum(base_path)!=BASE_CANDIDATE_SHA256:
        raise ValueError("The input must be the actual 48-cue delivered visual candidate")
    base=json.loads(base_path.read_bytes())
    candidate=apply_r1_candidate(base)
    assert len(candidate["cues"])==48 and candidate["frame_count"]==7320
    assert [cue for cue in base["cues"] if cue["beat_id"] in {"B08","B09","B10"}] == [
        cue for cue in candidate["cues"] if cue["beat_id"] in {"B08","B09","B10"}]
    sys.path.insert(0,str(inputs/COMPILED/"tools"))
    from compile_candidate import project_legacy

    schema=json.loads((inputs/COMPILED/"candidate.schema.json").read_bytes())
    errors=[error.message for error in Draft202012Validator(schema).iter_errors(candidate)]
    segments=project_legacy(candidate,json.loads((runtime/SCHEMA).read_bytes()))
    runtime_report=audit_runtime(candidate,segments,root,runtime)
    write(out/"candidate.json",candidate)
    write(out/"clock_revalidation.json",runtime_report)
    legacy=out/"legacy"
    legacy.mkdir(exist_ok=True)
    write(legacy/"segments.json",[{k:v for k,v in seg.items() if k!="timeline"} for seg in segments])
    for segment in segments:
        write(legacy/f'{segment["id"]}.json',segment["timeline"])
    reuse=reuse_b08(old_result,out,json.loads((inputs/"baseline_manifest.json").read_bytes()),root)
    write(out/"reused_b08.json",reuse)
    receipt={"passed":not errors and runtime_report["passed"],"editorial_base_commit":BASE_COMMIT,
             "compiled_commit":COMPILED_COMMIT,"runtime_commit":RUNTIME_COMMIT,
             "baseline_candidate_sha256":BASE_CANDIDATE_SHA256,"candidate_schema_errors":errors,
             "clock_passed":runtime_report["passed"],"runtime_errors":runtime_report["runtime"]["errors"],
             "candidate_frames":candidate["frame_count"],"fps":30,"candidate_cues":len(candidate["cues"]),
             "frame_ranges":BLOCKS,"newly_rendered_ranges":[BLOCKS["B01-B02"],BLOCKS["B16-B18"]],
             "references":{"latest_preferred_reference":"MISSING_ORIGINAL","white_house_reference":"MISSING_ORIGINAL",
                           "approved_fallback":str(FROZEN[-1]),"historical_building_with_verified_rights":"NOT_AVAILABLE"},
             "protected_input_sha256":records}
    write(out/"intake.json",receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k!="protected_input_sha256"},ensure_ascii=False,indent=2))
    return 0 if receipt["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())
