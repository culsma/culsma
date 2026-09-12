#!/usr/bin/env python3
"""Deterministic benchmark metrics from existing Culsma JSON artifacts.

The pilot supports the source shapes exercised by Cases 00 and 04. Unsupported shapes
fail explicitly. No Culsma parser is imported; only step comment lines are read.
capture invokes the existing CLI to establish a hash-bound artifact bundle.
extract reads that bundle and emits exactly three per-case evaluation files.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

RULE_VERSION = "patterns-metrics-00-04-v2"
BUNDLE_SCHEMA = "patterns-metrics-input-v2"
OUTPUT_SCHEMA = "patterns-metrics-v1"
ARTIFACT_NAMES = ("ast", "ir", "plan", "run", "result", "output")
FILES = ("action_descriptors.json", "material_state_continuity.json",
         "result_traceability.json")


class EvidenceError(ValueError):
    """Missing, ambiguous, unsupported, or inconsistent evidence."""


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def value_id(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def read_json(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    sort_keys=True, allow_nan=False) + "\n")


def plain(value):
    """Remove positions only; preserve authored parameter expressions."""
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items() if k != "span"}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def nodes(value, pointer=""):
    """Walk already-parsed JSON, retaining RFC 6901 pointers."""
    if isinstance(value, dict):
        yield pointer, value
        for key, item in value.items():
            if key != "span":
                escaped = key.replace("~", "~0").replace("/", "~1")
                yield from nodes(item, pointer + "/" + escaped)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from nodes(item, pointer + "/" + str(index))


def artifact_path(root, name):
    choices = [root / "artifacts" / (name + suffix)
               for suffix in (".json", ".json.gz")]
    found = [p for p in choices if p.is_file()]
    require(len(found) == 1, f"INPUT_ARTIFACT: expected one {name} JSON")
    return found[0]


def locked_versions(path=None):
    """Read the two pinned dependencies from this benchmark's pip lock file."""
    path = Path(path) if path is not None else Path(__file__).resolve().parents[1] / "requirements.lock"
    versions = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"(culsma|lark)==([A-Za-z0-9.+-]+)\s+--hash=sha256:[a-f0-9]{64}", line)
        require(match is not None, "DEPENDENCY_LOCK: expected an exact version and SHA-256")
        require(match[1] not in versions, "DEPENDENCY_LOCK: duplicate package")
        versions[match[1]] = match[2]
    require(set(versions) == {"culsma", "lark"}, "DEPENDENCY_LOCK: missing culsma or lark")
    return versions


def discover_scope(source, ast):
    """Read step comments; obtain entries, calls and boundaries from exported AST."""
    require(not ast.get("source_includes") and not ast.get("library_imports"),
            "UNSUPPORTED_FRONTEND: expected a single source file")
    procedures = {p["name"]: p for p in ast["protocols"]}
    require(len(procedures) == len(ast["protocols"]), "AMBIGUOUS_PROTOCOL")
    calls = [n for _, n in nodes(ast["statements"])
             if "args" in n and n.get("name") in procedures]
    require(len(calls) == 1, "UNSUPPORTED_ENTRY: expected one top-level protocol call")
    entry = calls[0]["name"]
    children = {name: {n["name"] for _, n in nodes(proc["statements"])
                       if "args" in n and n.get("name") in procedures}
                for name, proc in procedures.items()}
    reachable = set()

    def visit(name, stack):
        require(name not in stack, "RECURSIVE_CALL: " + name)
        if name in reachable:
            return
        reachable.add(name)
        for child in sorted(children[name]):
            visit(child, stack + [name])

    visit(entry, [])
    labels = {name: set() for name in reachable}
    offset = 0
    for line_no, line in enumerate(source.splitlines(keepends=True), 1):
        position = offset + len(line) - len(line.lstrip())
        offset += len(line)
        owners = [name for name in reachable
                  if procedures[name]["span"]["start"] <= position < procedures[name]["span"]["end"]]
        if not owners or not re.match(r"\s*//\s*Source step", line):
            continue
        require(len(owners) == 1, "STEP_MAPPING: ambiguous protocol owner")
        match = re.fullmatch(r"\s*//\s*Source step (S[1-9]\d*):[^\r\n]*[\r\n]*", line)
        require(match is not None, f"STEP_MARKER: invalid/ranged marker at line {line_no}")
        labels[owners[0]].add(match[1])
    found = set().union(*labels.values())
    require(found, "STEP_MARKER: no source steps found")
    expected = sorted(found, key=lambda s: int(s[1:]))
    require(expected == [f"S{i}" for i in range(1, len(expected) + 1)],
            "STEP_MARKER: labels must be contiguous from S1")
    # The benchmark has unmarked batch wrappers (10/12/13). Follow their
    # single callee, but keep branching or marked roots as the shared scope.
    scope = entry
    while not labels[scope] and len(children[scope]) == 1:
        scope = next(iter(children[scope]))
    return dict(protocol=entry, step_protocol=scope, expected_steps=expected)


