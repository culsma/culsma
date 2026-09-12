"""Nested source statistics using exported Culsma JSON only.

Source traversal never evaluates expressions or executes a protocol. Runtime
association is a constraint join on exported spans, argument roles and bindings;
ambiguous joins fail instead of reconstructing compiler naming conventions.
"""
from copy import deepcopy
from pathlib import Path
from collections import Counter
import re

from benchmark_metrics import (Extractor, EvidenceError, require, load_bundle,
                               nodes, plain, canonical, value_id, digest, select_groups)


def shape(node):
    return set(node) - {"span"}


def content(value):
    if isinstance(value, dict):
        return {k: content(v) for k, v in value.items() if not k.startswith("_")}
    if isinstance(value, list):
        return [content(v) for v in value]
    return value


def references(value):
    if isinstance(value, dict):
        if "object_id" in value:
            yield value
        else:
            elements = value.get("base", {}).get("elements")
            index = value.get("index", {}).get("value")
            if elements is not None and isinstance(index, (int, float)) and float(index).is_integer():
                require(0 <= index < len(elements), "SELECTION_RANGE: literal outside exported list")
                yield from references(elements[int(index)])
            else:
                for key, child in value.items():
                    if not key.startswith("_"):
                        yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def object_associations(facts):
    """Keep object roles/selections, not the child operation's other settings."""
    def project(value):
        if isinstance(value, dict):
            if "object_id" in value:
                return deepcopy(value)
            if "base" in value and ({"index", "member", "regions"} & set(value)):
                # A fraction/selector is part of the reference, including its index.
                return deepcopy(value) if any(references(value)) else None
            selected = {k: projected for k, v in value.items()
                        if not k.startswith("_") and (projected := project(v)) is not None}
            return selected or None
        if isinstance(value, list):
            selected = [projected for v in value if (projected := project(v)) is not None]
            return selected or None
        return None

    associated = {}
    for fact in facts:
        projected = project(fact["slots"])
        if projected is not None:
            associated.setdefault(canonical(content(projected)), projected)
    return [associated[k] for k in sorted(associated)]


