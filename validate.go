package ags

import (
	"bytes"
	_ "embed"
	"fmt"
	"regexp"
	"sort"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v5"
)

//go:embed schema/agentic-graph-1.0.schema.json
var graphSchema []byte

var (
	versionPattern  = regexp.MustCompile(`^(\d+)\.(\d+)$`)
	templatePattern = regexp.MustCompile(`\$\{\{(.*?)\}\}`)
)

func obj(value any) map[string]any {
	if v, ok := value.(map[string]any); ok {
		return v
	}
	return map[string]any{}
}
func arr(value any) []any {
	if v, ok := value.([]any); ok {
		return v
	}
	return nil
}
func strs(value any) []string {
	var out []string
	for _, v := range arr(value) {
		if s, ok := v.(string); ok {
			out = append(out, s)
		}
	}
	return out
}
func stringValue(value any) string { s, _ := value.(string); return s }

func compileSchema() (*jsonschema.Schema, error) {
	compiler := jsonschema.NewCompiler()
	if err := compiler.AddResource("ags-schema.json", bytes.NewReader(graphSchema)); err != nil {
		return nil, err
	}
	return compiler.Compile("ags-schema.json")
}

func Validate(document Document) Report {
	report := Report{Document: document}
	schema, err := compileSchema()
	if err != nil {
		report.add("AG001", "error", err.Error(), "")
		return report
	}
	if err := schema.Validate(map[string]any(document)); err != nil {
		if validation, ok := err.(*jsonschema.ValidationError); ok {
			addSchemaErrors(&report, validation)
		} else {
			report.add("AG001", "error", err.Error(), "")
		}
	}
	version := stringValue(document["ags_version"])
	match := versionPattern.FindStringSubmatch(version)
	if match == nil {
		report.add("AG002", "error", fmt.Sprintf("unparsable ags_version %q", version), "")
	} else if match[1] != "1" || match[2] != "0" {
		report.add("AG002", "error", fmt.Sprintf("unsupported AGS version %s", version), "")
	}
	if len(report.Errors) == 0 {
		validateSemantics(document, &report)
	}
	report.OK = len(report.Errors) == 0
	return report
}

func addSchemaErrors(report *Report, validation *jsonschema.ValidationError) {
	if len(validation.Causes) > 0 {
		for _, cause := range validation.Causes {
			addSchemaErrors(report, cause)
		}
		return
	}
	code := "AG001"
	location := validation.InstanceLocation
	keyword := validation.KeywordLocation
	if strings.Contains(keyword, "additionalProperties") {
		code = "AG003"
	}
	if strings.Contains(keyword, "enum") {
		code = "AG004"
	}
	if strings.Contains(location, "/edges/") && (strings.Contains(keyword, "not") || strings.Contains(keyword, "allOf")) {
		code = "AG103"
	}
	if strings.Contains(location, "/inputs/") && (strings.Contains(keyword, "oneOf") || strings.Contains(keyword, "maxProperties")) {
		code = "AG104"
	}
	report.add(code, "error", validation.Message, location)
}

type graphScope struct {
	pointer      string
	nodes        map[string]any
	edges        []any
	entrypoints  []string
	paramNames   map[string]bool
	isRoot       bool
	predecessors map[string]map[string]bool
}

func scopes(document Document) []graphScope {
	rootParams := stringSet(obj(document["params"]))
	result := []graphScope{{nodes: obj(document["nodes"]), edges: arr(document["edges"]), entrypoints: strs(document["entrypoints"]), paramNames: rootParams, isRoot: true}}
	var collect func(map[string]any, string, map[string]bool)
	collect = func(nodes map[string]any, base string, inheritedParams map[string]bool) {
		for id, raw := range nodes {
			node := obj(raw)
			typ := stringValue(node["type"])
			if typ == "" {
				typ = "task"
			}
			if typ != "loop" && typ != "map" && typ != "subgraph" {
				continue
			}
			block := obj(node[typ])
			key := "body"
			if typ == "subgraph" {
				key = "inline"
			}
			if fragment, ok := block[key].(map[string]any); ok {
				pointer := fmt.Sprintf("%s/nodes/%s/%s/%s", base, id, typ, key)
				params := stringSet(obj(fragment["params"]))
				if len(params) == 0 {
					params = cloneStringSet(inheritedParams)
				}
				child := graphScope{pointer: pointer, nodes: obj(fragment["nodes"]), edges: arr(fragment["edges"]), entrypoints: strs(fragment["entrypoints"]), paramNames: params}
				result = append(result, child)
				collect(child.nodes, pointer, params)
			}
		}
	}
	collect(result[0].nodes, "", rootParams)
	for name, raw := range obj(document["subgraphs"]) {
		fragment := obj(raw)
		pointer := "/subgraphs/" + name
		params := stringSet(obj(fragment["params"]))
		if len(params) == 0 {
			params = cloneStringSet(rootParams)
		}
		child := graphScope{pointer: pointer, nodes: obj(fragment["nodes"]), edges: arr(fragment["edges"]), entrypoints: strs(fragment["entrypoints"]), paramNames: params}
		result = append(result, child)
		collect(child.nodes, pointer, params)
	}
	return result
}

