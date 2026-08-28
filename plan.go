package ags

import "sort"

func EffectiveEdges(document Document) []EffectiveEdge {
	root := graphScope{nodes: obj(document["nodes"]), edges: arr(document["edges"])}
	return effectiveEdges(root)
}

func TopologicalOrder(document Document) ([]string, error) {
	nodes := obj(document["nodes"])
	edges := EffectiveEdges(document)
	incoming := map[string]int{}
	outgoing := map[string][]string{}
	for id := range nodes {
		incoming[id] = 0
	}
	for _, edge := range edges {
		if _, ok := nodes[edge.From]; !ok {
			continue
		}
		if _, ok := nodes[edge.To]; !ok {
			continue
		}
		incoming[edge.To]++
		outgoing[edge.From] = append(outgoing[edge.From], edge.To)
	}
	ready := []string{}
	for id, count := range incoming {
		if count == 0 {
			ready = append(ready, id)
		}
	}
	sort.Strings(ready)
	order := []string{}
	for len(ready) > 0 {
		id := ready[0]
		ready = ready[1:]
		order = append(order, id)
		for _, next := range outgoing[id] {
			incoming[next]--
			if incoming[next] == 0 {
				ready = append(ready, next)
				sort.Strings(ready)
			}
		}
	}
	if len(order) != len(nodes) {
		return nil, &PlanError{"graph contains a cycle"}
	}
	return order, nil
}

type PlanError struct{ Message string }

func (e *PlanError) Error() string { return e.Message }

func PlanGraph(document Document) (Plan, error) {
	order, err := TopologicalOrder(document)
	if err != nil {
		return Plan{}, err
	}
	digest, err := GraphDigest(document)
	if err != nil {
		return Plan{}, err
	}
	nodes := obj(document["nodes"])
	tiers := map[string]int{}
	worst := 0
	for _, raw := range nodes {
		node := obj(raw)
		tier := stringValue(obj(node["intelligence"])["tier"])
		if tier == "" {
			tier = "unspecified"
		}
		tiers[tier]++
		attempts := 1
		if retry := obj(obj(node["failure"])["retry"]); retry["max_attempts"] != nil {
			if n, ok := retry["max_attempts"].(int64); ok {
				attempts = int(n)
			}
		}
		iterations := 1
		typ := stringValue(node["type"])
		if typ == "loop" {
			if n, ok := obj(node["loop"])["max_iterations"].(int64); ok {
				iterations = int(n)
			}
		}
		if typ == "map" {
			if n, ok := obj(node["map"])["max_items"].(int64); ok {
				iterations = int(n)
			}
		}
		worst += attempts * iterations
	}
	reachableMap := map[string]bool{}
	out := map[string][]string{}
	for _, edge := range EffectiveEdges(document) {
		out[edge.From] = append(out[edge.From], edge.To)
	}
	stack := strs(document["entrypoints"])
	for len(stack) > 0 {
		id := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		if reachableMap[id] {
			continue
		}
		reachableMap[id] = true
		stack = append(stack, out[id]...)
	}
	reachable := []string{}
	unreachable := []string{}
	for id := range nodes {
		if reachableMap[id] {
			reachable = append(reachable, id)
		} else {
			unreachable = append(unreachable, id)
		}
	}
	sort.Strings(reachable)
	sort.Strings(unreachable)
	return Plan{GraphID: stringValue(document["id"]), GraphDigest: digest, Order: order, Entrypoints: strs(document["entrypoints"]), EffectiveEdges: EffectiveEdges(document), Reachable: reachable, Unreachable: unreachable, TierHistogram: tiers, WorstCaseNodeExecutions: worst, Executable: false, UnsupportedFeatures: []string{"execution"}}, nil
}