class NestedExtractor(Extractor):
    rules_version = "patterns-metrics-nested-v8"
    support_scope = "Nested AST calls, result members, declared plate groups/selectors, grouped readouts and conditional execution; unresolved JSON joins fail"

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.config, self.receipt, self.data, self.paths = load_bundle(self.root)
        self.adapter_sha256 = digest(__file__)
        self.source = (self.root / "protocol.culs").read_text()
        self.rows, self.objects, self.runtime_uses = {}, {}, {}
        self.parameters, self.covered_plan_ids = {}, set()
        self.facts, self.declarations, self.domains = [], {}, {}
        self.source_coverage = []
        self.group_membership_events = []
        self.collections, self.group_definitions = {}, []
        self.ir_nodes = list(nodes(self.data["ir"]["script_entry"], "/script_entry"))
        self.nonmaterial_bindings = {}
        self.extra_coverage = set()
        self.main_seen = False
        ast = self.data["ast"]
        require(not ast.get("source_includes") and not ast.get("library_imports"),
                "UNSUPPORTED_FRONTEND: nested adapter requires a single exported file")
        self.procedures = {}
        for i, proc in enumerate(ast["protocols"]):
            require(proc["name"] not in self.procedures, "AMBIGUOUS_PROTOCOL")
            require(proc["source_path"] == self.receipt["captured_source_path"], "INPUT_SOURCE_PATH")
            self.procedures[proc["name"]] = (f"/protocols/{i}", proc)
        self.step_protocol = self.config.get("step_protocol", self.config["protocol"])
        require(self.step_protocol in self.procedures, "STEP_PROTOCOL: definition missing")
        self.protocol_pointer, self.protocol = self.procedures[self.step_protocol]
        self.markers = self.step_map()
        self.rows = {s: {} for s in self.config["expected_steps"]}
        self.execution_index()
        self.identity_snapshots = {}
        latest = None
        previous_seq = -1
        for ei, event in enumerate(self.data["run"]["events"]):
            require(event["seq"] > previous_seq, "RUN_EVENT_ORDER")
            previous_seq = event["seq"]
            payload = event["payload"]
            if "material_state_snapshot" in payload:
                latest = (ei, payload["material_state_snapshot"])
            elif "material_delta" in payload:
                # Do not reconstruct state changes when a snapshot is missing.
                latest = None
            if latest is not None:
                self.identity_snapshots[ei] = latest
        self.allocation_bindings = {}
        for i, ps in enumerate(self.plan_steps):
            if ps["op"] == "AllocContainer" and ps["step_id"] in self.completed:
                ei = self.completed[ps["step_id"]]
                delta = self.data["run"]["events"][ei]["payload"]["material_delta"]
                require(delta["bind"] == ps["args"]["bind"], "ALLOCATION_BINDING")
                self.allocation_bindings.setdefault(delta["bind"], []).append((i, ei, delta["container_id"]))
        self.ir_by_span, self.plan_by_span = {}, {}
        for pointer, node in nodes(self.data["ir"]):
            if "span" in node:
                self.ir_by_span.setdefault(canonical(node["span"]), []).append((pointer, node))
        for i, node in enumerate(self.plan_steps):
            self.plan_by_span.setdefault(canonical(node["span"]), []).append((i, node))
        self.ir_by_id = {n["id"]: (p,n) for p,n in self.ir_nodes if "id" in n}
        # RC1 exports marker-panel parameter passing as local assignments.
        # Prove aliases from completed values, never from generated name patterns.
        self.panel_aliases = {}
        self.alias_step_ids = set()
        values = {}
        for i, ps in sorted(enumerate(self.plan_steps), key=lambda pair: self.completed.get(pair[1]['step_id'], float('inf'))):
            if ps['op'] != 'assign_local' or ps['step_id'] not in self.completed:
                continue
            ei = self.completed[ps['step_id']]
            payload = self.data['run']['events'][ei]['payload'].get('driver_payload', {})
            target, value = ps['args'].get('target'), payload.get('value')
            argument = ps['args'].get('value', {})
            if argument.get('kind') == 'IRIdentifier' and isinstance(value, dict) and value.get('kind') == 'marker_panel_ref':
                source = argument['name']
                require(source in values and values[source] == value, 'PARAMETER_ALIAS: panel value differs from producer')
                require(target not in values and target not in self.panel_aliases, 'PARAMETER_ALIAS: reassigned target')
                self.panel_aliases[target] = (source, i, ei)
            values[target] = value

    def declaration_role(self, node):
        """Roles come from exported allocation/producer/assignment evidence."""
        value = node["value"]
        if "args" not in value:
            return "group_descriptor" if shape(value) == {"base", "regions"} else None
        lowered = [n.get("value", {}) for _, n in self.ir_by_span.get(canonical(node["span"]), [])
                   if "id" in n and "name" in n and "value" in n]
        if any(v.get("name") == "AllocContainer" for v in lowered):
            return "container"
        plans = self.plan_by_span.get(canonical(node["span"]), [])
        roles = set()
        for _, ps in plans:
            if ps["op"] == "AllocContainer":
                roles.add("container")
            ei = self.completed.get(ps["step_id"])
            if ei is None:
                continue
            payload = self.data["run"]["events"][ei]["payload"]
            if "observation_delta" in payload:
                roles.add("readout")
            if ps["op"] == "assign_local":
                exported = payload.get("driver_payload", {}).get("value")
                if isinstance(exported, dict):
                    role = {"data_schema_ref": "schema", "data_ref": "external_data",
                            "marker_panel_ref": "marker_panel", "unit_stream_ref": "stream",
                            "data_group_ref": "data_group"}.get(exported.get("kind"))
                    require(role is not None, "STRUCTURE_UNADAPTED: assignment role at " + str(node["span"]))
                    roles.add(role)
        if roles:
            require(len(roles) == 1, "EVIDENCE_AMBIGUOUS: declaration role")
            return next(iter(roles))
        # The carrier relationship is an exported parameter relation, not a
        # spelling test on the source constructor's name.
        args = {a["name"]: a["value"] for a in value["args"]}
        carrier = args.get("carrier_id")
        if carrier is not None and any(ps["op"] == "AllocContainer" and
                ps["args"].get("carrier_id", {}).get("value") == carrier.get("value")
                and carrier.get("value") is not None for ps in self.plan_steps):
            return "plate_descriptor"
        if any("elements" in v for v in lowered):
            return "group_descriptor"
        if any(ps["op"] not in {"assign_local", "assign_member"} for _, ps in plans):
            return "operation_result"
        return None

    def step_map(self):
        """Associate comment locations with exported lexical statement lists.

        This scans comments only. Calls, block boundaries and reachable definitions
        come from AST JSON; neither file order nor execution order sorts labels.
        """
        expected = self.config["expected_steps"]
        require(expected == [f"S{i}" for i in range(1, len(expected) + 1)], "STEP_CONFIG")
        reachable = set()

        def visit(name, stack):
            require(name not in stack, "RECURSIVE_CALL: " + name)
            if name in reachable:
                return
            reachable.add(name)
            for _, node in nodes(self.procedures[name][1]["statements"]):
                if "args" in node and node.get("name") in self.procedures:
                    visit(node["name"], stack + [name])

        visit(self.step_protocol, [])
        scopes = []

        def scope(statements, pointer, span, depth, procedure):
            scopes.append(dict(pointer=pointer, span=span, depth=depth,
                               procedure=procedure, statements=statements))
            for i, node in enumerate(statements):
                path = f"{pointer}/{i}"
                if "statements" in node:
                    scope(node["statements"], path + "/statements", node["span"], depth+1, procedure)
                if "then_statements" in node:
                    # Exported arm statements delimit the two lists. A marker in
                    # the inter-arm gap belongs to the next arm, never both.
                    then, other = node["then_statements"], node["else_statements"]
                    boundary = then[-1]["span"]["end"] if then else node["span"]["start"]
                    scope(then, path + "/then_statements", dict(node["span"], end=boundary), depth+1, procedure)
                    scope(other, path + "/else_statements", dict(node["span"], start=boundary), depth+1, procedure)

        for name in sorted(reachable):
            pointer, proc = self.procedures[name]
            scope(proc["statements"], pointer + "/statements", proc["span"], 0, name)
            for _, node in nodes(proc):
                if "span" in node:
                    sp = node["span"]
                    require(0 <= sp["start"] < sp["end"] <= len(self.source), "SOURCE_SPAN")
                    require(self.source.count("\n", 0, sp["start"])+1 == sp["line"], "SOURCE_SPAN: line mismatch")
        self.scope_markers = {s["pointer"]: [] for s in scopes}
        all_markers = []
        offset = 0
        for line_no, line in enumerate(self.source.splitlines(keepends=True), 1):
            position = offset + len(line) - len(line.lstrip())
            offset += len(line)
            containing = [s for s in scopes if s["span"]["start"] <= position < s["span"]["end"]]
            if not containing or not re.match(r"\s*//\s*Source step", line):
                continue
            match = re.fullmatch(r"\s*//\s*Source step (S[1-9]\d*):[^\r\n]*[\r\n]*", line)
            require(match is not None, f"STEP_MARKER: invalid/ranged marker at line {line_no}")
            require(match[1] in expected, f"STEP_MARKER: out of range at line {line_no}")
            owner = max(containing, key=lambda s: s["depth"])
            for statement in owner["statements"]:
                sp = statement["span"]
                require(not sp["start"] < position < sp["end"],
                        f"STEP_MAPPING: marker inside indivisible statement at line {line_no}")
            marker = dict(step=match[1], marker_line=line_no, marker_offset=position,
                          scope=owner["pointer"], procedure=owner["procedure"])
            self.scope_markers[owner["pointer"]].append(marker)
            all_markers.append(marker)
        found = {m["step"] for m in all_markers}
        require(found == set(expected), f"STEP_MARKER: expected {expected}, found {sorted(found)}")
        return [{"step": s, "markers": [m for m in all_markers if m["step"] == s]} for s in expected]

    def mapped_step(self, node, scope, inherited, frame):
        markers = self.scope_markers.get(scope, [])
        effective = [m for m in markers if m["marker_offset"] <= node["span"]["start"]]
        if (not effective and scope == self.protocol_pointer + "/statements"
                and markers and markers[0]["step"] == "S1"):
            effective = [markers[0]]
        if effective:
            marker = effective[-1]
            return marker["step"], dict(kind="local", marker=marker)
        origin = frame.get("step_origin")
        return inherited, dict(kind="inherited", source=origin) if origin else None

    def execution_index(self):
        plan, run, result = self.data["plan"], self.data["run"], self.data["result"]
        require(not plan["diagnostics"] and run["ok"] and not run["diagnostics"], "RUN_FAILED")
        require(self.data["output"]["ok"] and self.data["output"]["report"] == result == run["user_result"],
                "RUN_REPORT: inconsistent outputs")
        require(len(plan["plans"]) == 1, "UNSUPPORTED_ENTRY: multiple independent plans")
        self.plan_steps = plan["plans"][0]["steps"]
        by_id = {s["step_id"]: s for s in self.plan_steps}
        require(len(by_id) == len(self.plan_steps), "RUN_PLAN: duplicate IDs")
        status = run["state"]["step_status"]
        require(set(status) == set(by_id), "RUN_STATUS: plan differs")
        self.completed, self.skipped, starts = {}, {}, {}
        for i, event in enumerate(run["events"]):
            sid, kind = event["step_id"], event["kind"]
            require(sid in by_id and event["span"] == by_id[sid]["span"], "RUN_EVENT: invalid source")
            if kind == "STEP_STARTED":
                require(sid not in starts and event["payload"]["op"] == by_id[sid]["op"], "RUN_START")
                starts[sid] = i
            elif kind == "STEP_COMPLETED":
                require(sid in starts and sid not in self.completed and sid not in self.skipped, "RUN_COMPLETION")
                self.completed[sid] = i
            elif kind == "STEP_SKIPPED":
                require(sid not in self.completed and sid not in self.skipped, "RUN_SKIP")
                self.skipped[sid] = i
            elif kind == "BINDING_OVERWRITTEN":
                require(sid in starts, "RUN_BINDING_EVENT: missing start")
            else:
                raise EvidenceError("UNSUPPORTED_RUN_EVENT: " + kind)
        require(set(self.completed) == {k for k, v in status.items() if v == "completed"}, "RUN_COMPLETION_STATUS")
        require(set(self.skipped) == {k for k, v in status.items() if v == "skipped"}, "RUN_SKIP_STATUS")
        require(set(status.values()) <= {"completed", "skipped"}, "RUN_FAILED: unfinished or failed")
        counts = Counter(status.values())
        for k, v in {"total_steps": len(by_id), "completed_steps": counts["completed"],
                     "skipped_steps": counts["skipped"], "failed_steps": 0}.items():
            require(result["execution"][k] == v, "RUN_COUNTS: " + k)
        require(result["execution"]["ok"] and result["execution"]["diagnostic_count"] == 0, "RUN_FAILED")

    def expression(self, node, pointer, env, tokens=False):
        require(isinstance(node, dict), "UNSUPPORTED_EXPRESSION: " + pointer)
        fields = shape(node)
        ev = self.ev("ast", pointer, node)
        if fields in ({"value"}, {"value", "unit"}):
            return dict(plain(node), _source=ev)
        if fields == {"name"}:
            if node["name"] not in env:
                exported_token = any(shape(n) == {"name"} and n["name"] == node["name"]
                                     for _, n in self.ir_by_span.get(canonical(node["span"]), []))
                require(tokens or exported_token, f"UNRESOLVED_REFERENCE: {node['name']} at {pointer}")
                return {"token": node["name"]}
            value = deepcopy(env[node["name"]])
            value.setdefault("_origins", []).append(ev)
            value["_source"] = ev
            return value
        if fields == {"name", "args"}:
            return {"call": node["name"], "args": self.args(node["args"], pointer + "/args", env, tokens),
                    "_source": ev}
        if fields == {"elements"}:
            return {"elements": [self.expression(n, f"{pointer}/elements/{i}", env, tokens)
                                 for i, n in enumerate(node["elements"])]}
        if fields == {"entries"}:
            return {"entries": {k: self.expression(v, pointer + "/entries/" + k, env, True)
                                for k, v in node["entries"].items()}}
        if fields == {"left", "right"}:
            return {k: self.expression(node[k], pointer + "/" + k, env, tokens) for k in fields}
        if fields == {"left", "right", "op"}:
            return {"op": node["op"], "left": self.expression(node["left"], pointer + "/left", env),
                    "right": self.expression(node["right"], pointer + "/right", env), "_source": ev}
        if fields == {"base", "member"}:
            base = self.expression(node["base"], pointer + "/base", env, tokens)
            if "return_bindings" in base:
                require(node["member"] in base["return_bindings"], "RETURN_MEMBER: " + pointer)
                value = deepcopy(base["return_bindings"][node["member"]])
                value.setdefault("_origins", []).append(ev)
                value["_source"] = ev
                return value
            return {"base": base, "member": node["member"], "_source": ev}
        if fields == {"base", "regions"}:
            base = self.expression(node["base"], pointer + "/base", env)
            require(base.get("object_id") in self.collections, "SELECTOR_BASE: " + pointer)
            return {"base": base, "regions": plain(node["regions"]), "_source": ev}
        if fields == {"base", "index"}:
            base = self.expression(node["base"], pointer + "/base", env)
            return {"base": base, "index": self.expression(node["index"], pointer + "/index", env), "_source": ev}
        if fields == {"source", "program", "index"}:
            return {k: self.expression(node[k], pointer + "/" + k, env) for k in fields}
        raise EvidenceError(f"UNSUPPORTED_EXPRESSION: {sorted(fields)} at {pointer}")

    def args(self, args, pointer, env, tokens=False):
        result = {}
        for i, arg in enumerate(args):
            key = arg["name"] if arg["name"] is not None else f"arg{i}"
            require(key not in result, "UNSUPPORTED_ARGUMENT: " + pointer)
            result[key] = self.expression(arg["value"], f"{pointer}/{i}/value", env,
                                          tokens or key in {"quantity", "mode"})
        return result

    def record(self, step, category, label, payload, pointer, node, frame, object_id=None,
               declaration_args=None):
        if frame.get("outside_scope"):
            return
        require(step in self.rows, "STEP_MAPPING: unmarked experimental fact at " + pointer)
        evidence = self.ev("ast", pointer, node)
        evidence["call_path"] = deepcopy(frame["path"])
        evidence["step_origin"] = deepcopy(frame.get("step_origin"))
        origins = []
        for _, part in nodes(payload):
            for origin in part.get("_origins", []):
                if origin not in origins:
                    origins.append(origin)
        if origins:
            evidence["parameter_sources"] = origins
        normalized = content(payload)
        if category == "object" and object_id in self.objects:
            normalized = {"object_id": object_id, "declaration": self.objects[object_id]["declaration"]}
        self.add(step, category, label, normalized, evidence, object_id)
        # Only a declaration supplies its current arguments separately. References
        # still stop at object identity; never traverse historical declarations.
        for ref in references([payload, declaration_args]):
            oid = ref["object_id"]
            obj = self.objects[oid]
            if obj["introduced_at"] is None:
                obj["introduced_at"] = step
                obj["external_reference"] = True
                obj["evidence"]["introduction"] = deepcopy(ref.get("_source", evidence))
            ref_ev = deepcopy(ref.get("_source", evidence))
            ref_ev["call_path"] = deepcopy(frame["path"])
            self.add(step, "object", obj["name"], {"object_id": oid, "declaration": obj["declaration"]},
                     ref_ev, oid)

    def declaration(self, node, pointer, env, frame, step, conditional):
        name, value = node["name"], node["value"]
        require(name not in env, "UNSUPPORTED_BINDING: reassignment/shadowing at " + pointer)
        if value.get("name") in self.procedures and "args" in value:
            result = self.call(value, pointer + "/value", env, frame, step, conditional)
            require(result is not None, "RETURN_BINDING: missing value at " + pointer)
            env[name] = result
            return
        constructor = value.get("name")
        role = self.declaration_role(node)
        if shape(value) == {"elements"}:
            resolved = self.expression(value, pointer + "/value", env)
            if resolved["elements"] and all(any(references(v)) for v in resolved["elements"]):
                role = "group_descriptor"
        if role in {"plate_descriptor", "group_descriptor"}:
            self.collection_declaration(node, pointer, env, frame, step, conditional)
            return
        if role == "operation_result":
            self.operation(value, pointer + "/value", node, env, frame, step, conditional,
                           environment=frame.get("environment"))
            env[name] = {"result_binding": [ps["args"]["bind"] for _, ps in
                         self.plan_by_span.get(canonical(node["span"]), []) if "bind" in ps["args"]],
                         "producer": self.expression(value, pointer + "/value", env),
                         "_source": self.ev("ast", pointer, node)}
            return
        if role is None:
            env[name] = self.expression(value, pointer + "/value", env)
            if "index" in value or "regions" in value:
                selected = []
                for irp, ir in self.ir_by_span.get(canonical(node["span"]), []):
                    if "id" in ir and "name" in ir and "value" in ir:
                        bindings = self.concrete_bindings(ir["value"], irp + "/value")
                        if bindings:
                            selected.extend(bindings)
                if selected:
                    env[name]["_selected_bindings"] = sorted({b for b,_ in selected})
                    env[name]["_selection_evidence"] = [self.ev("ir", p) for _,p in selected]
            env[name].setdefault("_origins", []).append(self.ev("ast", pointer, node))
            return
        decl = self.expression(value, pointer + "/value", env)
        oid = "source-object:" + value_id([frame["key"], pointer])[:20]
        self.objects[oid] = {"object_id": oid, "name": name,
                             "kind": role,
                             "introduced_at": step, "declaration": content(decl),
                             "evidence": {"declaration": self.ev("ast", pointer, node),
                                          "call_path": deepcopy(frame["path"])}}
        self.declarations[oid] = (node, pointer, frame, conditional)
        self.domains[oid] = set()
        if role == "readout":
            self.operation(value, pointer + "/value", node, env, frame, step, conditional, bind=oid, environment=frame.get("environment"))
            for ps in self.plan_steps:
                if ps["op"] == constructor and ps["span"] == node["span"]:
                    self.domains[oid].add(ps["args"]["bind"])
        elif role != "container":
            self.domains[oid] = {ps["args"]["target"] for ps in self.plan_steps
                                 if ps["op"] == "assign_local" and ps["span"] == node["span"]}
            self.facts.append({"op": "assign_local", "slots": {"/args/value": decl},
                               "span": node["span"], "pointer": pointer, "frame": frame, "step": step,
                               "conditional": conditional, "bind": oid, "binding_slot": "target", "metadata": True})
            if role == "schema":
                self.record(step, "schema", constructor, {"object_id": oid, **decl},
                            pointer + "/value", value, frame)
        else:
            self.domains[oid] = {ps["args"]["bind"] for ps in self.plan_steps
                                 if ps["op"] == "AllocContainer" and ps["span"] == node["span"]
                                 and all(self.compatible(v, ps["args"][k], "/args/"+k) is not None
                                         for k,v in decl["args"].items() if k in ps["args"])}
        env[name] = {"object_id": oid, "_source": self.ev("ast", pointer, node),
                     "_origins": [self.ev("ast", pointer, node)]}
        self.record(step, "object", name, {"object_id": oid, "declaration": decl},
                    pointer, node, frame, oid, declaration_args=decl.get("args"))

    def concrete_bindings(self, value, pointer):
        """Read lists already exported by IR/Plan, never calculate a selection."""
        if isinstance(value, list):
            result = []
            for i, child in enumerate(value):
                found = self.concrete_bindings(child, pointer + "/" + str(i))
                if found is None:
                    return None
                result.extend(found)
            return result
        if not isinstance(value, dict):
            return None
        if value.get("kind") == "IRIdentifier" or shape(value) == {"name"}:
            return [(value["name"], pointer)]
        if "elements" in value:
            return self.concrete_bindings(value["elements"], pointer + "/elements")
        return None

    def collection_declaration(self, node, pointer, env, frame, step, conditional):
        value = node["value"]
        decl = self.expression(value, pointer + "/value", env)
        oid = "source-object:" + value_id([frame["key"], pointer])[:20]
        evidence = {"declaration": self.ev("ast", pointer, node), "call_path": deepcopy(frame["path"])}
        if self.declaration_role(node) == "plate_descriptor":
            carrier = decl["args"].get("carrier_id", {}).get("value")
            require(isinstance(carrier, str), "PLATE_CARRIER: explicit literal required")
            require(not any(c.get("carrier") == carrier for c in self.collections.values()),
                    "CALL_INSTANCE_AMBIGUOUS: repeated plate carrier " + carrier)
            bindings = {s["args"]["bind"] for s in self.plan_steps if s["op"] == "AllocContainer"
                        and s["args"].get("carrier_kind", {}).get("value") == "plate"
                        and s["args"].get("carrier_id", {}).get("value") == carrier}
            self.collections[oid] = {"root": oid, "carrier": carrier}
            kind = "plate_descriptor"
        else:
            parent = decl.get("base", {}).get("object_id")
            referenced = {r["object_id"] for r in references(decl)}
            parent_domain = set().union(*(self.domains[o] for o in referenced))
            matches = [(p, n) for p, n in self.ir_nodes if n.get("span") == node["span"]
                       and "id" in n and "name" in n and "value" in n]
            require(matches, "GROUP_IR: missing declaration at " + pointer)
            ip, ir = matches[0]
            selected = self.concrete_bindings(ir["value"], ip + "/value")
            if (selected is None or any(b not in parent_domain for b,_ in selected)) and "elements" in decl:
                require("elements" in ir["value"], "GROUP_IR: missing structured member list")
                self.collections[oid] = {"root": None, "sources": sorted(referenced),
                                         "structured_members": decl["elements"]}
                self.domains[oid] = parent_domain
                self.objects[oid] = {"object_id": oid, "name": node["name"], "kind": "group_descriptor",
                                     "introduced_at": step, "declaration": content(decl), "evidence": evidence}
                self.declarations[oid] = (node, pointer, frame, conditional)
                env[node["name"]] = {"object_id": oid, "_source": evidence["declaration"],
                                     "_origins": [evidence["declaration"]]}
                self.group_definitions.append({"source_object": oid, "introduced_at": step,
                                               "source_members": sorted(referenced), "evidence": evidence})
                self.record(step, "object", node["name"], {"object_id": oid, "members": decl}, pointer, node, frame, oid)
                return
            require(selected, "GROUP_IR: concrete member list missing at " + ip)
            bindings = {b for b, _ in selected}
            require(len(bindings) == len(selected) and bindings <= parent_domain,
                    "GROUP_IR: duplicate or outside-parent member at " + ip)
            for other_pointer, other in matches[1:]:
                other_members = self.concrete_bindings(other["value"], other_pointer + "/value")
                require(other_members and [b for b, _ in other_members] == [b for b, _ in selected],
                        "GROUP_IR: ambiguous repeated declaration at " + pointer)
            evidence["ir"] = [self.ev("ir", p, n) for p, n in matches]
            self.collections[oid] = {"root": self.collections[parent]["root"] if parent in self.collections else None,
                                     "sources": sorted(referenced),
                                     "ordered_members": [b for b,_ in selected],
                                     "member_evidence": [self.ev("ir", p) for _,p in selected]}
            self.group_definitions.append({"source_object": oid, "introduced_at": step,
                                           "bindings": sorted(bindings), "evidence": evidence})
            kind = "group_descriptor"
        require(bindings or conditional, "PLATE_MEMBERS: missing allocations")
        self.domains[oid] = bindings
        self.objects[oid] = {"object_id": oid, "name": node["name"], "kind": kind,
                             "introduced_at": step, "declaration": content(decl), "evidence": evidence}
        self.declarations[oid] = (node, pointer, frame, conditional)
        env[node["name"]] = {"object_id": oid, "_source": evidence["declaration"],
                             "_origins": [evidence["declaration"]]}
        self.record(step, "object", node["name"], {"object_id": oid, "declaration": decl},
                    pointer, node, frame, oid, declaration_args=decl.get("args"))

    def operation(self, node, pointer, statement, env, frame, step, conditional, bind=None, environment=None):
        if shape(node) == {"target", "sources"}:
            payload = {"target": self.expression(node["target"], pointer + "/target", env),
                       "sources": [self.expression(n, f"{pointer}/sources/{i}", env)
                                   for i, n in enumerate(node["sources"])]}
            op, label = "Mutation", "transfer"
            slots = {"/args/target": payload["target"], "/args/sources": payload["sources"]}
            for source_pointer, source in nodes(node["sources"], pointer + "/sources"):
                if shape(source) == {"source", "program", "index"}:
                    partition = self.expression(source, source_pointer, env)
                    self.record(step, "operation", "partition", partition, source_pointer, source, frame)
                    self.record(step, "program", partition["program"]["call"],
                                {"source": partition["source"], "program": partition["program"]},
                                source_pointer + "/program", source["program"], frame)
        else:
            label = node["name"]
            matching = [ps for _, ps in self.plan_by_span.get(canonical(statement["span"]), [])]
            require(label == "hold" or any(ps["op"] == label for ps in matching)
                    or (conditional and label in {ps["op"] for ps in self.plan_steps}),
                    "STRUCTURE_UNADAPTED: operation role at " + pointer)
            args = self.args(node["args"], pointer + "/args", env)
            payload = {"call": label, "args": args}
            op = "env_hold" if label == "hold" else label
            if label == "hold":
                require(environment is not None and set(args) == {"sample"}, "HOLD_ENVIRONMENT")
                slots = {"/gate/env_targets": args["sample"] if self.collection_reference(args["sample"])
                         else args["sample"].get("elements", [args["sample"]])}
            else:
                slots = {"/args/" + k: v for k, v in args.items()}
            if "program" in args:
                program = args["program"]
                self.record(step, "program", program.get("call", "program"),
                            {"program": program, "sample": args["sample"]}, pointer, node, frame)
        if environment is not None:
            slots.update({"/gate/env/" + k: v for k,v in environment.get("_resolved_args", {}).items()})
        self.record(step, "operation", label, payload, pointer, node, frame)
        self.facts.append({"op": op, "slots": slots, "span": (environment if op == "env_hold" else statement)["span"],
                           "pointer": pointer, "frame": frame, "step": step,
                           "conditional": conditional, "bind": bind})

    def statements(self, ss, pointer, env, frame, inherited=None, conditional=False, environment=None):
        returned = None
        for i, node in enumerate(ss):
            path = f"{pointer}/{i}"
            step, origin = self.mapped_step(node, pointer, inherited, frame)
            local_frame = dict(frame, step_origin=origin, environment=environment)
            # The frame is per statement: child markers never leak to siblings.
            frame_for_scope, frame = frame, local_frame
            fields = shape(node)
            if fields == {"name", "value"}:
                self.declaration(node, path, env, frame, step, conditional)
            elif fields == {"target", "value"}:
                target = self.expression(node["target"], path + "/target", env)
                require("member" in target or "index" in target, "STRUCTURE_UNADAPTED: assignment target " + path)
                payload = {"target": target, "value": self.expression(node["value"], path + "/value", env)}
                self.record(step, "annotation", "assign_member", payload, path, node, frame)
                self.facts.append({"op": "assign_member", "slots": {"/args/" + k: v for k,v in payload.items()},
                                   "span": node["span"], "pointer": path, "frame": frame, "step": step,
                                   "conditional": conditional, "bind": None, "metadata": True})
            elif fields == {"name", "args"} and node["name"] in self.procedures:
                self.call(node, path, env, frame, step, conditional)
            elif fields == {"value"} and isinstance(node["value"], dict) and "method" in node["value"]:
                method = node["value"]
                require(shape(method) == {"base", "method", "args"}, "STRUCTURE_UNADAPTED: method " + path)
                payload = {"self": self.expression(method["base"], path + "/value/base", env),
                           **{f"arg{j}": self.expression(a, f"{path}/value/args/{j}", env)
                              for j, a in enumerate(method["args"])}}
                self.record(step, "annotation", method["method"], payload, path, node, frame)
                self.facts.append({"op": method["method"], "slots": {"/args/" + k: v for k,v in payload.items()},
                                   "span": node["span"], "pointer": path, "frame": frame, "step": step,
                                   "conditional": conditional, "bind": None, "metadata": True})
            elif fields in ({"target", "sources"}, {"name", "args"}):
                self.operation(node, path, node, env, frame, step, conditional, environment=environment)
            elif fields in ({"env_args", "statements"}, {"options", "requirements", "statements"},
                            {"binding", "iterable", "statements", "times"}):
                before = len(self.facts)
                child_env = dict(env)
                if "env_args" in node:
                    kind, label = "environment", "env"
                    payload = {"args": self.args(node["env_args"], path + "/env_args", env)}
                    inner_environment = dict(node, _resolved_args=payload["args"])
                elif "requirements" in node:
                    require(node["options"] == [], "UNSUPPORTED_CONSTRAINT_OPTIONS")
                    kind, label = "constraint", "constraint"
                    payload = {"requirements": plain(node["requirements"])}
                    inner_environment = environment
                else:
                    require(node["times"] is None and node["iterable"].get("name") == "schedule", "UNSUPPORTED_LOOP")
                    require(node["binding"] not in env, "UNSUPPORTED_LOOP_SHADOWING")
                    kind, label = "schedule", "schedule"
                    payload = self.expression(node["iterable"], path + "/iterable", env)
                    child_env[node["binding"]] = {"iterator": content(payload)}
                    inner_environment = environment
                self.statements(node["statements"], path + "/statements", child_env, frame, step,
                                conditional, inner_environment)
                payload["associations"] = object_associations(self.facts[before:])
                self.record(step, kind, label, payload, path, node, frame)
            elif fields == {"condition", "then_statements", "else_statements"}:
                condition = self.expression(node["condition"], path + "/condition", env)
                before = len(self.facts)
                for arm in ("then_statements", "else_statements"):
                    self.statements(node[arm], path + "/" + arm, dict(env), frame, step, True, environment)
                self.record(step, "condition", "if", {"condition": condition,
                            "associations": object_associations(self.facts[before:])},
                            path, node, frame)
                if any(references(condition)):
                    self.facts.append({"op": "condition_reference", "slots": {"condition": condition},
                                       "span": node["condition"]["span"], "pointer": path + "/condition",
                                       "frame": frame, "step": step, "conditional": True, "bind": None})
            elif fields == {"bindings", "value"}:
                require(i == len(ss)-1, "UNSUPPORTED_RETURN: non-terminal")
                if node["bindings"]:
                    require(node["value"] is None, "RETURN_BINDING: ambiguous form")
                    returned = {"return_bindings": {b["name"]: self.expression(b["value"],
                                f"{path}/bindings/{j}/value", env) for j, b in enumerate(node["bindings"])}}
                    if len(node["bindings"]) == 1:
                        key = node["bindings"][0]["name"]
                        returned = dict(returned["return_bindings"][key], _return_binding_name=key)
                else:
                    returned = self.expression(node["value"], path + "/value", env) if node["value"] else None
            else:
                raise EvidenceError(f"UNSUPPORTED_STATEMENT: {sorted(fields)} at {path}")
            self.source_coverage.append({"source": self.ev("ast", path, node), "step": step,
                                         "shape": sorted(fields), "call_path": deepcopy(frame["path"]),
                                         "classification": "auxiliary" if fields in ({"bindings", "value"},)
                                         or (fields == {"name", "value"} and node["name"] in env
                                             and "object_id" not in env[node["name"]]) else "experimental_structure",
                                         "step_origin": deepcopy(origin)})
            frame = frame_for_scope
        return returned

    def call(self, call, pointer, parent_env, parent, step, conditional=False):
        name = call["name"]
        require(name not in parent["stack"], "RECURSIVE_CALL: " + name)
        proc_pointer, proc = self.procedures[name]
        args = {}
        for i, arg in enumerate(call["args"]):
            require(arg["name"] is not None and arg["name"] not in args, "UNSUPPORTED_CALL_ARGUMENT")
            args[arg["name"]] = (arg["value"], f"{pointer}/args/{i}/value")
        env, parameter_links = {}, {}
        statement = self.data["ast"]
        statement_pointer = pointer[:-6] if pointer.endswith("/value") else pointer
        for part in statement_pointer.split("/")[1:]:
            statement = statement[int(part)] if isinstance(statement, list) else statement[part]
        compiled_arguments = [(p,n) for p,n in self.ir_by_span.get(canonical(statement["span"]), [])
                              if "id" in n and "name" in n and "value" in n]
        for i, param in enumerate(proc["params"]):
            key = param["name"]
            if key in args:
                node, source = args.pop(key)
                value = self.expression(node, source, parent_env)
                origin = dict(self.ev("ast", source, node), parameter=key, origin_kind="explicit")
            else:
                node = param["default"]
                require(node is not None, "MISSING_CALL_ARGUMENT: " + key)
                source = f"{proc_pointer}/params/{i}/default"
                value = self.expression(node, source, env)
                origin = dict(self.ev("ast", source, node), parameter=key, origin_kind="default")
            value.setdefault("_origins", []).append(origin)
            env[key] = value
            parameter_links[key] = [n["name"] for _,n in compiled_arguments
                                    if n["value"].get("span") == node["span"]]
        require(not args, "UNKNOWN_CALL_ARGUMENT: " + str(sorted(args)))
        path = parent["path"] + [self.ev("ast", pointer, call)]
        frame = {"path": path, "key": parent["key"] + [pointer], "stack": parent["stack"] + [name],
                 "step_origin": parent.get("step_origin"),
                 "parameter_links": parameter_links,
                 "in_scope": parent.get("in_scope", False) or name == self.step_protocol}
        if name == self.step_protocol:
            require(step is None, "UNSUPPORTED_CALL: step protocol called from nested experiment")
            self.parameters = {k: {"value": content(v), "sources": v.get("_origins", [])} for k,v in env.items()}
        if not frame["in_scope"]:
            return self.wrapper(proc["statements"], proc_pointer + "/statements", env, frame)
        if name == self.step_protocol:
            require(not self.main_seen, "UNSUPPORTED_ENTRY: multiple distinct main call sites")
            self.main_seen = True
        return self.statements(proc["statements"], proc_pointer + "/statements", env, frame,
                               step, conditional, parent.get("environment"))

    def wrapper(self, ss, pointer, env, frame):
        """Read batch structure once; runtime iterations are already in the Plan."""
        returned = None
        for i, statement in enumerate(ss):
            path = f"{pointer}/{i}"
            call = statement.get("value", statement)
            if call.get("name") in self.procedures and "args" in call:
                returned = self.call(call, path + ("/value" if "value" in statement else ""),
                                     env, frame, None)
            elif shape(statement) == {"binding", "iterable", "statements", "times"}:
                require(statement["times"] is None and statement["iterable"].get("name") == "schedule",
                        "UNSUPPORTED_WRAPPER_LOOP")
                child = dict(env)
                child[statement["binding"]] = {"iterator": content(self.expression(
                    statement["iterable"], path + "/iterable", env))}
                returned = self.wrapper(statement["statements"], path + "/statements", child, frame)
            else:
                raise EvidenceError("UNSUPPORTED_WRAPPER_STRUCTURE: " + path)
        return returned

    def compatible(self, expected, actual, pointer):
        """Match exported argument structure; return role-preserving object bindings."""
        if isinstance(expected, dict) and "index" in expected and "elements" in expected.get("base", {}):
            index = expected["index"].get("value")
            elements = expected["base"]["elements"]
            if isinstance(index, (int, float)) and float(index).is_integer() and 0 <= index < len(elements):
                selected = deepcopy(elements[int(index)])
                selected.setdefault("_origins", []).append(expected["_source"])
                return self.compatible(selected, actual, pointer)
        if isinstance(expected, dict) and "result_binding" in expected:
            if not isinstance(actual, dict) or actual.get("name") not in expected["result_binding"]:
                return None
            matches = []
            for i, ps in enumerate(self.plan_steps):
                if ps["args"].get("bind") != actual["name"]:
                    continue
                sample = expected["producer"]["args"].get("sample")
                if sample is not None and "sample" in ps["args"]:
                    refs = self.compatible(sample, ps["args"]["sample"], "/args/sample")
                    if refs is not None:
                        # Preserve the actual reference to the result; the producer
                        # separately proves its source object, not a new allocation.
                        matches.extend((o, b, pointer, dict(r, _source=expected["_source"],
                            _producer=self.ev("plan", f"/plans/0/steps/{i}"))) for o,b,_,r in refs)
            return matches or None
        collection = self.collection_reference(expected)
        if collection:
            oid, ref = collection
            if "structured_members" in self.collections[oid]:
                members = self.collections[oid]["structured_members"]
                if "index" in expected:
                    index = expected["index"].get("value")
                    if isinstance(index, (int,float)) and float(index).is_integer() and 0 <= index < len(members):
                        return self.compatible(members[int(index)], actual, pointer)
                    return None
                selected = actual if isinstance(actual, list) else actual.get("elements")
                if selected is None:
                    return None
                return self.compatible(members, selected, pointer if isinstance(actual, list) else pointer+"/elements")
            selected = self.concrete_bindings(actual, pointer)
            if not selected or any(b not in self.domains[oid] for b, _ in selected):
                return None
            if "_selected_bindings" in expected and any(b not in expected["_selected_bindings"] for b,_ in selected):
                return None
            literal_index = expected.get("index", {}).get("value")
            members = self.collections[oid].get("ordered_members")
            if members is not None and isinstance(literal_index, (int, float)):
                # The index value is already a JSON number; select its published
                # list position. Never evaluate an index expression or enumerate
                # a loop. The actual Plan argument must confirm the same member.
                if not float(literal_index).is_integer() or not 0 <= literal_index < len(members):
                    return None
                if any(b != members[int(literal_index)] for b,_ in selected):
                    return None
            if len({b for b, _ in selected}) != len(selected):
                return None
            # Direct group arguments in an IRGroup (or env_targets) denote the
            # complete exported set. A scalarized transfer/index proves only its
            # selected member and must never shrink the group's domain.
            if "object_id" in expected and (isinstance(actual, list) or actual.get("kind") == "IRGroup"):
                if {b for b, _ in selected} != self.domains[oid]:
                    return None
            selected_ref = dict(ref, _source=expected.get("_source", ref["_source"]))
            return [(oid, b, p, selected_ref) for b, p in selected]
        if isinstance(expected, list):
            if not isinstance(actual, list) or len(expected) != len(actual):
                return None
            result = []
            for i, (a, b) in enumerate(zip(expected, actual)):
                match = self.compatible(a, b, pointer + "/" + str(i))
                if match is None:
                    return None
                result.extend(match)
            return result
        if not isinstance(expected, dict):
            return [] if expected == actual else None
        if "object_id" in expected:
            if not isinstance(actual, dict) or actual.get("kind") != "IRIdentifier":
                return None
            oid, binding = expected["object_id"], actual["name"]
            alias_evidence = []
            seen = set()
            while binding in self.panel_aliases:
                require(binding not in seen, 'PARAMETER_ALIAS: cycle')
                seen.add(binding)
                binding, ai, ae = self.panel_aliases[binding]
                alias_evidence.append({'plan': self.ev('plan', f'/plans/0/steps/{ai}'),
                                       'completed_event': self.ev('run', f'/events/{ae}')})
            if binding not in self.domains[oid]:
                return None
            spans = [e.get("source_span") for e in expected.get("_origins", [])]
            if (self.objects[oid]["kind"] == "container" and actual.get("span")
                    and spans and actual["span"] not in spans):
                return None
            if alias_evidence:
                expected = dict(expected, _alias_evidence=alias_evidence)
                for alias in seen:
                    ai = self.panel_aliases[alias][1]
                    self.extra_coverage.add(self.plan_steps[ai]['step_id'])
                    self.alias_step_ids.add(self.plan_steps[ai]['step_id'])
            return [(oid, binding, pointer, expected)]
        if not isinstance(actual, dict):
            return [] if expected == actual else None
        if "token" in expected:
            return [] if actual.get("name", actual.get("value")) == expected["token"] else None
        if "call" in expected:
            if actual.get("name") != expected["call"]:
                return None
            args = {a["name"] if a["name"] is not None else f"arg{i}": (i, a["value"])
                    for i,a in enumerate(actual.get("args", []))}
            if set(args) != set(expected["args"]):
                # Some exported program slots are renamed (field -> voltage).
                # Match the preserved value span, never a source keyword table.
                aligned = {}
                for key, value in expected["args"].items():
                    span = value.get("_source", {}).get("source_span")
                    found = [(i,v) for i,v in args.values() if span and v.get("span") == span]
                    if len(found) != 1:
                        return None
                    aligned[key] = found[0]
                if len({i for i,_ in aligned.values()}) != len(args):
                    return None
                args = aligned
            result = []
            for k, v in expected["args"].items():
                i, value = args[k]
                match = self.compatible(v, value, f"{pointer}/args/{i}/value")
                if match is None:
                    return None
                result.extend(match)
            return result
        if "entries" in expected and "entries" not in actual:
            return self.compatible(expected["entries"], actual, pointer)
        fields = content(expected)
        actual_fields = {k: v for k,v in actual.items() if k not in {"span", "kind"}}
        if set(fields) != set(actual_fields):
            return None
        result = []
        for k in fields:
            a, b = expected[k], actual_fields[k]
            if isinstance(a, (dict, list)):
                match = self.compatible(a, b, pointer + "/" + k)
                if match is None:
                    return None
                result.extend(match)
            elif a != b:
                return None
        return result

    def collection_reference(self, value):
        if not isinstance(value, dict):
            return None
        base = value.get("base", {}) if "regions" in value or "index" in value else value
        oid = base.get("object_id")
        return (oid, base) if oid in self.collections else None

    def candidates(self, fact):
        result = []
        if fact["op"] == "condition_reference":
            for i, ps in enumerate(self.plan_steps):
                for j, condition in enumerate(ps["gate"].get("runtime_conditions", [])):
                    if condition["expr"].get("span") != fact["span"]:
                        continue
                    pointer = f"/gate/runtime_conditions/{j}/expr"
                    refs = self.compatible(fact["slots"]["condition"], condition["expr"], pointer)
                    if refs is not None:
                        result.append((i, ps, refs))
            return result
        for i, ps in enumerate(self.plan_steps):
            direct = ps["op"] == fact["op"] and ps["span"] == fact["span"]
            environment_gate = (fact["op"] == "env_hold" and ps["gate"].get("env_targets")
                                and fact["span"]["start"] <= ps["span"]["start"] < fact["span"]["end"])
            if not direct and not environment_gate:
                continue
            compiled = self.ir_by_id.get(ps["step_id"])
            if compiled:
                # Join the unchanged IR ID and explicit parameter declarations.
                # This distinguishes repeated calls even when Plan has resolved
                # both argument aliases to the same container and definition span.
                links = fact["frame"].get("parameter_links", {})
                bad = False
                for expected in fact["slots"].values():
                    for _, ref in nodes(expected):
                        ev = ref.get("_source", {})
                        if ev.get("file") != self.paths["ast"]:
                            continue
                        original = self.data["ast"]
                        for key in ev["json_pointer"].split("/")[1:]:
                            original = original[int(key)] if isinstance(original, list) else original[key]
                        allowed = links.get(original.get("name"))
                        if not allowed:
                            continue
                        symbols = [n["name"] for _,n in nodes(compiled[1])
                                   if shape(n) == {"name"} and n.get("span") == original.get("span")]
                        if symbols and not any(s in allowed for s in symbols):
                            bad = True
                            break
                    if bad:
                        break
                if bad:
                    continue
            refs = []
            for pointer, expected in fact["slots"].items():
                actual = ps
                for key in pointer.split("/")[1:]:
                    if not isinstance(actual, dict) or key not in actual:
                        actual = None
                        break
                    actual = actual[key]
                if pointer == "/gate/env_targets" and isinstance(actual, list):
                    # A single exported environment can include several authored
                    # holds/operations. Each hold proves its own targets; the
                    # environment target list is not one positional call argument.
                    coll = self.collection_reference(expected)
                    if coll and "structured_members" in self.collections[coll[0]]:
                        expected = self.collections[coll[0]]["structured_members"]
                    if self.collection_reference(expected):
                        oid, _ = self.collection_reference(expected)
                        subset = [a for a in actual if a.get("name") in self.domains[oid]]
                        match = self.compatible(expected, subset, pointer)
                        if match is not None:
                            match = [(o,b,f"{pointer}/{actual.index(subset[int(p.rsplit('/',1)[1])])}",r)
                                     for o,b,p,r in match]
                    else:
                        match = []
                        for ref in expected:
                            found = [self.compatible(ref, a, f"{pointer}/{j}") for j,a in enumerate(actual)]
                            found = [m for m in found if m is not None]
                            if len(found) != 1:
                                match = None
                                break
                            match.extend(found[0])
                else:
                    match = self.compatible(expected, actual, pointer)
                if match is None:
                    break
                refs.extend(match)
            else:
                if fact["bind"]:
                    binding = ps["args"][fact.get("binding_slot", "bind")]
                    if binding not in self.domains[fact["bind"]]:
                        continue
                    refs.append((fact["bind"], binding, "/args/" + fact.get("binding_slot", "bind"), None))
                result.append((i, ps, refs))
        return result

    def associate_runtime(self):
        # Arc consistency: a known argument can identify the local target binding
        # of that same exported operation without decoding compiler-generated names.
        for _ in range(len(self.objects) + 1):
            changed = False
            for fact in self.facts:
                matches = self.candidates(fact)
                if not matches:
                    require(fact["conditional"], "EXECUTION_MAPPING: " + fact["pointer"])
                    continue
                allowed = {}
                for _, _, refs in matches:
                    for oid, binding, _, _ in refs:
                        allowed.setdefault(oid, set()).add(binding)
                for oid, bindings in allowed.items():
                    if oid in self.collections:
                        continue
                    narrowed = self.domains[oid] & bindings
                    require(narrowed, "OBJECT_IDENTITY: inconsistent argument joins")
                    if narrowed != self.domains[oid]:
                        self.domains[oid] = narrowed
                        changed = True
            if not changed:
                break
        owners = {}
        for fact in self.facts:
            for _, ps, _ in self.candidates(fact):
                key = (fact["pointer"], ps["step_id"])
                ctx = canonical(fact["frame"]["key"])
                require(key not in owners or owners[key] == ctx,
                        "CALL_INSTANCE_AMBIGUOUS: " + fact["pointer"] + " / " + ps["step_id"])
                owners[key] = ctx
        self.runtime_objects = {}
        binding_owners = {}
        for oid, obj in self.objects.items():
            if obj["introduced_at"] is None:
                continue  # Unreferenced setup remains outside the experiment.
            if oid in self.collections and self.collections[oid]["root"] != oid:
                continue  # The plate's actual wells own identity, groups only select.
            node, pointer, frame, conditional = self.declarations[oid]
            if not self.domains[oid]:
                require(conditional, "DECLARATION_MAPPING: " + pointer)
            for binding in sorted(self.domains[oid]):
                require(binding not in binding_owners or binding_owners[binding] == oid,
                        "CALL_INSTANCE_AMBIGUOUS: declaration " + pointer)
                binding_owners[binding] = oid
                for i, ei, identity in self.allocation_bindings.get(binding, []):
                    rid = "container:" + value_id(identity)[:20]
                    obj_evidence = deepcopy(obj)
                    obj_evidence.update(object_id=rid, source_object_id=oid, runtime_binding=binding,
                                        runtime_identity={"container_id": identity})
                    obj_evidence["evidence"].update(plan=self.ev("plan", f"/plans/0/steps/{i}"),
                                                  completed_event=self.ev("run", f"/events/{ei}"))
                    if oid in self.collections:
                        ps = self.plan_steps[i]
                        intro_candidates = {self.objects[k]["introduced_at"] for k, (dn, _, _, _) in self.declarations.items()
                                            if dn["span"]["start"] <= ps["span"]["start"] < dn["span"]["end"]}
                        intro_candidates.update(f["step"] for f in self.facts if f["span"] == ps["span"])
                        require(len(intro_candidates) == 1, "PLATE_INTRODUCTION: ambiguous allocation source")
                        obj_evidence.update(kind="well", introduced_at=next(iter(intro_candidates)),
                                            name=ps["args"]["carrier_position"]["value"],
                                            declaration={k: plain(ps["args"][k]) for k in ("carrier_id", "carrier_position")})
                        self.extra_coverage.add(ps["step_id"])
                    require(rid not in self.runtime_objects, "DUPLICATE_RUNTIME_IDENTITY")
                    self.runtime_objects[rid] = obj_evidence
                    # Allocator expansion has source coverage, not extra descriptors.
                    for s in self.plan_steps:
                        sp=s["span"]
                        if node["span"]["start"] <= sp["start"] < node["span"]["end"] and s["op"] in {"AllocContainer", "DefineContent", "LoadContent", "FinalizeContainerContents"}:
                            self.extra_coverage.add(s["step_id"])
        # Establish non-material identities from completed producer records before
        # resolving references; source traversal order is not runtime event order.
        for fact in self.facts:
            if not fact["bind"]:
                continue
            for i, ps, _ in self.candidates(fact):
                if ps["step_id"] not in self.completed:
                    continue
                ei = self.completed[ps["step_id"]]
                binding = ps["args"][fact.get("binding_slot", "bind")]
                if self.objects[fact["bind"]]["kind"] == "readout":
                    delta = self.data["run"]["events"][ei]["payload"]["observation_delta"]
                    require(delta["binding"] == binding, "READOUT_IDENTITY: binding differs")
                    identity = {k: delta[k] for k in ("data_id", "data_group_id", "item_ids") if k in delta}
                    require(("data_id" in identity) != ("data_group_id" in identity), "READOUT_IDENTITY: missing/ambiguous ID")
                    if "data_group_id" in identity:
                        selected = self.concrete_bindings(ps["args"]["sample"], "/args/sample")
                        if selected is None:
                            sample = ps["args"]["sample"]
                            if sample.get("kind") in {"IRGroup", "IRList"}:
                                selected = sample["elements"]
                        items = identity.get("item_ids", [])
                        require(selected and len(items) == len(selected) and len(set(items)) == len(items),
                                "READOUT_IDENTITY: group item count")
                else:
                    identity = {"producer_step_id": ps["step_id"], "binding": binding}
                obj = deepcopy(self.objects[fact["bind"]])
                rid = "data:" + value_id(identity)[:20]
                obj.update(object_id=rid, source_object_id=fact["bind"], runtime_binding=binding,
                           runtime_identity=identity)
                obj["evidence"].update(plan=self.ev("plan", f"/plans/0/steps/{i}"),
                                      completed_event=self.ev("run", f"/events/{ei}"))
                require(rid not in self.runtime_objects, "DUPLICATE_RUNTIME_IDENTITY")
                self.runtime_objects[rid] = obj
                self.nonmaterial_bindings.setdefault(binding, []).append((ei, rid))
        for fact in self.facts:
            for i, ps, refs in self.candidates(fact):
                self.covered_plan_ids.add(ps["step_id"])
                if ps["step_id"] not in self.completed:
                    continue
                ei = self.completed[ps["step_id"]]
                if fact.get("metadata"):
                    if fact["op"] == "append":
                        receiver = ps["args"]["self"]
                        member = ps["args"]["arg0"]
                        root = receiver
                        while "base" in root:
                            root = root["base"]
                        identities = []
                        for value in (root, member):
                            require(value.get("kind") == "IRIdentifier", "GROUP_EVENT: unresolved member")
                            previous = [(e,r) for e,r in self.nonmaterial_bindings.get(value["name"], []) if e <= ei]
                            require(previous, "GROUP_EVENT: producer missing")
                            identities.append(max(previous)[1])
                        self.group_membership_events.append({"group": identities[0], "member": identities[1],
                            "step": fact["step"], "operation": "append", "event_seq": self.data["run"]["events"][ei]["seq"],
                            "plan": self.ev("plan", f"/plans/0/steps/{i}"),
                            "completed_event": self.ev("run", f"/events/{ei}")})
                    continue  # A declaration/annotation is not experimental use.
                for oid, binding, pointer, ref in refs:
                    if ref is None:
                        continue
                    # The binding spelling can be reused across iterations. Resolve
                    # the ID in the current exported snapshot (or the last snapshot
                    # with no intervening material delta). The operation argument
                    # proves use; the snapshot only supplies identity.
                    snapshot_index, snapshot = self.identity_snapshots.get(ei, (None, {}))
                    identity = snapshot.get("bindings", {}).get(binding)
                    if self.objects[oid]["kind"] not in {"container", "plate_descriptor", "group_descriptor"}:
                        previous = [(e, r) for e, r in self.nonmaterial_bindings.get(binding, []) if e <= ei]
                        require(previous, "REFERENCE_IDENTITY: data producer missing: " + binding)
                        producer_event, rid = max(previous)
                        identity_evidence = self.ev("run", f"/events/{producer_event}")
                    else:
                        require(identity is not None, "REFERENCE_IDENTITY: event binding missing: " + binding)
                        rid = "container:" + value_id(identity)[:20]
                        binding_key = binding.replace("~", "~0").replace("/", "~1")
                        identity_evidence = self.ev("run", f"/events/{snapshot_index}/payload/material_state_snapshot/bindings/{binding_key}")
                    owner = self.collections.get(oid, {}).get("root", oid)
                    owners = {owner} if owner is not None else set(self.collections[oid]["sources"])
                    require(rid in self.runtime_objects and self.runtime_objects[rid]["source_object_id"] in owners,
                            "REFERENCE_IDENTITY: allocation and event differ: " + binding)
                    use = {"source_object": oid, "actual_member": rid, "source_reference": ref["_source"],
                           "parameter_sources": ref.get("_origins", []),
                           "producer_evidence": ref.get("_producer"),
                           "selection_evidence": ref.get("_selection_evidence", []),
                           "parameter_alias_evidence": ref.get("_alias_evidence", []),
                           "identity_evidence": identity_evidence,
                           "call_path": fact["frame"]["path"],
                           "execution": [{"step_id": ps["step_id"],
                                          "plan": self.ev("plan", f"/plans/0/steps/{i}" + pointer),
                                          "completed_event": self.ev("run", f"/events/{ei}")}]}
                    self.runtime_uses.setdefault(rid, {}).setdefault(fact["step"], []).append(use)
        covered = self.covered_plan_ids | self.extra_coverage
        missing = [s for s in self.plan_steps if s["step_id"] not in covered]
        require(not missing, "EXECUTION_COVERAGE: " + str([(s['step_id'],s['op'],s['span']['line']) for s in missing[:5]]))

    def reuse_rows(self, order):
        candidates = []
        for group in self.group_definitions:
            bindings = group.get("bindings")
            if bindings is None:
                bindings = sorted(set().union(*(self.domains[o] for o in group["source_members"])))
            allocations = [self.allocation_bindings.get(b, []) for b in bindings]
            require(allocations and all(allocations) and len({len(a) for a in allocations}) == 1,
                    "GROUP_INSTANCE: incomplete member allocation cohorts")
            for cohort in zip(*allocations):
                # Every identity must coexist in the exported snapshot at the
                # completion of this allocation cohort; no state delta is replayed.
                last = max(e for _, e, _ in cohort)
                si, snapshot = self.identity_snapshots.get(last, (None, {}))
                members = []
                for binding, (_, _, identity) in zip(bindings, cohort):
                    require(snapshot.get("bindings", {}).get(binding) == identity,
                            "GROUP_INSTANCE: members do not share an identity snapshot")
                    members.append("container:" + value_id(identity)[:20])
                candidates.append({k: deepcopy(v) for k,v in group.items() if k != "bindings"} |
                                  {"members": members, "identity_evidence": self.ev(
                                      "run", f"/events/{si}/payload/material_state_snapshot/bindings")})
        entries, self.group_audit = select_groups(self.runtime_objects, self.runtime_uses, candidates, order)
        rows = []
        for entry in entries:
            members = entry["members"]
            obj = self.runtime_objects[members[0]]
            uses = self.runtime_uses.get(members[0], {})
            later = {s: uses[s] for s in sorted(uses,key=order.get) if order[s] > order[obj["introduced_at"]]}
            if later:
                rows.append({"entry_id": members[0] if len(members) == 1 else "group:" + value_id(members)[:20],
                             "members": [self.runtime_objects[m] for m in members],
                             "introduced_at": obj["introduced_at"], "group_bases": entry["bases"],
                             "used_in": list(later), "later_use_links": len(later),
                             "uses": {s: [u for m in members for u in self.runtime_uses[m][s]] for s in later}})
        return rows

    def traceability(self):
        result = super().traceability()
        result["entry"] = {"protocol": self.entry_name, "evidence": self.ev("ast", "/statements")}
        return result

    def derive(self):
        entry = self.data["ast"]["statements"]
        calls = [(i, n) for i,n in enumerate(entry)
                 if n.get("value", n).get("name") in self.procedures
                 and "args" in n.get("value", n)]
        require(len(calls) == 1, "UNSUPPORTED_ENTRY: expected one protocol invocation")
        index, entry_node = calls[0]
        # Setup has no paper step. Only explicit scalar / external-data records
        # are admitted here; experimental setup cannot be silently discarded.
        globals_env = {}
        for i, node in enumerate(entry):
            if i == index:
                continue
            path = f"/statements/{i}"
            if shape(node) == {"name", "value"}:
                self.declaration(node, path, globals_env,
                                 {"key": [], "path": [], "stack": [], "outside_scope": True}, None, False)
            elif shape(node) == {"target", "value"}:
                require(any(n.get("name") in globals_env for _,n in nodes(node["target"])),
                        "UNSUPPORTED_ENTRY_ASSIGNMENT: " + path)
            elif shape(node) != {"bindings", "value"}:
                raise EvidenceError("UNSUPPORTED_ENTRY_SETUP: " + path)
            for ps in self.plan_steps:
                if ps["span"] == node["span"]:
                    require(ps["op"] in {"assign_local", "assign_member", "AllocContainer", "DefineContent",
                                         "LoadContent", "FinalizeContainerContents"}, "UNSUPPORTED_ENTRY_OPERATION")
                    self.extra_coverage.add(ps["step_id"])
        call = entry_node.get("value", entry_node)
        self.entry_name = call["name"]
        pointer = f"/statements/{index}" + ("/value" if "value" in entry_node else "")
        self.call(call, pointer, globals_env, {"path": [], "key": [], "stack": []}, None)
        require(self.main_seen, "STEP_PROTOCOL: not reached by entry")
        self.associate_runtime()
        outputs = self.build_outputs()
        for result in outputs.values():
            result["statistics_scope"] = {"step_protocol": self.step_protocol,
                                          "source": "reachable nested AST constructs", "runtime": "whole invocation"}
        outputs["material_state_continuity.json"]["source_objects"] = list(self.objects.values())
        outputs["material_state_continuity.json"]["grouping_audit"] = self.group_audit
        outputs["material_state_continuity.json"]["actual_objects"] = [
            dict(obj, uses=self.runtime_uses.get(oid, {}))
            for oid, obj in sorted(self.runtime_objects.items())]
        outputs["material_state_continuity.json"]["later_use_order"] = "paper_step_number"
        outputs["material_state_continuity.json"]["group_membership_events"] = sorted(
            self.group_membership_events, key=lambda e:e["event_seq"])
        outputs["action_descriptors.json"]["source_coverage"] = self.source_coverage
        outputs["material_state_continuity.json"]["execution_coverage"] = [
            {"step_id": ps["step_id"], "op": ps["op"],
             "classification": ("parameter_binding" if ps["step_id"] in self.alias_step_ids else
                                "source_fact" if ps["step_id"] in self.covered_plan_ids else "allocation_or_setup"),
             "status": "completed" if ps["step_id"] in self.completed else "skipped",
             "plan": self.ev("plan", f"/plans/0/steps/{i}")}
            for i, ps in enumerate(self.plan_steps)]
        self.validate_outputs(outputs)
        return outputs

    def validate_outputs(self, outputs):
        """Validate emitted records and evidence, without re-running extraction."""
        require(set(outputs) == {"action_descriptors.json", "material_state_continuity.json",
                                 "result_traceability.json"}, "OUTPUT_SCHEMA: three files required")
        require(len({o["extraction_id"] for o in outputs.values()}) == 1, "OUTPUT_IDENTITY")
        descriptors = outputs["action_descriptors.json"]
        expected = self.config["expected_steps"]
        require([r["step"] for r in descriptors["rows"]] == expected, "OUTPUT_STEPS")
        require(descriptors["source_steps"] == len(expected), "OUTPUT_COUNTS: steps")
        total = 0
        for row in descriptors["rows"]:
            entries = row["descriptors"]
            require(row["descriptor_items"] == len(entries), "OUTPUT_COUNTS: descriptors")
            require(len({d["id"] for d in entries}) == len(entries), "OUTPUT_DUPLICATE_DESCRIPTOR")
            require(all(d["evidence"] for d in entries), "OUTPUT_EVIDENCE: descriptor")
            total += len(entries)
        require(total == descriptors["descriptor_items"], "OUTPUT_COUNTS: total")
        continuity = outputs["material_state_continuity.json"]
        actual = {o["object_id"]: o for o in continuity["actual_objects"]}
        require(len(actual) == len(continuity["actual_objects"]), "OUTPUT_DUPLICATE_OBJECT")
        for oid, obj in actual.items():
            require(obj["introduced_at"] in expected, "OUTPUT_INTRODUCTION")
            for step, uses in obj["uses"].items():
                require(step in expected and uses, "OUTPUT_USE_STEP")
                for use in uses:
                    require(use["actual_member"] == oid and use["source_object"] in self.objects,
                            "OUTPUT_USE_IDENTITY")
                    require(use["execution"] and all(e["step_id"] in self.completed for e in use["execution"]),
                            "OUTPUT_USE_COMPLETION")
        seen, count = set(), 0
        for row in continuity["rows"]:
            members = {m["object_id"] for m in row["members"]}
            require(members and not members & seen and members <= actual.keys(), "OUTPUT_GROUP_OVERLAP")
            seen.update(members)
            used = row["used_in"]
            require(used and len(used) == len(set(used)) == row["later_use_links"], "OUTPUT_COUNTS: later uses")
            require(all(s in expected and int(s[1:]) > int(row["introduced_at"][1:]) for s in used),
                    "OUTPUT_LATER_ORDER")
            require(set(used) == set(row["uses"]), "OUTPUT_USE_SET")
            for oid in members:
                actual_later = {s for s in actual[oid]["uses"] if int(s[1:]) > int(actual[oid]["introduced_at"][1:])}
                require(actual_later == set(used), "OUTPUT_GROUP_MEMBER_USES")
            count += len(used)
        require(count == continuity["later_use_links"] and len(continuity["rows"]) == continuity["reused_objects"],
                "OUTPUT_COUNTS: continuity")
        coverage = continuity["execution_coverage"]
        require(len(coverage) == len(self.plan_steps) and {e["step_id"] for e in coverage}
                == {p["step_id"] for p in self.plan_steps}, "OUTPUT_EXECUTION_COVERAGE")
        files = {path: self.data[name] for name,path in self.paths.items()}
        checked = set()
        for payload in outputs.values():
            for _, ev in nodes(payload):
                if "file" not in ev or "json_pointer" not in ev:
                    continue
                key = canonical(ev)
                if key in checked:
                    continue
                checked.add(key)
                require(ev["file"] in files, "OUTPUT_EVIDENCE_FILE")
                value = files[ev["file"]]
                try:
                    for part in ev["json_pointer"].split("/")[1:]:
                        part = part.replace("~1", "/").replace("~0", "~")
                        value = value[int(part)] if isinstance(value, list) else value[part]
                except (KeyError, IndexError, TypeError, ValueError) as error:
                    raise EvidenceError("OUTPUT_EVIDENCE_POINTER: " + ev["json_pointer"]) from error
                if "source_span" in ev:
                    require(isinstance(value, dict) and ev["source_span"] == value.get("span"),
                            "OUTPUT_EVIDENCE_SPAN: " + ev["json_pointer"])