func effectiveEdges(scope graphScope) []EffectiveEdge {
	var edges []EffectiveEdge
	for id, raw := range scope.nodes {
		for _, dep := range strs(obj(raw)["depends_on"]) {
			edges = append(edges, EffectiveEdge{From: dep, To: id, Kind: "sequence"})
		}
	}
	for _, raw := range scope.edges {
		edge := obj(raw)
		kind := stringValue(edge["kind"])
		if kind == "" {
			kind = "sequence"
		}
		edges = append(edges, EffectiveEdge{From: stringValue(edge["from"]), To: stringValue(edge["to"]), Kind: kind, When: stringValue(edge["when"])})
	}
	seen := map[string]bool{}
	out := edges[:0]
	for _, edge := range edges {
		key := edge.From + "\x00" + edge.To + "\x00" + edge.Kind + "\x00" + edge.When
		if !seen[key] {
			seen[key] = true
			out = append(out, edge)
		}
	}
	return out
}

func validateSemantics(document Document, report *Report) {
	allScopes := scopes(document)
	for i := range allScopes {
		validateScope(&allScopes[i], document, report)
	}
	checkRecursion(document, report)
	hasEstimate := false
	for _, scope := range allScopes {
		for _, raw := range scope.nodes {
			if _, ok := obj(raw)["estimate"]; ok {
				hasEstimate = true
			}
		}
	}
	if _, ok := obj(document["constraints"])["max_cost_usd"]; !ok && !hasEstimate {
		report.add("AG908", "warning", "graph has neither constraints.max_cost_usd nor any node estimate; its cost cannot be previewed", "")
	}
	checkUnreadOutputs(document, allScopes, report)
}

func validateScope(scope *graphScope, document Document, report *Report) {
	edges := effectiveEdges(*scope)
	incoming := map[string]int{}
	outgoing := map[string][]string{}
	direct := map[string][]string{}
	explicitPairs := map[string]bool{}
	for _, raw := range scope.edges {
		edge := obj(raw)
		explicitPairs[textPair(stringValue(edge["from"]), stringValue(edge["to"]))] = true
	}
	for id, raw := range scope.nodes {
		for _, dependency := range strs(obj(raw)["depends_on"]) {
			if _, ok := scope.nodes[dependency]; !ok {
				report.add("AG114", "error", fmt.Sprintf("depends_on references unknown node %q", dependency), scope.pointer+"/nodes/"+id)
			}
			if explicitPairs[textPair(dependency, id)] {
				report.add("AG901", "warning", fmt.Sprintf("%s -> %s declared by both depends_on and an explicit edge", dependency, id), scope.pointer+"/nodes/"+id)
			}
		}
	}
	for id := range scope.nodes {
		incoming[id] = 0
	}
	for _, edge := range edges {
		if _, ok := scope.nodes[edge.From]; !ok {
			report.add("AG113", "error", fmt.Sprintf("edge references unknown node %q", edge.From), scope.pointer)
			continue
		}
		if _, ok := scope.nodes[edge.To]; !ok {
			report.add("AG113", "error", fmt.Sprintf("edge references unknown node %q", edge.To), scope.pointer)
			continue
		}
		incoming[edge.To]++
		outgoing[edge.From] = append(outgoing[edge.From], edge.To)
		direct[edge.To] = append(direct[edge.To], edge.From)
	}
	if cycle := findCycle(scope.nodes, outgoing); len(cycle) > 0 {
		report.add("AG111", "error", "cycle in effective edge set: "+strings.Join(cycle, " -> "), scope.pointer)
	}
	scope.predecessors = transitive(scope.nodes, direct)
	for _, entry := range scope.entrypoints {
		if _, ok := scope.nodes[entry]; !ok {
			code := "AG133"
			if scope.isRoot {
				code = "AG115"
			}
			report.add(code, "error", fmt.Sprintf("entrypoint %q is not a node in this scope", entry), scope.pointer)
		} else if incoming[entry] > 0 {
			report.add("AG112", "error", fmt.Sprintf("entrypoint %q has incoming edges", entry), scope.pointer)
		}
	}
	reachable := map[string]bool{}
	stack := append([]string{}, scope.entrypoints...)
	for len(stack) > 0 {
		id := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		if reachable[id] {
			continue
		}
		reachable[id] = true
		stack = append(stack, outgoing[id]...)
	}
	ids := make([]string, 0, len(scope.nodes))
	for id := range scope.nodes {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		if !reachable[id] {
			report.add("AG903", "warning", fmt.Sprintf("node %q is unreachable from any entrypoint", id), scope.pointer+"/nodes/"+id)
		}
		validateNode(scope, id, obj(scope.nodes[id]), document, report, incoming[id])
	}
}