def capture(config_path, python, destination):
    """Run the existing compiler, without parsing or altering the input source."""
    config_path, destination = Path(config_path).resolve(), Path(destination).resolve()
    automatic = config_path.suffix == ".culs"
    if automatic:
        source = config_path
        case_id = source.parent.name
        require(re.fullmatch(r"[0-9]{2}", case_id), "CASE_ID: expected a two-digit case directory")
        config = dict(case_id=case_id, role="worked_example" if case_id == "00" else "corpus",
                      profile="nested-v1", source="protocol.culs", source_sha256=digest(source),
                      **{k + "_version": v for k, v in locked_versions().items()})
    else:
        # Retain reading historical capture configurations for regression tests.
        config = read_json(config_path)
        source = (config_path.parent / config["source"]).resolve()
    require(digest(source) == config["source_sha256"], "INPUT_SOURCE_HASH: config differs")
    require(not destination.exists(), f"OUTPUT_EXISTS: {destination}")
    # Make the executable independent of cwd without dereferencing a venv symlink.
    # Both subprocesses MUST use this same spelling: the symlink path selects pyvenv.cfg.
    selected = shutil.which(os.path.expanduser(str(python)))
    require(selected is not None, f"PYTHON_NOT_FOUND: {python}")
    python = os.path.abspath(selected)
    environment_code = (
        "import json,sys,culsma,importlib.metadata as m;"
        "print(json.dumps({'python':sys.version.split()[0],"
        "'culsma':m.version('culsma'),'lark':m.version('lark'),"
        "'executable':sys.executable,'prefix':sys.prefix,"
        "'culsma_file':culsma.__file__}))"
    )
    env = json.loads(subprocess.check_output(
        [str(python), "-I", "-c", environment_code], text=True))
    for key in ("culsma", "lark"):
        require(env[key] == config[key + "_version"], f"VERSION_MISMATCH: {key}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".capture-", dir=destination.parent))
    try:
        shutil.copyfile(source, temp / "protocol.culs")
        require(digest(temp / "protocol.culs") == config["source_sha256"],
                "INPUT_SOURCE_HASH: changed while copying")
        command = [python, "-I", "-m", "culsma.cli", "run",
                   "protocol.culs", "--json", "--artifacts-dir", "artifacts"]
        with (temp / "stdout.txt").open("w") as out, (temp / "stderr.txt").open("w") as err:
            result = subprocess.run(command, cwd=temp, stdout=out, stderr=err)
        require(result.returncode == 0,
                "CAPTURE_FAILED: " + (temp / "stderr.txt").read_text()[-3000:])
        require(digest(temp / "protocol.culs") == config["source_sha256"],
                "INPUT_SOURCE_HASH: changed during capture")
        for name in ARTIFACT_NAMES:
            artifact_path(temp, name)
        if automatic:
            config.update(discover_scope((temp / "protocol.culs").read_text(),
                                         read_json(artifact_path(temp, "ast"))))
        # This is generated capture metadata, not a maintained case input.
        write_json(temp / "case.json", dict(config, source="protocol.culs"))
        # Record the generated absolute source path before atomically moving.
        # Consumers use source hashes and relative file evidence, not this host path.
        receipt = {
            "schema": BUNDLE_SCHEMA, "environment": env,
            "command": command, "exit_code": result.returncode,
            "captured_source_path": str(temp / "protocol.culs"),
            "files": {str(p.relative_to(temp)): digest(p)
                      for p in sorted(temp.rglob("*")) if p.is_file()},
        }
        write_json(temp / "receipt.json", receipt)
        require(not destination.exists(), f"OUTPUT_EXISTS: {destination}")
        temp.rename(destination)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return destination


def load_bundle(root):
    root = Path(root).resolve()
    receipt = read_json(root / "receipt.json")
    require(receipt.get("schema") == BUNDLE_SCHEMA, "INPUT_SCHEMA: receipt")
    require(receipt["command"][0] == receipt["environment"]["executable"],
            "INPUT_INTERPRETER: version probe and execution paths differ")
    require(receipt.get("exit_code") == 0, "INPUT_RUN: capture failed")
    files = receipt.get("files", {})
    require(isinstance(files, dict), "INPUT_SCHEMA: files")
    for relative, expected in files.items():
        path = (root / relative).resolve()
        require(path.is_relative_to(root), "INPUT_PATH: escapes bundle")
        require(path.is_file() and digest(path) == expected,
                f"INPUT_HASH: {relative} differs from captured input")
    require(all(n in files for n in ("case.json", "protocol.culs")),
            "INPUT_HASH: source/config not covered")
    config = read_json(root / "case.json")
    require(config["source"] == "protocol.culs", "INPUT_SOURCE: unsupported path")
    require(digest(root / "protocol.culs") == config["source_sha256"],
            "INPUT_SOURCE_HASH: config differs")
    for key in ("culsma", "lark"):
        require(receipt["environment"][key] == config[key + "_version"],
                f"VERSION_MISMATCH: {key}")
    require(receipt["environment"]["culsma"] in {"1.0.6", "1.0.7rc1"},
            "UNSUPPORTED_VERSION: supported snapshots are Culsma 1.0.6 and 1.0.7rc1")
    data, paths = {}, {}
    for name in ARTIFACT_NAMES:
        path = artifact_path(root, name)
        relative = str(path.relative_to(root))
        require(relative in files, f"INPUT_HASH: {relative} not covered")
        data[name], paths[name] = read_json(path), relative
    return config, receipt, data, paths


class Extractor:
    support_scope = "Case 00 source shapes; unsupported shapes fail"
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.config, self.receipt, self.data, self.paths = load_bundle(self.root)
        self.source = (self.root / "protocol.culs").read_text()
        self.rows, self.objects, self.symbols = {}, {}, {}
        self.runtime_uses = {}
        self.covered_plan_ids = set()
        ast = self.data["ast"]
        require(not ast.get("source_includes") and not ast.get("library_imports"),
                "UNSUPPORTED_FRONTEND: includes/imports are not in pilot")
        protocols = ast["protocols"]
        require(len(protocols) == 1 and protocols[0]["name"] == self.config["protocol"],
                "UNSUPPORTED_ENTRY: pilot requires one named protocol")
        self.protocol = protocols[0]
        require(self.protocol["source_path"] == self.receipt["captured_source_path"],
                "INPUT_SOURCE_PATH: AST is from a different capture")
        entry = ast["statements"]
        require(len(entry) == 1, "UNSUPPORTED_ENTRY: expected one default call")
        call = entry[0].get("value", entry[0])
        require(call.get("name") == self.config["protocol"] and call.get("args") == [],
                "UNSUPPORTED_ENTRY: expected one default call")
        self.entry_binding = entry[0].get("name") if "value" in entry[0] else None
        self.parameters = {}
        for i, param in enumerate(self.protocol["params"]):
            require(set(param) == {"name", "default", "span"},
                    "UNSUPPORTED_PARAMETER")
            value = param["default"]
            require(isinstance(value, dict) and set(value) == {"value", "unit", "span"},
                    "UNSUPPORTED_PARAMETER: literal quantity default required")
            self.parameters[param["name"]] = {
                "value": plain(value), "evidence": self.ev("ast", f"/protocols/0/params/{i}", param)
            }
        self.markers = self.step_map()
        self.rows = {s: {} for s in self.config["expected_steps"]}
        self.plan = self.execution_index()

    def ev(self, artifact, pointer, node=None):
        evidence = {"file": self.paths[artifact], "json_pointer": pointer}
        if node and "span" in node:
            evidence.update(source_file="protocol.culs", source_span=node["span"])
        return evidence

    def step_map(self):
        expected = self.config["expected_steps"]
        require(expected == [f"S{i}" for i in range(1, len(expected) + 1)],
                "STEP_CONFIG: expected consecutive S1–SN")
        span = self.protocol["span"]
        markers = []
        offset = 0
        for line_no, line in enumerate(self.source.splitlines(keepends=True), 1):
            if span["start"] <= offset < span["end"] and re.match(r"\s*//\s*Source step", line):
                match = re.fullmatch(r"\s*//\s*Source step (S[1-9]\d*):[^\r\n]*[\r\n]*", line)
                require(match is not None, f"STEP_MARKER: invalid/ranged marker at line {line_no}")
                markers.append({"step": match[1], "marker_line": line_no,
                                "marker_offset": offset})
            offset += len(line)
        require([m["step"] for m in markers] == expected,
                f"STEP_MARKER: expected {expected}, found {[m['step'] for m in markers]}")
        first = self.protocol["statements"][0]["span"]["start"]
        for i, marker in enumerate(markers):
            marker["start"] = first if i == 0 else marker["marker_offset"]
            marker["end"] = markers[i+1]["marker_offset"] if i+1 < len(markers) else span["end"]
        for _, node in nodes(self.protocol):
            if "span" in node:
                sp = node["span"]
                require(0 <= sp["start"] < sp["end"] <= len(self.source),
                        "SOURCE_SPAN: outside source")
                require(self.source.count("\n", 0, sp["start"]) + 1 == sp["line"],
                        "SOURCE_SPAN: line/offset mismatch")
        return markers

    def step(self, node):
        span = node["span"]
        matches = [m for m in self.markers if m["start"] <= span["start"] < m["end"]]
        require(len(matches) == 1, f"STEP_MAPPING: line {span['line']}")
        require(span["end"] <= matches[0]["end"],
                f"STEP_MAPPING: construct crosses step boundary at line {span['line']}")
        return matches[0]["step"]

    def execution_index(self):
        plan, run, report = self.data["plan"], self.data["run"], self.data["result"]
        require(not plan["diagnostics"] and run["ok"] and not run["diagnostics"],
                "RUN_FAILED: diagnostics or non-success")
        require(self.data["output"]["ok"], "RUN_FAILED: output")
        require(self.data["output"]["report"] == report == run["user_result"],
                "RUN_REPORT: output, result and run differ")
        require(len(plan["plans"]) == 1, "UNSUPPORTED_ENTRY: multiple execution plans")
        steps = plan["plans"][0]["steps"]
        ids = [s["step_id"] for s in steps]
        require(len(ids) == len(set(ids)), "RUN_PLAN: duplicate step IDs")
        status = run["state"]["step_status"]
        require(set(status) == set(ids), "RUN_STATUS: plan/state ID mismatch")
        require(set(status.values()) <= {"completed", "skipped", "failed"},
                "RUN_STATUS: unknown/incomplete state")
        starts, completed = {}, {}
        for i, event in enumerate(run["events"]):
            key = event["step_id"]
            require(key in status, "RUN_EVENT: unknown step")
            if event["kind"] == "STEP_STARTED":
                require(key not in starts, "RUN_EVENT: duplicate start")
                starts[key] = i
            elif event["kind"] == "STEP_COMPLETED":
                require(key not in completed and key in starts,
                        "RUN_EVENT: duplicate completion or missing start")
                completed[key] = i
            else:
                raise EvidenceError("UNSUPPORTED_RUN_EVENT: " + event["kind"])
        require(set(completed) == {s for s in ids if status[s] == "completed"},
                "RUN_STATUS: completion events disagree")
        execution = report["execution"]
        counts = Counter(status.values())
        require(execution["ok"] and execution["failed_steps"] == 0
                and execution["diagnostic_count"] == 0, "RUN_FAILED: not clean")
        for field, count in (("total_steps", len(ids)), ("completed_steps", counts["completed"]),
                             ("skipped_steps", counts["skipped"]), ("failed_steps", counts["failed"])):
            require(type(execution[field]) is int and execution[field] == count,
                    "RUN_COUNTS: " + field)
        # Branch execution mapping will be implemented separately. Do not guess it.
        require(not counts["skipped"], "UNSUPPORTED_PATH: pilot requires fully completed plan")
        self.completed = completed
        indexed = []
        for i, item in enumerate(steps):
            event = run["events"][completed[item["step_id"]]]
            require(event["span"] == item["span"], "RUN_SPAN: plan/event mismatch")
            started = run["events"][starts[item["step_id"]]]
            require(started["payload"]["op"] == item["op"] and started["span"] == item["span"],
                    "RUN_OP: start event/plan mismatch")
            driver_op = event["payload"].get("driver_payload", {}).get("op")
            require(driver_op is None or driver_op == item["op"],
                    "RUN_OP: completion event/plan mismatch")
            indexed.append((i, item, completed[item["step_id"]]))
        return indexed

    def add(self, step, category, label, payload, evidence, identity=None):
        key = canonical([category, identity if identity else payload])
        row = self.rows[step].setdefault(key, {
            "id": "descriptor:" + value_id([step, key])[:20],
            "category": category, "label": label, "details": payload, "evidence": [],
        })
        if evidence not in row["evidence"]:
            row["evidence"].append(evidence)

    def expression(self, expr, pointer, allow_token=False):
        require(isinstance(expr, dict), f"UNSUPPORTED_EXPRESSION: {pointer}")
        shape = set(expr) - {"span"}
        if shape == {"value", "unit"} or shape == {"value"}:
            return plain(expr)
        if shape == {"name"}:
            name = expr["name"]
            if name in self.symbols:
                return {"object_id": self.symbols[name]}
            if name in self.parameters:
                return {"parameter": name, "default": self.parameters[name]["value"]}
            require(allow_token, f"UNRESOLVED_REFERENCE: {name} at {pointer}")
            return {"token": name}
        if shape == {"args", "name"}:
            require(expr["name"] in {"tube", "content", "centrifuge_program", "schedule"},
                    f"UNSUPPORTED_EXPRESSION_CALL: {expr['name']} at {pointer}")
            return {"call": expr["name"], "args": self.arguments(expr["args"], pointer + "/args", True)}
        if shape == {"elements"}:
            return [self.expression(x, f"{pointer}/elements/{i}", allow_token)
                    for i, x in enumerate(expr["elements"])]
        if shape == {"entries"}:
            return {k: self.expression(v, pointer + "/entries/" + k, True)
                    for k, v in expr["entries"].items()}
        if shape == {"left", "right"}:
            return {"source": self.expression(expr["left"], pointer + "/left"),
                    "amount": self.expression(expr["right"], pointer + "/right")}
        if shape == {"base", "member"}:
            if allow_token and expr["base"].get("name") in {"ContentKind", "ContentType", "ContainerKind"}:
                return {"base": {"token": expr["base"]["name"]}, "member": expr["member"]}
            require(expr["member"] == "contents", "UNSUPPORTED_MEMBER: " + pointer)
            return {"base": self.expression(expr["base"], pointer + "/base"),
                    "member": "contents"}
        if shape == {"base", "index"}:
            require(expr["base"].get("member") == "contents",
                    "UNSUPPORTED_SELECTOR: pilot supports contents fractions only")
            index = expr["index"]
            require(index.get("unit") is None and type(index.get("value")) in (int, float)
                    and index["value"] in (0, 1), "UNSUPPORTED_FRACTION_INDEX")
            return {"base": self.expression(expr["base"], pointer + "/base"),
                    "index": index["value"]}
        raise EvidenceError(f"UNSUPPORTED_EXPRESSION: {sorted(shape)} at {pointer}")

    def arguments(self, args, pointer, tokens=False):
        values = {}
        for i, arg in enumerate(args):
            require(set(arg) == {"name", "value", "span"} and arg["name"] is not None,
                    "UNSUPPORTED_ARGUMENT: " + pointer)
            require(arg["name"] not in values, "DUPLICATE_ARGUMENT")
            # Only language token/metadata slots allow unbound identifiers.
            token_slot = tokens and arg["name"] in {"kind", "type", "attrs"}
            values[arg["name"]] = self.expression(arg["value"], f"{pointer}/{i}/value", token_slot)
        return values

    def object_refs(self, expr, pointer):
        for path, node in nodes(expr, pointer):
            if set(node) == {"name", "span"} and node["name"] in self.symbols:
                yield self.symbols[node["name"]], path, node

    def match_execution(self, statement, op):
        matches = []
        span = statement["span"]
        for i, item, event_index in self.plan:
            # hold lowers to env_hold with its enclosing environment span.
            if op == "hold":
                found = (item["op"] == "env_hold"
                         and item["span"]["start"] <= span["start"]
                         and span["end"] <= item["span"]["end"])
            else:
                found = item["op"] == op and item["span"] == span
            if found:
                matches.append((i, item, event_index))
        require(matches, f"EXECUTION_MAPPING: {op} at line {span['line']}")
        self.covered_plan_ids.update(s["step_id"] for _, s, _ in matches)
        return matches

    def reference_execution(self, node, object_id, matches):
        evidence = []
        obj = self.objects[object_id]
        for index, item, event_index in matches:
            candidates = []
            structures = [("/args", item["args"])]
            if item["op"] == "env_hold":
                structures.append(("/gate/env_targets", item["gate"]["env_targets"]))
            for prefix, structure in structures:
                for pointer, value in nodes(structure, prefix):
                    if value.get("kind") == "IRIdentifier" and value.get("span") == node["span"]:
                        candidates.append((pointer, value))
            require(candidates, f"REFERENCE_MAPPING: {obj['name']} in {item['step_id']}")
            require(all(v["name"] == obj["runtime_binding"] for _, v in candidates),
                    f"REFERENCE_IDENTITY: {obj['name']} binding mismatch")
            for pointer, _ in candidates:
                evidence.append({
                    "step_id": item["step_id"],
                    "plan": self.ev("plan", f"/plans/0/steps/{index}" + pointer),
                    "completed_event": self.ev("run", f"/events/{event_index}"),
                })
        return evidence

    def uses(self, expression, pointer, statement, matches):
        step = self.step(statement)
        for oid, path, node in self.object_refs(expression, pointer):
            obj = self.objects[oid]
            self.add(step, "object", obj["name"],
                     {"object_id": oid, "declaration": obj["declaration"]},
                     self.ev("ast", path, node), oid)
            records = self.reference_execution(node, oid, matches)
            self.runtime_uses.setdefault(oid, {}).setdefault(step, []).append({
                "source_reference": self.ev("ast", path, node), "execution": records})

    def declare(self, statement, pointer):
        name = statement["name"]
        require(name not in self.symbols and name not in self.parameters,
                "UNSUPPORTED_BINDING: reassignment/shadowing")
        value = statement["value"]
        constructor = value.get("name")
        require(constructor in {"tube", "img"}, "UNSUPPORTED_DECLARATION: " + str(constructor))
        oid = "object:" + value_id([self.config["protocol"], pointer])[:20]
        if constructor == "tube":
            declaration = self.expression(value, pointer + "/value")
            matches = [(i, s, e) for i, s, e in self.plan
                       if s["op"] == "AllocContainer" and s["span"] == statement["span"]]
            require(len(matches) == 1, "DECLARATION_MAPPING: single allocation required")
            i, plan_step, event_index = matches[0]
            delta = self.data["run"]["events"][event_index]["payload"]["material_delta"]
            binding = plan_step["args"]["bind"]
            require(delta["bind"] == binding and delta["op"] == "AllocContainer",
                    "DECLARATION_IDENTITY: allocation differs")
            identity = {"container_id": delta["container_id"]}
            # Allocation/load expansion is covered by the same declaration range.
            for _, ps, _ in self.plan:
                if statement["span"]["start"] <= ps["span"]["start"] < statement["span"]["end"]:
                    require(ps["op"] in {"AllocContainer", "DefineContent", "LoadContent"},
                            "DECLARATION_MAPPING: unexpected lowered operation")
                    self.covered_plan_ids.add(ps["step_id"])
        else:
            matches = self.match_execution(statement, "img")
            require(len(matches) == 1, "DECLARATION_MAPPING: repeated readout")
            i, plan_step, event_index = matches[0]
            args = self.readout_args(value, pointer + "/value")
            declaration = {"call": "img", "args": args}
            binding = plan_step["args"]["bind"]
            delta = self.data["run"]["events"][event_index]["payload"]["observation_delta"]
            require(delta["binding"] == binding, "DECLARATION_IDENTITY: readout differs")
            identity = {"data_id": delta["data_id"]}
            self.uses(value, pointer + "/value", statement, matches)
            self.add(self.step(statement), "operation", "img", declaration,
                     self.ev("ast", pointer + "/value", value))
        self.symbols[name] = oid
        obj = {
            "object_id": oid, "name": name,
            "kind": "container" if constructor == "tube" else "readout",
            "introduced_at": self.step(statement), "declaration": declaration,
            "runtime_binding": binding, "runtime_identity": identity,
            "evidence": {
                "declaration": self.ev("ast", pointer, statement),
                "plan": self.ev("plan", f"/plans/0/steps/{i}"),
                "completed_event": self.ev("run", f"/events/{event_index}"),
            },
        }
        self.objects[oid] = obj
        self.add(obj["introduced_at"], "object", name,
                 {"object_id": oid, "declaration": declaration},
                 self.ev("ast", pointer, statement), oid)

    def readout_args(self, value, pointer):
        args = value["args"]
        result = {}
        require({a["name"] for a in args} == {"sample", "quantity", "save_raw"},
                "UNSUPPORTED_READOUT_ARGS")
        for i, arg in enumerate(args):
            require(arg["name"] not in result, "DUPLICATE_ARGUMENT")
            result[arg["name"]] = self.expression(
                arg["value"], f"{pointer}/args/{i}/value", arg["name"] == "quantity")
        return result

    def associations(self, statements):
        """Keep source objects and selections in block-setting deduplication keys."""
        references = {}
        iterators = dict(getattr(self, "loop_bindings", {}))
        for pointer, node in nodes(statements):
            if set(node) - {"span"} == {"binding", "iterable", "statements", "times"}:
                iterators[node["binding"]] = self.expression(node["iterable"], pointer + "/iterable")
        for pointer, node in nodes(statements):
            shape = set(node) - {"span"}
            ref = None
            if shape == {"name"} and node["name"] in self.symbols:
                ref = {"object_id": self.symbols[node["name"]]}
            elif shape in ({"base", "regions"}, {"base", "index"}):
                name = node["base"].get("name")
                if name in self.symbols:
                    ref = {"object_id": self.symbols[name]}
                    if "regions" in node:
                        ref["selector"] = plain(node["regions"])
                    else:
                        index = node["index"]
                        ref["index"] = ({"iterator": iterators[index["name"]]}
                                        if index.get("name") in iterators else plain(index))
            if ref is not None:
                references[canonical(ref)] = ref
        return [references[key] for key in sorted(references)]

    def statements(self, statements, pointer):
        for i, statement in enumerate(statements):
            self.visit_statement(statement, pointer + "/" + str(i))

    def visit_statement(self, statement, path):
        step, shape = self.step(statement), set(statement) - {"span"}
        evidence = self.ev("ast", path, statement)
        if shape == {"name", "value"}:
            self.declare(statement, path)
        elif shape == {"target", "sources"}:
            payload = {"target": self.expression(statement["target"], path + "/target"),
                       "sources": [self.expression(s, f"{path}/sources/{j}")
                                   for j, s in enumerate(statement["sources"])]}
            matches = self.match_execution(statement, "Mutation")
            self.uses(statement, path, statement, matches)
            self.add(step, "operation", "transfer", payload, evidence)
        elif shape == {"env_args", "statements"}:
            self.add(step, "environment", "env",
                     {"args": self.arguments(statement["env_args"], path + "/env_args"),
                      "objects": self.associations(statement["statements"])}, evidence)
            self.statements(statement["statements"], path + "/statements")
        elif shape == {"binding", "iterable", "statements", "times"}:
            require(statement["times"] is None
                    and statement["iterable"].get("name") == "schedule",
                    "UNSUPPORTED_LOOP")
            require(statement["binding"] not in self.symbols
                    and statement["binding"] not in self.parameters, "UNSUPPORTED_LOOP_BINDING")
            self.add(step, "schedule", "schedule",
                     {"schedule": self.expression(statement["iterable"], path + "/iterable"),
                      "objects": self.associations(statement["statements"])}, evidence)
            # Visit once for static descriptors; the plate adapter resolves iterator
            # uses from the concrete arguments of each expanded plan operation.
            self.statements(statement["statements"], path + "/statements")
        elif shape == {"name", "args"}:
            name = statement["name"]
            require(name in {"hold", "sep"}, "UNSUPPORTED_OPERATION: " + name)
            args = self.arguments(statement["args"], path + "/args")
            require(set(args) == ({"sample"} if name == "hold" else {"sample", "program"}),
                    "UNSUPPORTED_OPERATION_ARGS: " + name)
            matches = self.match_execution(statement, name)
            self.uses(statement, path, statement, matches)
            self.add(step, "operation", name, {"call": name, "args": args}, evidence)
            if name == "sep":
                program_index = next(j for j, a in enumerate(statement["args"])
                                     if a["name"] == "program")
                program = statement["args"][program_index]["value"]
                self.add(step, "program", "centrifuge_program",
                         {"program": args["program"], "sample": args["sample"]},
                         self.ev("ast", f"{path}/args/{program_index}/value", program))
        else:
            raise EvidenceError(f"UNSUPPORTED_STATEMENT: {sorted(shape)} at {path}")

    def derive(self):
        self.statements(self.protocol["statements"], "/protocols/0/statements")
        require(self.covered_plan_ids == {s["step_id"] for _, s, _ in self.plan},
                "EXECUTION_COVERAGE: some plan operations lack source evidence")
        return self.build_outputs()

    def build_outputs(self):
        order = {s: i for i, s in enumerate(self.config["expected_steps"])}
        reuse = self.reuse_rows(order)
        descriptor_rows = []
        for marker in self.markers:
            step = marker["step"]
            entries = sorted(self.rows[step].values(), key=lambda x: (x["category"], x["id"]))
            descriptor_rows.append({"step": step, "source_range": marker,
                                    "descriptors": entries, "descriptor_items": len(entries)})
        inputs = dict(self.receipt["files"])
        inputs["receipt.json"] = digest(self.root / "receipt.json")
        metadata = {
            "schema_version": OUTPUT_SCHEMA, "case_id": self.config["case_id"],
            "case_role": self.config["role"], "rules_version": getattr(self, "rules_version", RULE_VERSION),
            "extractor_sha256": digest(Path(__file__)),
            "adapter_sha256": getattr(self, "adapter_sha256", None),
            "input_files": inputs, "environment": self.receipt["environment"],
            "evidence_base": str(self.root),
            "support_scope": self.support_scope,
            "profile": self.config.get("profile", "tube-v1"),
        }
        metadata["extraction_id"] = value_id(metadata)
        descriptors = dict(metadata, section="3.2", source_steps=len(descriptor_rows),
                           descriptor_items=sum(r["descriptor_items"] for r in descriptor_rows),
                           parameters=self.parameters, rows=descriptor_rows)
        execution = self.data["result"]["execution"]
        continuity = dict(metadata, section="3.3", rows=reuse,
                          reused_objects=len(reuse),
                          later_use_links=sum(r["later_use_links"] for r in reuse),
                          active_steps=execution["total_steps"]-execution["skipped_steps"],
                          completed_steps=execution["completed_steps"],
                          execution=execution,
                          execution_evidence=self.ev("result", "/execution"))
        trace = dict(metadata, section="3.4", **self.traceability())
        return dict(zip(FILES, (descriptors, continuity, trace)))

    def reuse_rows(self, order):
        reuse = []
        for oid, obj in self.objects.items():
            later = {s: uses for s, uses in self.runtime_uses.get(oid, {}).items()
                     if order[s] > order[obj["introduced_at"]]}
            if later:
                reuse.append({
                    "entry_id": oid, "members": [obj], "introduced_at": obj["introduced_at"],
                    "used_in": sorted(later, key=order.get), "uses": later,
                    "later_use_links": len(later),
                })
        return reuse

    def traceability(self):
        result = self.data["result"]
        materials, containers = result["materials"], result["resource_summary"]["containers"]
        require(materials["has_material_state"] is True, "RESULT_MATERIAL_STATE: missing")
        names = containers["touched_names"]
        require(isinstance(names, list) and all(isinstance(n, str) for n in names),
                "RESULT_CONTAINERS: invalid touched_names")
        require(type(containers["touched_count"]) is int
                and containers["touched_count"] == len(names), "RESULT_CONTAINERS: count mismatch")
        output = {}
        for label, key in (("reagent_records", "reagent_consumption"),
                           ("final_material_states", "final_products")):
            records = materials[key]
            require(isinstance(records, list) and all(isinstance(r, dict) for r in records),
                    "RESULT_MATERIALS: invalid " + key)
            require(all(isinstance(r.get("name"), str) for r in records),
                    "RESULT_MATERIALS: missing name in " + key)
            output[label] = len(records)
            output[key] = [{"record": row, "evidence": self.ev("result", f"/materials/{key}/{i}")}
                           for i, row in enumerate(records)]
        output.update(
            touched_containers=len(names),
            touched_names=[{"name": name, "evidence": self.ev(
                "result", f"/resource_summary/containers/touched_names/{i}")}
                           for i, name in enumerate(names)],
            container_identity={"available": False, "evidence_level": "runtime_summary_name_record",
                                "note": "List indices locate summary records, not container identities."},
            entry={"protocol": self.config["protocol"],
                   "evidence": self.ev("ast", "/protocols/0")},
            formal_returns={"value": self.data["output"]["returns"],
                            "evidence": self.ev("output", "/returns")},
        )
        return output



def select_groups(objects, uses, candidates, order):
    """Normalize, qualify, then simultaneously reject overlapping qualified groups."""
    normalized = {}
    for candidate in candidates:
        members = tuple(sorted(set(candidate["members"])))
        require(members and all(m in objects for m in members), "GROUP_MEMBERS: unresolved")
        row = normalized.setdefault(members, {"members": list(members), "bases": []})
        row["bases"].append(candidate)
    qualified, audit = {}, []
    for key, row in sorted(normalized.items()):
        intros = {objects[m]["introduced_at"] for m in key}
        later_sets = [{s for s in uses.get(m, {}) if order[s] > order[objects[m]["introduced_at"]]}
                      for m in key]
        qualifies = (len(intros) == 1
                     and any(b["introduced_at"] in intros for b in row["bases"])
                     and all(s == later_sets[0] for s in later_sets))
        row["status"] = "qualified" if qualifies else "different_introduction_or_uses"
        if qualifies:
            qualified[key] = row
        audit.append(row)
    overlaps = {key for key in qualified
                if any(key != other and set(key) & set(other) for other in qualified)}
    retained = []
    for key, row in qualified.items():
        row["status"] = "overlap" if key in overlaps else "retained"
        if key not in overlaps:
            retained.append(row)
    covered = {m for row in retained for m in row["members"]}
    entries = retained + [{"members": [m], "bases": []} for m in sorted(objects) if m not in covered]
    return entries, audit


class PlateExtractor(Extractor):
    """Existing-JSON adapter for Case 04, including selectors and grouped operations."""
    support_scope = "Cases 00/04 source shapes; multiple protocols and branches remain unsupported"

    def __init__(self, root):
        super().__init__(root)
        self.candidates = []
        self.loop_bindings = {}
        self.source_only = set()
        self.binding_to_member = {}
        self.script_ir = self.data["ir"]["script_entry"]
        require(isinstance(self.script_ir, dict), "PLATE_IR: script entry missing")

    def ir_declaration(self, statement):
        matches = [(p, n) for p, n in nodes(self.script_ir, "/script_entry")
                   if n.get("span") == statement["span"] and "name" in n and "value" in n]
        require(len(matches) == 1, f"IR_DECLARATION: line {statement['span']['line']}")
        return matches[0]

    def source_object(self, statement, pointer, kind, declaration, members=None):
        name = statement["name"]
        require(name not in self.symbols and name not in self.parameters
                and name not in self.loop_bindings, "UNSUPPORTED_BINDING: reassignment/shadowing")
        oid = "object:" + value_id([self.config["protocol"], pointer])[:20]
        obj = {
            "object_id": oid, "name": name, "kind": kind,
            "introduced_at": self.step(statement), "declaration": declaration,
            "evidence": {"declaration": self.ev("ast", pointer, statement)},
        }
        if members is not None:
            obj["member_ids"] = members
            self.source_only.add(oid)
        self.symbols[name] = oid
        self.objects[oid] = obj
        self.add(self.step(statement), "object", name,
                 {"object_id": oid, "declaration": declaration},
                 self.ev("ast", pointer, statement), oid)
        return oid, obj

    def declare(self, statement, pointer):
        value = statement["value"]
        shape, name = set(value) - {"span"}, value.get("name")
        if name == "plate":
            declaration = {"call": "plate", "args": self.arguments(value["args"], pointer + "/value/args")}
            carrier = declaration["args"].get("carrier_id", {}).get("value")
            require(isinstance(carrier, str), "PLATE_CARRIER: literal carrier_id required")
            members = []
            positions = set()
            for i, ps, ei in self.plan:
                if ps["op"] != "AllocContainer":
                    continue
                args = ps["args"]
                if args.get("carrier_id", {}).get("value") != carrier:
                    continue
                require(args.get("carrier_kind", {}).get("value") == "plate",
                        "PLATE_CARRIER: allocation family mismatch")
                position = args["carrier_position"]["value"]
                require(position not in positions, "PLATE_MEMBER: duplicate position")
                positions.add(position)
                event = self.data["run"]["events"][ei]
                delta = event["payload"]["material_delta"]
                require(delta["bind"] == args["bind"], "PLATE_MEMBER: binding mismatch")
                oid = "well:" + value_id([carrier, position, delta["container_id"]])[:20]
                self.objects[oid] = {
                    "object_id": oid, "name": position, "kind": "well",
                    "introduced_at": self.step(ps), "declaration": {
                        "carrier_id": carrier, "carrier_position": position},
                    "runtime_binding": args["bind"],
                    "runtime_identity": {"container_id": delta["container_id"]},
                    "evidence": {
                        "declaration": self.ev("plan", f"/plans/0/steps/{i}", ps),
                        "completed_event": self.ev("run", f"/events/{ei}")},
                }
                self.binding_to_member[args["bind"]] = oid
                self.covered_plan_ids.add(ps["step_id"])
                members.append(oid)
            require(members, "PLATE_MEMBERS: no matching allocated wells")
            self.source_object(statement, pointer, "plate_descriptor", declaration, members)
            return
        if shape == {"base", "regions"}:
            base_name = value["base"].get("name")
            require(base_name in self.symbols, "SELECTOR_BASE: unknown plate")
            parent = self.objects[self.symbols[base_name]]
            require(parent["kind"] == "plate_descriptor", "SELECTOR_BASE: expected plate")
            ir_pointer, ir_node = self.ir_declaration(statement)
            elements = ir_node["value"].get("elements")
            require(isinstance(elements, list) and elements, "SELECTOR_IR: member list missing")
            members = []
            for element in elements:
                require(element.get("name") in self.binding_to_member, "SELECTOR_IR: unresolved binding")
                member = self.binding_to_member[element["name"]]
                require(member in parent["member_ids"], "SELECTOR_IR: wrong plate")
                members.append(member)
            require(len(members) == len(set(members)), "SELECTOR_IR: duplicate member")
            declaration = {"selector": plain(value), "member_ids": members,
                           "ir_evidence": self.ev("ir", ir_pointer, ir_node)}
            oid, obj = self.source_object(statement, pointer, "well_group", declaration, members)
            obj["evidence"]["ir"] = self.ev("ir", ir_pointer, ir_node)
            self.candidates.append({
                "source_object": oid, "members": members, "introduced_at": self.step(statement),
                "evidence": obj["evidence"]})
            return
        if name == "data_schema":
            args = {}
            for j, arg in enumerate(value["args"]):
                require(arg["name"] in {"label", "fields"}, "SCHEMA_ARGS: unsupported")
                require(arg["name"] not in args, "SCHEMA_ARGS: duplicate")
                args[arg["name"]] = self.expression(arg["value"], f"{pointer}/value/args/{j}/value", True)
            declaration = {"call": name, "args": args}
            oid, obj = self.source_object(statement, pointer, "schema", declaration)
            ir_pointer, ir_node = self.ir_declaration(statement)
            obj["runtime_binding"] = ir_node["name"]
            obj["evidence"]["ir"] = self.ev("ir", ir_pointer, ir_node)
            matches = [(i, s, e) for i, s, e in self.plan if s["span"] == statement["span"]]
            require(matches, "SCHEMA_PLAN: missing")
            for i, ps, ei in matches:
                require(ps["op"] == "assign_local" and ps["args"]["target"] == obj["runtime_binding"], "SCHEMA_PLAN: unsupported operation")
                self.covered_plan_ids.add(ps["step_id"])
                obj["evidence"]["plan"] = self.ev("plan", f"/plans/0/steps/{i}")
                obj["evidence"]["completed_event"] = self.ev("run", f"/events/{ei}")
            self.add(self.step(statement), "schema", name, {"object_id": oid, **declaration},
                     self.ev("ast", pointer + "/value", value))
            return
        if name == "img":
            matches = self.match_execution(statement, "img")
            require(len(matches) == 1, "READOUT_PLAN: expected one grouped source operation")
            i, ps, ei = matches[0]
            args = self.readout_args(value, pointer + "/value")
            self.uses(value, pointer + "/value", statement, matches)
            declaration = {"call": name, "args": args}
            oid, obj = self.source_object(statement, pointer, "readout", declaration)
            delta = self.data["run"]["events"][ei]["payload"]["observation_delta"]
            require(delta["binding"] == ps["args"]["bind"], "READOUT_IDENTITY: binding differs")
            obj["runtime_binding"] = delta["binding"]
            obj["runtime_identity"] = {k: delta[k] for k in ("data_id", "data_group_id", "item_ids") if k in delta}
            require(obj["runtime_identity"], "READOUT_IDENTITY: missing")
            obj["evidence"].update(
                plan=self.ev("plan", f"/plans/0/steps/{i}"),
                completed_event=self.ev("run", f"/events/{ei}"))
            self.add(self.step(statement), "operation", name, declaration,
                     self.ev("ast", pointer + "/value", value))
            return
        super().declare(statement, pointer)
        oid = self.symbols[statement["name"]]
        self.binding_to_member[self.objects[oid]["runtime_binding"]] = oid

    def expression(self, expr, pointer, allow_token=False):
        shape = set(expr) - {"span"}
        if shape == {"name"} and expr["name"] in self.loop_bindings:
            return {"iterator": self.loop_bindings[expr["name"]]}
        if shape == {"base", "regions"}:
            return {"base": self.expression(expr["base"], pointer + "/base"),
                    "regions": plain(expr["regions"])}
        if shape == {"base", "index"} and expr["base"].get("member") != "contents":
            return {"base": self.expression(expr["base"], pointer + "/base"),
                    "index": self.expression(expr["index"], pointer + "/index")}
        if shape == {"source", "program", "index"}:
            require(expr["program"].get("name") == "filtration_program",
                    "UNSUPPORTED_PARTITION_PROGRAM")
            return {"partition": self.expression(expr["source"], pointer + "/source"),
                    "program": self.expression(expr["program"], pointer + "/program"),
                    "index": self.expression(expr["index"], pointer + "/index")}
        if shape == {"args", "name"} and expr["name"] == "filtration_program":
            return {"call": expr["name"], "args": self.arguments(expr["args"], pointer + "/args")}
        return super().expression(expr, pointer, allow_token)

    def readout_args(self, value, pointer):
        names = [a["name"] for a in value["args"]]
        require(set(names) in ({"sample", "quantity", "save_raw"},
                               {"sample", "quantity", "schema_ref", "save_raw"})
                and len(names) == len(set(names)), "UNSUPPORTED_READOUT_ARGS")
        return {a["name"]: self.expression(a["value"], f"{pointer}/args/{i}/value",
                                          a["name"] == "quantity")
                for i, a in enumerate(value["args"])}

    def selected_bindings(self, value, pointer):
        """Return concrete plan argument bindings, never all snapshot containers."""
        if isinstance(value, list):
            result = []
            for i, item in enumerate(value):
                result.extend(self.selected_bindings(item, pointer + "/" + str(i)))
            return result
        if value.get("kind") == "IRIdentifier":
            return [(value["name"], pointer)]
        require(value.get("kind") in {"IRGroup", "IRList"}, "SELECTOR_PLAN: concrete members missing")
        return self.selected_bindings(value["elements"], pointer + "/elements")

    def pair_references(self, source, actual, source_pointer, plan_pointer):
        shape = set(source) - {"span"}
        if shape == {"left", "right"}:
            require(actual.get("kind") == "IRPair", "REFERENCE_PAIR: plan differs")
            yield from self.pair_references(source["left"], actual["left"],
                                           source_pointer + "/left", plan_pointer + "/left")
            return
        if shape == {"source", "program", "index"}:
            require(actual.get("kind") == "IRSourcePartitionRef", "PARTITION_PLAN: shape differs")
            yield from self.pair_references(source["source"], actual["source"],
                                           source_pointer + "/source", plan_pointer + "/source")
            return
        if shape in ({"base", "regions"}, {"base", "index"}):
            base = source["base"]
            if base.get("member") == "contents":
                require(actual.get("kind") == "IRIndex", "FRACTION_PLAN: shape differs")
                yield from self.pair_references(base["base"], actual["base"]["base"],
                                               source_pointer + "/base/base", plan_pointer + "/base/base")
                return
            require(set(base) == {"name", "span"}, "SELECTOR_SOURCE: unsupported nested base")
            source = base  # The full selection is preserved on the enclosing transfer.
            source_pointer += "/base"
        require(set(source) == {"name", "span"} and source["name"] in self.symbols,
                "REFERENCE_SOURCE: unknown object")
        oid = self.symbols[source["name"]]
        obj = self.objects[oid]
        selections = self.selected_bindings(actual, plan_pointer)
        require(selections, "REFERENCE_MEMBERS: empty")
        for binding, actual_pointer in selections:
            if "member_ids" in obj:
                require(binding in self.binding_to_member, "REFERENCE_MEMBERS: unknown binding")
                mid = self.binding_to_member[binding]
                require(mid in obj["member_ids"], "REFERENCE_MEMBERS: outside source group")
            else:
                require(binding == obj["runtime_binding"], "REFERENCE_IDENTITY: binding differs")
                mid = oid
            yield oid, mid, source, source_pointer, actual_pointer

    def uses(self, expression, pointer, statement, matches):
        step = self.step(statement)
        if "target" in expression:
            slots = [(expression["target"], pointer + "/target", "/args/target")]
            slots.extend((s, f"{pointer}/sources/{i}", f"/args/sources/{i}")
                         for i, s in enumerate(expression["sources"]))
        else:
            slots = [(a["value"], f"{pointer}/args/{i}/value", "/args/" + a["name"])
                     for i, a in enumerate(expression["args"]) if a["name"] in {"sample", "schema_ref"}]
        for source, source_pointer, slot in slots:
            for index, ps, ei in matches:
                actual = ps
                actual_pointer = slot
                if ps["op"] == "env_hold" and slot == "/args/sample":
                    actual = ps["gate"]["env_targets"]
                    actual_pointer = "/gate/env_targets"
                else:
                    for key in slot.split("/")[1:]:
                        actual = actual[int(key)] if isinstance(actual, list) else actual[key]
                for oid, mid, ref_node, ref_pointer, actual_ref in self.pair_references(
                        source, actual, source_pointer, actual_pointer):
                    obj = self.objects[oid]
                    self.add(step, "object", obj["name"],
                             {"object_id": oid, "declaration": obj["declaration"]},
                             self.ev("ast", ref_pointer, ref_node), oid)
                    use = {
                        "source_object": oid, "actual_member": mid,
                        "source_reference": self.ev("ast", source_pointer, source),
                        "execution": [{
                            "step_id": ps["step_id"],
                            "plan": self.ev("plan", f"/plans/0/steps/{index}" + actual_ref),
                            "completed_event": self.ev("run", f"/events/{ei}")}]}
                    bucket = self.runtime_uses.setdefault(mid, {}).setdefault(step, [])
                    if use not in bucket:
                        bucket.append(use)

    def visit_statement(self, statement, path):
        shape = set(statement) - {"span"}
        if shape == {"binding", "iterable", "statements", "times"}:
            binding = statement["binding"]
            require(binding not in self.loop_bindings and binding not in self.symbols,
                    "UNSUPPORTED_LOOP_SHADOWING")
            schedule = self.expression(statement["iterable"], path + "/iterable")
            self.loop_bindings[binding] = schedule
            try:
                super().visit_statement(statement, path)
            finally:
                del self.loop_bindings[binding]
            return
        if shape == {"options", "requirements", "statements"}:
            require(statement["options"] == [], "UNSUPPORTED_CONSTRAINT_OPTIONS")
            refs = self.associations(statement["statements"])
            self.add(self.step(statement), "constraint", "constraint",
                     {"requirements": statement["requirements"], "objects": refs},
                     self.ev("ast", path, statement))
            self.statements(statement["statements"], path + "/statements")
            return
        if shape == {"bindings", "value"}:
            require(statement["bindings"] == [] and set(statement["value"]) == {"name", "span"},
                    "UNSUPPORTED_RETURN")
            name = statement["value"]["name"]
            require(name in self.symbols and name in self.protocol["returns"],
                    "RETURN_REFERENCE: declaration differs")
            obj = self.objects[self.symbols[name]]
            require(obj["kind"] == "readout" and self.step(statement) == obj["introduced_at"],
                    "UNSUPPORTED_RETURN: expected immediate same-step readout")
            require(obj["runtime_binding"] == self.entry_binding, "RETURN_BINDING: entry differs")
            self.add(self.step(statement), "object", name,
                     {"object_id": obj["object_id"], "declaration": obj["declaration"]},
                     self.ev("ast", path + "/value", statement["value"]), obj["object_id"])
            return
        if shape == {"name", "args"} and statement["name"] == "agit":
            args = {}
            for i, arg in enumerate(statement["args"]):
                require(arg["name"] in {"sample", "mode", "duration"}, "UNSUPPORTED_AGIT_ARGS")
                require(arg["name"] not in args, "DUPLICATE_ARGUMENT")
                args[arg["name"]] = self.expression(arg["value"], f"{path}/args/{i}/value", arg["name"] == "mode")
            matches = self.match_execution(statement, "agit")
            self.uses(statement, path, statement, matches)
            self.add(self.step(statement), "operation", "agit", {"call": "agit", "args": args},
                     self.ev("ast", path, statement))
            return
        super().visit_statement(statement, path)
        if shape == {"target", "sources"}:
            for pointer, node in nodes(statement["sources"], path + "/sources"):
                if set(node) - {"span"} == {"source", "program", "index"}:
                    source = self.expression(node["source"], pointer + "/source")
                    program = self.expression(node["program"], pointer + "/program")
                    self.add(self.step(statement), "operation", "partition",
                             {"source": source, "program": program,
                              "index": self.expression(node["index"], pointer + "/index")},
                             self.ev("ast", pointer, node))
                    self.add(self.step(statement), "program", "filtration_program",
                             {"source": source, "program": program},
                             self.ev("ast", pointer + "/program", node["program"]))

    def reuse_rows(self, order):
        atoms = {oid: obj for oid, obj in self.objects.items() if oid not in self.source_only}
        entries, self.group_audit = select_groups(atoms, self.runtime_uses, self.candidates, order)
        rows = []
        for entry in entries:
            members = entry["members"]
            intro = atoms[members[0]]["introduced_at"]
            later = sorted({s for s in self.runtime_uses.get(members[0], {}) if order[s] > order[intro]},
                           key=order.get)
            if not later:
                continue
            rows.append({
                "entry_id": members[0] if len(members) == 1 else "group:" + value_id(members)[:20],
                "members": [atoms[m] for m in members], "introduced_at": intro,
                "used_in": later, "later_use_links": len(later), "group_bases": entry["bases"],
                "uses": {s: [u for m in members for u in self.runtime_uses[m][s]] for s in later},
            })
        return rows

    def derive(self):
        result = super().derive()
        result["material_state_continuity.json"]["grouping_audit"] = self.group_audit
        return result


def write_outputs(outputs, destination):
    destination = Path(destination).resolve()
    require(set(outputs) == set(FILES), "OUTPUT_SCHEMA: expected three files")
    require(len({v["extraction_id"] for v in outputs.values()}) == 1,
            "OUTPUT_IDENTITY: mixed extractions")
    require(not destination.exists(), f"OUTPUT_EXISTS: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".metrics-", dir=destination.parent))
    try:
        for name, payload in outputs.items():
            write_json(temporary / name, payload)
            require(read_json(temporary / name) == payload, "OUTPUT_ROUNDTRIP: " + name)
        require(not destination.exists(), f"OUTPUT_EXISTS: {destination}")
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def extract(bundle, destination):
    bundle, destination = Path(bundle).resolve(), Path(destination).resolve()
    require(not destination.is_relative_to(bundle) and not bundle.is_relative_to(destination),
            "OUTPUT_PATH: output must be separate from input bundle")
    config = read_json(bundle / "case.json")
    profile = config.get("profile", "tube-v1")
    require(profile in {"tube-v1", "plate-v1", "nested-v1"}, "UNSUPPORTED_PROFILE: " + str(profile))
    if profile == "nested-v1":
        from benchmark_metrics_nested import NestedExtractor
        cls = NestedExtractor
    else:
        cls = PlateExtractor if profile == "plate-v1" else Extractor
    outputs = cls(bundle).derive()
    write_outputs(outputs, destination)
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture_parser = sub.add_parser("capture", help="Run existing Culsma CLI and bind input hashes")
    inputs = capture_parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--source", help="Benchmark protocol.culs; discover scope and steps automatically")
    inputs.add_argument("--case", help="Historical configuration input (regression compatibility)")
    capture_parser.add_argument("--python", required=True)
    capture_parser.add_argument("--bundle", required=True)
    extract_parser = sub.add_parser("extract", help="Derive three evaluation JSONs")
    extract_parser.add_argument("--bundle", required=True)
    extract_parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        if args.command == "capture":
            print(capture(args.source or args.case, args.python, args.bundle))
        else:
            output = extract(args.bundle, args.out)
            print(json.dumps({name: {k: v for k, v in row.items() if k in {
                "source_steps", "descriptor_items", "reused_objects", "later_use_links",
                "active_steps", "completed_steps", "reagent_records", "touched_containers",
                "final_material_states"}} for name, row in output.items()}, ensure_ascii=False))
        return 0
    except (EvidenceError, KeyError, TypeError, OSError, json.JSONDecodeError,
            subprocess.SubprocessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.modules["benchmark_metrics"] = sys.modules[__name__]
    sys.exit(main())