func validateNode(scope *graphScope, id string, node map[string]any, document Document, report *Report, incoming int) {
	pointer := scope.pointer + "/nodes/" + id
	typ := stringValue(node["type"])
	if typ == "" {
		typ = "task"
	}
	if id == "self" {
		report.add("AG117", "error", "'self' is a reserved namespace root and cannot be a node id", pointer)
	}
	for _, other := range []string{"loop", "map", "subgraph", "gate", "decision"} {
		if _, exists := node[other]; exists && other != typ {
			report.add("AG101", "error", fmt.Sprintf("node of type %q declares a %q block", typ, other), pointer)
		}
	}
	if typ == "gate" {
		if _, exists := node["intelligence"]; exists {
			report.add("AG102", "error", "gate nodes must not declare intelligence", pointer)
		}
	}
	outputs := obj(node["outputs"])
	if (typ == "decision" || typ == "gate") && outputs["decision"] != nil {
		report.add("AG122", "error", "'decision' is a reserved output name on decision and gate nodes", pointer)
	}
	if stringValue(node["join"]) == "n_of" {
		if count, ok := node["join_count"].(int64); ok && int(count) > incoming {
			report.add("AG116", "error", fmt.Sprintf("join_count %d exceeds %d incoming edges", count, incoming), pointer)
		}
	}
	intel := obj(node["intelligence"])
	tiers := map[string]int{"minimal": 1, "standard": 2, "advanced": 3, "frontier": 4}
	tier := stringValue(intel["tier"])
	if level, ok := intel["level"].(int64); ok && tier != "" && tiers[tier] != int(level) {
		report.add("AG141", "error", "intelligence tier and level disagree", pointer)
	}
	if to := stringValue(intel["escalate_to"]); tier != "" && to != "" && tiers[to] < tiers[tier] {
		report.add("AG142", "error", "escalate_to is below the configured tier", pointer)
	}
	if tier == "frontier" && stringValue(intel["rationale"]) == "" {
		report.add("AG905", "warning", "frontier-tier node has no rationale", pointer)
	}
	if typ == "loop" || typ == "map" || typ == "subgraph" {
		block := obj(node[typ])
		if use := stringValue(block["use"]); use != "" {
			if _, ok := obj(document["subgraphs"])[use]; !ok {
				report.add("AG132", "error", fmt.Sprintf("%s.use names unknown fragment %q", typ, use), pointer)
			}
		}
		ref := obj(block["ref"])
		uri := stringValue(ref["uri"])
		if uri != "" && !strings.HasPrefix(uri, ".") && !strings.HasPrefix(uri, "/") {
			if _, ok := ref["integrity"]; !ok {
				report.add("AG909", "warning", "non-local subgraph reference has no integrity digest", pointer)
			}
		}
	}
	if typ == "decision" {
		decision := obj(node["decision"])
		branches := arr(decision["branches"])
		labels := map[string]int{}
		for i, raw := range branches {
			branch := obj(raw)
			label := stringValue(branch["label"])
			labels[label]++
			if stringValue(decision["evaluator"]) == "expression" {
				if _, exists := branch["when"]; !exists {
					report.add("AG121", "error", fmt.Sprintf("branch %q has no 'when' but evaluator is 'expression'", label), fmt.Sprintf("%s/decision/branches/%d", pointer, i))
				}
			}
		}
		duplicates := []string{}
		for label, count := range labels {
			if count > 1 {
				duplicates = append(duplicates, label)
			}
		}
		if len(duplicates) > 0 {
			sort.Strings(duplicates)
			report.add("AG124", "error", fmt.Sprintf("duplicate branch labels %v", duplicates), pointer)
		}
		if fallback := stringValue(decision["default_branch"]); fallback != "" && labels[fallback] == 0 {
			report.add("AG123", "error", fmt.Sprintf("default_branch %q is not a declared label", fallback), pointer)
		}
	}
	failure := obj(node["failure"])
	for index, raw := range arr(failure["fallback"]) {
		step := obj(raw)
		location := fmt.Sprintf("%s/failure/fallback/%d", pointer, index)
		strategy := stringValue(step["strategy"])
		if strategy == "alternate_node" {
			alternate := stringValue(step["node"])
			target, exists := scope.nodes[alternate]
			if !exists {
				report.add("AG113", "error", fmt.Sprintf("fallback node %q does not exist", alternate), location)
			} else {
				missing := []string{}
				available := declaredOutputs(obj(target))
				for name, spec := range outputs {
					required := true
					if value, ok := obj(spec)["required"].(bool); ok {
						required = value
					}
					if required && !available[name] {
						missing = append(missing, name)
					}
				}
				if len(missing) > 0 {
					sort.Strings(missing)
					report.add("AG151", "error", fmt.Sprintf("fallback node %q does not declare required outputs %v", alternate, missing), location)
				}
			}
		} else if strategy == "relax_criteria" {
			declared := map[string]bool{}
			for _, criterion := range arr(obj(node["success"])["criteria"]) {
				declared[stringValue(obj(criterion)["id"])] = true
			}
			unknown := []string{}
			for _, name := range strs(step["criteria"]) {
				if !declared[name] {
					unknown = append(unknown, name)
				}
			}
			if len(unknown) > 0 {
				report.add("AG153", "error", fmt.Sprintf("unknown criteria %v", unknown), location)
			}
		} else if strategy == "degrade_outputs" {
			unknown := []string{}
			for _, name := range strs(step["outputs"]) {
				if outputs[name] == nil {
					unknown = append(unknown, name)
				}
			}
			if len(unknown) > 0 {
				report.add("AG153", "error", fmt.Sprintf("unknown outputs %v", unknown), location)
			}
		}
	}
	if compensation := stringValue(failure["compensation"]); compensation != "" {
		target, exists := scope.nodes[compensation]
		if !exists {
			report.add("AG113", "error", fmt.Sprintf("compensation node %q does not exist", compensation), pointer)
		} else if obj(obj(target)["failure"])["compensation"] != nil {
			report.add("AG152", "error", fmt.Sprintf("compensation node %q declares its own compensation", compensation), pointer)
		}
	}
	escalation := obj(failure["escalation"])
	if stringValue(escalation["to"]) == "node" {
		target := stringValue(escalation["node"])
		if scope.nodes[target] == nil {
			report.add("AG113", "error", fmt.Sprintf("escalation node %q does not exist", target), pointer)
		}
	}
	requirements := obj(node["requirements"])
	mutating := stringValue(requirements["workspace"]) == "read_write"
	for _, permission := range strs(requirements["permissions"]) {
		for _, prefix := range []string{"fs:write", "fs:delete", "git:commit", "git:push", "shell:exec"} {
			mutating = mutating || strings.HasPrefix(permission, prefix)
		}
	}
	if mutating && node["success"] == nil && typ == "task" {
		report.add("AG902", "warning", "side-effecting node declares no success block", pointer)
	}
	if success := obj(node["success"]); len(success) > 0 {
		kinds := []string{}
		for _, raw := range arr(success["criteria"]) {
			criterion := obj(raw)
			if severity := stringValue(criterion["severity"]); severity == "" || severity == "required" {
				kinds = append(kinds, stringValue(criterion["kind"]))
			}
		}
		if len(kinds) > 0 {
			onlyJudged := true
			for _, kind := range kinds {
				if kind != "llm_judge" && kind != "human" {
					onlyJudged = false
				}
			}
			if onlyJudged {
				report.add("AG906", "warning", "success block has no deterministic required criterion", pointer)
			}
		}
	}
	constraints := obj(node["constraints"])
	if stringValue(constraints["determinism"]) == "strict" && constraints["seed"] == nil {
		report.add("AG907", "warning", "determinism 'strict' without a seed", pointer)
	}
	walkExpressions(node, pointer, scope, id, report)
}

func walkExpressions(value any, pointer string, scope *graphScope, nodeID string, report *Report) {
	var walk func(any, string, string)
	walk = func(raw any, path, key string) {
		switch v := raw.(type) {
		case map[string]any:
			for k, child := range v {
				if k == "body" || k == "inline" {
					continue
				}
				walk(child, path+"/"+k, k)
			}
		case []any:
			for i, child := range v {
				walk(child, fmt.Sprintf("%s/%d", path, i), key)
			}
		case string:
			isExpression := key == "from" || key == "when" || key == "expr" || key == "target" || key == "condition" || key == "over"
			texts := []string{}
			if isExpression {
				texts = []string{v}
			} else {
				for _, match := range templatePattern.FindAllStringSubmatch(v, -1) {
					texts = append(texts, match[1])
				}
			}
			for _, text := range texts {
				validateExpression(text, path, scope, nodeID, report)
			}
		}
	}
	walk(value, pointer, "")
}

func validateExpression(text, pointer string, scope *graphScope, nodeID string, report *Report) {
	trimmed := strings.TrimSpace(text)
	if templatePattern.MatchString(text) {
		report.add("AG211", "error", "'${{ }}' interpolation used in expression position", pointer)
		return
	}
	if trimmed == "" {
		return
	}
	parsed, err := ParseExpression(text)
	if err != nil {
		report.add("AG204", "error", "invalid expression: "+err.Error(), pointer)
		return
	}
	for _, call := range parsed.Calls {
		expected, exists := AGXFunctions[call.Name]
		if !exists {
			report.add("AG204", "error", fmt.Sprintf("unknown function %q", call.Name), pointer)
		} else if call.Arity < expected.Min || call.Arity > expected.Max {
			report.add("AG204", "error", fmt.Sprintf("function %s received %d argument(s)", call.Name, call.Arity), pointer)
		}
	}
	for _, parts := range parsed.References {
		if parts[0] == "secrets" {
			report.add("AG205", "error", "expressions must not reference secrets.*", pointer)
			continue
		}
		if parts[0] == "params" {
			if len(parts) >= 2 && !scope.paramNames[parts[1]] {
				report.add("AG203", "error", fmt.Sprintf("undeclared param %q", parts[1]), pointer)
			}
			continue
		}
		if parts[0] == "nodes" && len(parts) >= 2 {
			target := parts[1]
			if _, ok := scope.nodes[target]; !ok {
				childBound := strings.Contains(pointer, "/loop/condition") || strings.Contains(pointer, "/loop/collect/") || strings.Contains(pointer, "/map/collect/")
				if !childBound {
					code := "AG203"
					if !scope.isRoot {
						code = "AG202"
					}
					report.add(code, "error", fmt.Sprintf("unknown node %q", target), pointer)
				}
			} else if len(parts) >= 4 && parts[2] == "outputs" && !declaredOutputs(obj(scope.nodes[target]))[parts[3]] {
				report.add("AG206", "error", fmt.Sprintf("node %q does not declare output %q", target, parts[3]), pointer)
			} else if target != nodeID && !scope.predecessors[nodeID][target] {
				report.add("AG201", "error", fmt.Sprintf("node %q reads output of non-predecessor %q", nodeID, target), pointer)
			}
		}
	}
}

func stringSet(values map[string]any) map[string]bool {
	result := map[string]bool{}
	for key := range values {
		result[key] = true
	}
	return result
}

func cloneStringSet(values map[string]bool) map[string]bool {
	result := map[string]bool{}
	for key := range values {
		result[key] = true
	}
	return result
}

func textPair(left, right string) string { return left + "\x00" + right }
func declaredOutputs(node map[string]any) map[string]bool {
	out := map[string]bool{}
	for name := range obj(node["outputs"]) {
		out[name] = true
	}
	typ := stringValue(node["type"])
	if typ == "" {
		typ = "task"
	}
	if typ == "decision" || typ == "gate" {
		out["decision"] = true
	}
	block := obj(node[typ])
	if typ == "gate" || typ == "loop" || typ == "map" {
		for name := range obj(block["collect"]) {
			out[name] = true
		}
	}
	if typ == "subgraph" {
		for name := range obj(block["outputs_from"]) {
			out[name] = true
		}
	}
	return out
}
func checkUnreadOutputs(document Document, scopes []graphScope, report *Report) {
	reads := map[string]bool{}
	walkAllStrings(document, func(value string) {
		for _, match := range regexp.MustCompile(`nodes\.([A-Za-z_][\w-]*)\.outputs\.([A-Za-z_][\w-]*)`).FindAllStringSubmatch(value, -1) {
			reads[textPair(match[1], match[2])] = true
		}
	})
	for _, scope := range scopes {
		for id, raw := range scope.nodes {
			node := obj(raw)
			walkAllStrings(node, func(value string) {
				for _, match := range regexp.MustCompile(`(?:self|nodes\.self)\.outputs\.([A-Za-z_][\w-]*)`).FindAllStringSubmatch(value, -1) {
					reads[textPair(id, match[1])] = true
				}
			})
			for name := range obj(node["outputs"]) {
				if !reads[textPair(id, name)] {
					report.add("AG904", "warning", fmt.Sprintf("output %q of node %q is never read", name, id), scope.pointer+"/nodes/"+id+"/outputs/"+name)
				}
			}
		}
	}
}
func walkAllStrings(value any, visit func(string)) {
	switch current := value.(type) {
	case string:
		visit(current)
	case []any:
		for _, child := range current {
			walkAllStrings(child, visit)
		}
	case map[string]any:
		for _, child := range current {
			walkAllStrings(child, visit)
		}
	case Document:
		for _, child := range current {
			walkAllStrings(child, visit)
		}
	}
}

func findCycle(nodes map[string]any, outgoing map[string][]string) []string {
	state := map[string]int{}
	path := []string{}
	var visit func(string) []string
	visit = func(id string) []string {
		state[id] = 1
		path = append(path, id)
		for _, next := range outgoing[id] {
			if state[next] == 1 {
				return append(append([]string{}, path[indexOf(path, next):]...), next)
			}
			if state[next] == 0 {
				if found := visit(next); len(found) > 0 {
					return found
				}
			}
		}
		path = path[:len(path)-1]
		state[id] = 2
		return nil
	}
	ids := make([]string, 0, len(nodes))
	for id := range nodes {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		if state[id] == 0 {
			if found := visit(id); len(found) > 0 {
				return found
			}
		}
	}
	return nil
}
func indexOf(values []string, target string) int {
	for i, v := range values {
		if v == target {
			return i
		}
	}
	return 0
}
func transitive(nodes map[string]any, direct map[string][]string) map[string]map[string]bool {
	out := map[string]map[string]bool{}
	var visit func(string, map[string]bool) map[string]bool
	visit = func(id string, active map[string]bool) map[string]bool {
		if cached := out[id]; cached != nil {
			return cached
		}
		result := map[string]bool{}
		if active[id] {
			return result
		}
		next := map[string]bool{}
		for k, v := range active {
			next[k] = v
		}
		next[id] = true
		for _, p := range direct[id] {
			result[p] = true
			for ancestor := range visit(p, next) {
				result[ancestor] = true
			}
		}
		out[id] = result
		return result
	}
	for id := range nodes {
		visit(id, map[string]bool{})
	}
	return out
}

func checkRecursion(document Document, report *Report) {
	fragments := obj(document["subgraphs"])
	deps := map[string][]string{}
	for name, raw := range fragments {
		for _, nodeRaw := range obj(obj(raw)["nodes"]) {
			node := obj(nodeRaw)
			for _, typ := range []string{"loop", "map", "subgraph"} {
				if use := stringValue(obj(node[typ])["use"]); use != "" {
					deps[name] = append(deps[name], use)
				}
			}
		}
	}
	active := []string{}
	done := map[string]bool{}
	var visit func(string)
	visit = func(name string) {
		if at := indexOfOrMinus(active, name); at >= 0 {
			report.add("AG131", "error", "recursive subgraph reference: "+strings.Join(append(active[at:], name), " -> "), "/subgraphs/"+name)
			return
		}
		if done[name] {
			return
		}
		active = append(active, name)
		for _, next := range deps[name] {
			visit(next)
		}
		active = active[:len(active)-1]
		done[name] = true
	}
	for name := range fragments {
		visit(name)
	}
}
func indexOfOrMinus(values []string, target string) int {
	for i, v := range values {
		if v == target {
			return i
		}
	}
	return -1
}
